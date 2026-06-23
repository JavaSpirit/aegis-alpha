from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """Create agent_observations table for the agent market observer layer.

    First-class auditable record of an agent's interpretation of market facts.
    Mirrors the selection_audits pattern: thin indexed columns + payload_json.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_observations (
            observation_id TEXT PRIMARY KEY,
            trading_day TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'periodic_market_scan',
            observation_type TEXT NOT NULL DEFAULT 'watchlist_observation',
            symbol TEXT NOT NULL DEFAULT '',
            theme TEXT NOT NULL DEFAULT '',
            stance TEXT NOT NULL DEFAULT 'monitor_only',
            confidence TEXT NOT NULL DEFAULT 'low',
            expires_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_agent_observations_trading_day
            ON agent_observations (trading_day);
        CREATE INDEX IF NOT EXISTS idx_agent_observations_day_type
            ON agent_observations (trading_day, observation_type);
        CREATE INDEX IF NOT EXISTS idx_agent_observations_symbol
            ON agent_observations (symbol);
        """
    )
