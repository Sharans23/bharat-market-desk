"""Local credential setup. Windows DPAPI encryption; environment variables elsewhere."""
import ctypes
from ctypes import wintypes
import getpass
import json
import os
from pathlib import Path
import tempfile
from .transport import BrokerError

ENV = {
    "kite": {"api_key": "KITE_API_KEY", "access_token": "KITE_ACCESS_TOKEN"},
    "dhan": {"client_id": "DHAN_CLIENT_ID", "access_token": "DHAN_ACCESS_TOKEN"},
    "groww": {"access_token": "GROWW_ACCESS_TOKEN"},
}


def data_home():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "IndiaTrader"
    return Path.home() / ".local/share/india-trader"


def validate(broker, values):
    if broker not in ENV:
        raise BrokerError("Unknown broker")
    result = {}
    for key in ENV[broker]:
        value = values.get(key)
        if not isinstance(value, str) or not value.strip() or any(c.isspace() for c in value) or len(value) > 16384:
            raise BrokerError(f"Missing or invalid {ENV[broker][key]}; run connections connect {broker}")
        result[key] = value
    return result


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def dpapi(data, decrypt=False):
    if os.name != "nt":
        raise BrokerError("Encrypted persistent credentials are supported on Windows; use environment variables on this OS")
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buf), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise BrokerError("Windows could not protect/unprotect credentials for this user")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(target.pbData)


class Vault:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_home() / "credentials"

    def path(self, broker):
        if broker not in ENV:
            raise BrokerError("Unknown broker")
        return self.root / (broker + ".dpapi")

    def load(self, broker):
        names = ENV[broker]
        present = {key: os.environ.get(env) for key, env in names.items()}
        if any(present.values()):
            # Never combine a partial environment account with a different saved account.
            return validate(broker, present)
        path = self.path(broker)
        if not path.exists():
            raise BrokerError(f"{broker} is not configured; run connections connect {broker}")
        try:
            return validate(broker, json.loads(dpapi(path.read_bytes(), decrypt=True)))
        except (ValueError, UnicodeError):
            raise BrokerError("Saved credentials are invalid; reconnect") from None

    def save(self, broker, values):
        blob = dpapi(json.dumps(validate(broker, values)).encode())
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(blob)
            os.replace(temp, self.path(broker))
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def forget(self, broker):
        self.path(broker).unlink(missing_ok=True)

    def status(self, broker):
        values = [bool(os.environ.get(env)) for env in ENV[broker].values()]
        return {"broker": broker, "environment": "complete" if all(values) else "partial" if any(values) else "absent",
                "encrypted_credentials_saved": self.path(broker).exists(), "authenticated": "not_checked"}


def prompt_secret(label):
    import sys
    if not sys.stdin.isatty():
        raise BrokerError("Run interactive connection in a local terminal; do not pipe credentials or paste them into chat")
    return getpass.getpass(label + ": ").strip()
