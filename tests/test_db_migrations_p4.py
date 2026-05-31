from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p4_migration_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"outcome_attributions", "historical_candidate_snapshots", "backtest_runs"}.issubset(names)
    assert current_version(db) >= 4


def test_p4_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_outcome_attributions_symbol_day" in names
    assert "idx_historical_snapshots_symbol_day" in names
    assert "idx_backtest_runs_status" in names


def test_p4_migration_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    first = apply_migrations(db)
    second = apply_migrations(db)
    assert second == first
