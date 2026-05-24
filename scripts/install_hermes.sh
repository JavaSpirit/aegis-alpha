#!/usr/bin/env bash
set -euo pipefail

INSTALLER_URL="${HERMES_INSTALLER_URL:-https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh}"
RUN_INSTALL=false
BRANCH=""
INSTALL_DIR=""
HERMES_HOME_DIR=""
SKIP_SETUP=false

usage() {
  cat <<'USAGE'
Aegis Alpha Hermes installer helper

This script helps install or verify Hermes Agent without forking or modifying
Hermes. By default it only prints the action it would take.

Usage:
  scripts/install_hermes.sh [options]

Options:
  --run                 Download and execute the official Hermes installer.
  --branch NAME         Pass --branch NAME to the Hermes installer.
  --dir PATH            Pass --dir PATH to the Hermes installer.
  --hermes-home PATH    Pass --hermes-home PATH to the Hermes installer.
  --skip-setup          Pass --skip-setup to the Hermes installer.
  -h, --help            Show this help.

Examples:
  scripts/install_hermes.sh
  scripts/install_hermes.sh --run
  scripts/install_hermes.sh --run --skip-setup
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run)
      RUN_INSTALL=true
      shift
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --hermes-home)
      HERMES_HOME_DIR="$2"
      shift 2
      ;;
    --skip-setup)
      SKIP_SETUP=true
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

if command -v hermes >/dev/null 2>&1; then
  echo "Hermes is already available: $(command -v hermes)"
  hermes --version 2>/dev/null || true
  exit 0
fi

args=()
if [[ -n "$BRANCH" ]]; then
  args+=(--branch "$BRANCH")
fi
if [[ -n "$INSTALL_DIR" ]]; then
  args+=(--dir "$INSTALL_DIR")
fi
if [[ -n "$HERMES_HOME_DIR" ]]; then
  args+=(--hermes-home "$HERMES_HOME_DIR")
fi
if [[ "$SKIP_SETUP" == true ]]; then
  args+=(--skip-setup)
fi

if [[ "$RUN_INSTALL" != true ]]; then
  echo "Hermes is not installed."
  echo
  echo "Dry run only. To install Hermes with the official installer, run:"
  printf '  %q --run' "$0"
  if [[ ${#args[@]:-0} -gt 0 ]]; then
    for arg in "${args[@]}"; do
      printf ' %q' "$arg"
    done
  fi
  echo
  echo
  echo "Official installer URL:"
  echo "  $INSTALLER_URL"
  exit 0
fi

tmp_file="$(mktemp "${TMPDIR:-/tmp}/hermes-install.XXXXXX.sh")"
trap 'rm -f "$tmp_file"' EXIT

echo "Downloading official Hermes installer:"
echo "  $INSTALLER_URL"
curl -fsSL "$INSTALLER_URL" -o "$tmp_file"
chmod +x "$tmp_file"

echo "Running Hermes installer from:"
echo "  $tmp_file"
if [[ ${#args[@]:-0} -gt 0 ]]; then
  bash "$tmp_file" "${args[@]}"
else
  bash "$tmp_file"
fi
