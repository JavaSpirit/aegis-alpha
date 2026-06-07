from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """Make grade_at_pick nullable in historical_candidate_snapshots.

    Program grading removed in phase 1A — grades are now agent/human-set in
    a later phase. Existing rows with a grade are preserved; new rows may have
    NULL grade_at_pick.
    """
    conn.executescript(
        """
        -- SQLite does not support ALTER COLUMN; recreate the table.
        CREATE TABLE IF NOT EXISTS historical_candidate_snapshots_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            grade_at_pick TEXT,
            theme TEXT,
            theme_role TEXT,
            previous_consecutive_boards INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day)
        );

        INSERT OR IGNORE INTO historical_candidate_snapshots_new
            (id, symbol, trading_day, grade_at_pick, theme, theme_role,
             previous_consecutive_boards, payload_json, created_at)
        SELECT id, symbol, trading_day, grade_at_pick, theme, theme_role,
               previous_consecutive_boards, payload_json, created_at
        FROM historical_candidate_snapshots;

        DROP TABLE historical_candidate_snapshots;

        ALTER TABLE historical_candidate_snapshots_new
            RENAME TO historical_candidate_snapshots;

        CREATE INDEX IF NOT EXISTS idx_historical_snapshots_symbol_day
            ON historical_candidate_snapshots (symbol, trading_day);
        """
    )
