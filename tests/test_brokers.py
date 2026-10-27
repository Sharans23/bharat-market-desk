import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from india_trader.brokers import connect
from india_trader.brokers.adapters import Kite, Dhan, Groww, broker_time
from india_trader.brokers.credentials import Vault, dpapi
from india_trader.brokers.transport import BrokerError, NoRedirect, Transport
from india_trader.brokers import commands
from india_trader.cli import parser, run
from india_trader.core import read, write
from india_trader.trading import order

CREDS = {"kite": {"api_key": "demo-api-key", "access_token": "demo-secret-token"},
         "dhan": {"client_id": "100000001", "access_token": "demo-secret-token"},
         "groww": {"access_token": "demo-secret-token"}}


class FakeTransport:
    def __init__(self, responses):
        self.responses = copy.deepcopy(responses)
        self.calls = []

    def request(self, method, path, headers, **kwargs):
        self.calls.append((method, path, headers, kwargs))
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


def kite(data):
    return {"status": "success", "data": data}


def groww(data):
    return {"status": "SUCCESS", "payload": data}


class Connections(unittest.TestCase):
    def test_kite_login_checksum_and_form(self):
        transport = FakeTransport({"/session/token": kite({"access_token": "new-token"})})
        result = Kite.exchange("key", "secret", "request", transport)
        method, path, headers, kwargs = transport.calls[0]
        self.assertEqual((method, path), ("POST", "/session/token"))
        self.assertEqual(kwargs["body"]["checksum"], hashlib.sha256(b"keyrequestsecret").hexdigest())
        self.assertTrue(kwargs["form"])
        self.assertNotIn("secret", kwargs["body"])
        self.assertEqual(result["access_token"], "new-token")

    def test_login_url_is_official_and_encoded(self):
        self.assertEqual(Kite.login_url("a&b"), "https://kite.zerodha.com/connect/login?v=3&api_key=a%26b")

    def test_headers(self):
        self.assertEqual(Kite(CREDS["kite"]).headers()["Authorization"], "token demo-api-key:demo-secret-token")
        self.assertEqual(Dhan(CREDS["dhan"]).headers()["client-id"], "100000001")
        self.assertEqual(Groww(CREDS["groww"]).headers()["X-API-VERSION"], "1.0")

    def test_missing_and_header_injection_credentials(self):
        for values in [{}, {"access_token": "x\r\nInjected:y"}]:
            with self.assertRaises(BrokerError):
                Groww(values)

    def test_profile_summary_no_pii_or_token(self):
        fake = FakeTransport({"/user/profile": kite({"user_id": "AB123", "email": "private@example.invalid", "access_token": "bad-echo"})})
        summary = Kite(CREDS["kite"], fake).profile_summary()
        self.assertTrue(summary["authenticated"])
        self.assertNotIn("private", json.dumps(summary))
        self.assertNotIn("AB123", json.dumps(summary))
        self.assertNotIn("bad-echo", json.dumps(summary))

    def test_dhan_identity_must_match(self):
        fake = FakeTransport({"/profile": {"dhanClientId": "other"}})
        with self.assertRaises(BrokerError):
            Dhan(CREDS["dhan"], fake).profile_summary()

    def test_rejected_envelopes_do_not_echo_messages(self):
        for client in [Kite(CREDS["kite"]), Dhan(CREDS["dhan"]), Groww(CREDS["groww"])]:
            with self.subTest(client=client.name), self.assertRaises(BrokerError) as err:
                client.unwrap({"status": "error", "errorCode": "BAD", "message": "demo-secret-token"})
            self.assertNotIn("demo-secret-token", str(err.exception))

    def test_kite_snapshot_keeps_positions_separate(self):
        fake = FakeTransport({"/user/profile": kite({"user_id": "AB123"}), "/user/margins/equity": kite({"net": 1000, "available": {"collateral": 500}}),
            "/portfolio/holdings": kite([{"tradingsymbol": "INFY", "quantity": 10, "t1_quantity": 2}]),
            "/portfolio/positions": kite({"net": [{"tradingsymbol": "INFY", "quantity": 1}], "day": []}), "/orders": kite([])})
        result = Kite(CREDS["kite"], fake).snapshot()
        self.assertEqual(result["holdings"][0]["quantity"], 10)
        self.assertEqual(result["positions"]["net"][0]["quantity"], 1)
        self.assertNotIn("cash_inr", result)
        self.assertTrue(all(call[0] == "GET" for call in fake.calls))

    def test_snapshot_failure_not_silently_empty(self):
        fake = FakeTransport({"/user/profile": kite({"user_id": "AB123"}), "/user/margins/equity": BrokerError("timeout")})
        with self.assertRaises(BrokerError):
            Kite(CREDS["kite"], fake).snapshot()

    def test_groww_portfolio_contracts(self):
        fake = FakeTransport({"/holdings/user": groww({"holdings": []}), "/positions/user": groww({"positions": []}), "/margins/detail/user": groww({"clear_cash": 100})})
        client = Groww(CREDS["groww"], fake)
        self.assertEqual(client.holdings(), [])
        self.assertEqual(client.positions(), [])
        self.assertEqual(fake.calls[-1][3]["query"], {"segment": "CASH"})
        self.assertEqual(client.funds()["clear_cash"], 100)


