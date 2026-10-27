"""Command-line interface. Run from the repository: python -m india_trader --help."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys
from .core import DataError, ROOT, read, write, rows, config, timestamp, calendar_status, digest, fees, quote
from . import trading, research, sources, tax, alerts


@contextmanager
def account_lock(workspace):
    path = workspace / ".account.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise DataError("Account busy. If a previous process crashed, confirm it stopped before removing .account.lock")
    try:
        os.close(fd)
        yield
    finally:
        path.unlink()


def parser():
    p = argparse.ArgumentParser(description="India Trader: research, paper trading and Kite/Dhan/Groww account/data connections")
    p.add_argument("--workspace", default="trader", help="Local data/state directory")
    p.add_argument("--now", help="Timezone-aware deterministic simulation time; omit for real current time")
    p.add_argument("--out", help="Write JSON output to this path")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Create synthetic example workspace, refusing existing files")
    sub.add_parser("budget", help="Whole-share new-money allocation")
    x = sub.add_parser("intraday", help="Long cash-equity stop-based sizing")
    x.add_argument("symbol"); x.add_argument("--entry", required=True); x.add_argument("--stop", required=True)
    sub.add_parser("risk", help="Check exact proposals and current account cumulatively")
    x = sub.add_parser("broker", help="Show/approve/paper-fill one ticket; never submit live orders")
    x.add_argument("action", choices=["show", "approve", "fill", "log"])
    x.add_argument("--index", type=int, default=1)
    x.add_argument("--reply"); x.add_argument("--fill-price")
    x = sub.add_parser("quote", help="Unofficial Yahoo .NS research quotes")
    x.add_argument("symbols", nargs="+")
    x = sub.add_parser("clock", help="Verified calendar bounds and CAS-aware session")
    x.add_argument("--exchange", default="NSE", choices=["NSE", "BSE"])
    x.add_argument("--cas", choices=["yes", "no", "unknown"], default="unknown")
    x = sub.add_parser("news", help="India RSS news or normalized saved feed")
    x.add_argument("symbols", nargs="*"); x.add_argument("--input"); x.add_argument("--hours", type=int, default=48)
    x = sub.add_parser("filings", help="Read NSE public metadata; web endpoints may block automated access")
    x.add_argument("kind", choices=["announcements", "insider", "results", "shareholding"])
    x.add_argument("symbols", nargs="*"); x.add_argument("--start"); x.add_argument("--end")
    x = sub.add_parser("disclosures", help="Normalize and deduplicate public insider disclosure CSV/JSON")
    x.add_argument("input")
    x = sub.add_parser("copycat", help="Copy a disclosed equity sleeve or compare share counts")
    x.add_argument("input"); x.add_argument("--previous"); x.add_argument("--top", type=int)
    x = sub.add_parser("analyst", help="Compute quarterly metrics from normalized results")
    x.add_argument("input")
    x = sub.add_parser("screen", help="Filter/rank metrics with explicit missing-value failures")
    x.add_argument("--input"); x.add_argument("--rules")
    x = sub.add_parser("tax", help="FIFO accounting / unrealized loss candidates, no final tax return")
    x.add_argument("action", choices=["report", "harvest"]); x.add_argument("--input"); x.add_argument("--fy"); x.add_argument("--min-loss", type=float, default=100)
    sub.add_parser("alerts", help="Run one poll of alerts and persist once-per-day deduplication")
    x = sub.add_parser("rebalance", help="Capped whole-share delivery drift plan")
    x.add_argument("--band", type=float, default=5)
    x = sub.add_parser("charges", help="Estimated NSE EQ charges for one order")
    x.add_argument("turnover"); x.add_argument("--side", choices=["BUY", "SELL"], required=True); x.add_argument("--product", choices=["CNC", "MIS"], required=True)
    from .brokers.commands import add_parser
    add_parser(sub)
    return p


def run(a):
    if a.cmd == "connections":
        from .brokers.commands import run as run_connections
        return run_connections(a)
    ws = Path(a.workspace)
    def get(name):
        return read(ws / (name + ".json"))
    def put(name, doc):
        write(ws / (name + ".json"), doc)
        return doc
    def state(name):
        path = ws / (name + ".json")
        return read(path) if path.exists() else {}
    def inputs():
        account = get("account")
        cal = get("calendar") if (ws / "calendar.json").exists() else None
        return (get("orders"), config(get("config")), account["portfolio"], get("prices"), get("instruments"), {"events": account["events"]}, cal)
    def checked():
        doc, cfg, portfolio, prices, instruments, events, cal = inputs()
        report = trading.risk_check(doc, cfg, portfolio, prices, instruments, events, a.now, cal)
        return (doc, cfg, portfolio, prices, instruments, events, cal), report

    if a.cmd == "init":
        if ws.exists() and any(ws.iterdir()):
            raise DataError("Refusing to overwrite nonempty workspace; choose a new --workspace")
        ws.mkdir(parents=True, exist_ok=True)
        for path in (ROOT / "examples/workspace").glob("*.json"):
            shutil.copyfile(path, ws / path.name)
        shutil.copyfile(ROOT / "data/default-config.json", ws / "config.json")
        return {"workspace": str(ws.resolve()), "synthetic": True, "simulation_time": "2026-10-26T10:00:00+05:30", "note": "Examples are not market data. Replace quotes, instruments, cash, positions and P&L before actual analysis."}
    if a.cmd == "charges":
        return fees(a.turnover, a.side, a.product)
    if a.cmd == "clock":
        cal = get("calendar") if (ws / "calendar.json").exists() else None
        return calendar_status(timestamp(a.now), a.exchange, {"yes": True, "no": False, "unknown": None}[a.cas], cal)
    if a.cmd == "quote":
        result = sources.fetch_quotes(a.symbols)
        if result["quotes"]:
            # Replacement intentionally drops missing/stale prior symbols.
            put("prices", result)
        return result
    if a.cmd == "filings":
        return sources.nse_rows(a.kind, a.symbols, a.start, a.end)
    if a.cmd in ("news", "disclosures"):
        if a.cmd == "news":
            if not a.input and not a.symbols:
                raise DataError("Supply symbols or --input")
            doc = read(a.input) if a.input else sources.news(a.symbols)
        else:
            doc = research.disclosures(rows(a.input))
        result, newstate = sources.new_items(doc, state(a.cmd + "-state"), a.now, getattr(a, "hours", 48))
        put(a.cmd + "-state", newstate)
        return result
    if a.cmd == "copycat":
        incoming = rows(a.input)
        if a.previous:
            return research.holdings_diff(rows(a.previous), incoming)
        return put("targets", research.copy_portfolio(incoming, a.top))
    if a.cmd == "analyst":
        return put("metrics", research.analyze(rows(a.input)))
    if a.cmd == "screen":
        companies = rows(a.input, "companies") if a.input else get("metrics")["companies"]
        return put("shortlist", research.screen(companies, read(a.rules) if a.rules else get("rules")))
    if a.cmd == "budget":
        return put("orders", trading.budget_plan(get("targets"), get("prices"), get("config"), a.now))
    if a.cmd == "intraday":
        return put("orders", trading.intraday_plan(a.symbol, a.entry, a.stop, get("config"), a.now))
    if a.cmd == "rebalance":
        return put("orders", trading.rebalance(get("targets"), get("account")["portfolio"], get("prices"), get("config"), a.band, a.now))
    if a.cmd == "risk":
        _, report = checked()
        return put("risk", report)
    if a.cmd == "broker":
        with account_lock(ws):
            if a.action == "log":
                return {"events": get("account")["events"]}
            (doc, cfg, portfolio, prices, instruments, events, cal), report = checked()
            if a.action == "show":
                put("risk", report)
                tickets = []
                for o, verdict in zip(doc["orders"], report["results"]):
                    entry = {"order": o, **verdict}
                    if verdict["verdict"] == "PASS":
                        entry["kite_manual_payload"] = trading.ticket(o, instruments)
                        entry["acknowledgement"] = "YES " + digest(o)
                    tickets.append(entry)
                return {"tickets": tickets, "paper_only": True, "note": "No network order submission. Stop_loss is planning metadata, not a linked protective order."}
            if not 1 <= a.index <= len(doc["orders"]):
                raise DataError("Order index out of range")
            o = doc["orders"][a.index - 1]
            saved = get("risk")
            if saved["context"] != report["context"]:
                raise DataError("Inputs changed since last risk check; run risk/show and review again")
            acct = get("account")
            if a.action == "approve":
                approval = trading.approve(o, saved, a.reply or "", a.now, cfg["risk_ttl_seconds"])
                acct.setdefault("approvals", {})[digest(o)] = approval
                put("account", acct)
                return approval
            approval = acct.get("approvals", {}).get(digest(o))
            if not approval or a.fill_price is None:
                raise DataError("Requires exact approval and --fill-price")
            # Both current and saved risk must pass; current check catches session/quote expiry.
            trading.approve(o, report, approval["reply"], a.now, cfg["risk_ttl_seconds"])
            updated, newevents = trading.paper_fill(o, approval, saved, portfolio, events, a.fill_price, a.now, cfg["risk_ttl_seconds"], prices)
            acct["portfolio"], acct["events"] = updated, newevents["events"]
            acct["approvals"].pop(digest(o))
            put("account", acct)
            return {"paper_fill": acct["events"][-1], "cash_inr": updated["cash_inr"]}
    if a.cmd == "tax":
        if a.action == "report":
            if not a.input:
                raise DataError("tax report requires --input complete normalized trade ledger")
            return tax.ledger_report(rows(a.input), a.fy)
        return tax.harvest(get("account")["portfolio"].get("lots", []), get("prices"), timestamp(a.now).date().isoformat(), a.min_loss)
    if a.cmd == "alerts":
        cfg = config(get("config"))
        cal = get("calendar") if (ws / "calendar.json").exists() else None
        result, newstate = alerts.evaluate(get("alerts")["rules"], get("prices"), state("alerts-state"), a.now, cfg["max_quote_age_seconds"], cal)
        put("alerts-state", newstate)
        return result
    raise DataError("Unsupported command")


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        result = run(a)
        if a.out:
            write(a.out, result)
        print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        return 1 if result.get("blocked") or result.get("errors") else 0
    except (DataError, OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        from .brokers.transport import BrokerError
        message = str(exc)
        if a.cmd == "connections" and not isinstance(exc, BrokerError):
            message = "Invalid local input or broker response; check the documented schema and connection setup"
        print(json.dumps({"error": message}, ensure_ascii=True), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print(json.dumps({"error": "Operation cancelled"}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
