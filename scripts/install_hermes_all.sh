#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTALL_HERMES=true
INSTALL_SKILL=true
INSTALL_CONFIG=true
RUN_CHECK=true
REPLACE_CONFIG=false
HERMES_SKIP_SETUP=false

usage() {
  cat <<'USAGE'
Aegis Alpha one-click Hermes integration installer

Usage:
  scripts/install_hermes_all.sh [options]

Options:
  --skip-hermes       Do not install Hermes itself.
  --skip-skill        Do not install the second-board-radar Hermes skill.
  --skip-config       Do not install the reproducible Hermes project config.
  --skip-check        Do not run the final integration check.
  --replace-config    Kept for compatibility. Project config installs with
                      replacement after backing up existing config.
  --skip-setup        Pass --skip-setup to the official Hermes installer.
  -h, --help          Show this help.

Environment:
  HERMES_CONFIG       Hermes config path. Default: ~/.hermes/config.yaml
  HERMES_SKILLS_DIR   Hermes skills directory. Default: ~/.hermes/skills

Examples:
  scripts/install_hermes_all.sh
  scripts/install_hermes_all.sh --skip-setup
  scripts/install_hermes_all.sh --skip-hermes
  scripts/install_hermes_all.sh --replace-config
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-hermes)
      INSTALL_HERMES=false
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
  "$@"
}

cd "$REPO_ROOT"

echo "Aegis Alpha one-click Hermes integration installer"
echo "Workspace: $REPO_ROOT"

if [[ "$INSTALL_HERMES" == true ]]; then
  hermes_args=(--run)
  if [[ "$HERMES_SKIP_SETUP" == true ]]; then
    hermes_args+=(--skip-setup)
  fi
  run_step "Install or verify Hermes" "$SCRIPT_DIR/install_hermes.sh" "${hermes_args[@]}"
else
  echo
  echo "==> Install or verify Hermes"
  echo "Skipped by --skip-hermes"
fi

if [[ "$INSTALL_SKILL" == true ]]; then
  run_step "Install second-board-radar skill" "$SCRIPT_DIR/install_hermes_skill.sh"
else
  echo
  echo "==> Install second-board-radar skill"
  echo "Skipped by --skip-skill"
fi

if [[ "$INSTALL_CONFIG" == true ]]; then
  run_step "Install Hermes project config" "$SCRIPT_DIR/install_hermes_project_config.sh" --replace
else
  echo
  echo "==> Install Hermes project config"
  echo "Skipped by --skip-config"
fi

if [[ "$RUN_CHECK" == true ]]; then
  run_step "Check Hermes integration" "$SCRIPT_DIR/check_hermes_integration.sh"
else
  echo
  echo "==> Check Hermes integration"
  echo "Skipped by --skip-check"
fi

echo
echo "Done."
