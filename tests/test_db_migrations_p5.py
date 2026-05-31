from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p5_migration_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {
        "dragon_tiger_records",
        "contrarian_pool_snapshots",
        "capital_flow_slices",
    }.issubset(names)
    assert current_version(db) >= 5


def test_p5_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_dragon_tiger_day" in names
    assert "idx_dragon_tiger_symbol_day" in names
    assert "idx_contrarian_pool_day_kind" in names
    assert "idx_capital_flow_symbol_day" in names
