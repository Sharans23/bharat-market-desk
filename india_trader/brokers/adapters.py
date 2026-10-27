"""Official REST adapters with injectable transport for offline contract tests."""
import csv
from datetime import datetime
import hashlib
import io
from urllib.parse import urlencode
from ..core import IST, DataError, digest, integer, money, number, positive, symbol, timestamp
from ..trading import validate_order
from .credentials import validate
from .transport import BrokerError, Transport


def require_dict(value):
    if not isinstance(value, dict):
        raise BrokerError("Broker response schema changed: expected object")
    return value


def require_list(value):
    if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
        raise BrokerError("Broker response schema changed: expected row list")
    return value


def broker_time(value, broker):
    if value is None or value == "":
        raise BrokerError("Quote has no provider timestamp")
    try:
        if broker == "groww":
            out = datetime.fromtimestamp(float(positive(value)) / 1000, IST)
        else:
            try:
                out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                out = datetime.strptime(value, "%d/%m/%Y %H:%M:%S")
            if out.tzinfo is None:
                out = out.replace(tzinfo=IST)  # broker's documented exchange-local timestamps
        if out.year < 2000:
            raise ValueError()
        return out.astimezone(IST).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        raise BrokerError("Quote has an invalid or sentinel provider timestamp") from None


def normalized_quote(row, broker):
    return {"price": money(positive(row["last_price"], "broker price")), "currency": "INR",
            "as_of": broker_time(row.get("last_trade_time"), broker), "source": broker + " official quote API",
            "timestamp_basis": "last_trade_time", "execution_grade": False,
            "lower_band": row.get("lower_circuit_limit"), "upper_band": row.get("upper_circuit_limit")}


def nse_keys(keys):
    if not keys or len(keys) > 50:
        raise BrokerError("Request 1..50 NSE equity symbols")
    out = list(dict.fromkeys(symbol(k) for k in keys))
    if any(not k.startswith("NSE:") for k in out):
        raise BrokerError("This connector quote/payload scope is NSE cash equity")
    return out


class Adapter:
    name = ""
    capabilities = ("profile", "funds", "holdings", "positions", "orders", "quotes", "preview")

    def __init__(self, credentials, transport=None):
        self.credentials = validate(self.name, credentials)
        self.transport = transport or Transport(self.name)

    def call(self, method, path, **kwargs):
        return self.unwrap(self.transport.request(method, path, self.headers(), **kwargs))

    def account_identity(self, profile):
        raise NotImplementedError

    def profile_summary(self):
        p = self.profile()
        identity = self.account_identity(p)
        if not identity:
            raise BrokerError("Broker profile is missing account identity")
        return {"broker": self.name, "account_ref": digest([self.name, str(identity)])[:16],
                "authenticated": True, "checked_at": timestamp().isoformat(), "capabilities": list(self.capabilities)}

    def snapshot(self):
        # Reads are sequential snapshots, not a transaction-consistent broker ledger.
        started = timestamp().isoformat()
        profile = self.profile_summary()
        funds, holdings, positions, orders = self.funds(), self.holdings(), self.positions(), self.orders()
        return {**profile, "started_at": started, "fetched_at": timestamp().isoformat(),
                "funds": funds, "holdings": holdings, "positions": positions, "orders": orders,
                "read_only": True, "complete": True,
                "note": "Broker holdings, positions and funds retain their own semantics. Not merged into the paper ledger or assumed to be settled cash/FIFO lots."}

    def quote_result(self, keys, fetch):
        quotes, errors = {}, {}
        for key in keys:
            try:
                quotes[key] = normalized_quote(fetch(key), self.name)
            except (DataError, KeyError, TypeError) as exc:
                errors[key] = str(exc) if isinstance(exc, BrokerError) else "Invalid or missing broker quote fields"
        return {"broker": self.name, "fetched_at": timestamp().isoformat(), "quotes": quotes, "errors": errors}

    def preview(self, order, mapping=None):
        validate_order(order)
        nse_keys([order["symbol"]])
        payload = self.order_payload(order, mapping)
        return {"broker": self.name, "order": order, "payload": payload,
                "fingerprint": digest([self.name, payload]), "submitted": False,
                "readiness": "FORMAT_ONLY", "note": "Payload preview only. No live risk approval, protective stop or submission. Reconcile broker funds/holdings and current broker charges before any live action."}


