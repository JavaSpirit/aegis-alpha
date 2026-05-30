from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def test_apply_migrations_creates_initial_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "aegis_alpha.db"

    version = apply_migrations(db_path)

    assert version >= 1
    assert current_version(db_path) == version
    assert {
        "schema_versions",
        "market_events",
        "signal_snapshots",
        "candidate_scores",
        "agent_reviews",
        "agent_review_corrections",
        "correction_action_proposals",
        "correction_action_decisions",
        "provider_runs",
        "review_outcomes",
    }.issubset(_table_names(db_path))


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "aegis_alpha.db"

    first = apply_migrations(db_path)
    second = apply_migrations(db_path)

    assert second == first
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT version FROM schema_versions").fetchall()
    assert len(rows) == first


def test_migration_0002_creates_theme_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "aegis_alpha.db"

    apply_migrations(db_path)

    names = _table_names(db_path)
    assert "theme_leaders" in names
    assert "limit_up_ladder" in names
    assert current_version(db_path) >= 2
