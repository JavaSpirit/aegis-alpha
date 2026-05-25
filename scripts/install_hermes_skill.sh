#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="${SKILL_NAME:-second-board-radar}"
SOURCE_DIR="${SOURCE_DIR:-.hermes/skills/$SKILL_NAME}"
TARGET_ROOT="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"
TARGET_DIR="$TARGET_ROOT/$SKILL_NAME"

usage() {
  cat <<'USAGE'
Aegis Alpha Hermes skill installer

Usage:
  scripts/install_hermes_skill.sh [options]

Options:
  --target PATH       Hermes skills directory. Defaults to ~/.hermes/skills.
  --skill NAME        Skill name. Defaults to second-board-radar.
  -h, --help          Show this help.

Examples:
  scripts/install_hermes_skill.sh
  scripts/install_hermes_skill.sh --target ~/.hermes/skills
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_ROOT="$2"
      TARGET_DIR="$TARGET_ROOT/$SKILL_NAME"
      shift 2
      ;;
    --skill)
      SKILL_NAME="$2"
      SOURCE_DIR=".hermes/skills/$SKILL_NAME"
      TARGET_DIR="$TARGET_ROOT/$SKILL_NAME"
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

if [[ ! -f "$SOURCE_DIR/SKILL.md" ]]; then
  echo "Skill not found: $SOURCE_DIR/SKILL.md" >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT"
rm -rf "$TARGET_DIR"
cp -R "$SOURCE_DIR" "$TARGET_DIR"

echo "Installed Hermes skill:"
echo "  $TARGET_DIR"
echo
echo "After starting Hermes, ask:"
echo "  Use the $SKILL_NAME skill to review today's second-board candidates."
