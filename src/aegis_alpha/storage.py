from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable

from aegis_alpha.models import CandidateOutcomeReview, MarketEvent, SignalSnapshot


def default_data_dir() -> Path:
    return Path(os.environ.get("AEGIS_ALPHA_DATA_DIR", "data")).expanduser()


def default_db_path() -> Path:
    return Path(os.environ.get("AEGIS_ALPHA_DB_PATH", default_data_dir() / "aegis_alpha.db")).expanduser()


class AegisAlphaStore:
    """Small local SQLite store for structured events, signals, and review records."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser() if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
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

    def save_market_events(self, events: Iterable[MarketEvent]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO market_events (
                    event_id, event_type, symbol, theme, score, confidence,
                    provider_timestamp, received_at, freshness_status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.event_id,
                        event.event_type,
                        event.symbol,
                        event.theme,
                        event.score,
                        event.confidence,
                        event.provider_timestamp,
                        event.received_at,
                        event.freshness_status,
                        event.model_dump_json(),
                    )
                    for event in events
                ],
            )

    def save_signal_snapshot(self, snapshot: SignalSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO signal_snapshots (
                    symbol, data_timestamp, provider_timestamp,
                    received_at, freshness_status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.symbol,
                    snapshot.data_timestamp,
                    snapshot.provider_timestamp,
                    snapshot.received_at,
                    snapshot.freshness_status,
                    snapshot.model_dump_json(),
                ),
            )

    def recent_market_events(self, limit: int = 20, event_type: str | None = None) -> list[MarketEvent]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = "SELECT payload_json FROM market_events"
        params: list[object] = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        query += " ORDER BY received_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [MarketEvent.model_validate_json(row[0]) for row in rows]

    def latest_signal_snapshot(self, symbol: str) -> SignalSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM signal_snapshots
                WHERE symbol = ?
                ORDER BY data_timestamp DESC, id DESC
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()
        return SignalSnapshot.model_validate_json(row[0]) if row else None

    def save_review_outcome(self, review: CandidateOutcomeReview) -> CandidateOutcomeReview:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO review_outcomes (symbol, trading_day, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol, trading_day) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (review.symbol, review.trading_day, review.model_dump_json()),
            )
        return review

    def get_review_outcome(self, symbol: str, trading_day: str) -> CandidateOutcomeReview:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM review_outcomes
                WHERE symbol = ? AND trading_day = ?
                LIMIT 1
                """,
                (symbol, trading_day),
            ).fetchone()
        if row:
            return CandidateOutcomeReview.model_validate_json(row[0])
        return CandidateOutcomeReview(
            symbol=symbol,
            trading_day=trading_day,
            notes=["No stored review outcome yet."],
        )


class ParquetSink:
    """Optional Parquet writer boundary; active when pyarrow is installed later."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).expanduser() if root else default_data_dir() / "parquet"
        self.root.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        try:
            import pyarrow  # noqa: F401
        except Exception:
            return {
                "enabled": False,
                "root": str(self.root),
                "reason": "pyarrow is not installed; Parquet persistence is reserved for the next storage phase.",
            }
        return {"enabled": True, "root": str(self.root)}

    def write_manifest(self, dataset: str, payload: dict) -> Path:
        path = self.root / dataset
        path.mkdir(parents=True, exist_ok=True)
        manifest = path / "_manifest.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return manifest
