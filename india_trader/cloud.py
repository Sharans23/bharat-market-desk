"""Single-owner HTTPS deployment of the existing engine. Run with Gunicorn, one worker."""
import base64
from collections import deque
from datetime import timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, request, session, send_from_directory, redirect
from werkzeug.exceptions import HTTPException

from .core import ROOT, DataError
from .web import Application
from .brokers.credentials import ENV, validate
from .brokers.transport import BrokerError


class EncryptedVault:
    """Authenticated encrypted files on the mounted disk; no broker-token env overrides."""
    def __init__(self, root, secret):
        self.root = Path(root)
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be a generated secret of at least 32 characters")
        self.cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))

    def path(self, provider):
        if provider not in ENV: raise BrokerError("Unsupported broker")
        return self.root / (provider + ".fernet")

    def load(self, provider):
        path = self.path(provider)
        if not path.exists(): raise BrokerError("Broker is not connected. Open Connections and log in.")
        try:
            return validate(provider, json.loads(self.cipher.decrypt(path.read_bytes())))
        except (InvalidToken, ValueError, TypeError):
            raise BrokerError("Saved credentials cannot be decrypted. Check the server encryption key or reconnect.") from None

    def save(self, provider, values):
        path = self.path(provider)
        encrypted = self.cipher.encrypt(json.dumps(validate(provider, values)).encode())
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream: stream.write(encrypted)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def forget(self, provider): self.path(provider).unlink(missing_ok=True)

    def status(self, provider):
        return {"broker": provider, "environment": "absent", "encrypted_credentials_saved": self.path(provider).exists(), "authenticated": "not_checked"}


