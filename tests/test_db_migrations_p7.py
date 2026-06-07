from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p7_grade_at_pick_is_nullable(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        columns = {
            row[1]: row  # name -> (cid, name, type, notnull, dflt_value, pk)
            for row in conn.execute(
                "PRAGMA table_info(historical_candidate_snapshots)"
            ).fetchall()
        }
    assert "grade_at_pick" in columns, "grade_at_pick column must exist"
    # notnull flag: 0 = nullable, 1 = NOT NULL
    assert columns["grade_at_pick"][3] == 0, "grade_at_pick must be nullable (notnull=0)"
    assert current_version(db) >= 7


def test_p7_data_preservation_both_null_and_nonnull(tmp_path: Path) -> None:
    """Verify the column accepts both a real grade value and NULL after migration."""
    db = tmp_path / "test.db"
    apply_migrations(db)
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with sqlite3.connect(db) as conn:
        # Row with a real grade
        conn.execute(
            """
            INSERT INTO historical_candidate_snapshots
                (symbol, trading_day, grade_at_pick, theme, theme_role,
                 previous_consecutive_boards, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("000001.SZ", "2026-01-02", "A", "new-energy", "leader", 2, "{}", now),
        )
        # Row with NULL grade
        conn.execute(
            """
            INSERT INTO historical_candidate_snapshots
                (symbol, trading_day, grade_at_pick, theme, theme_role,
                 previous_consecutive_boards, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("000002.SZ", "2026-01-02", None, "robotics", "follower", 1, "{}", now),
        )

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT symbol, grade_at_pick FROM historical_candidate_snapshots ORDER BY symbol"
        ).fetchall()

    assert len(rows) == 2
    assert rows[0] == ("000001.SZ", "A")
    assert rows[1] == ("000002.SZ", None)
