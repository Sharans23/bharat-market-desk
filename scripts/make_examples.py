"""Regenerate explicitly synthetic examples; never contacts a data source."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def save(name, doc):
    path = ROOT / "examples" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


at = "2026-10-26T10:00:00+05:30"
save("workspace/account.json", {"portfolio": {"currency": "INR", "cash_inr": 100000, "positions": [], "lots": [], "trading_date": "2026-10-26", "daily_pnl_inr": 0, "day_start_equity_inr": 100000}, "events": [], "approvals": {}})
save("workspace/prices.json", {"synthetic": True, "quotes": {s: {"price": p, "as_of": at, "currency": "INR", "source": "SYNTHETIC EXAMPLE, NOT A MARKET QUOTE", "execution_grade": False} for s, p in {"NSE:INFY": 1500, "NSE:TCS": 3000, "NSE:RELIANCE": 1250, "NSE:HDFCBANK": 1000}.items()}})
save("workspace/instruments.json", {"synthetic": True, "as_of": "2026-10-26", "source": "SYNTHETIC EXAMPLE; replace from exchange/broker master and surveillance lists", "instruments": {s: {"segment": "EQ", "series": "EQ", "active": True, "lot_size": 1, "tick_size": 0.1, "lower_band": p * 0.9, "upper_band": p * 1.1, "cas_eligible": True, "surveillance": "NONE", "intraday_allowed": True, "broker_symbol": s.split(":")[1]} for s, p in {"NSE:INFY": 1500, "NSE:TCS": 3000, "NSE:RELIANCE": 1250, "NSE:HDFCBANK": 1000}.items()}})
save("workspace/targets.json", {"weights": [{"symbol": s, "weight": w} for s, w in {"NSE:INFY": 30, "NSE:TCS": 25, "NSE:RELIANCE": 25, "NSE:HDFCBANK": 20}.items()], "source": "SYNTHETIC educational weights"})
save("workspace/alerts.json", {"rules": [{"kind": "above", "symbol": "NSE:INFY", "price": 1500}, {"kind": "open", "exchange": "NSE", "cas_eligible": True}, {"kind": "square_off_reminder", "exchange": "NSE", "cas_eligible": True, "time": "15:00"}]})
save("workspace/rules.json", {"rules": [{"metric": "net_margin_pct", "op": ">=", "value": 10}, {"metric": "revenue_growth_yoy_pct", "op": ">", "value": 0}], "rank": [{"metric": "revenue_growth_yoy_pct", "order": "desc", "weight": 1}], "top": 5})
save("holdings.json", {"rows": [{"symbol": s, "quantity": n, "market_value_inr": n * p, "as_of": "2026-09-30", "source_url": "https://example.invalid/synthetic-holdings"} for s, n, p in [("NSE:INFY", 100, 1500), ("NSE:TCS", 40, 3000), ("NSE:RELIANCE", 100, 1250), ("NSE:HDFCBANK", 80, 1000)]]})
save("holdings-previous.json", {"rows": [{"symbol": "NSE:INFY", "quantity": 80}, {"symbol": "NSE:TCS", "quantity": 40}, {"symbol": "NSE:ITC", "quantity": 100}]})
save("results.json", {"rows": [{"symbol": "NSE:INFY", "period_end": d, "period_type": "quarter", "basis": "consolidated", "unit": "crore", "revenue": revenue, "net_profit": profit, "eps": eps, "source_url": "https://example.invalid/synthetic-results"} for d, revenue, profit, eps in [("2026-09-30", 11000, 2000, 20), ("2026-06-30", 10500, 1900, 19), ("2026-03-31", 10200, 1850, 18.5), ("2025-12-31", 10000, 1800, 18), ("2025-09-30", 9000, 1700, 17)]]})
save("disclosures.json", {"rows": [{"symbol": "NSE:INFY", "person": "Synthetic Example Person", "transaction_date": "2026-10-22", "disclosed_at": "2026-10-26T09:30:00+05:30", "transaction_type": "Market purchase", "quantity": 100, "source_url": "https://example.invalid/synthetic-disclosure"}]})
save("news.json", {"rows": [{"symbol": "NSE:INFY", "title": "Synthetic earnings announcement", "published_at": "2026-10-26T09:30:00+05:30", "url": "https://example.invalid/synthetic-news", "id": "synthetic-news-1"}], "errors": {}})
save("tax-ledger.json", {"rows": [{"account": "DEMO-DEMAT", "symbol": "NSE:INFY", "side": side, "quantity": 10, "price": p, "date": d, "delivery": delivery, "costs_ex_stt_inr": 0} for d, side, p, delivery in [("2025-01-01", "BUY", 1400, True), ("2026-04-02", "SELL", 1500, True), ("2026-10-26", "BUY", 1500, False), ("2026-10-26", "SELL", 1510, False)]]})
