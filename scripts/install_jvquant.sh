#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-}"
PACKAGE_SPEC="${JVQUANT_PACKAGE_SPEC:-jvquant==1.20.5 requests>=2.32.0,<3.0.0 websocket-client>=1.8.0,<2.0.0}"

usage() {
  cat <<'USAGE'
Aegis Alpha jvQuant dependency installer

Usage:
  scripts/install_jvquant.sh [options]

Options:
  --python PATH       Python executable to use. Defaults to .venv/bin/python
                      when available, otherwise python3.11.
  -h, --help          Show this help.

Environment:
  JVQUANT_PACKAGE_SPEC   Space-separated package specs to install.
                         Default: jvquant==1.20.5 requests>=2.32.0,<3.0.0 websocket-client>=1.8.0,<2.0.0

Examples:
  scripts/install_jvquant.sh
  scripts/install_jvquant.sh --python .venv/bin/python
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3.11"
  fi
fi

echo "Using Python: $PYTHON_BIN"
"$PYTHON_BIN" --version

echo "Installing jvQuant dependencies: $PACKAGE_SPEC"
# Intentional word splitting: JVQUANT_PACKAGE_SPEC is a space-separated list of pip specs.
# shellcheck disable=SC2086
"$PYTHON_BIN" -m pip install $PACKAGE_SPEC

echo "Verifying import name: jvQuant"
"$PYTHON_BIN" - <<'PY'
import jvQuant

print("jvQuant import ok")
PY

echo "jvQuant dependency is ready."
