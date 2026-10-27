"""Optional read-only connectivity smoke test; records successes and observed failures."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from india_trader.sources import PublicClient, fetch_quotes, nse_rows
from india_trader.core import timestamp, write

result = {"checked_at": timestamp().isoformat(), "quotes": fetch_quotes(["NSE:INFY"]), "nse": {}}
client = PublicClient()
for kind in ("announcements", "insider", "results", "shareholding"):
    try:
        doc = nse_rows(kind, ["NSE:INFY"], client=client)
        result["nse"][kind] = {"ok": True, "row_count": len(doc["rows"]), "sample": doc["rows"][:1]}
    except Exception as exc:
        result["nse"][kind] = {"ok": False, "error": str(exc)}
write(Path(__file__).resolve().parents[1] / "docs/live-probe.json", result)
print(json.dumps(result, indent=2))
