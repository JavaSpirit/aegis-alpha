from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS suspended_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            suspension_start_day TEXT NOT NULL,
            suspension_end_day TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, suspension_start_day)
        );
        CREATE INDEX IF NOT EXISTS idx_suspended_day
            ON suspended_stocks (suspension_start_day);
        CREATE INDEX IF NOT EXISTS idx_suspended_symbol
            ON suspended_stocks (symbol);
        """
    )
