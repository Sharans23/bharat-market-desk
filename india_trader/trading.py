"""Whole-share planning, cumulative risk checks, exact-ticket approvals, paper fills."""
from copy import deepcopy
from decimal import Decimal
from .core import (DataError, ROOT, read, config, digest, fees, integer, money, number, positive,
                   quote, symbol, timestamp, calendar_status)


def targets(doc):
    result = {}
    for row in doc["weights"]:
        key = symbol(row["symbol"])
        if key in result:
            raise DataError(f"Duplicate target {key}")
        result[key] = positive(row["weight"], "weight")
    if not result:
        raise DataError("No target weights")
    return result


def allocation(weights, budget, buffer, cap):
    """Water-fill allocation, redistributing capped weights; unallocatable cash stays idle."""
    active, out = dict(weights), {}
    remaining = budget * (1 - buffer / 100)
    ceiling = budget * cap / 100
    while active:
        total = sum(active.values())
        trial = {k: remaining * v / total for k, v in active.items()}
        over = [k for k, v in trial.items() if v > ceiling]
        if not over:
            out.update(trial)
            break
        for k in over:
            out[k] = ceiling
            remaining -= ceiling
            del active[k]
    return out


def order(key, qty, price, side="BUY", product="CNC", stop=None):
    out = {"symbol": symbol(key), "side": side, "quantity": integer(qty),
           "product": product, "order_type": "LIMIT", "validity": "DAY", "price": money(price)}
    if stop is not None:
        out["stop_loss"] = money(stop)
    return out


def proposal(orders, now=None, **extra):
    return {"currency": "INR", "paper": True, "status": "proposed",
            "created_at": timestamp(now).isoformat(), "orders": orders, **extra}


def budget_plan(target_doc, prices, cfg, now=None):
    cfg = config(cfg)
    w = {k: v for k, v in targets(target_doc).items() if k not in cfg["blocked"]}
    if not w:
        raise DataError("All targets blocked")
    budget = positive(cfg["budget_inr"])
    alloc = allocation(w, budget, number(cfg["cash_buffer_pct"]), number(cfg["max_position_pct"]))
    orders, spent = [], Decimal(0)
    for key, amount in sorted(alloc.items()):
        p = quote(prices, key)
        limit = min(amount, number(cfg["max_order_inr"]))
        qty = int(limit / p)
        while qty and qty * p + number(fees(qty * p, "BUY", "CNC")["total"]) > amount:
            qty -= 1
        if qty and qty * p >= number(cfg["min_order_inr"]):
            orders.append(order(key, qty, p))
            spent += qty * p + number(fees(qty * p, "BUY", "CNC")["total"])
    return proposal(orders, now, estimated_cash_after=money(budget - spent),
                    note="New-cash allocation. Existing holdings require rebalance. Risk must revalidate fresh quotes.")


def intraday_plan(key, entry, stop, cfg, now=None):
    cfg = config(cfg)
    entry, stop = positive(entry, "entry"), positive(stop, "stop")
    if stop >= entry or not cfg["allow_intraday"]:
        raise DataError("Long intraday requires stop < entry and allow_intraday=true")
    budget = positive(cfg["budget_inr"])
    limit = min(budget * number(cfg["max_position_pct"]) / 100,
                budget * (1 - number(cfg["cash_buffer_pct"]) / 100), number(cfg["max_order_inr"]))
    risk = budget * number(cfg["risk_per_trade_pct"]) / 100
    qty = min(int(limit / entry), int(risk / (entry - stop)))
    while qty:
        costs = number(fees(qty * entry, "BUY", "MIS")["total"]) + number(fees(qty * stop, "SELL", "MIS")["total"])
        if qty * (entry - stop) + costs <= risk and qty * entry + costs <= limit:
            break
        qty -= 1
    if not qty or qty * entry < number(cfg["min_order_inr"]):
        raise DataError("No whole-share trade fits risk/capital/minimum limits")
    return proposal([order(key, qty, entry, product="MIS", stop=stop)], now,
                    planned_loss_inr=money(qty * (entry - stop) + costs),
                    note="Stop is a plan, not an exchange order; gaps/slippage can exceed planned loss. No automatic square-off.")


def positions(portfolio):
    if portfolio.get("currency") != "INR":
        raise DataError("Portfolio currency must be INR")
    out = {}
    for r in portfolio.get("positions", []):
        key = (symbol(r["symbol"]), r["product"])
        if key[1] not in ("CNC", "MIS") or key in out:
            raise DataError("Invalid/duplicate portfolio symbol-product")
        out[key] = integer(r["quantity"], minimum=0)
    return out


