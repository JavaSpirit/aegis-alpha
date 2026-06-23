from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("AEGIS_ALPHA_PROJECT_ROOT", str(ROOT))
os.environ.setdefault("AEGIS_ALPHA_ENV_FILE", str(ROOT / ".env.local"))

from aegis_alpha.config import load_project_env

load_project_env()

from aegis_alpha.mcp.server import main


if __name__ == "__main__":
    raise SystemExit(main())
