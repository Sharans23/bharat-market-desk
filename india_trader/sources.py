"""Read-only, bounded public HTTP adapters. No authenticated endpoints or broker calls."""
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from .core import DataError, IST, money, positive, symbol, timestamp, digest

MAX_BYTES = 10 * 1024 * 1024


class PublicClient:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.last = 0
        self.nse_ready = False

    def get(self, url):
        host = urllib.parse.urlparse(url).hostname
        if urllib.parse.urlparse(url).scheme != "https" or host not in {
            "www.nseindia.com", "query1.finance.yahoo.com", "news.google.com"
        }:
            raise DataError("Only built-in HTTPS public-data hosts are supported")
        delay = 1 - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; IndiaTraderResearch/1.0)", "Accept": "application/json,text/xml,text/html", "Referer": "https://www.nseindia.com/"})
        try:
            with self.opener.open(request, timeout=15) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise DataError("Public response exceeds 10 MB limit; narrow request")
                return data
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DataError(f"Public source unavailable ({host}): {exc}. Use downloaded CSV/JSON; no data was fabricated.")
        finally:
            self.last = time.monotonic()

    def nse(self, endpoint, params):
        if not self.nse_ready:
            self.get("https://www.nseindia.com/")
            self.nse_ready = True
        url = "https://www.nseindia.com/api/" + endpoint + "?" + urllib.parse.urlencode(params)
        try:
            return json.loads(self.get(url)), url
        except (ValueError, UnicodeError):
            raise DataError("NSE returned non-JSON (possibly access denied); use exchange download/import")


def yahoo_code(key):
    exchange, name = symbol(key).split(":")
    if exchange == "BSE":
        raise DataError("BSE numeric codes do not map safely to Yahoo .BO names; import a verified quote")
    return name + ".NS"


def parse_yahoo(doc, key):
    chart = doc.get("chart", {})
    if chart.get("error") or not chart.get("result"):
        raise DataError(f"No Yahoo quote for {key}")
    meta = chart["result"][0]["meta"]
    if meta.get("symbol", "").upper() != yahoo_code(key) or meta.get("currency") != "INR":
        raise DataError("Provider symbol/currency mismatch")
    at = datetime.fromtimestamp(float(meta["regularMarketTime"]), IST)
    return {"price": money(positive(meta["regularMarketPrice"])), "currency": "INR",
            "as_of": at.isoformat(), "source": "Yahoo chart (unofficial; delay not guaranteed)",
            "execution_grade": False}


def fetch_quotes(keys, client=None):
    client = client or PublicClient()
    out, errors = {}, {}
    for key in keys:
        key = symbol(key)
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(yahoo_code(key), safe="") + "?interval=1m&range=1d"
            out[key] = parse_yahoo(json.loads(client.get(url)), key)
        except (DataError, ValueError, KeyError, IndexError, TypeError) as exc:
            errors[key] = str(exc)
    return {"quotes": out, "errors": errors, "fetched_at": timestamp().isoformat()}


def nse_rows(kind, keys=(), start=None, end=None, client=None):
    client = client or PublicClient()
    endpoint = {"announcements": "corporate-announcements", "insider": "corporates-pit", "results": "corporates-financial-results", "shareholding": "corporate-share-holdings-master"}[kind]
    params = {"index": "equities"}
    if start:
        params["from_date"] = datetime.fromisoformat(start).strftime("%d-%m-%Y")
    if end:
        params["to_date"] = datetime.fromisoformat(end).strftime("%d-%m-%Y")
    if len(keys) == 1:
        params["symbol"] = symbol(keys[0]).split(":")[1]
    raw, url = client.nse(endpoint, params)
    raw = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(raw, list):
        raise DataError("NSE response schema changed; expected a row list")
    selected = []
    for row in raw:
        key = "NSE:" + str(row.get("symbol", "")).upper()
        if keys and key not in keys:
            continue
        selected.append({"symbol": key, "source_url": url, "raw": row, "id": digest(row)})
    return {"kind": kind, "fetched_at": timestamp().isoformat(), "rows": selected,
            "note": "Raw exchange disclosure metadata; follow attached filings. Fetch time is not transaction/publication time."}


def parse_rss(data, key):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise DataError("DTD/entities are unsupported in feeds")
    root = ET.fromstring(data)
    out = []
    for item in root.findall(".//item"):
        title, link, pub = (item.findtext(k, "").strip() for k in ("title", "link", "pubDate"))
        try:
            at = parsedate_to_datetime(pub).astimezone(IST).isoformat()
        except (ValueError, TypeError):
            continue
        out.append({"symbol": key, "title": title, "url": link, "published_at": at,
                    "id": digest([key, link, title]), "source": "Google News RSS; verify original publisher"})
    return out


def news(keys, client=None):
    client = client or PublicClient()
    out, errors = [], {}
    for key in keys:
        key = symbol(key)
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": key.split(":")[1] + " India stock", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
        try:
            out.extend(parse_rss(client.get(url), key))
        except (DataError, ET.ParseError) as exc:
            errors[key] = str(exc)
    return {"rows": out, "errors": errors, "fetched_at": timestamp().isoformat()}


def new_items(doc, state, now=None, hours=48):
    now = timestamp(now)
    seen = set(state.get("seen", []))
    result = []
    for row in doc["rows"]:
        if row["id"] in seen:
            continue
        if row.get("published_at"):
            age = (now - timestamp(row["published_at"])).total_seconds()
            if age < 0 or age > hours * 3600:
                continue
        result.append(row)
        seen.add(row["id"])
    return {**doc, "rows": result}, {"seen": sorted(seen)}