def validate_order(o):
    required = {"symbol", "side", "quantity", "product", "order_type", "validity", "price"}
    if required - o.keys() or o.keys() - required - {"stop_loss"}:
        raise DataError("Order fields must match schema; notional/derivative/unknown fields are unsupported")
    symbol(o["symbol"])
    if o["symbol"] != symbol(o["symbol"]):
        raise DataError("Symbol must be canonical uppercase")
    integer(o["quantity"])
    positive(o["price"], "limit price")
    if o["side"] not in ("BUY", "SELL") or o["product"] not in ("CNC", "MIS"):
        raise DataError("Only BUY/SELL cash-equity CNC/MIS is supported")
    if o["order_type"] != "LIMIT" or o["validity"] != "DAY":
        raise DataError("Only LIMIT DAY orders are supported")
    if "stop_loss" in o:
        positive(o["stop_loss"], "stop_loss")


def risk_check(doc, cfg, portfolio, prices, instruments, state=None, now=None, calendar=None):
    cfg, now = config(cfg), timestamp(now)
    state = state or {"events": []}
    held = positions(portfolio)
    available_to_sell = dict(held)
    cash = number(portfolio["cash_inr"], "cash_inr", 0)
    valuation = {}
    for key, qty in held.items():
        if qty:
            valuation[key[0]] = quote(prices, key[0], now.isoformat(), cfg["max_quote_age_seconds"])
    equity = cash + sum(qty * valuation.get(key[0], 0) for key, qty in held.items())
    positive(equity, "portfolio equity")
    today = now.date().isoformat()
    if portfolio.get("trading_date") != today:
        raise DataError("Portfolio trading_date must match IST today; reconcile balances/P&L first")
    daily_pnl = number(portfolio.get("daily_pnl_inr"), "daily_pnl_inr")
    start_equity = positive(portfolio.get("day_start_equity_inr"), "day_start_equity_inr")
    # Current marked equity catches unrealized losses even if an imported P&L is optimistic.
    net_flow = number(portfolio.get("day_net_cash_flow_inr", 0), "day_net_cash_flow_inr")
    daily_pnl = min(daily_pnl, equity - start_equity - net_flow)
    events = [e for e in state.get("events", []) if e.get("at", "")[:10] == today and e.get("status") == "filled"]
    used = {(e["order"]["symbol"], e["order"]["side"], e["order"]["product"]) for e in events}
    count, results = len(events), []
    if doc.get("paper") is not True or doc.get("currency") != "INR" or doc.get("status") != "proposed":
        raise DataError("Expected INR paper proposal")
    if not isinstance(doc.get("orders"), list) or not doc["orders"]:
        raise DataError("No proposed orders")
    for o in doc["orders"]:
        reasons = []
        try:
            validate_order(o)
            key = o["symbol"]
            instrument = instruments.get("instruments", {}).get(key)
            if not instrument or instrument.get("segment") != "EQ" or instrument.get("active") is not True:
                raise DataError("Instrument missing, inactive, or not supported main-board EQ")
            if instruments.get("as_of") != today:
                raise DataError("Instrument eligibility/tick/circuit data must be verified today")
            if key.split(":")[0] != "NSE":
                raise DataError("BSE execution requires a verified BSE calendar and group-specific charges; research only in this build")
            if instrument.get("surveillance") != "NONE" or instrument.get("series") != "EQ":
                raise DataError("ASM/GSM/T2T/unknown surveillance or non-EQ series blocked")
            if instrument.get("lot_size") != 1:
                raise DataError("Only whole-share main-board equity, lot_size=1")
            if instrument.get("broker_symbol") != key.split(":")[1]:
                raise DataError("Broker symbol must match the verified NSE equity symbol")
            status = calendar_status(now, "NSE", instrument.get("cas_eligible"), calendar)
            if not status["continuous"]:
                reasons.append("Session: " + status["phase"])
            q = quote(prices, key, now.isoformat(), cfg["max_quote_age_seconds"])
            p, qty = positive(o["price"]), integer(o["quantity"])
            tick = positive(instrument["tick_size"], "tick_size")
            if p % tick:
                reasons.append("Price is not aligned to current instrument tick size")
            lo, hi = positive(instrument["lower_band"]), positive(instrument["upper_band"])
            if not lo <= p <= hi:
                reasons.append("Price outside current circuit band")
            if abs(p - q) / q * 100 > number(cfg["max_quote_deviation_pct"]):
                reasons.append("Limit price too far from quote")
            if key in cfg["blocked"]:
                reasons.append("Symbol blocked")
            product, side = o["product"], o["side"]
            value = p * qty
            cost = number(fees(value, side, product)["total"])
            if not number(cfg["min_order_inr"]) <= value <= number(cfg["max_order_inr"]):
                reasons.append("Order value outside min/max")
            keyp = (key, product)
            if side == "BUY":
                if cash - value - cost < equity * number(cfg["cash_buffer_pct"]) / 100:
                    reasons.append("Cash buffer / fully funded purchase limit")
                existing = sum(n * max(q, p) for (s, _), n in held.items() if s == key)
                if existing + qty * max(q, p) > equity * number(cfg["max_position_pct"]) / 100:
                    reasons.append("Post-trade position cap")
                if daily_pnl <= -start_equity * number(cfg["max_daily_loss_pct"]) / 100:
                    reasons.append("Daily loss limit; new buys halted")
                if product == "MIS":
                    if not cfg["allow_intraday"] or instrument.get("intraday_allowed") is not True:
                        reasons.append("Intraday not enabled/eligible")
                    if now.strftime("%H:%M") >= cfg["intraday_entry_cutoff"]:
                        reasons.append("Intraday entry cutoff reached")
                    stop = positive(o.get("stop_loss"), "MIS stop_loss")
                    if stop >= p or stop % tick or not lo <= stop <= hi:
                        reasons.append("Invalid stop loss / tick / circuit band")
                    loss = qty * (p - stop) + cost + number(fees(qty * stop, "SELL", "MIS")["total"])
                    if loss > equity * number(cfg["risk_per_trade_pct"]) / 100:
                        reasons.append("Per-trade planned loss exceeds limit")
            elif qty > available_to_sell.get(keyp, 0):
                reasons.append("Naked short / insufficient holdings in this product")
            dupe = (key, side, product)
            if dupe in used:
                reasons.append("Duplicate symbol/side/product today or in batch")
            if side == "BUY" and count >= cfg["max_orders_per_day"]:
                reasons.append("Daily order limit; new buys halted")
            if not reasons:
                # Never fund new buys from a merely proposed sell. Recheck after its actual fill.
                if side == "BUY":
                    cash -= value + cost
                    held[keyp] = held.get(keyp, 0) + qty
                else:
                    available_to_sell[keyp] -= qty
                used.add(dupe)
                count += 1
        except (DataError, KeyError, TypeError) as exc:
            reasons.append(str(exc))
        results.append({"fingerprint": digest(o), "verdict": "BLOCK" if reasons else "PASS", "reasons": reasons})
    return {"at": now.isoformat(), "context": digest([doc, cfg, portfolio, prices, instruments, state,
            calendar or read(ROOT / "data/calendar-2026.json"), read(ROOT / "data/charges.json")]),
            "results": results, "passed": sum(r["verdict"] == "PASS" for r in results),
            "blocked": sum(r["verdict"] == "BLOCK" for r in results),
            "cash_after_buys_inr": money(cash)}


