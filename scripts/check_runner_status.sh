#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="${LABEL:-com.aegis-alpha.runner}"
STATUS_CMD=("$REPO_ROOT/.venv/bin/python" -m aegis_alpha.runner --config "$REPO_ROOT/config/runner.yaml" --status)

echo "Aegis Alpha runner status"
echo

if launchctl print "gui/$UID/$LABEL" >/tmp/aegis-alpha-launchd-status.txt 2>/tmp/aegis-alpha-launchd-status.err; then
  echo "[ok] launchd service is registered: $LABEL"
  sed -n '1,24p' /tmp/aegis-alpha-launchd-status.txt
else
  echo "[warn] launchd service is not registered or not visible: $LABEL"
  sed -n '1,8p' /tmp/aegis-alpha-launchd-status.err || true
fi

echo
echo "Runner status file:"
PYTHONPATH="$REPO_ROOT/src" "${STATUS_CMD[@]}"
