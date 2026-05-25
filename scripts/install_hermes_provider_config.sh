#!/usr/bin/env bash
set -euo pipefail

SOURCE_CONFIG="${SOURCE_CONFIG:-.hermes/config/providers.deepseek-openrouter.example.yaml}"
TARGET_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
SOURCE_ENV="${SOURCE_ENV:-.hermes/env.example}"
TARGET_ENV="${HERMES_ENV:-$HOME/.hermes/.env}"
MODE="${MODE:-append}"

usage() {
  cat <<'USAGE'
Aegis Alpha Hermes provider config installer

Usage:
  scripts/install_hermes_provider_config.sh [options]

Options:
  --target-config PATH   Hermes config path. Defaults to ~/.hermes/config.yaml.
  --target-env PATH      Hermes env path. Defaults to ~/.hermes/.env.
  --replace-config       Replace target config with provider example.
  --append-config        Append provider example to existing config. Default.
  -h, --help             Show this help.

Notes:
  - DeepSeek direct is the primary provider.
  - OpenRouter is optional for contrast/fallback and should not be used to call DeepSeek.
  - Existing files are backed up before mutation.
  - Real API keys are never written by this script.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-config)
      TARGET_CONFIG="$2"
      shift 2
      ;;
    --target-env)
      TARGET_ENV="$2"
      shift 2
      ;;
    --replace-config)
      MODE="replace"
      shift
      ;;
    --append-config)
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
  echo "Source provider config not found: $SOURCE_CONFIG" >&2
  exit 1
fi

if [[ ! -f "$SOURCE_ENV" ]]; then
  echo "Source env example not found: $SOURCE_ENV" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET_CONFIG")"
mkdir -p "$(dirname "$TARGET_ENV")"

if [[ -f "$TARGET_CONFIG" ]]; then
  backup="${TARGET_CONFIG}.$(date +%Y%m%d%H%M%S).bak"
  cp "$TARGET_CONFIG" "$backup"
  echo "Backed up existing Hermes config:"
  echo "  $backup"
fi

if [[ "$MODE" == "replace" || ! -f "$TARGET_CONFIG" ]]; then
  cp "$SOURCE_CONFIG" "$TARGET_CONFIG"
else
  {
    echo
    echo "# Aegis Alpha provider config appended on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    cat "$SOURCE_CONFIG"
  } >> "$TARGET_CONFIG"
fi

if [[ -f "$TARGET_ENV" ]]; then
  backup="${TARGET_ENV}.$(date +%Y%m%d%H%M%S).bak"
  cp "$TARGET_ENV" "$backup"
  echo "Backed up existing Hermes env:"
  echo "  $backup"
  touch "$TARGET_ENV"
  if ! grep -q "^DEEPSEEK_API_KEY=" "$TARGET_ENV"; then
    echo "DEEPSEEK_API_KEY=" >> "$TARGET_ENV"
  fi
  if ! grep -q "^OPENROUTER_API_KEY=" "$TARGET_ENV"; then
    echo "OPENROUTER_API_KEY=" >> "$TARGET_ENV"
  fi
else
  cp "$SOURCE_ENV" "$TARGET_ENV"
fi

chmod 600 "$TARGET_ENV" 2>/dev/null || true

echo "Installed Hermes provider config scaffold:"
echo "  config: $TARGET_CONFIG"
echo "  env:    $TARGET_ENV"
echo
echo "Edit $TARGET_ENV and fill DEEPSEEK_API_KEY. OPENROUTER_API_KEY is optional."

