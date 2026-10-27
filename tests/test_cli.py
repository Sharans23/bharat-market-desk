import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from india_trader.core import ROOT, digest


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp.name) / "data"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "india_trader", "--workspace", str(self.ws), "--now", "2026-10-26T10:00:00+05:30", *args], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return json.loads(result.stdout if result.stdout else result.stderr)

    def test_full_research_to_approved_paper_fill(self):
        self.cli("init")
        self.cli("copycat", str(ROOT / "examples/holdings.json"))
        self.cli("analyst", str(ROOT / "examples/results.json"))
        self.assertEqual(len(self.cli("screen")["passed"]), 1)
        orders = self.cli("budget")["orders"]
        self.assertEqual(self.cli("risk")["blocked"], 0)
        self.cli("broker", "show")
        self.cli("broker", "approve", "--reply", "YES " + digest(orders[0]))
        fill = self.cli("broker", "fill", "--fill-price", str(orders[0]["price"]))
        self.assertTrue(fill["paper_fill"]["paper"])
        self.cli("broker", "fill", "--fill-price", str(orders[0]["price"]), expected=2)
        self.assertEqual(len(self.cli("broker", "log")["events"]), 1)

    def test_all_offline_workflows(self):
        self.cli("init")
        self.cli("intraday", "NSE:INFY", "--entry", "1500", "--stop", "1480")
        self.assertEqual(self.cli("risk")["blocked"], 0)
        self.cli("clock", "--cas", "yes")
        self.cli("charges", "15000", "--side", "BUY", "--product", "MIS")
        self.cli("news", "--input", str(ROOT / "examples/news.json"))
        self.cli("disclosures", str(ROOT / "examples/disclosures.json"))
        self.cli("tax", "report", "--input", str(ROOT / "examples/tax-ledger.json"), "--fy", "2026-27")
        self.cli("tax", "harvest")
        self.cli("rebalance", "--band", "5")
        self.cli("alerts")
        self.cli("copycat", str(ROOT / "examples/holdings.json"), "--previous", str(ROOT / "examples/holdings-previous.json"))

    def test_init_refuses_overwrite(self):
        self.cli("init")
        self.cli("init", expected=2)

    def test_lock_prevents_parallel_account_write(self):
        self.cli("init")
        (self.ws / ".account.lock").touch()
        self.cli("broker", "log", expected=2)

    def test_skill_launcher_from_other_directory(self):
        result = subprocess.run([sys.executable, str(ROOT / "skills/india-trader-risk/scripts/run.py"), "--help"], cwd=self.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
