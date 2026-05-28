#!/usr/bin/env bash
set -euo pipefail

LABEL="${LABEL:-com.aegis-alpha.runner}"
TARGET="${TARGET:-$HOME/Library/LaunchAgents/$LABEL.plist}"
REMOVE_PLIST=false

usage() {
  cat <<'USAGE'
Aegis Alpha launchd runner uninstaller

Usage:
  scripts/uninstall_launchd_runner.sh [options]

Options:
  --remove-plist  Delete the installed plist after bootout.
  -h, --help      Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove-plist)
      REMOVE_PLIST=true
      shift
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

launchctl bootout "gui/$UID/$LABEL" >/dev/null 2>&1 || true
echo "Unloaded launchd service:"
echo "  $LABEL"

if [[ "$REMOVE_PLIST" == true && -f "$TARGET" ]]; then
  rm "$TARGET"
  echo "Removed plist:"
  echo "  $TARGET"
fi
