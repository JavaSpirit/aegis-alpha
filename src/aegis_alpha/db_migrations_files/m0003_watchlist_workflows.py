from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            closed_at TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_watchlists_owner_status
            ON watchlists (owner, status);

        CREATE TABLE IF NOT EXISTS watchlist_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watchlist_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            added_at TEXT NOT NULL,
            last_action TEXT NOT NULL,
            last_action_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(watchlist_id, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_watchlist_entries_watchlist
            ON watchlist_entries (watchlist_id);

        CREATE TABLE IF NOT EXISTS seal_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_seal_timeline_symbol_day
            ON seal_timeline_events (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS agent_alerts (
            alert_id TEXT PRIMARY KEY,
            event_id TEXT,
            symbol TEXT,
            theme TEXT,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_status_created
            ON agent_alerts (status, created_at);

        CREATE TABLE IF NOT EXISTS theme_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day TEXT NOT NULL,
            theme TEXT NOT NULL,
            rank INTEGER NOT NULL,
            score REAL NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(trading_day, theme)
        );
        CREATE INDEX IF NOT EXISTS idx_theme_rankings_day_rank
            ON theme_rankings (trading_day, rank);
        """
    )
