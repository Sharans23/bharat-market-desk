"""Shared validation, files, instrument identity, calendar and estimated charges."""
import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[1]


class DataError(ValueError):
    pass


def number(value, name="number", minimum=None):
    if isinstance(value, bool):
        raise DataError(f"{name}: boolean is not a number")
    try:
        out = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        raise DataError(f"{name}: invalid number {value!r}")
    if not out.is_finite() or (minimum is not None and out < Decimal(str(minimum))):
        raise DataError(f"{name}: must be finite and >= {minimum}")
    return out


def positive(value, name="number"):
    out = number(value, name, 0)
    if out == 0:
        raise DataError(f"{name}: must be positive")
    return out


def integer(value, name="quantity", minimum=1):
    out = number(value, name, minimum)
    if out != out.to_integral_value():
        raise DataError(f"{name}: whole shares required")
    return int(out)


def money(value):
    return float(number(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def read(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh, parse_constant=lambda s: (_ for _ in ()).throw(DataError(f"Invalid JSON number: {s}")))


def write(path, doc):
    """Atomic replacement; callers serialize multi-file workflows with a lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False, allow_nan=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def rows(path, key="rows"):
    if str(path).lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    doc = read(path)
    result = doc.get(key) if isinstance(doc, dict) else doc
    if not isinstance(result, list):
        raise DataError(f"Expected a list or {{{key}: [...]}} in {path}")
    return result


def timestamp(value=None):
    if value is None:
        return datetime.now(IST)
    out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if out.tzinfo is None:
        raise DataError("Timestamp requires timezone, e.g. 2026-10-26T10:00:00+05:30")
    return out.astimezone(IST)


def digest(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def symbol(value):
    value = str(value).strip().upper()
    if not re.fullmatch(r"(?:NSE:[A-Z0-9][A-Z0-9&.-]{0,29}|BSE:[0-9]{6})", value):
        raise DataError(f"Use exchange-qualified equity symbol, e.g. NSE:INFY or BSE:500209: {value!r}")
    return value


def config(doc=None):
    out = read(ROOT / "data/default-config.json")
    out.update(doc or {})
    if out["currency"] != "INR" or out["paper"] is not True:
        raise DataError("This build supports INR paper trading and manual broker tickets only")
    for key in ("cash_buffer_pct", "max_position_pct", "risk_per_trade_pct", "max_daily_loss_pct"):
        n = number(out[key], key, 0)
        if n > 100 or (key != "cash_buffer_pct" and n == 0):
            raise DataError(f"{key} must be within 0..100 (risk/caps must be positive)")
    for key in ("budget_inr", "max_order_inr", "max_quote_age_seconds", "max_quote_deviation_pct", "risk_ttl_seconds"):
        positive(out[key], key)
    integer(out["max_orders_per_day"], "max_orders_per_day")
    number(out["min_order_inr"], "min_order_inr", 0)
    if number(out["min_order_inr"]) > number(out["max_order_inr"]):
        raise DataError("min_order_inr exceeds max_order_inr")
    if not isinstance(out["allow_intraday"], bool):
        raise DataError("allow_intraday must be boolean")
    for key in ("intraday_entry_cutoff", "intraday_exit_reminder"):
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", str(out[key])):
            raise DataError(f"{key} requires HH:MM IST")
    for s in out["blocked"]:
        symbol(s)
    return out


def calendar_status(now, exchange="NSE", cas_eligible=None, calendar=None):
    cal = calendar or read(ROOT / "data/calendar-2026.json")
    now = timestamp(now) if not isinstance(now, datetime) else now.astimezone(IST)
    d = now.date().isoformat()
    result = {"at": now.isoformat(), "exchange": exchange, "phase": "UNKNOWN", "continuous": False}
    if exchange != cal["exchange"] or not cal["valid_from"] <= d <= cal["valid_through"]:
        return dict(result, reason="Calendar coverage unavailable; supply verified exchange calendar")
    if d in cal.get("unresolved_sessions", []):
        return dict(result, reason="Special session requires a verified timing override")
    override = cal.get("special_sessions", {}).get(d)
    if not override and (now.weekday() >= 5 or d in cal["holidays"]):
        return dict(result, phase="CLOSED", reason=cal["holidays"].get(d, "Weekend"))
    if override:
        opening, closing = override["open"], override["close"]
    else:
        if d >= "2026-08-03" and not isinstance(cas_eligible, bool):
            return dict(result, reason="CAS eligibility missing in current instrument master")
        opening = "09:15"
        closing = "15:15" if d >= "2026-08-03" and cas_eligible else "15:30"
    t = now.strftime("%H:%M")
    phase = "CONTINUOUS" if opening <= t < closing else "CLOSED"
    if not override and d >= "2026-08-03" and cas_eligible and "15:15" <= t < "15:35":
        phase = "CLOSING_AUCTION"
    elif not override and "09:00" <= t < opening:
        phase = "PREOPEN"
    return dict(result, phase=phase, continuous=phase == "CONTINUOUS", open=opening, close=closing)


def fees(turnover, side, product, exchange="NSE", profile=None):
    """Illustrative Zerodha cash-equity profile, per order, estimated paise rounding."""
    p = profile or read(ROOT / "data/charges.json")
    if exchange != "NSE":
        raise DataError("Bundled fee profile is NSE EQ only; BSE group-specific tariffs need a custom profile")
    if product not in ("CNC", "MIS") or side not in ("BUY", "SELL"):
        raise DataError("Charges support CNC/MIS and BUY/SELL only")
    v = number(turnover, "turnover", 0)
    brokerage = min(v * number(p["intraday_brokerage_rate"]), number(p["intraday_brokerage_cap"])) if product == "MIS" else Decimal(0)
    stt = v * number(p["delivery_stt_rate"] if product == "CNC" else p["intraday_sell_stt_rate"]) if product == "CNC" or side == "SELL" else Decimal(0)
    exchange_fee = v * number(p["exchange_rate"])
    sebi = v * number(p["sebi_rate"])
    stamp = v * number(p["delivery_stamp_rate"] if product == "CNC" else p["intraday_stamp_rate"]) if side == "BUY" else Decimal(0)
    gst = (brokerage + exchange_fee + sebi) * number(p["gst_rate"])
    dp = number(p["delivery_sell_dp_including_gst"]) if product == "CNC" and side == "SELL" else Decimal(0)
    parts = dict(brokerage=brokerage, stt=stt, exchange=exchange_fee, sebi=sebi, stamp=stamp, gst=gst, dp=dp)
    return {**{k: money(v) for k, v in parts.items()}, "total": money(sum(parts.values())), "estimated": True}


def quote(prices, key, now=None, max_age=None):
    q = prices.get("quotes", {}).get(symbol(key))
    if not isinstance(q, dict) or q.get("currency") != "INR" or not q.get("source"):
        raise DataError(f"{key}: missing INR quote with source")
    p = positive(q.get("price"), f"{key} price")
    at = timestamp(q.get("as_of")) if q.get("as_of") else None
    if at is None:
        raise DataError(f"{key}: missing quote timestamp")
    if now is not None and max_age is not None:
        age = (timestamp(now) - at).total_seconds()
        if age < -5 or age > float(max_age):
            raise DataError(f"{key}: stale or future quote ({age:.0f}s)")
    return p
