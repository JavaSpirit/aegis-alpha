from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS outcome_attributions (
            attribution_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            primary_tag TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_outcome_attributions_symbol_day
            ON outcome_attributions (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS historical_candidate_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            grade_at_pick TEXT NOT NULL,
            theme TEXT,
            theme_role TEXT,
            previous_consecutive_boards INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day)
        );
        CREATE INDEX IF NOT EXISTS idx_historical_snapshots_symbol_day
            ON historical_candidate_snapshots (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS backtest_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            start_day TEXT NOT NULL,
            end_day TEXT NOT NULL,
            sample_size INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_backtest_runs_status
            ON backtest_runs (status, started_at);
        """
    )
