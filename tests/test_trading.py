import copy
from decimal import Decimal
import unittest
from india_trader.core import DataError, ROOT, read, config, digest, number, integer, fees, calendar_status, quote
from india_trader import trading

NOW = "2026-10-26T10:00:00+05:30"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.cfg = config()
        self.prices = read(ROOT / "examples/workspace/prices.json")
        self.master = read(ROOT / "examples/workspace/instruments.json")
        self.portfolio = read(ROOT / "examples/workspace/account.json")["portfolio"]
        self.events = {"events": []}
        self.o = trading.order("NSE:INFY", 10, 1500)

    def risk(self, orders=None, now=NOW):
        return trading.risk_check(trading.proposal(orders or [self.o], now), self.cfg, self.portfolio, self.prices, self.master, self.events, now)


class Numbers(unittest.TestCase):
    def test_reject_nonfinite_and_bool(self):
        for x in [True, False, "NaN", "Infinity", "-Infinity", None]:
            with self.subTest(x=x), self.assertRaises(DataError):
                number(x)

    def test_reject_fractional_quantity(self):
        with self.assertRaises(DataError):
            integer("1.5")

    def test_indian_commas(self):
        self.assertEqual(number("1,00,000"), Decimal(100000))

    def test_bad_config(self):
        for cfg in [{"paper": False}, {"currency": "USD"}, {"max_order_inr": "NaN"}, {"max_position_pct": 101}, {"intraday_entry_cutoff": "25:00"}]:
            with self.subTest(cfg=cfg), self.assertRaises(DataError):
                config(cfg)


class Calendar(unittest.TestCase):
    def test_holiday(self):
        self.assertEqual(calendar_status("2026-10-20T10:00:00+05:30", cas_eligible=True)["phase"], "CLOSED")

    def test_weekend(self):
        self.assertFalse(calendar_status("2026-10-25T10:00:00+05:30", cas_eligible=True)["continuous"])

    def test_special_is_unknown(self):
        self.assertEqual(calendar_status("2026-11-08T18:00:00+05:30", cas_eligible=True)["phase"], "UNKNOWN")

    def test_cas_boundary(self):
        self.assertTrue(calendar_status("2026-10-26T15:14:59+05:30", cas_eligible=True)["continuous"])
        self.assertEqual(calendar_status("2026-10-26T15:15:00+05:30", cas_eligible=True)["phase"], "CLOSING_AUCTION")
        self.assertTrue(calendar_status("2026-10-26T15:15:00+05:30", cas_eligible=False)["continuous"])
        self.assertFalse(calendar_status("2026-10-26T15:30:00+05:30", cas_eligible=False)["continuous"])

    def test_timezone_conversion(self):
        self.assertTrue(calendar_status("2026-10-26T04:30:00Z", cas_eligible=True)["continuous"])

    def test_unknown_calendar(self):
        for day in ["2027-01-04", "2026-12-07"]:
            self.assertEqual(calendar_status(day + "T10:00:00+05:30", cas_eligible=True)["phase"], "UNKNOWN")

    def test_no_cas_or_bse_assumption(self):
        self.assertEqual(calendar_status(NOW)["phase"], "UNKNOWN")
        self.assertEqual(calendar_status(NOW, exchange="BSE", cas_eligible=True)["phase"], "UNKNOWN")


class Charges(unittest.TestCase):
    def test_intraday_sides(self):
        buy, sell = fees(100000, "BUY", "MIS"), fees(100000, "SELL", "MIS")
        self.assertEqual(buy["brokerage"], 20)
        self.assertEqual(buy["stamp"], 3)
        self.assertEqual(buy["stt"], 0)
        self.assertEqual(sell["stt"], 25)
        self.assertEqual(sell["stamp"], 0)
        self.assertEqual(sell["dp"], 0)

    def test_delivery(self):
        f = fees(100000, "BUY", "CNC")
        self.assertEqual(f["stt"], 100)
        self.assertEqual(f["stamp"], 15)
        self.assertEqual(f["brokerage"], 0)
        self.assertEqual(fees(10000, "SELL", "CNC")["dp"], 15.34)


