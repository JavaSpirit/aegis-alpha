#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="${LABEL:-com.aegis-alpha.runner}"
TEMPLATE="${TEMPLATE:-$REPO_ROOT/.launchd/$LABEL.plist.template}"
TARGET="${TARGET:-$HOME/Library/LaunchAgents/$LABEL.plist}"
LOAD=true

usage() {
  cat <<'USAGE'
Aegis Alpha launchd runner installer

Usage:
  scripts/install_launchd_runner.sh [options]

Options:
  --no-load       Install the plist but do not bootstrap it.
  --target PATH   LaunchAgent plist path. Defaults to ~/Library/LaunchAgents/com.aegis-alpha.runner.plist.
  -h, --help      Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-load)
      LOAD=false
      shift
      ;;
    --target)
      TARGET="$2"
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

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Template not found: $TEMPLATE" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")" "$REPO_ROOT/logs" "$REPO_ROOT/data"

tmp_file="$(mktemp "${TMPDIR:-/tmp}/aegis-alpha-runner.XXXXXX.plist")"
awk -v root="$REPO_ROOT" '{ gsub(/__PROJECT_ROOT__/, root); print }' "$TEMPLATE" > "$tmp_file"
plutil -lint "$tmp_file" >/dev/null

if [[ -f "$TARGET" ]]; then
  backup="${TARGET}.$(date +%Y%m%d%H%M%S).bak"
  cp "$TARGET" "$backup"
  echo "Backed up existing LaunchAgent:"
  echo "  $backup"
fi

mv "$tmp_file" "$TARGET"
echo "Installed LaunchAgent:"
echo "  $TARGET"

if [[ "$LOAD" == true ]]; then
  launchctl bootout "gui/$UID/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$UID" "$TARGET"
  launchctl enable "gui/$UID/$LABEL"
  launchctl kickstart -k "gui/$UID/$LABEL"
  echo "Loaded launchd service:"
  echo "  $LABEL"
else
  echo "Skipped launchctl bootstrap by --no-load."
fi
