#!/usr/bin/env bash
set -euo pipefail

SOURCE_CONFIG="${SOURCE_CONFIG:-.hermes/config/providers.deepseek-openrouter.example.yaml}"
TARGET_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
SOURCE_ENV="${SOURCE_ENV:-.hermes/env.example}"
LOCAL_ENV="${LOCAL_ENV:-.env.local}"
TARGET_ENV="${HERMES_ENV:-$HOME/.hermes/.env}"
MODE="${MODE:-append}"
SYNC_FROM_LOCAL_ENV=true

usage() {
  cat <<'USAGE'
Aegis Alpha Hermes provider config installer

Usage:
  scripts/install_hermes_provider_config.sh [options]

Options:
  --target-config PATH   Hermes config path. Defaults to ~/.hermes/config.yaml.
  --target-env PATH      Hermes env path. Defaults to ~/.hermes/.env.
  --local-env PATH       Local project env file. Defaults to .env.local.
  --replace-config       Replace target config with provider example.
  --append-config        Append provider example to existing config. Default.
  --sync-from-local-env  Copy supported provider keys from local env. Default.
  --no-sync-from-local-env
                         Do not copy provider keys from local env.
  -h, --help             Show this help.

Notes:
  - OpenRouter is the primary provider.
  - DeepSeek direct is the fallback provider.
  - Do not use OpenRouter to call DeepSeek when direct DeepSeek is available.
  - Existing files are backed up before mutation.
  - Real API keys are copied only from the local env file when present.
  - Key values are never printed.
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
    --local-env)
      LOCAL_ENV="$2"
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
    --sync-from-local-env)
      SYNC_FROM_LOCAL_ENV=true
      shift
      ;;
    --no-sync-from-local-env)
      SYNC_FROM_LOCAL_ENV=false
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

sync_env_key() {
  local key="$1"
  local value

  value="$(grep -E "^${key}=" "$LOCAL_ENV" | tail -n 1 | sed "s/^${key}=//" || true)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"

  if [[ -z "$value" ]]; then
    return 0
  fi

  if grep -q "^${key}=" "$TARGET_ENV"; then
    tmp_file="$(mktemp "${TMPDIR:-/tmp}/hermes-env.XXXXXX")"
    awk -v key="$key" -v value="$value" 'BEGIN { prefix = key "=" } index($0, prefix) == 1 { print key "=" value; next } { print }' "$TARGET_ENV" > "$tmp_file"
    mv "$tmp_file" "$TARGET_ENV"
  else
    echo "${key}=${value}" >> "$TARGET_ENV"
  fi

  echo "Synced $key from $LOCAL_ENV"
}

if [[ "$SYNC_FROM_LOCAL_ENV" == true ]]; then
  if [[ -f "$LOCAL_ENV" ]]; then
    sync_env_key "DEEPSEEK_API_KEY"
    sync_env_key "OPENROUTER_API_KEY"
    chmod 600 "$TARGET_ENV" 2>/dev/null || true
  else
    echo "Local env not found, skipped provider key sync: $LOCAL_ENV"
  fi
fi

echo "Installed Hermes provider config scaffold:"
echo "  config: $TARGET_CONFIG"
echo "  env:    $TARGET_ENV"
echo
echo "Provider keys may be synced from $LOCAL_ENV. Edit $TARGET_ENV if values are still empty."