class Plans(Fixture):
    def test_budget_cash_and_whole_shares(self):
        target = read(ROOT / "examples/workspace/targets.json")
        plan = trading.budget_plan(target, self.prices, self.cfg, NOW)
        self.assertGreaterEqual(plan["estimated_cash_after"], 10000)
        self.assertTrue(all(isinstance(o["quantity"], int) for o in plan["orders"]))
        self.assertEqual(self.risk(plan["orders"])["blocked"], 0)

    def test_waterfill(self):
        alloc = trading.allocation({"A": Decimal(99), "B": Decimal(1)}, Decimal(100000), Decimal(10), Decimal(25))
        self.assertEqual(alloc, {"A": 25000, "B": 25000})

    def test_intraday_includes_fees(self):
        plan = trading.intraday_plan("NSE:INFY", 1500, 1480, self.cfg, NOW)
        self.assertLessEqual(plan["planned_loss_inr"], 500)
        self.assertEqual(self.risk(plan["orders"])["blocked"], 0)

    def test_invalid_stop(self):
        with self.assertRaises(DataError):
            trading.intraday_plan("NSE:INFY", 1500, 1510, self.cfg)

    def test_no_fractional_expensive_shares(self):
        self.cfg["budget_inr"] = 1000
        with self.assertRaises(DataError):
            trading.intraday_plan("NSE:INFY", 1500, 1480, self.cfg)


class Risk(Fixture):
    def test_valid(self):
        self.assertEqual(self.risk()["passed"], 1)

    def test_stale_quote(self):
        self.assertEqual(self.risk(now="2026-10-26T10:02:00+05:30")["blocked"], 1)

    def test_future_quote(self):
        self.prices["quotes"]["NSE:INFY"]["as_of"] = "2026-10-26T10:01:00+05:30"
        self.assertEqual(self.risk()["blocked"], 1)

    def test_currency_mismatch(self):
        self.prices["quotes"]["NSE:INFY"]["currency"] = "USD"
        self.assertEqual(self.risk()["blocked"], 1)

    def test_fractional_order(self):
        self.o["quantity"] = 1.5
        self.assertEqual(self.risk()["blocked"], 1)

    def test_unknown_fields(self):
        self.o["notional"] = 15000
        self.assertEqual(self.risk()["blocked"], 1)

    def test_unverified_master(self):
        self.master["as_of"] = "2026-10-25"
        self.assertEqual(self.risk()["blocked"], 1)

    def test_surveillance_and_tick(self):
        for field, value in [("surveillance", "ASM"), ("series", "BE"), ("active", False), ("lot_size", 100), ("broker_symbol", "TCS")]:
            saved = copy.deepcopy(self.master)
            self.master["instruments"]["NSE:INFY"][field] = value
            self.assertEqual(self.risk()["blocked"], 1)
            self.master = saved
        self.o["price"] = 1500.05
        self.assertEqual(self.risk()["blocked"], 1)

    def test_circuit_and_deviation(self):
        self.o["price"] = 1700
        result = self.risk()
        self.assertTrue(any("circuit" in r for r in result["results"][0]["reasons"]))

    def test_no_short(self):
        self.o["side"] = "SELL"
        self.assertEqual(self.risk()["blocked"], 1)

    def test_proposed_buy_does_not_create_sellable_holding(self):
        sell = dict(self.o, side="SELL")
        self.assertEqual(self.risk([self.o, sell])["blocked"], 1)

    def test_duplicate_batch(self):
        self.assertEqual(self.risk([self.o, self.o])["blocked"], 1)

    def test_daily_loss_halts_buys(self):
        self.portfolio["daily_pnl_inr"] = -2000
        self.assertEqual(self.risk()["blocked"], 1)

    def test_unrealized_loss_halts_even_if_reported_pnl_zero(self):
        self.portfolio["cash_inr"] = 80000
        self.portfolio["positions"] = [{"symbol": "NSE:TCS", "product": "CNC", "quantity": 5}]
        result = self.risk()
        self.assertTrue(any("Daily loss" in r for r in result["results"][0]["reasons"]))

    def test_loss_halt_allows_exit(self):
        self.portfolio["daily_pnl_inr"] = -2000
        self.portfolio["positions"] = [{"symbol": "NSE:INFY", "product": "CNC", "quantity": 10}]
        self.o["side"] = "SELL"
        self.assertEqual(self.risk()["passed"], 1)

    def test_existing_holding_counted(self):
        self.portfolio["cash_inr"] = 85000
        self.portfolio["positions"] = [{"symbol": "NSE:INFY", "product": "CNC", "quantity": 10}]
        self.assertEqual(self.risk()["blocked"], 1)

    def test_cumulative_cash(self):
        self.cfg["max_position_pct"] = 100
        self.cfg["max_order_inr"] = 90000
        a = trading.order("NSE:INFY", 40, 1500)
        b = trading.order("NSE:TCS", 15, 3000)
        self.assertEqual(self.risk([a, b])["blocked"], 1)

    def test_intraday_missing_stop(self):
        self.o["product"] = "MIS"
        self.assertEqual(self.risk()["blocked"], 1)

    def test_intraday_cutoff(self):
        self.o.update(product="MIS", stop_loss=1480)
        self.prices["quotes"]["NSE:INFY"]["as_of"] = "2026-10-26T14:45:00+05:30"
        self.assertEqual(self.risk(now="2026-10-26T14:45:00+05:30")["blocked"], 1)

    def test_position_without_quote_fails(self):
        self.portfolio["positions"] = [{"symbol": "NSE:ITC", "quantity": 1, "product": "CNC"}]
        with self.assertRaises(DataError):
            self.risk()


