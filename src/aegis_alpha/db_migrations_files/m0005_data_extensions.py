from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dragon_tiger_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            list_reason TEXT NOT NULL DEFAULT '',
            total_buy_cny REAL NOT NULL DEFAULT 0,
            total_sell_cny REAL NOT NULL DEFAULT 0,
            net_amount_cny REAL NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day)
        );
        CREATE INDEX IF NOT EXISTS idx_dragon_tiger_day
            ON dragon_tiger_records (trading_day);
        CREATE INDEX IF NOT EXISTS idx_dragon_tiger_symbol_day
            ON dragon_tiger_records (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS contrarian_pool_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day TEXT NOT NULL,
            pool_kind TEXT NOT NULL,
            symbol TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(trading_day, pool_kind, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_contrarian_pool_day_kind
            ON contrarian_pool_snapshots (trading_day, pool_kind);

        CREATE TABLE IF NOT EXISTS capital_flow_slices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            window TEXT NOT NULL,
            big_order_net_inflow_cny REAL NOT NULL DEFAULT 0,
            main_capital_net_inflow_cny REAL NOT NULL DEFAULT 0,
            retail_capital_net_inflow_cny REAL NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day, window)
        );
        CREATE INDEX IF NOT EXISTS idx_capital_flow_symbol_day
            ON capital_flow_slices (symbol, trading_day);
        """
    )
