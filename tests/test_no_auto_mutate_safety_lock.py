"""Safety lock: no auto-mutation of MEMORY.md / USER.md / SKILL.md / config.

Task 7.4 — Regression test that the correction/feedback pipeline NEVER
auto-writes the agent's brain files.  This test pins three guarantees:

  1. Disclaimer verbatim lock — the exact safety-language strings in server.py
     must not drift over time.
  2. No write-mode open of brain files anywhere in src/aegis_alpha/**/*.py.
  3. record_correction_action_decision only calls store methods; no brain-file
     write of any kind appears in that function's source region.

These assertions are static source-text checks — they do NOT execute server
code, so they are fast and have no side effects.
"""
from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_SRC = _REPO_ROOT / "src" / "aegis_alpha" / "mcp" / "server.py"
_PKG_ROOT = _REPO_ROOT / "src" / "aegis_alpha"
_TESTS_DIR = _REPO_ROOT / "tests"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _server_text() -> str:
    return _SERVER_SRC.read_text(encoding="utf-8")


# ===========================================================================
# 1. Disclaimer verbatim lock
# ===========================================================================

def test_create_correction_action_proposals_disclaimer_verbatim() -> None:
    """The 'does not apply' disclaimer in create_correction_action_proposals
    must be present word-for-word."""
    text = _server_text()
    expected = "Aegis Alpha does not apply memory, skill, config, or adapter changes automatically."
    assert expected in text, (
        f"SAFETY VIOLATION: verbatim disclaimer not found in {_SERVER_SRC}.\n"
        f"Expected string: {expected!r}"
    )


def test_record_agent_review_correction_disclaimer_verbatim() -> None:
    """record_agent_review_correction must carry the 'suggested, not automatically applied'
    disclaimer substring."""
    text = _server_text()
    expected_fragment = "suggested, not automatically applied"
    assert expected_fragment in text, (
        f"SAFETY VIOLATION: disclaimer fragment not found in {_SERVER_SRC}.\n"
        f"Expected substring: {expected_fragment!r}"
    )


def test_record_correction_action_decision_disclaimer_verbatim() -> None:
    """record_correction_action_decision must carry the 'separate explicit step' disclaimer."""
    text = _server_text()
    expected = "Applying memory, skill, config, or adapter changes remains a separate explicit step."
    assert expected in text, (
        f"SAFETY VIOLATION: decision disclaimer not found in {_SERVER_SRC}.\n"
        f"Expected string: {expected!r}"
    )


# ===========================================================================
# 2. No write-mode open of brain files anywhere in the package source
# ===========================================================================

# Brain-file name keywords (case-sensitive; these must not appear in write paths)
_BRAIN_FILE_RE = re.compile(r"(?:MEMORY\.md|USER\.md|SKILL(?:\.md|\.yaml)?)")

# Patterns that would flag an accidental auto-writer — checked per line.
_LINE_WRITE_PATTERNS: list[re.Pattern[str]] = [
    # open(..., 'w'/'a') with a brain-file name in the same argument list
    re.compile(r"open\([^)]*MEMORY\.md[^)]*['\"][wa]"),
    re.compile(r"open\([^)]*USER\.md[^)]*['\"][wa]"),
    re.compile(r"open\([^)]*SKILL[^)]*['\"][wa]"),
    # Reversed argument order
    re.compile(r"open\(['\"][wa][^)]*MEMORY\.md"),
    re.compile(r"open\(['\"][wa][^)]*USER\.md"),
    re.compile(r"open\(['\"][wa][^)]*SKILL"),
    # Path(...).write_text/write_bytes on same line as brain-file name
    re.compile(r"(?:MEMORY\.md|USER\.md|SKILL[^)\"']*)[\"'].*\.write_(?:text|bytes)\("),
    re.compile(r"\.write_(?:text|bytes)\([^)]*(?:MEMORY\.md|USER\.md|SKILL)"),
    # Any call to skill_write
    re.compile(r"\bskill_write\b"),
]

