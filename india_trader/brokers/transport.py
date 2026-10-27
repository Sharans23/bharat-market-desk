"""Bounded HTTPS broker transport. Auth and reads only; order mutations are absent."""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from ..core import DataError


class BrokerError(DataError):
    """Safe-to-display error; never includes response bodies, tokens or request URLs."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BrokerError("Broker redirect refused; credentials were not forwarded")


ROUTES = {
    "kite": ("https://api.kite.trade", {
        "GET": [r"/user/profile", r"/user/margins/equity", r"/portfolio/holdings", r"/portfolio/positions", r"/orders", r"/trades", r"/quote", r"/instruments/NSE", r"/instruments/historical/[0-9]+/(?:minute|3minute|5minute|10minute|15minute|30minute|60minute|day)"],
        "POST": [r"/session/token"],
    }),
    "dhan": ("https://api.dhan.co/v2", {
        "GET": [r"/profile", r"/fundlimit", r"/holdings", r"/positions", r"/orders", r"/trades"],
        "POST": [r"/marketfeed/quote"],
    }),
    "groww": ("https://api.groww.in/v1", {
        "GET": [r"/user/detail", r"/margins/detail/user", r"/holdings/user", r"/positions/user", r"/order/list", r"/live-data/quote"],
        "POST": [],
    }),
}


class Transport:
    def __init__(self, broker, opener=None, pause=1.05):
        if broker not in ROUTES:
            raise BrokerError("Unsupported broker")
        self.broker = broker
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.pause, self.last = pause, 0

    def request(self, method, path, headers, query=None, body=None, form=False, text=False):
        base, routes = ROUTES[self.broker]
        if not any(re.fullmatch(pattern, path) for pattern in routes.get(method, [])):
            raise BrokerError("Endpoint not allowed by this account/data connector")
        url = base + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        h = {"Accept": "application/json", "User-Agent": "IndiaTrader/1.1", **headers}
        data = None
        if body is not None:
            data = (urllib.parse.urlencode(body) if form else json.dumps(body, allow_nan=False)).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        delay = self.pause - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        try:
            request = urllib.request.Request(url, data=data, headers=h, method=method)
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise BrokerError("Broker response exceeds size limit")
            if text:
                return raw.decode("utf-8-sig")
            return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except urllib.error.HTTPError as exc:
            message = {400: "Request rejected; check broker instrument/parameters", 401: "Authentication expired or invalid; reconnect", 403: "Access denied; check API permissions/subscription", 429: "Rate limited; wait before another request"}.get(exc.code, "Broker service error")
            raise BrokerError(f"{self.broker}: {message} (HTTP {exc.code})") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise BrokerError(f"{self.broker}: Network request failed; no automatic retry") from None
        except (ValueError, UnicodeError):
            raise BrokerError(f"{self.broker}: Invalid response format") from None
        finally:
            self.last = time.monotonic()
