from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS theme_leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            leader_symbol TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_theme_leaders_theme_day
            ON theme_leaders (theme, trading_day);

        CREATE TABLE IF NOT EXISTS limit_up_ladder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            consecutive_boards INTEGER NOT NULL,
            height_label TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, trading_day)
        );
        CREATE INDEX IF NOT EXISTS idx_limit_up_ladder_day_height
            ON limit_up_ladder (trading_day, consecutive_boards);
        """
    )
