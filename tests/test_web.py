import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from india_trader.core import DataError, read, write
from india_trader.brokers.transport import BrokerError
from india_trader.web import ACTIONS, Application, Server


class FakeVault:
    def __init__(self): self.values = {}
    def save(self, name, values): self.values[name] = values
    def load(self, name):
        if name not in self.values: raise BrokerError("Not configured")
        return self.values[name]
    def forget(self, name): self.values.pop(name, None)
    def status(self, name): return {"broker": name, "encrypted_credentials_saved": name in self.values, "environment": "absent", "authenticated": "not_checked"}


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = FakeVault()
        self.app = Application(self.temp.name, self.vault)
    def tearDown(self): self.temp.cleanup()
    def execute(self, action, params=None, workspace="practice", simulation=True):
        return self.app.execute({"action": action, "params": params or {}, "workspace": workspace, "simulation": simulation})

    def test_bootstrap_and_workspace_isolation(self):
        sample = self.app.bootstrap("practice", "sid")
        clean = self.app.bootstrap("research", "sid")
        self.assertEqual(sample["documents"]["account"]["portfolio"]["cash_inr"], 100000)
        self.assertEqual(clean["documents"]["account"]["portfolio"]["cash_inr"], 0)
        self.assertEqual(clean["documents"]["prices"]["quotes"], {})
        self.assertFalse(clean["live_orders"])

    def test_failed_initialization_does_not_leave_partial_workspace(self):
        with patch("india_trader.web.cli.run",side_effect=OSError("disk full")),self.assertRaises(OSError):
            self.app.workspace("practice")
        self.assertFalse((self.app.home/"workspaces/practice").exists())
        self.assertTrue(self.app.workspace("practice").exists())

    def test_all_services_registered(self):
        self.assertTrue({"budget", "intraday", "risk", "tickets", "approve", "fill", "log", "quote", "clock", "news", "filings", "disclosures", "copycat", "analyst", "screen", "tax_report", "tax_harvest", "alerts", "rebalance", "charges"}.issubset(ACTIONS))
        self.assertEqual(len([a for a in ACTIONS if a.startswith("connection_")]), 9)

    def test_end_to_end_paper_trade_requires_exact_approval(self):
        plan = self.execute("budget")
        self.assertEqual(len(plan["orders"]), 4)
        tickets = self.execute("tickets")
        t = tickets["tickets"][0]
        with self.assertRaises(DataError): self.execute("fill", {"index": 1, "fill_price": t["order"]["price"]})
        with self.assertRaises(DataError): self.execute("approve", {"index": 1, "reply": "yes"})
        self.execute("approve", {"index": 1, "reply": t["acknowledgement"]})
        self.execute("fill", {"index": 1, "fill_price": t["order"]["price"]})
        self.assertEqual(len(self.execute("log")["events"]), 1)
        with self.assertRaises(DataError): self.execute("fill", {"index": 1, "fill_price": t["order"]["price"]})

    def test_research_workflows_from_examples(self):
        self.assertIn("companies", self.execute("analyst", {"input": "example:results"}))
        self.execute("screen")
        self.execute("copycat", {"input": "example:holdings"})
        self.execute("copycat", {"input": "example:holdings", "previous": "example:holdings-previous"})
        self.execute("disclosures", {"input": "example:disclosures"})
        self.execute("news", {"input": "example:news"})
        self.execute("tax_report", {"input": "example:tax-ledger", "fy": "2026-27"})
        self.execute("tax_harvest")
        self.execute("alerts")
        self.execute("clock", {"cas": "yes"})
        self.execute("charges", {"turnover": 10000, "side": "BUY", "product": "CNC"})
        self.execute("intraday", {"symbol": "NSE:INFY", "entry": 1500, "stop": 1480})
        self.execute("rebalance", {"band": 5})

    def test_only_uploaded_files_and_examples_can_be_read(self):
        for reference in ["C:/Windows/win.ini", "../../credentials/kite.dpapi", "example:../account", "upload:../../../key.json"]:
            with self.assertRaises(DataError): self.app.file_path(reference)
        meta = self.app.upload({"name": "input.csv", "content": "symbol,quantity\nNSE:INFY,1"})
        self.assertTrue(self.app.file_path(meta["id"]).exists())
        self.assertIn(meta, self.app.files())

    def test_bad_upload_and_invalid_operation_rejected(self):
        for body in [{"name":"x.exe","content":"x"},{"name":"x.json","content":"NaN"},{"name":"x.json","content":"x"}]:
            with self.assertRaises(ValueError): self.app.upload(body)
        with self.assertRaises(DataError): self.execute("shell", {"cmd": "anything"})
        with self.assertRaises(DataError): self.execute("budget", {"out": "outside.json"})
        with self.assertRaises(DataError): self.app.workspace("../outside")
        with self.assertRaises(DataError): self.execute("budget", workspace="research")

    def test_saving_inputs_clears_approvals_and_cannot_enable_live_trading(self):
        ws = self.app.workspace("practice")
        account = read(ws / "account.json")
        account["approvals"] = {"old": "old"}
        write(ws / "account.json", account)
        self.app.save_document({"name":"targets","document":{"weights":[]}})
        self.assertEqual(read(ws / "account.json")["approvals"], {})
        with self.assertRaises(DataError): self.app.save_document({"name":"config","document":{"paper":False}})
        with self.assertRaises(DataError): self.app.save_document({"name":"account","document":{"portfolio":[]}})
        account["approvals"] = {"forged":"approval"}
        self.app.save_document({"name":"account","document":account})
        self.assertEqual(read(ws / "account.json")["approvals"], {})

    def test_kite_login_state_and_single_use_exchange(self):
        start = self.app.login_start({"api_key":"synthetic-key","api_secret":"synthetic-secret"}, "browser")
        self.assertNotIn("synthetic-secret", json.dumps(start))
        self.assertTrue(start["url"].startswith("https://kite.zerodha.com/"))
        flow = self.app.pending["browser"]
        state = parse_qs(parse_qs(urlsplit(start["url"]).query)["redirect_params"][0])["it_state"][0]
        self.assertEqual(state, flow["state"])
        with self.assertRaises(BrokerError): self.app.login_finish({"request_token":"once","it_state":"wrong"}, "browser", callback=True)
        with self.assertRaises(BrokerError): self.app.login_finish({"request_token":"once","it_state":state}, "other", callback=True)
        values = {"api_key":"synthetic-key","access_token":"synthetic-token"}
        client = Mock(); client.profile_summary.return_value = {"authenticated":True}
        with patch("india_trader.web.Kite.exchange", return_value=values) as exchange, patch("india_trader.web.connect", return_value=client):
            self.app.login_finish({"request_token":"once","it_state":state}, "browser", callback=True)
        exchange.assert_called_once_with("synthetic-key","synthetic-secret","once")
        self.assertEqual(self.vault.values["kite"], values)
        self.assertNotIn("browser", self.app.pending)
        with self.assertRaises(BrokerError): self.app.login_finish({"request_token":"once"}, "browser")

    def test_expired_and_failed_login_preserve_saved_credentials(self):
        self.vault.values["kite"] = {"old":"old"}
        self.app.login_start({"api_key":"key","api_secret":"secret"}, "browser")
        self.app.pending["browser"]["expires"] = time.monotonic()-1
        with self.assertRaises(BrokerError): self.app.login_finish({"request_token":"x"}, "browser")
        self.assertNotIn("browser", self.app.pending)
        client=Mock();client.profile_summary.side_effect=BrokerError("Authentication failed")
        with patch("india_trader.web.connect",return_value=client), self.assertRaises(BrokerError):
            self.app.token_connect({"provider":"kite","credentials":{"api_key":"new","access_token":"new"}})
        self.assertEqual(self.vault.values["kite"], {"old":"old"})

    def test_manual_ui_callback_and_cancel(self):
        self.app.login_start({"api_key":"key","api_secret":"secret"}, "browser")
        client=Mock();client.profile_summary.return_value={"authenticated":True}
        with patch("india_trader.web.Kite.exchange",return_value={"api_key":"key","access_token":"token"}),patch("india_trader.web.connect",return_value=client):
            self.app.login_finish({"request_token":"http://127.0.0.1:8000?request_token=once"},"browser")
        self.app.login_start({"api_key":"key","api_secret":"secret"}, "browser")
        self.app.post("/api/auth/cancel",{},"browser")
        self.assertNotIn("browser",self.app.pending)