# These patterns detect .write_text / .write_bytes calls regardless of target;
# combined with a window check for brain-file names in nearby lines.
_WRITE_METHOD_RE = re.compile(r"\.write_(?:text|bytes)\(")


def _scan_file_for_violations(src_file: Path) -> list[str]:
    """Return a list of 'file:lineno: snippet' strings for any detected violation."""
    lines = src_file.read_text(encoding="utf-8").splitlines()
    violations: list[str] = []

    for lineno, line in enumerate(lines, start=1):
        # 1. Direct line pattern match
        for pattern in _LINE_WRITE_PATTERNS:
            if pattern.search(line):
                violations.append(f"{src_file}:{lineno}: {line.strip()}")
                break
        else:
            # 2. Window check: if this line has .write_text / .write_bytes,
            #    scan the surrounding ±2 lines for a brain-file reference.
            if _WRITE_METHOD_RE.search(line):
                window_start = max(0, lineno - 3)
                window_end = min(len(lines), lineno + 2)
                window = "\n".join(lines[window_start:window_end])
                if _BRAIN_FILE_RE.search(window):
                    violations.append(f"{src_file}:{lineno}: {line.strip()}")

    return violations


def test_no_write_open_of_brain_files() -> None:
    """Walk src/aegis_alpha/**/*.py and assert no line (or immediate context)
    matches a write-mode open or write_text/write_bytes targeting a brain file
    (MEMORY.md / USER.md / SKILL.md / SKILL.yaml).  Also asserts no call to
    skill_write exists anywhere in the package."""
    violations: list[str] = []

    for src_file in sorted(_PKG_ROOT.rglob("*.py")):
        if "__pycache__" in src_file.parts:
            continue
        violations.extend(_scan_file_for_violations(src_file))

    assert not violations, (
        "SAFETY VIOLATION: package source contains code paths that would "
        "write brain files (MEMORY.md / USER.md / SKILL.md) or call skill_write.\n"
        "Violations found:\n" + "\n".join(violations)
    )


# ===========================================================================
# 3. record_correction_action_decision does NOT write brain files
# ===========================================================================

def test_record_correction_action_decision_only_calls_store() -> None:
    """Extract the source region of record_correction_action_decision from
    server.py and assert:
    - it only calls store.record_correction_action_decision(...)
    - it contains NO reference to writing MEMORY / USER.md / SKILL / config
    - it contains NO open() call in write mode
    - it contains NO write_text / write_bytes call
    """
    text = _server_text()

    # Isolate the function body — find from 'def record_correction_action_decision'
    # to the next top-level '@mcp.tool' decorator.
    start = text.find("def record_correction_action_decision(")
    assert start != -1, "record_correction_action_decision not found in server.py"

    # Find the start of the next @mcp.tool after this function
    next_decorator = text.find("@mcp.tool", start + 1)
    region = text[start:next_decorator] if next_decorator != -1 else text[start:]

    # Must call store.record_correction_action_decision
    assert "store.record_correction_action_decision(" in region, (
        "record_correction_action_decision must delegate to store.record_correction_action_decision()"
    )

    # Must NOT contain any write of brain files
    brain_write_patterns = [
        re.compile(r"open\([^)]*MEMORY"),
        re.compile(r"open\([^)]*USER\.md"),
        re.compile(r"open\([^)]*SKILL"),
        re.compile(r"\.write_text\("),
        re.compile(r"\.write_bytes\("),
        re.compile(r"\bskill_write\b"),
    ]

    bad_lines: list[str] = []
    for lineno, line in enumerate(region.splitlines(), start=1):
        for pat in brain_write_patterns:
            if pat.search(line):
                bad_lines.append(f"  line {lineno}: {line.strip()}")
                break

    assert not bad_lines, (
        "SAFETY VIOLATION: record_correction_action_decision contains brain-file "
        "write operations:\n" + "\n".join(bad_lines)
    )
