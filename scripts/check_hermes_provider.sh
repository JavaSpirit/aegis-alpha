#!/usr/bin/env bash
set -euo pipefail

HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
HERMES_ENV="${HERMES_ENV:-$HOME/.hermes/.env}"

echo "Hermes provider check"
echo

if [[ -f "$HERMES_ENV" ]]; then
  echo "[ok] Hermes env exists: $HERMES_ENV"
  if grep -q "^DEEPSEEK_API_KEY=." "$HERMES_ENV"; then
    echo "[ok] DEEPSEEK_API_KEY appears to be set"
  elif grep -q "^DEEPSEEK_API_KEY=" "$HERMES_ENV"; then
    echo "[warn] DEEPSEEK_API_KEY exists but is empty"
  else
    echo "[warn] DEEPSEEK_API_KEY missing"
  fi

  if grep -q "^OPENROUTER_API_KEY=." "$HERMES_ENV"; then
    echo "[ok] OPENROUTER_API_KEY appears to be set"
  elif grep -q "^OPENROUTER_API_KEY=" "$HERMES_ENV"; then
    echo "[info] OPENROUTER_API_KEY exists but is empty"
  else
    echo "[info] OPENROUTER_API_KEY missing; optional"
  fi
else
  echo "[warn] Hermes env missing: $HERMES_ENV"
fi

if [[ -f "$HERMES_CONFIG" ]]; then
  echo "[ok] Hermes config exists: $HERMES_CONFIG"
  if grep -q 'provider: "deepseek"' "$HERMES_CONFIG" || grep -q "provider: deepseek" "$HERMES_CONFIG"; then
    echo "[ok] Hermes config selects DeepSeek direct"
  else
    echo "[warn] Hermes config does not visibly select provider: deepseek"
  fi

  if grep -q 'provider: "openrouter"' "$HERMES_CONFIG" || grep -q "provider: openrouter" "$HERMES_CONFIG"; then
    echo "[info] Hermes config includes OpenRouter as optional provider/fallback"
  fi
else
  echo "[warn] Hermes config missing: $HERMES_CONFIG"
fi

echo
echo "Provider policy:"
echo "  primary: DeepSeek direct"
echo "  optional: OpenRouter for non-DeepSeek contrast/fallback"

