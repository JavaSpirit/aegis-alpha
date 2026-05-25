#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_CONFIG="${SOURCE_CONFIG:-$REPO_ROOT/.hermes/config/config.example.yaml}"
TARGET_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
SOURCE_ENV="${SOURCE_ENV:-$REPO_ROOT/.hermes/env.example}"
LOCAL_ENV="${LOCAL_ENV:-$REPO_ROOT/.env.local}"
TARGET_ENV="${HERMES_ENV:-$HOME/.hermes/.env}"
REPLACE=false

usage() {
  cat <<'USAGE'
Aegis Alpha reproducible Hermes project config installer

Usage:
  scripts/install_hermes_project_config.sh [options]

Options:
  --target-config PATH   Hermes config path. Defaults to ~/.hermes/config.yaml.
  --target-env PATH      Hermes env path. Defaults to ~/.hermes/.env.
  --local-env PATH       Local project env file. Defaults to .env.local.
  --replace              Replace target config. Default behavior also creates it
                         when missing, but refuses to overwrite unless --replace.
  -h, --help             Show this help.

This installs the complete reproducible Hermes config template for Aegis Alpha:
provider, fallback, and MCP server. The project root placeholder is resolved to
the current checkout path. API keys are synced from .env.local into ~/.hermes/.env
without printing values.
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
    --replace)
      REPLACE=true
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

  if [[ "$REPLACE" != true ]]; then
    echo "Target config already exists. Re-run with --replace to install the project template." >&2
    exit 1
  fi
fi

tmp_config="$(mktemp "${TMPDIR:-/tmp}/hermes-config.XXXXXX")"
awk -v root="$REPO_ROOT" '{ gsub(/__PROJECT_ROOT__/, root); print }' "$SOURCE_CONFIG" > "$tmp_config"
mv "$tmp_config" "$TARGET_CONFIG"

if [[ -f "$TARGET_ENV" ]]; then
  backup="${TARGET_ENV}.$(date +%Y%m%d%H%M%S).bak"
  cp "$TARGET_ENV" "$backup"
  echo "Backed up existing Hermes env:"
  echo "  $backup"
else
  cp "$SOURCE_ENV" "$TARGET_ENV"
fi

ensure_env_key() {
  local key="$1"

  if ! grep -q "^${key}=" "$TARGET_ENV"; then
    echo "${key}=" >> "$TARGET_ENV"
  fi
}

sync_env_key() {
  local key="$1"
  local value

  if [[ ! -f "$LOCAL_ENV" ]]; then
    return 0
  fi

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

ensure_env_key "DEEPSEEK_API_KEY"
ensure_env_key "OPENROUTER_API_KEY"
sync_env_key "DEEPSEEK_API_KEY"
sync_env_key "OPENROUTER_API_KEY"

chmod 600 "$TARGET_ENV" 2>/dev/null || true

echo "Installed reproducible Hermes project config:"
echo "  config: $TARGET_CONFIG"
echo "  env:    $TARGET_ENV"