class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.app=Application(cls.temp.name,FakeVault())
        cls.server=Server(("127.0.0.1",0),cls.app)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.server.server_address[1]
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=10)
        conn.request(method,path,json.dumps(body) if body is not None else None,headers or {})
        r=conn.getresponse();raw=r.read();result=(r.status,dict(r.getheaders()),raw)
        conn.close();return result
    def login(self):
        status,headers,raw=self.request("GET","/api/bootstrap",headers={"X-Requested-With":"IndiaTrader"})
        self.assertEqual(status,200)
        return {"Cookie":headers["Set-Cookie"].split(";")[0],"Origin":f"http://127.0.0.1:{self.port}","Content-Type":"application/json","X-CSRF-Token":json.loads(raw)["csrf"]}
    def test_cross_origin_csrf_and_dns_rebinding_blocked(self):
        self.assertEqual(self.request("GET","/api/bootstrap")[0],403)
        self.assertEqual(self.request("GET","/api/bootstrap",headers={"Host":"evil.example","X-Requested-With":"IndiaTrader"})[0],403)
        headers=self.login()
        self.assertEqual(self.request("POST","/api/action",{"action":"budget"},{**headers,"Origin":"https://evil.example"})[0],403)
        self.assertEqual(self.request("POST","/api/action",{"action":"budget"},{**headers,"X-CSRF-Token":"wrong"})[0],403)
        self.assertEqual(self.request("POST","/api/action",{"action":"budget","simulation":True},headers)[0],200)
    def test_response_security_headers_and_no_source_file_access(self):
        status,headers,raw=self.request("GET","/api/bootstrap",headers={"X-Requested-With":"IndiaTrader"})
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertIn("HttpOnly",headers["Set-Cookie"])
        self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET","/../../india_trader/web.py")[0],404)
        self.assertEqual(self.request("GET","/api/docs?name=../../key",headers={"X-Requested-With":"IndiaTrader"})[0],400)
    def test_unexpected_auth_failure_does_not_echo_secret(self):
        headers=self.login()
        with patch.object(self.app,"token_connect",side_effect=ValueError("secret-token-must-not-appear")):
            status,_,raw=self.request("POST","/api/auth/token",{},headers)
        self.assertEqual(status,400)
        self.assertNotIn(b"secret-token-must-not-appear",raw)
    def test_callback_scrubs_query_and_records_success(self):
        headers=self.login()
        sid=headers["Cookie"].split("=",1)[1]
        self.app.login_start({"api_key":"key","api_secret":"secret"},sid)
        state=self.app.pending[sid]["state"]
        client=Mock();client.profile_summary.return_value={"authenticated":True}
        with patch("india_trader.web.Kite.exchange",return_value={"api_key":"key","access_token":"token"}),patch("india_trader.web.connect",return_value=client):
            status,response,raw=self.request("GET",f"/kite/callback?request_token=once&it_state={state}",headers={"Cookie":headers["Cookie"]})
        self.assertEqual(status,303)
        self.assertEqual(response["Location"],"/#brokers")
        self.assertNotIn(b"once",raw)
        self.assertTrue(self.app.auth_notice[sid]["ok"])


if __name__ == "__main__": unittest.main()
