"""FIFO ledger arithmetic; separate delivery capital gains and non-delivery business P&L."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from .core import DataError, integer, number, positive, money, symbol


def financial_year(day):
    d = date.fromisoformat(day)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def long_term(acquired, sold):
    a, s = date.fromisoformat(acquired), date.fromisoformat(sold)
    anniversary = a.replace(year=a.year + 1, day=min(a.day, monthrange(a.year + 1, a.month)[1]))
    return s > anniversary


def ledger_report(trades, fy=None):
    """Input must include complete opening buys and chronological fills, per demat account.

    delivery denotes settlement classification, not broker product: same-day CNC
    round trips must be marked false. Supply tax-deductible costs excluding STT.
    """
    lots, results = {}, []
    for r in sorted(enumerate(trades), key=lambda x: (x[1]["date"], x[0])):
        r = r[1]
        day = date.fromisoformat(r["date"])
        key = (r["account"], symbol(r["symbol"]), r["delivery"])
        if not isinstance(r["delivery"], bool) or not r["account"]:
            raise DataError("Tax ledger requires account and boolean delivery classification")
        qty, p = integer(r["quantity"]), positive(r["price"])
        costs = number(r.get("costs_ex_stt_inr", 0), "costs_ex_stt_inr", 0)
        if r["side"] == "BUY":
            lots.setdefault(key, []).append({"date": day, "qty": qty, "price": p, "costs": costs})
            continue
        if r["side"] != "SELL":
            raise DataError("Tax side must be BUY/SELL")
        remaining = qty
        for lot in lots.get(key, []):
            if not lot["qty"]:
                continue
            if not r["delivery"] and lot["date"] != day:
                raise DataError("Non-delivery cash-equity lot cannot remain overnight")
            take = min(remaining, lot["qty"])
            buy_cost = lot["costs"] * take / lot["qty"]
            gain = take * (p - lot["price"]) - buy_cost - costs * take / qty
            term = "LTCG" if long_term(lot["date"].isoformat(), r["date"]) else "STCG"
            if not r["delivery"]:
                term = "SPECULATIVE_BUSINESS"
            results.append({"symbol": key[1], "account": key[0], "quantity": take,
                "acquired": lot["date"].isoformat(), "sold": r["date"], "financial_year": financial_year(r["date"]),
                "classification": term, "gain_inr": money(gain)})
            lot["qty"] -= take
            lot["costs"] -= buy_cost
            remaining -= take
            if not remaining:
                break
        if remaining:
            raise DataError("Sale exceeds available FIFO lots in this account/delivery class")
    selected = [r for r in results if fy is None or r["financial_year"] == fy]
    totals = {k: money(sum(number(r["gain_inr"]) for r in selected if r["classification"] == k)) for k in ("STCG", "LTCG", "SPECULATIVE_BUSINESS")}
    return {"sales": selected, "totals_inr": totals,
            "note": "Classification/arithmetic only, assuming delivery shares are capital assets. No final tax liability. Business classification, grandfathering, corporate actions, loss set-off/carry-forward, exemption, surcharge and cess require separate review. No US wash-sale rule applied."}


def harvest(lots, prices, sold, min_loss=100):
    from .core import quote
    out = []
    for lot in lots:
        if lot.get("product") != "CNC":
            continue
        qty = integer(lot["quantity"])
        gain = qty * (quote(prices, lot["symbol"]) - positive(lot["price"]))
        if gain <= -number(min_loss, "min_loss", 0):
            out.append({"symbol": lot["symbol"], "quantity": qty, "unrealized_gain_inr": money(gain),
                "term": "LTCG" if long_term(lot["acquired"], sold) else "STCG"})
    return {"candidates": out, "note": "Pre-cost estimates only; actual demat sales follow FIFO, so a selected later loss lot may not be the lot sold. No orders generated."}
