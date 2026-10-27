import copy
import unittest
from india_trader.core import DataError, ROOT, read, rows
from india_trader import research, sources, tax, alerts
NOW = "2026-10-26T10:00:00+05:30"


class Research(unittest.TestCase):
    def test_copy_values(self):
        result = research.copy_portfolio(rows(ROOT / "examples/holdings.json"), 2)
        self.assertAlmostEqual(sum(r["weight"] for r in result["weights"]), 100)
        self.assertEqual(len(result["weights"]), 2)

    def test_ownership_is_not_portfolio_weight(self):
        with self.assertRaises(DataError):
            research.copy_portfolio([{"symbol": "NSE:INFY", "ownership_pct": 3, "as_of": "2026-09-30", "source_url": "source"}])

    def test_mixed_dates(self):
        rs = rows(ROOT / "examples/holdings.json")
        rs[0]["as_of"] = "2026-06-30"
        with self.assertRaises(DataError):
            research.copy_portfolio(rs)

    def test_quantity_diff(self):
        result = research.holdings_diff(rows(ROOT / "examples/holdings-previous.json"), rows(ROOT / "examples/holdings.json"))
        changes = {r["symbol"]: r["change"] for r in result["rows"]}
        self.assertEqual(changes["NSE:INFY"], "ADDED")
        self.assertEqual(changes["NSE:ITC"], "EXITED")

    def test_units_and_yoy(self):
        result = research.analyze(rows(ROOT / "examples/results.json"))["companies"][0]
        self.assertEqual(result["revenue_inr"], 110000000000)
        self.assertEqual(result["eps_ttm"], 75.5)
        self.assertAlmostEqual(result["revenue_growth_yoy_pct"], 22.22222222)

    def test_missing_quarter_no_ttm(self):
        rs = rows(ROOT / "examples/results.json")
        del rs[1]
        self.assertIsNone(research.analyze(rs)["companies"][0]["eps_ttm"])

    def test_ytd_rejected(self):
        rs = rows(ROOT / "examples/results.json")
        rs[0]["period_type"] = "YTD"
        with self.assertRaises(DataError):
            research.analyze(rs)

    def test_reporting_basis_separate(self):
        rs = rows(ROOT / "examples/results.json")
        rs.append(dict(rs[0], basis="standalone"))
        self.assertEqual(len(research.analyze(rs)["companies"]), 2)

    def test_screen_missing_metric_fails(self):
        result = research.screen([{"symbol": "NSE:INFY", "growth": None}], {"rules": [{"metric": "growth", "op": ">", "value": 0}]})
        self.assertEqual(len(result["excluded"]), 1)

    def test_screen_rank(self):
        rs = [{"symbol": "NSE:INFY", "growth": 20}, {"symbol": "NSE:TCS", "growth": 10}]
        spec = {"rules": [], "rank": [{"metric": "growth", "order": "desc"}]}
        self.assertEqual(research.screen(rs, spec)["passed"][0]["symbol"], "NSE:INFY")

    def test_disclosures_dedup(self):
        doc = research.disclosures(rows(ROOT / "examples/disclosures.json"))
        first, state = sources.new_items(doc, {}, NOW)
        second, _ = sources.new_items(doc, state, NOW)
        self.assertEqual(len(first["rows"]), 1)
        self.assertEqual(second["rows"], [])


