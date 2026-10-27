"""Polling alerts: no background scheduler, no order placement."""
from .core import DataError, positive, quote, timestamp, digest, calendar_status


def evaluate(rules, prices, state, now=None, max_age=60, calendar=None):
    now = timestamp(now)
    seen = set(state.get("seen", []))
    fired, errors = [], []
    for rule in rules:
        try:
            kind = rule["kind"]
            key = rule.get("symbol")
            hit = False
            if kind in ("above", "below", "stop"):
                p = quote(prices, key, now.isoformat(), max_age)
                level = positive(rule["price"])
                hit = p >= level if kind == "above" else p <= level
            elif kind == "open":
                status = calendar_status(now, rule.get("exchange", "NSE"), rule.get("cas_eligible"), calendar)
                hit = status["continuous"]
            elif kind == "square_off_reminder":
                status = calendar_status(now, rule.get("exchange", "NSE"), rule.get("cas_eligible"), calendar)
                hit = status["continuous"] and now.strftime("%H:%M") >= rule.get("time", "15:00")
            else:
                raise DataError("Unknown alert kind")
            token = digest([rule, now.date().isoformat()])
            if hit and token not in seen:
                fired.append(rule)
                seen.add(token)
        except (DataError, KeyError, TypeError) as exc:
            errors.append({"rule": rule, "error": str(exc)})
    return {"at": now.isoformat(), "fired": fired, "errors": errors}, {"seen": sorted(seen)}