def ticket(o, instruments):
    validate_order(o)
    i = instruments["instruments"][o["symbol"]]
    return {"exchange": o["symbol"].split(":")[0], "tradingsymbol": i["broker_symbol"],
            "transaction_type": o["side"], "quantity": integer(o["quantity"]),
            "product": o["product"], "order_type": "LIMIT", "price": money(o["price"]), "validity": "DAY"}


def approve(o, report, reply, now=None, ttl=120):
    now, at = timestamp(now), timestamp(report["at"])
    if not 0 <= (now - at).total_seconds() <= float(ttl):
        raise DataError("Risk report expired")
    fp = digest(o)
    if not any(r["fingerprint"] == fp and r["verdict"] == "PASS" for r in report["results"]):
        raise DataError("Exact order has no PASS")
    if reply.strip() != f"YES {fp}":
        raise DataError(f"Exact acknowledgement required: YES {fp}")
    return {"fingerprint": fp, "risk_context": report["context"], "at": now.isoformat(), "reply": reply, "status": "approved"}


def paper_fill(o, approval, report, portfolio, state, fill_price, now=None, ttl=120, prices=None):
    now = timestamp(now)
    fp = digest(o)
    if approval.get("fingerprint") != fp or approval.get("risk_context") != report["context"]:
        raise DataError("Approval does not match current order/context; rerun risk and approve")
    if not 0 <= (now - timestamp(approval["at"])).total_seconds() <= float(ttl):
        raise DataError("Approval expired")
    approve(o, report, approval["reply"], now.isoformat(), ttl)
    if any(e.get("approval_id") == digest(approval) for e in state.get("events", [])):
        raise DataError("Approval already consumed")
    p = positive(fill_price, "paper fill price")
    limit = positive(o["price"])
    if (o["side"] == "BUY" and p > limit) or (o["side"] == "SELL" and p < limit):
        raise DataError("Paper fill violates limit")
    # Conservative simulation: fill exactly at the approved limit, no guessed better fills.
    if p != limit:
        raise DataError("Paper simulator requires the approved limit price")
    out, state = deepcopy(portfolio), deepcopy(state)
    held = positions(out)
    key = (o["symbol"], o["product"])
    qty = integer(o["quantity"])
    cost = number(fees(qty * p, o["side"], o["product"])["total"])
    sign = 1 if o["side"] == "BUY" else -1
    held[key] = held.get(key, 0) + sign * qty
    cash = number(out["cash_inr"]) - sign * qty * p - cost
    if cash < 0 or held[key] < 0:
        raise DataError("Insufficient cash/holdings")
    lots = out.setdefault("lots", [])
    realized = Decimal(0)
    if sign == 1:
        lots.append({"symbol": key[0], "product": key[1], "quantity": qty, "price": money(p),
                     "acquired": now.date().isoformat(), "buy_costs_inr": money(cost)})
    else:
        remaining = qty
        for lot in sorted(lots, key=lambda l: l["acquired"]):
            if (lot["symbol"], lot["product"]) != key or not lot["quantity"]:
                continue
            take = min(remaining, integer(lot["quantity"]))
            basis_fees = number(lot.get("buy_costs_inr", 0)) * take / lot["quantity"]
            realized += take * (p - number(lot["price"])) - basis_fees
            lot["buy_costs_inr"] = money(number(lot.get("buy_costs_inr", 0)) - basis_fees)
            lot["quantity"] -= take
            remaining -= take
            if not remaining:
                break
        if remaining:
            raise DataError("Missing FIFO cost lots; reconcile portfolio before paper sale")
        realized -= cost
    out["lots"] = [l for l in lots if l["quantity"]]
    out["cash_inr"] = money(cash)
    out["positions"] = [{"symbol": s, "product": prod, "quantity": n} for (s, prod), n in held.items() if n]
    # Revalue total equity instead of adding realized P&L to a value which may already
    # include unrealized gains/losses. Direct callers without marks must reconcile.
    out["daily_pnl_inr"] = None
    if prices is not None:
        marked = cash + sum(n * quote(prices, s) for (s, _), n in held.items() if n)
        out["daily_pnl_inr"] = money(marked - positive(out["day_start_equity_inr"]) - number(out.get("day_net_cash_flow_inr", 0)))
    state.setdefault("events", []).append({"at": now.isoformat(), "status": "filled", "paper": True,
        "approval_id": digest(approval), "order": o, "fill_price": money(p), "fees_inr": money(cost), "realized_pnl_inr": money(realized)})
    return out, state