class Quotes(unittest.TestCase):
    def test_kite_last_trade_timestamp_preserved(self):
        fake = FakeTransport({"/quote": kite({"NSE:INFY": {"last_price": 1500, "last_trade_time": "2026-10-26 10:00:00", "timestamp": "2026-10-26 10:01:00"}})})
        result = Kite(CREDS["kite"], fake).quotes(["NSE:INFY", "NSE:TCS"])
        self.assertEqual(result["quotes"]["NSE:INFY"]["as_of"], "2026-10-26T10:00:00+05:30")
        self.assertIn("NSE:TCS", result["errors"])
        self.assertEqual(fake.calls[0][3]["query"]["i"], ["NSE:INFY", "NSE:TCS"])

    def test_missing_timestamp_rejected(self):
        fake = FakeTransport({"/quote": kite({"NSE:INFY": {"last_price": 1500}})})
        result = Kite(CREDS["kite"], fake).quotes(["NSE:INFY"])
        self.assertFalse(result["quotes"])
        self.assertTrue(result["errors"])

    def test_dhan_id_mapping_and_quote_post(self):
        fake = FakeTransport({"/marketfeed/quote": {"status": "success", "data": {"NSE_EQ": {"123": {"last_price": 1500, "last_trade_time": "26/10/2026 10:00:00"}}}}})
        mapping = {"instruments": {"NSE:INFY": {"dhan": {"security_id": "123", "exchange_segment": "NSE_EQ"}}}}
        result = Dhan(CREDS["dhan"], fake).quotes(["NSE:INFY"], mapping)
        self.assertEqual(fake.calls[0][3]["body"], {"NSE_EQ": [123]})
        self.assertEqual(result["quotes"]["NSE:INFY"]["price"], 1500)

    def test_dhan_never_guesses_id(self):
        with self.assertRaises(BrokerError):
            Dhan(CREDS["dhan"]).quotes(["NSE:INFY"])

    def test_groww_millisecond_timestamp(self):
        fake = FakeTransport({"/live-data/quote": groww({"last_price": 1500, "last_trade_time": 1792981800000})})
        result = Groww(CREDS["groww"], fake).quotes(["NSE:INFY"])
        self.assertIn("+05:30", result["quotes"]["NSE:INFY"]["as_of"])
        self.assertEqual(fake.calls[0][3]["query"]["segment"], "CASH")

    def test_sentinel_and_bse_rejected(self):
        with self.assertRaises(BrokerError):
            broker_time("01/01/1980 00:00:00", "dhan")
        with self.assertRaises(BrokerError):
            Kite(CREDS["kite"]).quotes(["BSE:500209"])


