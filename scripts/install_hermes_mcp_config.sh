#!/usr/bin/env bash
set -euo pipefail

SOURCE_CONFIG="${SOURCE_CONFIG:-.hermes/config/aegis-alpha-mcp.yaml}"
TARGET_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
MODE="${MODE:-append}"

usage() {
  cat <<'USAGE'
Aegis Alpha Hermes MCP config installer

Usage:
  scripts/install_hermes_mcp_config.sh [options]

Options:
  --target PATH       Hermes config path. Defaults to ~/.hermes/config.yaml.
  --source PATH       MCP config snippet. Defaults to .hermes/config/aegis-alpha-mcp.yaml.
  --replace           Replace target config with the Aegis Alpha snippet.
  --append            Append snippet to an existing config only when no existing
                     mcp_servers block is present. Default.
  -h, --help          Show this help.

Notes:
  - Existing config files are backed up before mutation.
  - If your config already has mcp_servers, use the reproducible project config
    installer or --replace. Appending another top-level mcp_servers block can
    produce ambiguous YAML.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_CONFIG="$2"
      shift 2
      ;;
    --source)
      SOURCE_CONFIG="$2"
      shift 2
      ;;
    --replace)
      MODE="replace"
      shift
      ;;
    --append)
      MODE="append"
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

if [[ ! -f "$SOURCE_CONFIG" ]]; then
  echo "Source config not found: $SOURCE_CONFIG" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET_CONFIG")"

if [[ -f "$TARGET_CONFIG" ]]; then
  backup="${TARGET_CONFIG}.$(date +%Y%m%d%H%M%S).bak"
  cp "$TARGET_CONFIG" "$backup"
  echo "Backed up existing Hermes config:"
  echo "  $backup"
fi

if [[ "$MODE" == "append" && -f "$TARGET_CONFIG" ]] && grep -q "^mcp_servers:" "$TARGET_CONFIG"; then
  echo "Target config already has a top-level mcp_servers block:" >&2
  echo "  $TARGET_CONFIG" >&2
  echo "Refusing to append a duplicate block. Use scripts/install_hermes_project_config.sh --replace or rerun with --replace." >&2
  exit 1
fi

if [[ "$MODE" == "replace" || ! -f "$TARGET_CONFIG" ]]; then
  cp "$SOURCE_CONFIG" "$TARGET_CONFIG"
else
  {
    echo
    echo "# Aegis Alpha MCP config appended on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    cat "$SOURCE_CONFIG"
  } >> "$TARGET_CONFIG"
fi

echo "Installed Aegis Alpha MCP config:"
echo "  $TARGET_CONFIG"
echo
echo "Review the file before starting Hermes, especially if another mcp_servers block already exists."