class Broker(Fixture):
    def test_exact_ack(self):
        report = self.risk()
        for reply in ["yes", "yes all", "YES wrong", "maybe"]:
            with self.assertRaises(DataError):
                trading.approve(self.o, report, reply, NOW)

    def test_order_mutation_invalidates(self):
        report = self.risk()
        old = digest(self.o)
        self.o["quantity"] += 1
        with self.assertRaises(DataError):
            trading.approve(self.o, report, "YES " + old, NOW)

    def test_expired_report(self):
        with self.assertRaises(DataError):
            trading.approve(self.o, self.risk(), "YES " + digest(self.o), "2026-10-26T10:03:00+05:30")

    def test_paper_fill_once(self):
        report = self.risk()
        ack = trading.approve(self.o, report, "YES " + digest(self.o), NOW)
        portfolio, events = trading.paper_fill(self.o, ack, report, self.portfolio, self.events, 1500, NOW)
        self.assertLess(portfolio["cash_inr"], 85000)
        self.assertEqual(portfolio["positions"][0]["quantity"], 10)
        with self.assertRaises(DataError):
            trading.paper_fill(self.o, ack, report, portfolio, events, 1500, NOW)

    def test_context_mutation_invalidates_fill(self):
        report = self.risk()
        ack = trading.approve(self.o, report, "YES " + digest(self.o), NOW)
        self.cfg["cash_buffer_pct"] = 20
        with self.assertRaises(DataError):
            trading.paper_fill(self.o, ack, self.risk(), self.portfolio, self.events, 1500, NOW)

    def test_limit_violation(self):
        report = self.risk()
        ack = trading.approve(self.o, report, "YES " + digest(self.o), NOW)
        with self.assertRaises(DataError):
            trading.paper_fill(self.o, ack, report, self.portfolio, self.events, 1501, NOW)

    def test_payload_whole_shares(self):
        result = trading.ticket(self.o, self.master)
        self.assertEqual(result["quantity"], 10)
        self.assertEqual(result["tradingsymbol"], "INFY")
        self.assertNotIn("stop_loss", result)

    def test_paper_roundtrip_pnl_matches_cash_change(self):
        self.o.update(product="MIS", stop_loss=1480)
        report = self.risk()
        ack = trading.approve(self.o, report, "YES " + digest(self.o), NOW)
        self.portfolio, self.events = trading.paper_fill(self.o, ack, report, self.portfolio, self.events, 1500, NOW, prices=self.prices)
        self.prices["quotes"]["NSE:INFY"]["price"] = 1510
        self.o = trading.order("NSE:INFY", 10, 1510, "SELL", "MIS")
        report = self.risk()
        ack = trading.approve(self.o, report, "YES " + digest(self.o), NOW)
        result, events = trading.paper_fill(self.o, ack, report, self.portfolio, self.events, 1510, NOW, prices=self.prices)
        self.assertEqual(result["positions"], [])
        self.assertAlmostEqual(result["daily_pnl_inr"], result["cash_inr"] - 100000, places=2)
        self.assertAlmostEqual(events["events"][-1]["realized_pnl_inr"], result["daily_pnl_inr"], places=2)


if __name__ == "__main__":
    unittest.main()