class InstrumentsAndPreview(unittest.TestCase):
    def test_kite_csv_only_identifier_data(self):
        csv = "instrument_token,tradingsymbol,exchange,instrument_type,tick_size,lot_size\n123,INFY,NSE,EQ,0.1,1\n456,INFY-FUT,NFO,FUT,0.1,400\n"
        result = Kite(CREDS["kite"], FakeTransport({"/instruments/NSE": csv})).instruments()
        self.assertEqual(list(result["instruments"]), ["NSE:INFY"])
        self.assertNotIn("surveillance", result["instruments"]["NSE:INFY"])

    def test_duplicate_csv_rejected(self):
        csv = "instrument_token,tradingsymbol,exchange,instrument_type,tick_size,lot_size\n123,INFY,NSE,EQ,0.1,1\n456,INFY,NSE,EQ,0.1,1\n"
        with self.assertRaises(BrokerError):
            Kite(CREDS["kite"], FakeTransport({"/instruments/NSE": csv})).instruments()

    def test_historical_candles(self):
        fake = FakeTransport({"/instruments/historical/123/day": kite({"candles": [["2026-10-26T09:15:00+05:30", 100, 110, 90, 105, 1000]]})})
        result = Kite(CREDS["kite"], fake).history(123, "day", "2026-10-26T09:00:00+05:30", "2026-10-26T16:00:00+05:30")
        self.assertEqual(result["candles"][0]["close"], 105)

    def test_history_range_and_interval_rejected_before_network(self):
        client = Kite(CREDS["kite"])
        for interval, end in [("garbage", "2026-10-27T10:00:00+05:30"), ("day", "2027-01-01T10:00:00+05:30"), ("day", "2026-11-25T10:00:01+05:30")]:
            with self.assertRaises(BrokerError):
                client.history(123, interval, "2026-10-26T10:00:00+05:30", end)

    def test_preview_is_not_a_trade_or_protective_stop(self):
        proposal = order("NSE:INFY", 2, 1500, product="MIS", stop=1490)
        mapping = {"instruments": {"NSE:INFY": {"dhan": {"security_id": 123, "exchange_segment": "NSE_EQ"}}}}
        for name in CREDS:
            fake = FakeTransport({})
            result = connect(name, CREDS[name], fake).preview(proposal, mapping)
            self.assertEqual(result["readiness"], "FORMAT_ONLY")
            self.assertFalse(result["submitted"])
            self.assertNotIn("stop_loss", result["payload"])
            self.assertEqual(fake.calls, [])

    def test_groww_pagination(self):
        client = Groww(CREDS["groww"], FakeTransport({}))
        with patch.object(client, "call", side_effect=[{"order_list": [{"id": i} for i in range(100)]}, {"order_list": [{"id": 100}]}]) as call:
            self.assertEqual(len(client.orders()), 101)
            self.assertEqual(call.call_args.kwargs["query"]["page"], 1)

    def test_groww_repeated_page_fails(self):
        client = Groww(CREDS["groww"], FakeTransport({}))
        with patch.object(client, "call", return_value={"order_list": [{"id": i} for i in range(100)]}):
            with self.assertRaises(BrokerError):
                client.orders()