class Providers(unittest.TestCase):
    def test_yahoo_currency_and_time(self):
        doc = {"chart": {"result": [{"meta": {"symbol": "INFY.NS", "currency": "INR", "regularMarketPrice": 1500, "regularMarketTime": 1792981800}}]}}
        q = sources.parse_yahoo(doc, "NSE:INFY")
        self.assertEqual(q["price"], 1500)
        self.assertIn("+05:30", q["as_of"])
        doc["chart"]["result"][0]["meta"]["currency"] = "USD"
        with self.assertRaises(DataError):
            sources.parse_yahoo(doc, "NSE:INFY")

    def test_bse_not_blindly_mapped(self):
        with self.assertRaises(DataError):
            sources.yahoo_code("BSE:500209")

    def test_empty_provider_response(self):
        with self.assertRaises(DataError):
            sources.parse_yahoo({"chart": {"result": None}}, "NSE:INFY")

    def test_rss_date(self):
        data = b'<rss><channel><item><title>Test</title><link>https://example.invalid</link><pubDate>Mon, 26 Oct 2026 04:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(sources.parse_rss(data, "NSE:INFY")[0]["published_at"], "2026-10-26T09:30:00+05:30")

    def test_rss_entities_rejected(self):
        with self.assertRaises(DataError):
            sources.parse_rss(b'<!DOCTYPE a><rss/>', "NSE:INFY")

    def test_feed_dedupe_and_time_filter(self):
        doc = read(ROOT / "examples/news.json")
        doc["rows"].append(dict(doc["rows"][0], id="future", published_at="2026-10-27T10:00:00+05:30"))
        out, state = sources.new_items(doc, {}, NOW)
        self.assertEqual(len(out["rows"]), 1)
        self.assertEqual(sources.new_items(doc, state, NOW)[0]["rows"], [])


class Tax(unittest.TestCase):
    def test_fy_boundary(self):
        self.assertEqual(tax.financial_year("2026-03-31"), "2025-26")
        self.assertEqual(tax.financial_year("2026-04-01"), "2026-27")

    def test_holding_boundary(self):
        self.assertFalse(tax.long_term("2025-04-01", "2026-04-01"))
        self.assertTrue(tax.long_term("2025-04-01", "2026-04-02"))
        self.assertFalse(tax.long_term("2024-02-29", "2025-02-28"))

    def test_delivery_vs_intraday(self):
        result = tax.ledger_report(rows(ROOT / "examples/tax-ledger.json"), "2026-27")
        self.assertEqual(result["totals_inr"]["LTCG"], 1000)
        self.assertEqual(result["totals_inr"]["SPECULATIVE_BUSINESS"], 100)

    def test_fifo_partial_lots(self):
        base = {"account": "A", "symbol": "NSE:INFY", "delivery": True, "costs_ex_stt_inr": 0}
        rs = [dict(base, side="BUY", quantity=10, price=100, date="2025-01-01"), dict(base, side="BUY", quantity=10, price=200, date="2026-01-01"), dict(base, side="SELL", quantity=15, price=300, date="2026-06-01")]
        result = tax.ledger_report(rs)
        self.assertEqual(result["totals_inr"]["LTCG"], 2000)
        self.assertEqual(result["totals_inr"]["STCG"], 500)

    def test_account_lots_cannot_mix(self):
        rs = rows(ROOT / "examples/tax-ledger.json")
        rs[1]["account"] = "OTHER"
        with self.assertRaises(DataError):
            tax.ledger_report(rs)

    def test_overnight_intraday_rejected(self):
        rs = rows(ROOT / "examples/tax-ledger.json")[-2:]
        rs[1]["date"] = "2026-10-27"
        with self.assertRaises(DataError):
            tax.ledger_report(rs)


class Alerts(unittest.TestCase):
    def test_once_per_ist_day(self):
        rules = [{"kind": "above", "symbol": "NSE:INFY", "price": 1400}]
        prices = read(ROOT / "examples/workspace/prices.json")
        first, state = alerts.evaluate(rules, prices, {}, NOW)
        self.assertEqual(len(first["fired"]), 1)
        self.assertEqual(alerts.evaluate(rules, prices, state, NOW)[0]["fired"], [])

    def test_stale_not_fired(self):
        result, _ = alerts.evaluate([{"kind": "stop", "symbol": "NSE:INFY", "price": 1600}], read(ROOT / "examples/workspace/prices.json"), {}, "2026-10-26T10:02:00+05:30")
        self.assertFalse(result["fired"])
        self.assertEqual(len(result["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
