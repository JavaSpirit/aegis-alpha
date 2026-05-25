#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"
VENV_PYTHON="$VENV_DIR/bin/python"

INSTALL_VENV=true
INSTALL_PROJECT=true
INSTALL_JVQUANT=true
INSTALL_HERMES=true
INSTALL_PROVIDER=true
INSTALL_SKILL=true
INSTALL_CONFIG=true
RUN_CHECK=true
REPLACE_CONFIG=false
HERMES_SKIP_SETUP=false
DRY_RUN=false

usage() {
  cat <<'USAGE'
Aegis Alpha one-click installer

Usage:
  scripts/install_all.sh [options]

Installs the local Python environment, Aegis Alpha package, jvQuant dependency,
Hermes, Aegis Alpha Hermes skill, Aegis Alpha MCP config, and then runs the
integration check.

Options:
  --dry-run           Print the planned steps without executing them.
  --skip-venv         Do not create or verify .venv.
  --skip-project      Do not install Aegis Alpha into .venv.
  --skip-jvquant      Do not install jvQuant market-data dependency.
  --skip-hermes       Do not install Hermes itself.
  --skip-provider     Do not install Hermes provider config scaffold.
  --skip-skill        Do not install the second-board-radar Hermes skill.
  --skip-config       Do not install the Aegis Alpha MCP config.
  --skip-check        Do not run the final integration check.
  --replace-config    Replace ~/.hermes/config.yaml instead of appending.
  --skip-setup        Pass --skip-setup to the official Hermes installer.
  --python PATH       Python executable used to create .venv. Default: python3.11.
  -h, --help          Show this help.

Environment:
  PYTHON_BIN          Python executable used to create .venv.
  VENV_DIR            Virtualenv directory. Default: ./ .venv under repo root.
  HERMES_CONFIG       Hermes config path. Default: ~/.hermes/config.yaml
  HERMES_SKILLS_DIR   Hermes skills directory. Default: ~/.hermes/skills

Examples:
  scripts/install_all.sh
  scripts/install_all.sh --dry-run
  scripts/install_all.sh --skip-hermes
  scripts/install_all.sh --replace-config
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-venv)
      INSTALL_VENV=false
      shift
      ;;
    --skip-project)
      INSTALL_PROJECT=false
      shift
      ;;
    --skip-jvquant)
      INSTALL_JVQUANT=false
      shift
      ;;
    --skip-hermes)
      INSTALL_HERMES=false
      shift
      ;;
    --skip-provider)
      INSTALL_PROVIDER=false
      shift
      ;;
    --skip-skill)
      INSTALL_SKILL=false
      shift
      ;;
    --skip-config)
      INSTALL_CONFIG=false
      shift
      ;;
    --skip-check)
      RUN_CHECK=false
      shift
      ;;
    --replace-config)
      REPLACE_CONFIG=true
      shift
      ;;
    --skip-setup)
      HERMES_SKIP_SETUP=true
      shift
      ;;
    --python)
      PYTHON_BIN="$2"
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

run_step() {
  local title="$1"
  shift
  echo
  echo "==> $title"
  if [[ "$DRY_RUN" == true ]]; then
    printf 'dry-run:'
    for arg in "$@"; do
      printf ' %q' "$arg"
    done
    echo
  else
    "$@"
  fi
}

skip_step() {
  local title="$1"
  local reason="$2"
  echo
  echo "==> $title"
  echo "Skipped: $reason"
}

cd "$REPO_ROOT"

echo "Aegis Alpha one-click installer"
echo "Workspace: $REPO_ROOT"
echo "Virtualenv: $VENV_DIR"

if [[ "$INSTALL_VENV" == true ]]; then
  if [[ -x "$VENV_PYTHON" ]]; then
    run_step "Verify Python virtualenv" "$VENV_PYTHON" --version
  else
    run_step "Create Python virtualenv" "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
else
  skip_step "Create or verify Python virtualenv" "--skip-venv"
fi

if [[ "$INSTALL_PROJECT" == true ]]; then
  run_step "Install Aegis Alpha package" "$VENV_PYTHON" -m pip install -e ".[dev]"
else
  skip_step "Install Aegis Alpha package" "--skip-project"
fi

if [[ "$INSTALL_JVQUANT" == true ]]; then
  run_step "Install jvQuant dependency" "$SCRIPT_DIR/install_jvquant.sh" --python "$VENV_PYTHON"
else
  skip_step "Install jvQuant dependency" "--skip-jvquant"
fi

if [[ "$INSTALL_HERMES" == true ]]; then
  hermes_args=(--run)
  if [[ "$HERMES_SKIP_SETUP" == true ]]; then
    hermes_args+=(--skip-setup)
  fi
  run_step "Install or verify Hermes" "$SCRIPT_DIR/install_hermes.sh" "${hermes_args[@]}"
else
  skip_step "Install or verify Hermes" "--skip-hermes"
fi

if [[ "$INSTALL_PROVIDER" == true ]]; then
  project_config_args=(--replace)
  run_step "Install Hermes project config" "$SCRIPT_DIR/install_hermes_project_config.sh" "${project_config_args[@]}"
else
  skip_step "Install Hermes project config" "--skip-provider"
fi

if [[ "$INSTALL_SKILL" == true ]]; then
  run_step "Install second-board-radar Hermes skill" "$SCRIPT_DIR/install_hermes_skill.sh"
else
  skip_step "Install second-board-radar Hermes skill" "--skip-skill"
fi

if [[ "$INSTALL_CONFIG" == true ]]; then
  if [[ "$INSTALL_PROVIDER" == true ]]; then
    echo
    echo "==> Install Aegis Alpha MCP config"
    echo "Skipped: included in project config"
  else
    config_args=()
    if [[ "$REPLACE_CONFIG" == true ]]; then
      config_args+=(--replace)
    else
      config_args+=(--append)
    fi
    run_step "Install Aegis Alpha MCP config" "$SCRIPT_DIR/install_hermes_mcp_config.sh" "${config_args[@]}"
  fi
else
  skip_step "Install Aegis Alpha MCP config" "--skip-config"
fi

if [[ "$RUN_CHECK" == true ]]; then
  run_step "Check Hermes integration" "$SCRIPT_DIR/check_hermes_integration.sh"
else
  skip_step "Check Hermes integration" "--skip-check"
fi

echo
echo "Done."
