from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """Create selection_audits table for closed-loop strategy validation (二期A #3)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS selection_audits (
            audit_id TEXT PRIMARY KEY,
            as_of_day TEXT NOT NULL,
            picks_json TEXT NOT NULL DEFAULT '[]',
            rejected_json TEXT NOT NULL DEFAULT '[]',
            baseline_json TEXT NOT NULL DEFAULT '{}',
            equals_baseline INTEGER NOT NULL DEFAULT 0,
            confidence_label TEXT NOT NULL DEFAULT 'exploratory',
            candidate_pool_size INTEGER NOT NULL DEFAULT 0,
            provider TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_selection_audits_as_of_day
            ON selection_audits (as_of_day);
        """
    )
