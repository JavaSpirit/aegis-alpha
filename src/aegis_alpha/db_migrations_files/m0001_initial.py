from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            symbol TEXT,
            theme TEXT,
            score REAL NOT NULL,
            confidence TEXT NOT NULL,
            provider_timestamp TEXT,
            received_at TEXT NOT NULL,
            freshness_status TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signal_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            data_timestamp TEXT NOT NULL,
            provider_timestamp TEXT,
            received_at TEXT,
            freshness_status TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidate_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT,
            grade TEXT,
            score REAL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            symbol TEXT,
            provider TEXT,
            model TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_review_corrections (
            correction_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL,
            symbol TEXT,
            correction_type TEXT NOT NULL,
            expected_grade TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correction_action_proposals (
            proposal_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            correction_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correction_action_decisions (
            decision_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT,
            decided_by TEXT,
            previous_status TEXT,
            new_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS provider_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS review_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, trading_day)
        );
        """
    )