def rebalance(target_doc, portfolio, prices, cfg, band=5, now=None):
    cfg, band = config(cfg), number(band, "band", 0)
    held = positions(portfolio)
    if any(prod == "MIS" and qty for (_, prod), qty in held.items()):
        raise DataError("Close/reconcile intraday positions before delivery rebalance")
    w = targets(target_doc)
    keys = set(w) | {k[0] for k in held}
    ps = {k: quote(prices, k) for k in keys}
    equity = number(portfolio["cash_inr"]) + sum(q * ps[s] for (s, _), q in held.items())
    alloc = allocation(w, equity, number(cfg["cash_buffer_pct"]), number(cfg["max_position_pct"]))
    result, drift = [], []
    for key in sorted(keys):
        current = held.get((key, "CNC"), 0)
        target = alloc.get(key, Decimal(0))
        delta_pct = (current * ps[key] - target) / positive(equity) * 100
        drift.append({"symbol": key, "drift_percentage_points": money(delta_pct)})
        if abs(delta_pct) < band:
            continue
        desired = int(target / ps[key])
        change = desired - current
        qty = min(abs(change), int(number(cfg["max_order_inr"]) / ps[key]))
        if qty and qty * ps[key] >= number(cfg["min_order_inr"]):
            result.append(order(key, qty, ps[key], "BUY" if change > 0 else "SELL"))
    result.sort(key=lambda o: o["side"] == "BUY")
    return proposal(result, now, drift=drift,
        note="Partial capped plan. Sell first, reconcile fills, then regenerate buys; proposed sale proceeds cannot fund buys.")
