"""Broker connection CLI, private snapshots and opt-in paper quote publication."""
from pathlib import Path
import os
import webbrowser
from urllib.parse import parse_qs, urlparse
from . import ADAPTERS, connect
from .adapters import Kite
from .credentials import ENV, Vault, data_home, prompt_secret
from .transport import BrokerError
from ..core import read, write, timestamp


def add_parser(sub):
    root = sub.add_parser("connections", help="Connect Kite/Dhan/Groww accounts and read broker data")
    commands = root.add_subparsers(dest="connection_action", required=True)
    commands.add_parser("list", help="Show saved credential presence; does not log in")
    for action in ("connect", "status", "sync", "forget", "quotes", "preview", "instruments", "history", "trades", "report"):
        p = commands.add_parser(action)
        p.add_argument("provider", choices=sorted(ADAPTERS))
        if action == "connect":
            p.add_argument("--existing-token", action="store_true", help="Enter an already-issued token locally instead of Kite login exchange")
            p.add_argument("--no-browser", action="store_true", help="Print the official login URL instead of opening it")
        if action in ("quotes", "preview"):
            p.add_argument("--mapping", help="Verified broker ID map JSON (required for Dhan)")
        if action == "quotes":
            p.add_argument("symbols", nargs="+")
            p.add_argument("--publish", action="store_true", help="Also replace workspace prices.json for paper planning; fails if any symbol missing")
        if action == "preview":
            p.add_argument("--index", type=int, default=1)
        if action == "history":
            p.add_argument("--instrument-token", required=True)
            p.add_argument("--interval", default="day")
            p.add_argument("--start", required=True)
            p.add_argument("--end", required=True)


def interactive_connect(provider, existing_token=False, no_browser=False, vault=None):
    if os.name != "nt":
        raise BrokerError("Interactive encrypted setup currently supports Windows; use documented environment variables on this OS")
    vault = vault or Vault()
    if provider == "kite" and not existing_token:
        api_key = prompt_secret("Kite API key")
        api_secret = prompt_secret("Kite API secret (used for this login only, not saved)")
        url = Kite.login_url(api_key)
        print("Complete Zerodha login and 2FA in your browser. Then copy the request_token or full redirect URL into the hidden prompt.")
        if no_browser or not webbrowser.open(url):
            print(url)
        reply = prompt_secret("Kite request_token or redirect URL")
        if reply.startswith(("http://", "https://")):
            tokens = parse_qs(urlparse(reply).query).get("request_token", [])
            if len(tokens) != 1:
                raise BrokerError("Redirect URL has no single request_token; repeat login")
            reply = tokens[0]
        values = Kite.exchange(api_key, api_secret, reply)
    else:
        values = {field: prompt_secret(name) for field, name in ENV[provider].items()}
    client = connect(provider, values)
    summary = client.profile_summary()  # do not persist credentials until authentication is checked
    vault.save(provider, values)
    return {**summary, "credentials_saved": "Windows DPAPI, current user, outside repository",
            "environment_overrides_saved_credentials": any(os.environ.get(name) for name in ENV[provider].values()),
            "note": "Broker API sessions expire. Reconnect on authentication failure. Environment variables take precedence over saved credentials. No orders submitted."}


def snapshot_path(provider):
    if provider not in ADAPTERS:
        raise BrokerError("Unsupported broker")
    return data_home() / "snapshots" / (provider + ".json")


def run(a, vault=None, client_factory=None, snapshot_dir=None):
    vault = vault or Vault()
    action = a.connection_action
    if a.now:
        raise BrokerError("--now is an offline simulation option; broker connections always use actual time")
    if action == "list":
        return {"brokers": [vault.status(name) for name in ADAPTERS], "live_order_submission": False}
    name = a.provider
    saved_snapshot = Path(snapshot_dir) / (name + ".json") if snapshot_dir else snapshot_path(name)
    if action == "connect":
        return interactive_connect(name, a.existing_token, a.no_browser)
    if action == "forget":
        vault.forget(name)
        return {"broker": name, "local_credentials_removed": True,
                "note": "Does not revoke the broker token, clear environment variables or erase account snapshots. Revoke active tokens in the broker portal if needed."}
    if action == "report":
        result = read(saved_snapshot)
        result["snapshot_age_seconds"] = round((timestamp() - timestamp(result["fetched_at"])).total_seconds())
        result["historical_snapshot"] = True
        return result
    client = client_factory(name) if client_factory else connect(name)
    if action == "status":
        return client.profile_summary()
    if action == "sync":
        snapshot = client.snapshot()
        write(saved_snapshot, snapshot)
        positions = snapshot["positions"]
        count = len(positions.get("net", [])) if isinstance(positions, dict) else len(positions)
        return {"broker": name, "account_ref": snapshot["account_ref"], "fetched_at": snapshot["fetched_at"],
                "holdings_rows": len(snapshot["holdings"]), "positions_rows": count, "order_rows": len(snapshot["orders"]),
                "saved_to": str(saved_snapshot), "paper_account_changed": False}
    if action == "quotes":
        mapping = read(a.mapping) if a.mapping else None
        result = client.quotes(a.symbols, mapping)
        if a.publish:
            if result["errors"] or not result["quotes"]:
                raise BrokerError("Incomplete quote snapshot; workspace prices were not replaced")
            # Last-trade timestamps stay intact; risk/alerts still enforce freshness.
            write(Path(a.workspace) / "prices.json", result)
            result["published_to_paper_workspace"] = True
        return result
    if action == "preview":
        doc = read(Path(a.workspace) / "orders.json")
        if not 1 <= a.index <= len(doc["orders"]):
            raise BrokerError("Order index out of range")
        return client.preview(doc["orders"][a.index - 1], read(a.mapping) if a.mapping else None)
    if action not in client.capabilities:
        raise BrokerError(f"{action} is not implemented for {name}; supported: {', '.join(client.capabilities)}")
    if action == "instruments":
        return client.instruments()
    if action == "history":
        return client.history(a.instrument_token, a.interval, a.start, a.end)
    if action == "trades":
        return {"broker": name, "fetched_at": timestamp().isoformat(), "trades": client.trades()}
    raise BrokerError("Unknown connection action")
