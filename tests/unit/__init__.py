import sys
import types
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
poe_trade_dir = project_root / "poe_trade"

if "poe_trade" not in sys.modules:
    poe_trade_stub = types.ModuleType("poe_trade")
    poe_trade_stub.__path__ = [str(poe_trade_dir)]
    setattr(poe_trade_stub, "__version__", "0.1.0")
    sys.modules["poe_trade"] = poe_trade_stub
