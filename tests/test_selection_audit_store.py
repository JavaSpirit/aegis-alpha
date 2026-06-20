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


from aegis_alpha.models import SelectionAudit, SelectionPick


def test_save_and_get_selection_audit(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    audit = SelectionAudit(
        audit_id="sa_test1", as_of_day="2026-06-19",
        picks=[SelectionPick(symbol="002491", rank=1)],
        candidate_pool_size=55,
    )
    store.save_selection_audit(audit)
    got = store.get_selection_audit_by_day("2026-06-19")
    assert got is not None
    assert got.audit_id == "sa_test1"
    assert got.picks[0].symbol == "002491"


def test_save_selection_audit_idempotent_upsert(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    a = SelectionAudit(audit_id="sa_dup", as_of_day="2026-06-19",
                       picks=[SelectionPick(symbol="002491", rank=1)])
    store.save_selection_audit(a)
    store.save_selection_audit(a)  # same audit_id → upsert, not duplicate
    assert store.count_selection_audit_days() == 1


def test_count_selection_audit_days_distinct(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    store.save_selection_audit(SelectionAudit(audit_id="s1", as_of_day="2026-06-18"))
    store.save_selection_audit(SelectionAudit(audit_id="s2", as_of_day="2026-06-19"))
    assert store.count_selection_audit_days() == 2


def test_get_selection_audit_missing_returns_none(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "t.db"))
    assert store.get_selection_audit_by_day("2099-01-01") is None