class Kite(Adapter):
    name = "kite"
    capabilities = Adapter.capabilities + ("instruments", "history", "trades", "login_exchange")

    def headers(self):
        return {"X-Kite-Version": "3", "Authorization": "token " + self.credentials["api_key"] + ":" + self.credentials["access_token"]}

    def unwrap(self, doc):
        if require_dict(doc).get("status") != "success" or "data" not in doc:
            raise BrokerError("Kite rejected request; reconnect or check subscription/parameters")
        return doc["data"]

    @staticmethod
    def login_url(api_key):
        validate("kite", {"api_key": api_key, "access_token": "unused"})
        return "https://kite.zerodha.com/connect/login?" + urlencode({"v": "3", "api_key": api_key})

    @staticmethod
    def exchange(api_key, api_secret, request_token, transport=None):
        for value in (api_key, api_secret, request_token):
            if not value or any(c.isspace() for c in value):
                raise BrokerError("Invalid login values")
        checksum = hashlib.sha256((api_key + request_token + api_secret).encode()).hexdigest()
        doc = (transport or Transport("kite")).request("POST", "/session/token", {"X-Kite-Version": "3"},
            body={"api_key": api_key, "request_token": request_token, "checksum": checksum}, form=True)
        if require_dict(doc).get("status") != "success":
            raise BrokerError("Kite token exchange failed; repeat broker login")
        return validate("kite", {"api_key": api_key, "access_token": require_dict(doc.get("data")).get("access_token")})

    def account_identity(self, p):
        return p.get("user_id")

    def profile(self):
        return require_dict(self.call("GET", "/user/profile"))

    def funds(self):
        return require_dict(self.call("GET", "/user/margins/equity"))

    def holdings(self):
        return require_list(self.call("GET", "/portfolio/holdings"))

    def positions(self):
        result = require_dict(self.call("GET", "/portfolio/positions"))
        require_list(result.get("net")); require_list(result.get("day"))
        return result

    def orders(self):
        return require_list(self.call("GET", "/orders"))

    def trades(self):
        return require_list(self.call("GET", "/trades"))

    def quotes(self, keys, mapping=None):
        keys = nse_keys(keys)
        raw = require_dict(self.call("GET", "/quote", query={"i": keys}))
        return self.quote_result(keys, lambda k: raw[k])

    def instruments(self):
        raw = self.transport.request("GET", "/instruments/NSE", self.headers(), text=True)
        reader = csv.DictReader(io.StringIO(raw))
        required = {"instrument_token", "tradingsymbol", "exchange", "instrument_type", "tick_size", "lot_size"}
        if not required.issubset(reader.fieldnames or []):
            raise BrokerError("Unexpected Kite instrument CSV schema")
        out = {}
        for r in reader:
            if r["exchange"] != "NSE" or r["instrument_type"] != "EQ":
                continue
            key = symbol("NSE:" + r["tradingsymbol"])
            if key in out:
                raise BrokerError("Ambiguous instrument mapping")
            out[key] = {"kite": {"instrument_token": integer(r["instrument_token"]), "tradingsymbol": r["tradingsymbol"]},
                        "tick_size": float(positive(r["tick_size"])), "lot_size": integer(r["lot_size"])}
        return {"broker": self.name, "as_of": timestamp().date().isoformat(), "instruments": out,
                "note": "Identifier/tick map only. EQ may include ETFs; series, surveillance, CAS and intraday eligibility are not supplied here."}

    def history(self, token, interval, start, end):
        token = integer(token, "instrument_token")
        start_dt, end_dt = timestamp(start), timestamp(end)
        if start_dt >= end_dt or (end_dt - start_dt).total_seconds() > 30 * 86400:
            raise BrokerError("Use an ordered historical range of at most 30 days")
        if interval not in {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"}:
            raise BrokerError("Unsupported candle interval")
        raw = require_dict(self.call("GET", f"/instruments/historical/{token}/{interval}",
            query={"from": start_dt.strftime("%Y-%m-%d %H:%M:%S"), "to": end_dt.strftime("%Y-%m-%d %H:%M:%S"), "continuous": 0, "oi": 0}))
        candles = raw.get("candles")
        if not isinstance(candles, list):
            raise BrokerError("Missing historical candles")
        out = []
        for row in candles:
            if not isinstance(row, list) or len(row) < 6:
                raise BrokerError("Malformed candle")
            at = timestamp(row[0])
            if not start_dt <= at <= end_dt:
                raise BrokerError("Candle outside requested range")
            out.append({"at": at.isoformat(), "open": money(positive(row[1])), "high": money(positive(row[2])),
                        "low": money(positive(row[3])), "close": money(positive(row[4])), "volume": integer(row[5], minimum=0)})
        return {"broker": self.name, "instrument_token": token, "interval": interval, "candles": out}

    def order_payload(self, o, mapping=None):
        return {"tradingsymbol": o["symbol"].split(":")[1], "exchange": "NSE", "transaction_type": o["side"],
                "order_type": "LIMIT", "quantity": integer(o["quantity"]), "product": o["product"], "price": money(o["price"]), "validity": "DAY"}


class Dhan(Adapter):
    name = "dhan"
    capabilities = Adapter.capabilities + ("trades",)

    def headers(self):
        return {"access-token": self.credentials["access_token"], "client-id": self.credentials["client_id"]}

    def unwrap(self, doc):
        if isinstance(doc, dict) and (doc.get("errorCode") or doc.get("errorType") or doc.get("status") in ("failure", "failed", "error")):
            raise BrokerError("Dhan rejected request; reconnect or check access/parameters")
        return doc

    def account_identity(self, p):
        if str(p.get("dhanClientId", "")) != self.credentials["client_id"]:
            raise BrokerError("Dhan profile does not match configured client ID")
        return p["dhanClientId"]

    def profile(self):
        return require_dict(self.call("GET", "/profile"))

    def funds(self):
        return require_dict(self.call("GET", "/fundlimit"))

    def holdings(self):
        return require_list(self.call("GET", "/holdings"))

    def positions(self):
        return require_list(self.call("GET", "/positions"))

    def orders(self):
        return require_list(self.call("GET", "/orders"))

    def trades(self):
        return require_list(self.call("GET", "/trades"))

    @staticmethod
    def security_id(key, mapping):
        try:
            r = mapping["instruments"][key]["dhan"]
            if r["exchange_segment"] != "NSE_EQ":
                raise BrokerError("Dhan symbol requires an NSE_EQ mapping")
            return integer(r["security_id"], "Dhan security_id")
        except (KeyError, TypeError):
            raise BrokerError("Missing verified Dhan security-id mapping; supply --mapping") from None

    def quotes(self, keys, mapping=None):
        keys = nse_keys(keys)
        ids = {k: self.security_id(k, mapping) for k in keys}
        if len(set(ids.values())) != len(ids):
            raise BrokerError("Duplicate Dhan security IDs for different symbols")
        doc = require_dict(self.call("POST", "/marketfeed/quote", body={"NSE_EQ": list(ids.values())}))
        if doc.get("status") != "success":
            raise BrokerError("Dhan quote response unsuccessful")
        raw = require_dict(require_dict(doc.get("data")).get("NSE_EQ"))
        return self.quote_result(keys, lambda k: raw[str(ids[k])])

    def order_payload(self, o, mapping=None):
        return {"dhanClientId": self.credentials["client_id"], "transactionType": o["side"], "exchangeSegment": "NSE_EQ",
                "productType": "CNC" if o["product"] == "CNC" else "INTRADAY", "orderType": "LIMIT", "validity": "DAY",
                "securityId": str(self.security_id(o["symbol"], mapping)), "quantity": integer(o["quantity"]), "price": money(o["price"]), "afterMarketOrder": False}


class Groww(Adapter):
    name = "groww"

    def headers(self):
        return {"Authorization": "Bearer " + self.credentials["access_token"], "X-API-VERSION": "1.0"}

    def unwrap(self, doc):
        if require_dict(doc).get("status") != "SUCCESS" or "payload" not in doc:
            raise BrokerError("Groww rejected request; reconnect or check subscription/parameters")
        return doc["payload"]

    def account_identity(self, p):
        return p.get("ucc") or p.get("vendor_user_id")

    def profile(self):
        return require_dict(self.call("GET", "/user/detail"))

    def funds(self):
        return require_dict(self.call("GET", "/margins/detail/user"))

    def holdings(self):
        return require_list(require_dict(self.call("GET", "/holdings/user")).get("holdings"))

    def positions(self):
        return require_list(require_dict(self.call("GET", "/positions/user", query={"segment": "CASH"})).get("positions"))

    def orders(self):
        out, seen = [], set()
        for page in range(20):
            data = require_dict(self.call("GET", "/order/list", query={"segment": "CASH", "page": page, "page_size": 100}))
            batch = require_list(data.get("order_list"))
            if batch:
                fingerprint = digest(batch)
                if fingerprint in seen:
                    raise BrokerError("Groww pagination repeated a page; refusing incomplete order book")
                seen.add(fingerprint)
            out.extend(batch)
            if len(batch) < 100:
                return out
        raise BrokerError("Groww order book exceeds pagination limit; no complete snapshot saved")

    def quotes(self, keys, mapping=None):
        keys = nse_keys(keys)
        return self.quote_result(keys, lambda k: require_dict(self.call("GET", "/live-data/quote",
            query={"exchange": "NSE", "segment": "CASH", "trading_symbol": k.split(":")[1]})))

    def order_payload(self, o, mapping=None):
        return {"trading_symbol": o["symbol"].split(":")[1], "exchange": "NSE", "segment": "CASH", "transaction_type": o["side"],
                "quantity": integer(o["quantity"]), "price": money(o["price"]), "product": o["product"], "order_type": "LIMIT", "validity": "DAY",
                "order_reference_id": "it-" + digest(o)[:16]}
