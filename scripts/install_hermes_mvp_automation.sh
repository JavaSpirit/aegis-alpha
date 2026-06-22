#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SCRIPTS_DIR="${HERMES_SCRIPTS_DIR:-$HOME/.hermes/scripts}"
HERMES_ENV_FILE="${HERMES_ENV_FILE:-$HOME/.hermes/.env}"
PROJECT_ENV_FILE="${PROJECT_ENV_FILE:-$PROJECT_ROOT/.env.local}"
WEBHOOK_PORT="${WEBHOOK_PORT:-8644}"
WEBHOOK_ROUTE="${WEBHOOK_ROUTE:-aegis-alpha-alerts}"
WEBHOOK_URL="${WEBHOOK_URL:-http://127.0.0.1:${WEBHOOK_PORT}/webhooks/${WEBHOOK_ROUTE}}"
CREATE_JOBS=false
INSTALL_GATEWAY=false
CONFIGURE_MODEL=true

usage() {
  cat <<'USAGE'
Aegis Alpha Hermes-native automation installer

Installs thin context scripts for Hermes cron and optionally creates Hermes
cron/webhook jobs. Hermes remains the scheduler and event-triggered agent.
Aegis runner remains only the jvQuant WebSocket listener.

Usage:
  scripts/install_hermes_mvp_automation.sh [options]

Options:
  --create-jobs       Create Hermes cron jobs and webhook subscription.
  --install-gateway   Install/start Hermes gateway user service.
  --skip-model-config Do not set Hermes default model to DeepSeek direct.
  -h, --help          Show this help.

Environment:
  HERMES_SCRIPTS_DIR  Defaults to ~/.hermes/scripts.
  HERMES_ENV_FILE     Defaults to ~/.hermes/.env.
  PROJECT_ENV_FILE    Defaults to <repo>/.env.local.
  WEBHOOK_PORT        Defaults to 8644.
  WEBHOOK_ROUTE       Defaults to aegis-alpha-alerts.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create-jobs)
      CREATE_JOBS=true
      shift
      ;;
    --install-gateway)
      INSTALL_GATEWAY=true
      shift
      ;;
    --skip-model-config)
      CONFIGURE_MODEL=false
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

update_env_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  if grep -q "^${key}=" "$file"; then
    perl -0pi -e "s|^${key}=.*$|${key}=${value}|m" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

secret_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  fi
}

mkdir -p "$HERMES_SCRIPTS_DIR"

if [[ "$CONFIGURE_MODEL" == "true" ]]; then
  "$PROJECT_ROOT/scripts/switch_hermes_model.sh" deepseek
fi

cat > "$HERMES_SCRIPTS_DIR/aegis_alpha_mvp_prepare_context.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$PROJECT_ROOT"
PYTHONPATH=src .venv/bin/python scripts/mvp_pilot.py cron-context prepare
EOF

cat > "$HERMES_SCRIPTS_DIR/aegis_alpha_mvp_report_context.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$PROJECT_ROOT"
PYTHONPATH=src .venv/bin/python scripts/mvp_pilot.py cron-context report
EOF

chmod +x "$HERMES_SCRIPTS_DIR/aegis_alpha_mvp_prepare_context.sh"
chmod +x "$HERMES_SCRIPTS_DIR/aegis_alpha_mvp_report_context.sh"

echo "Installed Hermes context scripts:"
echo "  $HERMES_SCRIPTS_DIR/aegis_alpha_mvp_prepare_context.sh"
echo "  $HERMES_SCRIPTS_DIR/aegis_alpha_mvp_report_context.sh"

if [[ "$INSTALL_GATEWAY" == "true" ]]; then
  update_env_key "$HERMES_ENV_FILE" WEBHOOK_ENABLED true
  update_env_key "$HERMES_ENV_FILE" WEBHOOK_PORT "$WEBHOOK_PORT"
  update_env_key "$HERMES_ENV_FILE" WEBHOOK_SECRET "$(secret_hex)"
  export WEBHOOK_ENABLED=true
  export WEBHOOK_PORT="$WEBHOOK_PORT"
  export WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(grep '^WEBHOOK_SECRET=' "$HERMES_ENV_FILE" | tail -1 | cut -d= -f2-)}"
  hermes gateway install
fi

if [[ "$CREATE_JOBS" == "true" ]]; then
  WEBHOOK_SECRET_VALUE="$(secret_hex)"
  update_env_key "$PROJECT_ENV_FILE" AEGIS_ALPHA_HERMES_WEBHOOK_ENABLED true
  update_env_key "$PROJECT_ENV_FILE" HERMES_AEGIS_WEBHOOK_URL "$WEBHOOK_URL"
  update_env_key "$PROJECT_ENV_FILE" HERMES_AEGIS_WEBHOOK_SECRET "$WEBHOOK_SECRET_VALUE"
  export WEBHOOK_ENABLED=true
  export WEBHOOK_PORT="$WEBHOOK_PORT"
  export WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(grep '^WEBHOOK_SECRET=' "$HERMES_ENV_FILE" | tail -1 | cut -d= -f2-)}"

  hermes webhook remove "$WEBHOOK_ROUTE" >/dev/null 2>&1 || true
  hermes webhook subscribe "$WEBHOOK_ROUTE" \
    --events "aegis.buy_point_alert,aegis.selection_validation,aegis.seal_order_decay,aegis.big_order_inflow_spike,aegis.theme_divergence,aegis.theme_leader_break_board,aegis.sector_rotation,aegis.market_bottom_reversal" \
    --skills "second-board-radar" \
    --deliver "log" \
    --secret "$WEBHOOK_SECRET_VALUE" \
    --description "Aegis Alpha runner alerts trigger Hermes explanation" \
    --prompt "Aegis Alpha runner alert: {summary.title}
severity={summary.severity}
symbol={summary.symbol}
theme={summary.theme}
body={summary.body}
event_id={summary.event_id}

请使用 second-board-radar skill 的边界解释这个 alert：区分 exact/proxy/missing，不输出买卖指令；如果需要事实，请调用 Aegis Alpha MCP 工具。"

  hermes cron create \
    --name "aegis-alpha-daily-prepare" \
    --workdir "$PROJECT_ROOT" \
    --skill "second-board-radar" \
    --script "aegis_alpha_mvp_prepare_context.sh" \
    --deliver "local" \
    "10 16 * * 1-5" \
    "根据脚本输出的 hermes_cron_context，站在 suggested_as_of_day 收盘，调用 get_daily_strategy_candidate_pool，选择 Top3，并调用 record_selection_audit。完成后输出 audit_id、Top3、主要缺口和 runner 应订阅的 symbols。不要读取未来 target_day 结果，不要输出买卖指令。"

  hermes cron create \
    --name "aegis-alpha-morning-report" \
    --workdir "$PROJECT_ROOT" \
    --skill "second-board-radar" \
    --script "aegis_alpha_mvp_report_context.sh" \
    --deliver "local" \
    "5 10 * * 1-5" \
    "根据脚本输出的 hermes_cron_context，读取最新 selection audit、runner alerts、get_selection_trigger_validation，并解释今天早盘是否触发主策略。区分主策略触发、强势延续未触发、二板接力路径和未启动；不要输出买卖指令。"

  echo "Hermes cron jobs and webhook subscription created."
  echo "Runner webhook env written to: $PROJECT_ENV_FILE"
fi

echo "Next checks:"
echo "  hermes gateway status"
echo "  hermes cron list"
echo "  hermes webhook list"
