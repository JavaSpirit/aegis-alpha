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
  if awk '
    /^model:/ { in_model=1; next }
    /^[^[:space:]][^:]*:/ && in_model { in_model=0 }
    in_model && /provider:[[:space:]]*"?openrouter"?/ { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$HERMES_CONFIG"; then
    echo "[ok] Hermes primary provider is OpenRouter"
  else
    echo "[warn] Hermes primary provider does not visibly select OpenRouter"
  fi

  if grep -q 'provider: "deepseek"' "$HERMES_CONFIG" || grep -q "provider: deepseek" "$HERMES_CONFIG"; then
    echo "[ok] Hermes config includes DeepSeek direct fallback"
    if grep -q 'model: "deepseek-v4-pro"' "$HERMES_CONFIG" || grep -q "model: deepseek-v4-pro" "$HERMES_CONFIG"; then
      echo "[ok] DeepSeek fallback model is deepseek-v4-pro"
    else
      echo "[warn] DeepSeek fallback exists but model is not visibly deepseek-v4-pro"
    fi
  else
    echo "[warn] Hermes config does not visibly include DeepSeek direct fallback"
  fi
else
  echo "[warn] Hermes config missing: $HERMES_CONFIG"
fi

echo
echo "Provider policy:"
echo "  primary: OpenRouter"
echo "  fallback: DeepSeek direct deepseek-v4-pro"
