"""Launch the shared India Trader CLI from any working directory."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from india_trader.cli import main
raise SystemExit(main())