class Http(unittest.TestCase):
    def test_order_mutations_and_arbitrary_hosts_disallowed(self):
        for provider, path in [("kite", "/orders/regular"), ("dhan", "/orders"), ("groww", "/order/create"), ("kite", "https://evil.invalid")]:
            with self.subTest(provider=provider), self.assertRaises(BrokerError):
                Transport(provider, pause=0).request("POST", path, {})

    def test_http_errors_do_not_leak_tokens_or_body(self):
        class Opener:
            def open(self, req, timeout):
                raise urllib.error.HTTPError("https://example.invalid?demo-secret-token", 401, "demo-secret-token", {}, io.BytesIO(b"demo-secret-token"))
        with self.assertRaises(BrokerError) as err:
            Transport("kite", opener=Opener(), pause=0).request("GET", "/user/profile", {})
        self.assertNotIn("demo-secret-token", str(err.exception))
        self.assertIn("401", str(err.exception))

    def test_redirect_never_forwards_auth(self):
        with self.assertRaises(BrokerError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid")

    def test_repeated_quote_query_params(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        class Opener:
            def open(self, req, timeout):
                self.url = req.full_url
                return Response(b'{"status":"success","data":{}}')
        opener = Opener()
        Transport("kite", opener=opener, pause=0).request("GET", "/quote", {}, query={"i": ["NSE:INFY", "NSE:TCS"]})
        self.assertIn("i=NSE%3AINFY&i=NSE%3ATCS", opener.url)


class CredentialStorage(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows interactive setup")
    def test_interactive_login_saves_only_verified_access_credentials(self):
        from unittest.mock import Mock
        vault, client = Mock(), Mock()
        client.profile_summary.return_value = {"authenticated": True}
        with patch.object(commands, "prompt_secret", side_effect=["key", "secret", "http://127.0.0.1:8000?request_token=once&status=success"]), patch.object(Kite, "exchange", return_value=CREDS["kite"]) as exchange, patch.object(commands, "connect", return_value=client), patch.object(commands.webbrowser, "open", return_value=True), patch("builtins.print"):
            commands.interactive_connect("kite", vault=vault)
        exchange.assert_called_once_with("key", "secret", "once")
        vault.save.assert_called_once_with("kite", CREDS["kite"])

    @unittest.skipUnless(os.name == "nt", "Windows interactive setup")
    def test_failed_login_does_not_replace_saved_credentials(self):
        from unittest.mock import Mock
        vault, client = Mock(), Mock()
        client.profile_summary.side_effect = BrokerError("Authentication failed")
        with patch.object(commands, "prompt_secret", side_effect=["key", "token"]), patch.object(commands, "connect", return_value=client), self.assertRaises(BrokerError):
            commands.interactive_connect("kite", existing_token=True, vault=vault)
        vault.save.assert_not_called()

    def test_partial_environment_does_not_mix_with_vault(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"KITE_API_KEY": "only-key"}, clear=True):
            with self.assertRaises(BrokerError):
                Vault(temp).load("kite")

    def test_status_does_not_claim_authenticated(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            result = Vault(temp).status("kite")
            self.assertEqual(result["authenticated"], "not_checked")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_dpapi_roundtrip_not_plaintext(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            vault = Vault(temp)
            vault.save("kite", CREDS["kite"])
            self.assertNotIn(b"demo-secret-token", vault.path("kite").read_bytes())
            self.assertEqual(vault.load("kite"), CREDS["kite"])
            vault.forget("kite")
            self.assertFalse(vault.path("kite").exists())


class CliIntegration(unittest.TestCase):
    def test_packaging_excludes_private_accounts_and_tokens(self):
        from scripts.package import release_files
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ["README.md", "india_trader/core.py", "private-account.json", ".env.kite", "credentials/kite.dpapi", "trader/account.json", "docs/private-account.json", "ui/dist/index.html", "ui/src/main.jsx", "ui/package-lock.json", "ui/node_modules/dependency.js", "ui/test-results/secret.json", ".ui-test-data/account.json"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic", encoding="utf-8")
            included = {str(p.relative_to(root)).replace("\\", "/") for p in release_files(root)}
            self.assertEqual(included, {"README.md", "india_trader/core.py", "ui/dist/index.html", "ui/src/main.jsx", "ui/package-lock.json"})

    def test_now_cannot_fake_connection_time(self):
        args = parser().parse_args(["--now", "2026-10-26T10:00:00+05:30", "connections", "list"])
        with self.assertRaises(BrokerError):
            run(args)

    def test_sync_does_not_overwrite_paper_account(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = Path(temp)
            write(ws / "account.json", {"paper": "untouched"})
            fake = FakeTransport({"/user/profile": kite({"user_id": "AB123"}), "/user/margins/equity": kite({}),
                "/portfolio/holdings": kite([]), "/portfolio/positions": kite({"net": [], "day": []}), "/orders": kite([])})
            client = Kite(CREDS["kite"], fake)
            args = parser().parse_args(["--workspace", temp, "connections", "sync", "kite"])
            with patch.object(commands, "connect", return_value=client), patch.object(commands, "snapshot_path", return_value=ws / "private/snapshot.json"):
                result = run(args)
            self.assertFalse(result["paper_account_changed"])
            self.assertEqual(read(ws / "account.json"), {"paper": "untouched"})

    def test_partial_quotes_do_not_clobber_prices(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = Path(temp)
            write(ws / "prices.json", {"quotes": "old"})
            args = parser().parse_args(["--workspace", temp, "connections", "quotes", "kite", "NSE:INFY", "--publish"])
            client = Kite(CREDS["kite"], FakeTransport({"/quote": kite({})}))
            with patch.object(commands, "connect", return_value=client), self.assertRaises(BrokerError):
                run(args)
            self.assertEqual(read(ws / "prices.json"), {"quotes": "old"})


if __name__ == "__main__":
    unittest.main()
