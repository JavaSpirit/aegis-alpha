from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.storage import AegisAlphaStore


def test_selection_audits_table_exists(tmp_path: Path):
    db = tmp_path / "t.db"
    AegisAlphaStore(str(db))  # applies migrations on init
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='selection_audits'"
        ).fetchone()
    assert row is not None


def test_selection_audits_columns(tmp_path: Path):
    db = tmp_path / "t.db"
    AegisAlphaStore(str(db))
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(selection_audits)").fetchall()}
    expected = {"audit_id", "as_of_day", "picks_json", "rejected_json", "baseline_json",
                "equals_baseline", "confidence_label", "candidate_pool_size",
                "provider", "model", "created_at"}
    assert expected <= cols
