"""Transparent normalized imports: copy portfolios, compare filings, analyze results, screen."""
from .core import DataError, number, positive, money, symbol, digest, timestamp


def copy_portfolio(rows, top=None):
    """Use market values or fund NAV weights, never issuer ownership % as portfolio weight."""
    if not rows:
        raise DataError("No holdings")
    seen, converted = set(), []
    basis = "market_value_inr" if all(r.get("market_value_inr") not in (None, "") for r in rows) else "portfolio_weight_pct"
    periods = {r.get("as_of") for r in rows}
    if len(periods) != 1 or not next(iter(periods)):
        raise DataError("Holdings must share one explicit snapshot date")
    for r in rows:
        key = symbol(r["symbol"])
        if key in seen:
            raise DataError("Duplicate holding; aggregate a single instrument first")
        seen.add(key)
        if r.get("ownership_pct") and basis not in r:
            raise DataError("Issuer ownership % is not an investor portfolio weight; provide market values")
        value = positive(r.get(basis), basis)
        if not r.get("source_url"):
            raise DataError("Every holding requires source_url")
        converted.append({"symbol": key, "value": value, "source_url": r["source_url"]})
    converted.sort(key=lambda r: -r["value"])
    if top is not None:
        if top <= 0:
            raise DataError("top must be positive")
        converted = converted[:top]
    total = sum(r["value"] for r in converted)
    return {"as_of": next(iter(periods)), "basis": basis,
            "weights": [{"symbol": r["symbol"], "weight": float(r["value"] / total * 100), "source_url": r["source_url"]} for r in converted],
            "note": "Selected disclosed equity sleeve, renormalized. Does not reconstruct undisclosed holdings, cash, shorts or current trades."}


def holdings_diff(old, new):
    def quantities(rows):
        result = {}
        for r in rows:
            key = symbol(r["symbol"])
            if key in result:
                raise DataError("Duplicate holding")
            result[key] = number(r["quantity"], "quantity", 0)
        return result
    a, b = quantities(old), quantities(new)
    out = []
    for key in sorted(a.keys() | b.keys()):
        delta = b.get(key, 0) - a.get(key, 0)
        action = "NEW" if key not in a else "EXITED" if key not in b else "ADDED" if delta > 0 else "TRIMMED" if delta < 0 else "UNCHANGED"
        out.append({"symbol": key, "change": action, "quantity_delta": float(delta)})
    return {"rows": out, "note": "Share-count changes require split/bonus/merger adjustment; not proof of purchases or sales."}


def analyze(rows):
    grouped = {}
    units = {"INR": 1, "lakh": 100000, "crore": 10000000}
    for r in rows:
        key = symbol(r["symbol"])
        if r.get("period_type") != "quarter" or r.get("basis") not in ("standalone", "consolidated"):
            raise DataError("Use individual quarter results with standalone/consolidated basis; do not mix YTD with quarters")
        if r.get("unit") not in units or not r.get("source_url"):
            raise DataError("Results require unit INR/lakh/crore and source_url")
        end = timestamp(r["period_end"] + "T00:00:00+05:30").date()
        if (end.month, end.day) not in ((3, 31), (6, 30), (9, 30), (12, 31)):
            raise DataError("Only standard Indian fiscal quarter ends supported")
        row = {**r, "revenue_inr": float(number(r["revenue"]) * units[r["unit"]]),
               "net_profit_inr": float(number(r["net_profit"]) * units[r["unit"]]),
               "eps": float(number(r["eps"]))}
        grouped.setdefault((key, r["basis"]), []).append(row)
    companies = []
    for (key, basis), series in sorted(grouped.items()):
        series.sort(key=lambda r: r["period_end"], reverse=True)
        if len({r["period_end"] for r in series}) != len(series):
            raise DataError("Duplicate quarter; choose original or restated series explicitly")
        latest = series[0]
        previous_year = str(int(latest["period_end"][:4]) - 1) + latest["period_end"][4:]
        prev = next((r for r in series if r["period_end"] == previous_year), None)
        quarters = [int(r["period_end"][:4]) * 4 + int(r["period_end"][5:7]) // 3 for r in series[:4]]
        consecutive = len(quarters) == 4 and quarters == list(range(quarters[0], quarters[0] - 4, -1))
        companies.append({"symbol": key, "basis": basis, "as_of": latest["period_end"],
            "revenue_inr": latest["revenue_inr"], "net_profit_inr": latest["net_profit_inr"],
            "net_margin_pct": 100 * latest["net_profit_inr"] / latest["revenue_inr"] if latest["revenue_inr"] > 0 else None,
            "revenue_growth_yoy_pct": 100 * (latest["revenue_inr"] / prev["revenue_inr"] - 1) if prev and prev["revenue_inr"] > 0 else None,
            "eps_ttm": sum(r["eps"] for r in series[:4]) if consecutive else None,
            "source_url": latest["source_url"]})
    return {"companies": companies, "note": "EPS requires consistent share basis/corporate-action adjustments; banks/NBFCs need sector-specific interpretation."}


def screen(companies, spec):
    ops = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}
    selected, excluded = [], []
    for r in companies:
        reasons = []
        for rule in spec["rules"]:
            if rule["op"] not in ops:
                raise DataError("Unsupported screening operator")
            a = r.get(rule["metric"])
            if a is None or not ops[rule["op"]](number(a), number(rule["value"])):
                reasons.append(rule["metric"])
        if reasons:
            excluded.append({"symbol": r["symbol"], "failed_or_missing": reasons})
        else:
            selected.append(dict(r))
    rank = spec.get("rank", [])
    for r in selected:
        r["score"] = 0.0
        r["missing_rank_metrics"] = []
    total_weight = sum(positive(x.get("weight", 1), "rank weight") for x in rank)
    for rule in rank:
        key = rule["metric"]
        if rule.get("order", "desc") not in ("asc", "desc"):
            raise DataError("Rank order must be asc/desc")
        values = [number(r[key]) for r in selected if r.get(key) is not None]
        if not values:
            for r in selected:
                r["missing_rank_metrics"].append(key)
            continue
        lo, hi = min(values), max(values)
        for r in selected:
            if r.get(key) is None:
                r["missing_rank_metrics"].append(key)
                continue
            score = (number(r[key]) - lo) / (hi - lo) if hi != lo else 1
            if hi != lo and rule.get("order", "desc") == "asc":
                score = 1 - score
            r["score"] += float(score * positive(rule.get("weight", 1)) / total_weight)
    selected.sort(key=lambda r: (-r["score"], r["symbol"]))
    top = spec.get("top", len(selected))
    return {"passed": selected[:top], "excluded": excluded}


def disclosures(rows):
    out = []
    for r in rows:
        for field in ("symbol", "person", "transaction_date", "disclosed_at", "transaction_type", "quantity", "source_url"):
            if r.get(field) in (None, ""):
                raise DataError(f"Disclosure missing {field}")
        row = dict(r, symbol=symbol(r["symbol"]), quantity=float(number(r["quantity"], "quantity", 0)))
        timestamp(r["disclosed_at"])
        row["id"] = digest(row)
        out.append(row)
    return {"rows": out, "note": "Public promoter/insider disclosures, not politician trades or private information. Gifts, pledges and inter-se transfers are not market buys."}