def create_app(settings=None):
    settings = dict(os.environ) if settings is None else dict(settings)
    origin = settings.get("PUBLIC_ORIGIN") or settings.get("RENDER_EXTERNAL_URL", "")
    parsed = urlsplit(origin)
    testing = settings.get("TESTING") is True
    if not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password or (parsed.scheme != "https" and not testing):
        raise ValueError("PUBLIC_ORIGIN or RENDER_EXTERNAL_URL must be the exact HTTPS application origin")
    origin = origin.rstrip("/")
    for key in ("APP_ACCESS_KEY", "SESSION_SIGNING_KEY", "CREDENTIAL_ENCRYPTION_KEY"):
        if len(settings.get(key, "")) < 32: raise ValueError(key + " must contain at least 32 random characters")
    root = Path(settings.get("APP_DATA_DIR", ""))
    if not root.is_absolute() or root.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("APP_DATA_DIR must be an absolute persistent directory outside the source checkout")
    if settings.get("PERSISTENT_STORAGE_CONFIRMED") != "true" and not testing:
        raise ValueError("Mount a persistent disk and set PERSISTENT_STORAGE_CONFIRMED=true")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine = Application(root / "ui", EncryptedVault(root / "credentials", settings["CREDENTIAL_ENCRYPTION_KEY"]), snapshot_dir=root / "snapshots")
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=settings["SESSION_SIGNING_KEY"], TESTING=testing,
        SESSION_COOKIE_NAME="__Host-bmd_session" if not testing else "bmd_session",
        SESSION_COOKIE_SECURE=not testing, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_PATH="/", PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=3_000_000, TRUSTED_HOSTS=[parsed.hostname])
    app.extensions["engine"] = engine
    attempts = deque()
    access_digest = hashlib.sha256(settings["APP_ACCESS_KEY"].encode()).digest()

    def clean():
        now = time.monotonic()
        with engine.lock:
            for sid in list(engine.pending):
                if engine.pending[sid]["expires"] < now: engine.pending.pop(sid, None)
            for sid in list(engine.sessions):
                if engine.sessions[sid]["expires"] < now:
                    engine.sessions.pop(sid, None)
                    engine.pending.pop(sid, None)
                    engine.auth_notice.pop(sid, None)
            while attempts and attempts[0] < now - 900: attempts.popleft()

    # The single Gunicorn worker owns ephemeral sessions/login flows. Never persist API secrets.
    if not testing:
        def janitor():
            while True:
                time.sleep(30)
                clean()
        threading.Thread(target=janitor, daemon=True, name="expired-login-cleanup").start()

    @app.before_request
    def guard():
        clean()
        if request.method == "OPTIONS": return jsonify(error="Cross-origin access is not enabled"), 403
        if request.method not in {"GET", "HEAD", "POST"}: return jsonify(error="Method not allowed"), 405
        if request.method == "POST" and request.headers.get("Origin") != origin:
            return jsonify(error="Request origin rejected"), 403
        public = request.path in {"/healthz", "/api/session", "/api/login"} or not request.path.startswith("/api/")
        record = engine.sessions.get(session.get("sid"))
        if not public and not record: return jsonify(error="Sign in to your private workspace", authentication_required=True), 401
        if request.method == "POST" and request.path != "/api/login":
            if not record or not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), record["csrf"]):
                return jsonify(error="Session expired. Sign in again."), 403
        if request.path.startswith("/api/") and request.method == "GET" and request.headers.get("X-Requested-With") != "IndiaTrader":
            return jsonify(error="Open this service through the application"), 403

    @app.after_request
    def secure(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if not testing: response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error="Request rejected"), exc.code
        body = request.get_json(silent=True)
        body = body if isinstance(body, dict) else {}
        sensitive = request.path.startswith("/api/auth") or (request.path == "/api/action" and str(body.get("action", "")).startswith("connection_"))
        safe = isinstance(exc, BrokerError) or (isinstance(exc, DataError) and not sensitive)
        return jsonify(error=str(exc) if safe else "Request failed. Check the input, broker connection and available server storage."), 400

    @app.get("/healthz")
    def health():
        if not (engine.assets / "index.html").is_file(): return jsonify(status="ui_missing"), 503
        return jsonify(status="ok", app="bharat-market-desk", version="1.3.0")

    @app.get("/api/session")
    def session_state():
        return jsonify(hosted=True, authentication_required=session.get("sid") not in engine.sessions)

    @app.post("/api/login")
    def login():
        body = request.get_json()
        if not isinstance(body, dict): return jsonify(error="Invalid login request"), 400
        supplied = body.get("access_key", "")
        if not isinstance(supplied, str) or len(supplied) > 1024: supplied = ""
        with engine.lock:
            if len(attempts) >= 20: return jsonify(error="Too many sign-in attempts. Try again in 15 minutes."), 429
            if not hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(), access_digest):
                attempts.append(time.monotonic())
                return jsonify(error="Invalid access key"), 401
            old = session.get("sid")
            engine.sessions.pop(old, None); engine.pending.pop(old, None)
            sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            engine.sessions[sid] = {"csrf": csrf, "expires": time.monotonic() + 12*3600}
            session.clear(); session["sid"] = sid; session.permanent = True
        return jsonify(authenticated=True, csrf=csrf)

    @app.post("/api/logout")
    def logout():
        with engine.lock:
            sid = session.get("sid")
            engine.sessions.pop(sid, None); engine.pending.pop(sid, None); engine.auth_notice.pop(sid, None)
            session.clear()
        return jsonify(signed_out=True)

    @app.get("/api/bootstrap")
    def bootstrap():
        with engine.lock:
            result = engine.bootstrap(request.args.get("workspace", "practice"), session["sid"])
            result.update(csrf=engine.sessions[session["sid"]]["csrf"], hosted=True, version="1.3.0", public_origin=origin)
        return jsonify(result)

    @app.get("/api/docs")
    def docs():
        name = request.args.get("name", "schemas")
        if name not in {"schemas", "brokers", "operations", "tax", "sources", "ui", "hosting"}: raise DataError("Unknown guide")
        return jsonify(text=(ROOT / "docs" / (name + ".md")).read_text(encoding="utf-8"))

    @app.post("/api/<path:route>")
    def operation(route):
        if route == "shutdown": return jsonify(error="Server shutdown is available only in the local application"), 403
        return jsonify(engine.post("/api/" + route, request.get_json(), session["sid"]))

    @app.get("/kite/callback")
    def callback():
        sid = session.get("sid")
        if sid not in engine.sessions:
            return redirect("/?login=expired#brokers", code=303)
        try:
            if len(request.args.getlist("request_token")) != 1 or len(request.args.getlist("it_state")) != 1:
                raise BrokerError("Incomplete broker login response. Start again from Connections.")
            with engine.lock: engine.login_finish(request.args.to_dict(), sid, callback=True)
            engine.auth_notice[sid] = {"ok": True, "message": "Kite connected. Refresh account to load your portfolio."}
        except Exception as exc:
            engine.auth_notice[sid] = {"ok": False, "message": str(exc) if isinstance(exc, BrokerError) else "Broker login failed. Start again from Connections."}
        return redirect("/#brokers", code=303)

    @app.get("/")
    def index(): return send_from_directory(engine.assets, "index.html")

    @app.get("/assets/<path:name>")
    def assets(name): return send_from_directory(engine.assets / "assets", name)

    return app
