"""Local React application server. No shell commands and no live order submission."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
import time
import tempfile
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

from . import cli
from .core import ROOT, DataError, config, read, write, timestamp
from .brokers import ADAPTERS, connect
from .brokers.adapters import Kite
from .brokers.credentials import Vault, data_home, validate
from .brokers.transport import BrokerError

SIMULATION = "2026-10-26T10:00:00+05:30"
DOCUMENTS = {"account", "config", "targets", "prices", "instruments", "orders", "rules", "alerts", "metrics", "calendar"}
EXAMPLES = {p.stem: p for p in (ROOT / "examples").glob("*.json")}
# Every existing service is exposed through a fixed operation, not arbitrary CLI arguments.
ACTIONS = {
    "budget": (["budget"], {}, {}),
    "intraday": (["intraday"], {"symbol": None, "entry": "--entry", "stop": "--stop"}, {}),
    "risk": (["risk"], {}, {}),
    "tickets": (["broker", "show"], {}, {}),
    "approve": (["broker", "approve"], {"index": "--index", "reply": "--reply"}, {}),
    "fill": (["broker", "fill"], {"index": "--index", "fill_price": "--fill-price"}, {}),
    "log": (["broker", "log"], {}, {}),
    "quote": (["quote"], {"symbols": None}, {}),
    "clock": (["clock"], {"exchange": "--exchange", "cas": "--cas"}, {}),
    "news": (["news"], {"symbols": None, "input": "--input", "hours": "--hours"}, {"input": True}),
    "filings": (["filings"], {"kind": None, "symbols": None, "start": "--start", "end": "--end"}, {}),
    "disclosures": (["disclosures"], {"input": None}, {"input": True}),
    "copycat": (["copycat"], {"input": None, "previous": "--previous", "top": "--top"}, {"input": True, "previous": True}),
    "analyst": (["analyst"], {"input": None}, {"input": True}),
    "screen": (["screen"], {"input": "--input", "rules": "--rules"}, {"input": True, "rules": True}),
    "tax_report": (["tax", "report"], {"input": "--input", "fy": "--fy"}, {"input": True}),
    "tax_harvest": (["tax", "harvest"], {"min_loss": "--min-loss"}, {}),
    "alerts": (["alerts"], {}, {}),
    "rebalance": (["rebalance"], {"band": "--band"}, {}),
    "charges": (["charges"], {"turnover": None, "side": "--side", "product": "--product"}, {}),
}
for _action in ("status", "sync", "report", "quotes", "preview", "instruments", "history", "trades", "forget"):
    _fields = {"provider": None}
    if _action == "quotes":
        _fields.update(symbols=None, mapping="--mapping", publish="--publish")
    if _action == "preview":
        _fields.update(index="--index", mapping="--mapping")
    if _action == "history":
        _fields.update(instrument_token="--instrument-token", interval="--interval", start="--start", end="--end")
    ACTIONS["connection_" + _action] = (["connections", _action], _fields, {"mapping": True})


class Application:
    def __init__(self, home=None, vault=None, snapshot_dir=None):
        self.home = Path(home) if home else data_home() / "ui"
        self.vault = vault or Vault()
        self.snapshot_dir = snapshot_dir
        self.lock = threading.RLock()
        self.pending = {}
        self.sessions = {}
        self.auth_notice = {}
        self.assets = ROOT / "ui/dist"

    def workspace(self, name):
        if name not in {"practice", "research"}:
            raise DataError("Choose Practice or Research workspace")
        ws = self.home / "workspaces" / name
        if not ws.exists():
            ws.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=ws.parent, prefix="initializing-") as staging:
                staged = Path(staging) / name
                cli.run(cli.parser().parse_args(["--workspace", str(staged), "init"]))
                if name == "research":
                    write(staged / "account.json", {"portfolio": {"currency": "INR", "cash_inr": 0, "positions": [], "lots": [], "trading_date": timestamp().date().isoformat(), "daily_pnl_inr": 0, "day_start_equity_inr": 0}, "events": [], "approvals": {}})
                    for key, value in {"targets": {"weights": []}, "prices": {"quotes": {}}, "instruments": {"as_of": timestamp().date().isoformat(), "instruments": {}}, "alerts": {"rules": []}}.items():
                        write(staged / (key + ".json"), value)
                os.replace(staged, ws)
        return ws

    def files(self):
        result = [{"id": "example:" + key, "name": key.replace("-", " ") + " · synthetic example"} for key in EXAMPLES]
        folder = self.home / "uploads"
        if folder.exists():
            for path in sorted(folder.glob("*.meta.json")):
                result.append(read(path))
        return result

    def file_path(self, reference):
        if not isinstance(reference, str):
            raise DataError("Select an uploaded file or example")
        if reference.startswith("example:") and reference[8:] in EXAMPLES:
            return EXAMPLES[reference[8:]]
        if re.fullmatch(r"upload:[a-f0-9]{32}\.(json|csv)", reference):
            path = self.home / "uploads" / reference[7:]
            if path.is_file():
                return path
        raise DataError("File is not available. Upload it in Data workspace.")

    def bootstrap(self, workspace, session):
        ws = self.workspace(workspace)
        documents = {name: read(ws / (name + ".json")) for name in DOCUMENTS if (ws / (name + ".json")).exists()}
        return {"app": "india-trader", "version": "1.2.0", "workspace": workspace, "documents": documents,
                "files": self.files(), "brokers": [self.vault.status(name) for name in ADAPTERS],
                "simulation_time": SIMULATION, "server_time": timestamp().isoformat(), "actions": list(ACTIONS),
                "auth_notice": self.auth_notice.pop(session, None), "live_orders": False}

    def execute(self, body):
        action = body.get("action")
        if action not in ACTIONS:
            raise DataError("Unsupported service")
        ws = self.workspace(body.get("workspace", "practice"))
        params = body.get("params", {})
        if not isinstance(params, dict):
            raise DataError("Invalid service parameters")
        base, fields, files = ACTIONS[action]
        if set(params) - set(fields):
            raise DataError("Unexpected service parameter")
        argv = ["--workspace", str(ws)]
        if body.get("simulation"):
            if body.get("workspace", "practice") != "practice":
                raise DataError("Simulation clock is available only in Practice")
            if not action.startswith("connection_"):
                argv += ["--now", SIMULATION]
        argv += base
        for key, flag in fields.items():
            value = params.get(key)
            if value is None or value == "" or value is False:
                continue
            if key == "publish":
                if value is not True:
                    raise DataError("Publish must be a boolean")
                argv.append(flag)
                continue
            if flag:
                argv.append(flag)
            if key in files:
                argv.append(str(self.file_path(value)))
            elif key == "symbols":
                if not isinstance(value, str):
                    raise DataError("Enter exchange-qualified symbols")
                symbols = value.replace(",", " ").split()
                if len(symbols) > 50:
                    raise DataError("Use at most 50 symbols")
                argv += symbols
            elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
                argv.append(str(value))
            else:
                raise DataError("Invalid field value")
        try:
            args = cli.parser().parse_args(argv)
        except SystemExit:
            raise DataError("Check required fields and valid parameter values") from None
        # UI uses the same vault as its authentication routes; injectable in tests.
        if action.startswith("connection_"):
            from .brokers import commands
            return commands.run(args, vault=self.vault, client_factory=lambda name: connect(name, self.vault.load(name)), snapshot_dir=self.snapshot_dir)
        return cli.run(args)

    def save_document(self, body):
        name, doc = body.get("name"), body.get("document")
        if name not in DOCUMENTS or not isinstance(doc, dict):
            raise DataError("Select a supported document containing a JSON object")
        if name == "config":
            config(doc)
        shapes = {"account": {"portfolio": dict, "events": list}, "targets": {"weights": list}, "prices": {"quotes": dict}, "instruments": {"instruments": dict}, "orders": {"orders": list}, "alerts": {"rules": list}, "metrics": {"companies": list}}
        for key, kind in shapes.get(name, {}).items():
            if not isinstance(doc.get(key), kind):
                raise DataError(f"{name} requires a {kind.__name__} field named {key}")
        if name == "account":
            doc["approvals"] = {}  # approvals can only be generated by the reviewed ticket flow
        ws = self.workspace(body.get("workspace", "practice"))
        with cli.account_lock(ws):
            write(ws / (name + ".json"), doc)
            if name != "account":
                account = read(ws / "account.json")
                account["approvals"] = {}
                write(ws / "account.json", account)
        return {"saved": name, "note": "Saved. Prior paper approvals cleared; run risk again before filling."}

    def upload(self, body):
        name, content = body.get("name", ""), body.get("content")
        suffix = Path(name).suffix.lower()
        if suffix not in {".json", ".csv"} or not isinstance(content, str) or len(content.encode()) > 2_000_000:
            raise DataError("Upload JSON or CSV up to 2 MB")
        if suffix == ".json":
            json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(DataError("Non-finite JSON")))
        token = secrets.token_hex(16) + suffix
        folder = self.home / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / token).write_text(content, encoding="utf-8")
        meta = {"id": "upload:" + token, "name": Path(name).name[:120]}
        write(folder / (token + ".meta.json"), meta)
        return meta

    def login_start(self, body, session):
        api_key, secret = body.get("api_key"), body.get("api_secret")
        validate("kite", {"api_key": api_key, "access_token": secret})
        state = secrets.token_urlsafe(32)
        # Only one outstanding flow per browser session; secrets stay in memory for 10 minutes.
        self.pending[session] = {"key": api_key, "secret": secret, "state": state, "expires": time.monotonic() + 600}
        return {"url": Kite.login_url(api_key) + "&" + urlencode({"redirect_params": urlencode({"it_state": state})}), "expires_seconds": 600}

    def login_finish(self, body, session, callback=False):
        flow = self.pending.get(session)
        if not flow or flow["expires"] < time.monotonic():
            self.pending.pop(session, None)
            raise BrokerError("Login expired or belongs to a different browser. Start Kite login again.")
        token = body.get("request_token", "")
        if not isinstance(token, str):
            raise BrokerError("Invalid login response")
        if token.startswith(("http://", "https://")):
            query = parse_qs(urlsplit(token).query)
            token = query.get("request_token", [""])[0]
            supplied_state = query.get("it_state", [None])[0]
        else:
            supplied_state = body.get("it_state")
        if (callback or supplied_state is not None) and supplied_state != flow["state"]:
            raise BrokerError("Login state did not match. Start again in this browser.")
        self.pending.pop(session, None)  # consume even on a failed exchange
        values = Kite.exchange(flow["key"], flow["secret"], token)
        result = connect("kite", values).profile_summary()
        self.vault.save("kite", values)
        result["note"] = "Kite connected. Refresh account to fetch your holdings and funds."
        return result

    def token_connect(self, body):
        provider = body.get("provider")
        values = validate(provider, body.get("credentials", {}))
        result = connect(provider, values).profile_summary()
        self.vault.save(provider, values)
        return result

    def post(self, path, body, session):
        if not isinstance(body, dict):
            raise DataError("Request must be a JSON object")
        with self.lock:
            if path == "/api/action": return self.execute(body)
            if path == "/api/document": return self.save_document(body)
            if path == "/api/upload": return self.upload(body)
            if path == "/api/auth/kite/start": return self.login_start(body, session)
            if path == "/api/auth/kite/finish": return self.login_finish(body, session)
            if path == "/api/auth/token": return self.token_connect(body)
            if path == "/api/auth/cancel":
                self.pending.pop(session, None)
                return {"cancelled": True}
        raise DataError("Unknown endpoint")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, app):
        self.app = app
        super().__init__(address, Handler)

    def service_actions(self):
        # Remove expired login secrets even when the browser stops making requests.
        if self.app.lock.acquire(blocking=False):
            try:
                for sid in list(self.app.pending):
                    if self.app.pending[sid]["expires"] < time.monotonic():
                        self.app.pending.pop(sid, None)
            finally:
                self.app.lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "IndiaTrader"
    def log_message(self, *args): pass  # callback URLs and request bodies must never be logged

    def send(self, status, payload, content_type="application/json", cookie=None, location=None):
        raw = json.dumps(payload, allow_nan=False).encode() if content_type == "application/json" else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie: self.send_header("Set-Cookie", cookie)
        if location: self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(raw)

    def allowed_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def session(self, create=False):
        cookies = SimpleCookie()
        try: cookies.load(self.headers.get("Cookie", ""))
        except Exception: pass
        sid = cookies["it_session"].value if "it_session" in cookies else None
        app = self.server.app
        now = time.monotonic()
        for key in list(app.sessions):
            if app.sessions[key]["expires"] < now:
                app.sessions.pop(key, None)
                app.pending.pop(key, None)
        for key in list(app.pending):
            if app.pending[key]["expires"] < now:
                app.pending.pop(key, None)
        if sid not in app.sessions:
            if not create: return None, None
            sid = secrets.token_urlsafe(32)
            app.sessions[sid] = {"csrf": secrets.token_urlsafe(32), "expires": now + 12 * 3600}
        return sid, app.sessions[sid]

    def do_GET(self):
        if not self.allowed_host(): return self.send(403, {"error": "Local host only"})
        parsed = urlsplit(self.path)
        app = self.server.app
        try:
            if parsed.path in {"/kite/callback", "/"} and "request_token" in parse_qs(parsed.query):
                sid, session = self.session()
                try:
                    if not session: raise BrokerError("Open the app and start Kite login in this browser first.")
                    query = parse_qs(parsed.query)
                    with app.lock:
                        app.login_finish({k: v[0] for k, v in query.items()}, sid, callback=True)
                    app.auth_notice[sid] = {"ok": True, "message": "Kite connected. Refresh account to load your portfolio."}
                except Exception as exc:
                    if sid: app.auth_notice[sid] = {"ok": False, "message": str(exc) if isinstance(exc, BrokerError) else "Kite login failed. Start again from Connections."}
                return self.send(303, b"", "text/plain", location="/#brokers")
            if parsed.path.startswith("/api/"):
                if self.headers.get("X-Requested-With") != "IndiaTrader":
                    return self.send(403, {"error": "Open this service through the app"})
                sid, session = self.session(create=True)
                query = parse_qs(parsed.query)
                with app.lock:
                    if parsed.path == "/api/bootstrap":
                        result = app.bootstrap(query.get("workspace", ["practice"])[0], sid)
                        result["csrf"] = session["csrf"]
                    elif parsed.path == "/api/docs":
                        name = query.get("name", ["schemas"])[0]
                        if name not in {"schemas", "brokers", "operations", "tax", "sources", "ui"}: raise DataError("Unknown guide")
                        result = {"text": (ROOT / "docs" / (name + ".md")).read_text(encoding="utf-8")}
                    else: return self.send(404, {"error": "Unknown endpoint"})
                return self.send(200, result, cookie=f"it_session={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200")
            relative = parsed.path.lstrip("/") or "index.html"
            path = (app.assets / relative).resolve()
            if not path.is_relative_to(app.assets.resolve()) or not path.is_file():
                return self.send(404, b"Page not found. Open the app home page.", "text/plain")
            mime = {".js": "text/javascript", ".css": "text/css", ".html": "text/html; charset=utf-8"}.get(path.suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            return self.send(200, path.read_bytes(), mime)
        except Exception as exc:
            return self.send(400, {"error": str(exc) if isinstance(exc, DataError) else "Unable to load data. Check your workspace files."})

    def do_POST(self):
        if not self.allowed_host(): return self.send(403, {"error": "Local host only"})
        origin = self.headers.get("Origin")
        if origin != "http://" + self.headers.get("Host", ""):
            return self.send(403, {"error": "Request origin rejected"})
        sid, session = self.session()
        if not session or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            return self.send(403, {"error": "Session expired. Reload the app."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 3_000_000: raise DataError("Request size exceeds 3 MB")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json": raise DataError("JSON required")
            body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(DataError("Non-finite JSON")))
            if urlsplit(self.path).path == "/api/shutdown":
                self.send(200, {"stopped": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            result = self.server.app.post(urlsplit(self.path).path, body, sid)
            return self.send(200, result)
        except Exception as exc:
            # Broker responses/credentials can contain sensitive strings. Never return raw unexpected exceptions.
            sensitive = self.path.startswith("/api/auth") or (isinstance(locals().get("body"), dict) and str(body.get("action", "")).startswith("connection_"))
            safe = isinstance(exc, BrokerError) or (isinstance(exc, DataError) and not sensitive)
            return self.send(400, {"error": str(exc) if safe else "Request failed. Check the input, broker session and API subscription, then retry."})


def main():
    p = argparse.ArgumentParser(description="India Trader local application")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true")
    p.add_argument("--data-dir", type=Path)
    args = p.parse_args()
    app = Application(args.data_dir)
    if not (app.assets / "index.html").exists():
        raise SystemExit("UI build missing. Use the packaged release, or run npm install and npm run build in ui/.")
    url = f"http://127.0.0.1:{args.port}"
    try:
        server = Server(("127.0.0.1", args.port), app)
    except OSError:
        # Open only if the occupied port is already serving this app.
        import urllib.request
        try:
            req = urllib.request.Request(url + "/api/bootstrap", headers={"X-Requested-With": "IndiaTrader"})
            with urllib.request.urlopen(req, timeout=3) as r: existing = json.load(r)
            if existing.get("app") != "india-trader": raise ValueError()
            if args.open: webbrowser.open(url)
            return
        except Exception:
            raise SystemExit("Port is occupied by another service. Choose a different port.") from None
    if args.open: threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__": main()
