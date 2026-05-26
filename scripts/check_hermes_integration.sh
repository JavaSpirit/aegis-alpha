#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE:-/Users/xietian/Documents/trading}"
HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
HERMES_SKILL_DIR="${HERMES_SKILL_DIR:-$HOME/.hermes/skills/second-board-radar}"
MCP_COMMAND="${MCP_COMMAND:-$WORKSPACE/.venv/bin/aegis-alpha-mcp}"

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
  echo "[ok] MCP command executable: $MCP_COMMAND"
else
  echo "[warn] MCP command not executable: $MCP_COMMAND"
fi

if [[ -f "$WORKSPACE/.env.local" ]]; then
  echo "[ok] local env file exists: $WORKSPACE/.env.local"
else
  echo "[warn] local env file missing: $WORKSPACE/.env.local"
fi

"$WORKSPACE/scripts/check_hermes_provider.sh" || true
echo

if [[ -x "$WORKSPACE/.venv/bin/python" ]]; then
  if "$WORKSPACE/.venv/bin/python" - <<'PY' >/dev/null 2>&1
from aegis_alpha.mcp.server import mcp
assert mcp.name == "aegis-alpha"
PY
  then
    echo "[ok] Aegis Alpha MCP import check passed in installed environment"
  else
    echo "[warn] Aegis Alpha MCP import check failed in installed environment"
  fi
else
  echo "[warn] Python virtualenv missing: $WORKSPACE/.venv/bin/python"
fi

echo
echo "Next Hermes prompt:"
echo "  Use the second-board-radar skill and Aegis Alpha MCP to review today's second-board candidates."
