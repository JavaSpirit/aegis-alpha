#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
HERMES_SKILL_DIR="${HERMES_SKILL_DIR:-$HOME/.hermes/skills/second-board-radar}"
MCP_COMMAND="${MCP_COMMAND:-$WORKSPACE/.venv/bin/aegis-alpha-mcp}"
MCP_RUNNER="${MCP_RUNNER:-$WORKSPACE/scripts/run_mcp.py}"

echo "Aegis Alpha Hermes integration check"
echo

if command -v hermes >/dev/null 2>&1; then
  echo "[ok] hermes command: $(command -v hermes)"
else
  echo "[warn] hermes command not found"
fi

if [[ -f "$HERMES_CONFIG" ]]; then
  echo "[ok] Hermes config exists: $HERMES_CONFIG"
  if grep -q "aegis_alpha" "$HERMES_CONFIG"; then
    echo "[ok] Hermes config mentions aegis_alpha"
  else
    echo "[warn] Hermes config does not mention aegis_alpha"
  fi
else
  echo "[warn] Hermes config missing: $HERMES_CONFIG"
fi

if [[ -f "$HERMES_SKILL_DIR/SKILL.md" ]]; then
  echo "[ok] second-board-radar skill installed: $HERMES_SKILL_DIR"
else
  echo "[warn] second-board-radar skill missing: $HERMES_SKILL_DIR"
fi

if [[ -x "$MCP_COMMAND" ]]; then
  echo "[ok] legacy MCP command executable: $MCP_COMMAND"
else
  echo "[warn] legacy MCP command not executable: $MCP_COMMAND"
fi

if [[ -x "$WORKSPACE/.venv/bin/python" && -f "$MCP_RUNNER" ]]; then
  echo "[ok] source MCP runner: $WORKSPACE/.venv/bin/python $MCP_RUNNER"
else
  echo "[warn] source MCP runner unavailable: $WORKSPACE/.venv/bin/python $MCP_RUNNER"
fi

if [[ -f "$WORKSPACE/.env.local" ]]; then
  echo "[ok] local env file exists: $WORKSPACE/.env.local"
else
  echo "[warn] local env file missing: $WORKSPACE/.env.local"
fi

"$WORKSPACE/scripts/check_hermes_provider.sh" || true
echo

if [[ -x "$WORKSPACE/.venv/bin/python" ]]; then
  if PYTHONPATH="$WORKSPACE/src" "$WORKSPACE/.venv/bin/python" - <<'PY' >/dev/null 2>&1
from aegis_alpha.mcp.server import mcp
assert mcp.name == "aegis-alpha"
PY
  then
    echo "[ok] Aegis Alpha MCP import check passed from source tree"
  else
    echo "[warn] Aegis Alpha MCP import check failed from source tree"
  fi
else
  echo "[warn] Python virtualenv missing: $WORKSPACE/.venv/bin/python"
fi

echo
echo "Next Hermes prompt:"
echo "  Use the second-board-radar skill and Aegis Alpha MCP to review today's second-board candidates."
