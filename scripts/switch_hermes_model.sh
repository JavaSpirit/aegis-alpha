#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"

usage() {
  cat <<'USAGE'
Switch Hermes default model mode.

Usage:
  scripts/switch_hermes_model.sh deepseek
  scripts/switch_hermes_model.sh openrouter

Modes:
  deepseek    Default automation mode. Uses DeepSeek direct.
  openrouter  Strong-model mode. Uses OpenRouter Claude Opus.
USAGE
}

case "$MODE" in
  deepseek)
    hermes config set model.provider deepseek
    hermes config set model.default deepseek-v4-pro
    hermes config set model.base_url ""
    hermes config set model.api_mode chat_completions
    ;;
  openrouter)
    hermes config set model.provider openrouter
    hermes config set model.default anthropic/claude-opus-4.7
    hermes config set model.base_url https://openrouter.ai/api/v1
    hermes config set model.api_mode chat_completions
    ;;
  -h|--help|"")
    usage
    exit 0
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    usage >&2
    exit 2
    ;;
esac

hermes gateway restart || true
echo "Hermes model mode switched to: $MODE"
