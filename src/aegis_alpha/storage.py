from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from aegis_alpha.models import (
    AgentCorrectionAction,
    AgentCorrectionSummary,
    AgentReview,
    AgentReviewCorrection,
    CandidateOutcomeReview,
    MarketEvent,
    RunnerStatus,
    SignalSnapshot,
)

SH_TZ = ZoneInfo("Asia/Shanghai")


def default_data_dir() -> Path:
    return Path(os.environ.get("AEGIS_ALPHA_DATA_DIR", "data")).expanduser()


def default_db_path() -> Path:
    return Path(os.environ.get("AEGIS_ALPHA_DB_PATH", default_data_dir() / "aegis_alpha.db")).expanduser()


def default_runner_status_path() -> Path:
    return Path(
        os.environ.get("AEGIS_ALPHA_RUNNER_STATUS_PATH", default_data_dir() / "runner_status.json")
    ).expanduser()


def now_iso() -> str:
    return datetime.now(SH_TZ).isoformat(timespec="seconds")


def current_freshness_status(provider_timestamp: str, max_age_seconds: int = 180) -> str:
    if not provider_timestamp:
        return "unknown"
    try:
        provider_dt = datetime.fromisoformat(provider_timestamp)
    except ValueError:
        return "unknown"
    if provider_dt.tzinfo is None:
        provider_dt = provider_dt.replace(tzinfo=SH_TZ)
    age_seconds = abs((datetime.now(SH_TZ) - provider_dt).total_seconds())
    return "fresh" if age_seconds <= max_age_seconds else "stale"


def refresh_snapshot_freshness(snapshot: SignalSnapshot, max_age_seconds: int = 180) -> SignalSnapshot:
    status = current_freshness_status(snapshot.provider_timestamp or snapshot.data_timestamp, max_age_seconds)
    if status == snapshot.freshness_status:
        return snapshot
    notes = list(snapshot.notes)
    notes.append(f"freshness_status_refreshed_at={now_iso()}")
    data = snapshot.model_dump()
    data["freshness_status"] = status
    data["notes"] = notes
    return SignalSnapshot.model_validate(data)


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

    def signal_snapshot_count(self, symbol: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM signal_snapshots"
        params: list[object] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    def market_event_count(self, event_type: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM market_events"
        params: list[object] = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0

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
        return refresh_snapshot_freshness(SignalSnapshot.model_validate_json(row[0])) if row else None

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

    def save_provider_run(
        self,
        *,
        provider: str,
        run_type: str,
        status: str,
        payload: dict,
        started_at: str = "",
        ended_at: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_runs (
                    provider, run_type, status, started_at, ended_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    run_type,
                    status,
                    started_at,
                    ended_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def save_agent_review(self, review: AgentReview) -> AgentReview:
        if not review.created_at:
            review.created_at = now_iso()
        if not review.review_id:
            review.review_id = f"{review.run_type}:{review.target_time}:{review.created_at}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_reviews (event_id, symbol, provider, model, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    ",".join(review.symbols),
                    review.provider,
                    review.model,
                    review.model_dump_json(),
                ),
            )
        return review

    def recent_agent_reviews(self, limit: int = 20) -> list[AgentReview]:
        safe_limit = max(1, min(int(limit or 20), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM agent_reviews
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [AgentReview.model_validate_json(row[0]) for row in rows]

    def save_agent_review_correction(self, correction: AgentReviewCorrection) -> AgentReviewCorrection:
        if not correction.created_at:
            correction.created_at = now_iso()
        if not correction.correction_id:
            correction.correction_id = (
                f"{correction.review_id}:{correction.symbol or 'ALL'}:"
                f"{correction.correction_type}:{correction.created_at}"
            )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_review_corrections (
                    correction_id, review_id, symbol, correction_type,
                    expected_grade, comment, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correction.correction_id,
                    correction.review_id,
                    correction.symbol,
                    correction.correction_type,
                    correction.expected_grade,
                    correction.comment,
                    correction.created_at,
                    correction.model_dump_json(),
                ),
            )
        return correction

    def recent_agent_review_corrections(
        self,
        limit: int = 20,
        review_id: str | None = None,
    ) -> list[AgentReviewCorrection]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = "SELECT payload_json FROM agent_review_corrections"
        params: list[object] = []
        if review_id:
            query += " WHERE review_id = ?"
            params.append(review_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AgentReviewCorrection.model_validate_json(row[0]) for row in rows]

    def agent_correction_summary(self, limit: int = 100) -> AgentCorrectionSummary:
        corrections = self.recent_agent_review_corrections(limit=limit)
        by_type: dict[str, int] = {}
        by_symbol: dict[str, int] = {}
        for correction in corrections:
            by_type[correction.correction_type] = by_type.get(correction.correction_type, 0) + 1
            if correction.symbol:
                by_symbol[correction.symbol] = by_symbol.get(correction.symbol, 0) + 1

        suggested_memory = ""
        suggested_skill_patch = ""
        recommended_actions: list[AgentCorrectionAction] = []
        recommended_next_action = "No correction pattern yet. Keep collecting chat-based feedback."
        data_skill_patch = (
            "Before grading an Aegis Alpha candidate, verify data_mode, freshness_status, "
            "data_timestamp, and provider_timestamp. If data is unavailable or stale, halt or cap the grade."
        )
        strategy_skill_patch = (
            "When repeated user corrections mark a strategy judgment as too aggressive, lower the grade unless "
            "fresh speed, big-order inflow, seal amount, orderbook quality, and same-theme linkage all support the conclusion."
        )
        expression_skill_patch = (
            "Express Aegis Alpha outputs as observation, rating rationale, trigger conditions, and avoid conditions; "
            "do not phrase them as direct buy/sell commands."
        )

        if by_type.get("UNIT_ERROR", 0):
            suggested_memory = (
                "Aegis Alpha agent reviews must treat `_pct` fields as already-percent values, "
                "`_ratio` fields as ratios, `_cny` fields as CNY amounts, and `_score` fields as 0-100 internal scores."
            )
            recommended_actions.append(
                AgentCorrectionAction(
                    target="memory",
                    priority="high",
                    status="ready_to_apply",
                    correction_type="UNIT_ERROR",
                    evidence_count=by_type["UNIT_ERROR"],
                    reason="Unit misunderstandings are stable agent context and should be remembered across sessions.",
                    action="Ask Hermes to save a concise project memory after human confirmation.",
                    suggested_patch=suggested_memory,
                )
            )
            recommended_next_action = "Ask Hermes to save the suggested memory if this correction was valid."

        if by_type.get("DATA_ERROR", 0):
            suggested_memory = (
                suggested_memory
                or "When Aegis Alpha reports stale, unavailable, or synthetic data, agent conclusions must be capped and must not infer missing live metrics."
            )
            suggested_skill_patch = (
                data_skill_patch
            )
            recommended_actions.append(
                AgentCorrectionAction(
                    target="adapter",
                    priority="high",
                    status="needs_human_review",
                    correction_type="DATA_ERROR",
                    evidence_count=by_type["DATA_ERROR"],
                    reason="Data errors usually indicate adapter, provider, timestamp, or freshness issues rather than agent reasoning issues.",
                    action="Inspect the source adapter output and freshness metadata before changing strategy or skill behavior.",
                )
            )
            recommended_actions.append(
                AgentCorrectionAction(
                    target="skill",
                    priority="medium",
                    status="ready_to_apply",
                    correction_type="DATA_ERROR",
                    evidence_count=by_type["DATA_ERROR"],
                    reason="The agent should halt or downgrade when Aegis Alpha reports stale, empty, unavailable, or synthetic data.",
                    action="Patch the Aegis Alpha Hermes skill to reinforce data availability and freshness checks.",
                    suggested_patch=data_skill_patch,
                )
            )
            recommended_next_action = "Review the adapter/data source first, then update Hermes memory or skill only after the data issue is understood."

        if by_type.get("STRATEGY_ERROR", 0) >= 2:
            suggested_skill_patch = strategy_skill_patch
            recommended_actions.append(
                AgentCorrectionAction(
                    target="scoring_config",
                    priority="medium",
                    status="needs_human_review",
                    correction_type="STRATEGY_ERROR",
                    evidence_count=by_type["STRATEGY_ERROR"],
                    reason="Repeated strategy corrections suggest the rule weights or thresholds may be too optimistic.",
                    action="Review config/event_scoring.yaml and candidate grading rules against the corrected examples.",
                )
            )
            recommended_actions.append(
                AgentCorrectionAction(
                    target="skill",
                    priority="medium",
                    status="ready_to_apply",
                    correction_type="STRATEGY_ERROR",
                    evidence_count=by_type["STRATEGY_ERROR"],
                    reason="Repeated strategy corrections can also improve how the agent interprets rule scores and explains caution.",
                    action="Promote the stable strategy pattern into the Aegis Alpha Hermes skill after manual review.",
                    suggested_patch=strategy_skill_patch,
                )
            )
            recommended_next_action = "Promote this repeated strategy correction into the Aegis Alpha Hermes skill after manual review."
        elif by_type.get("STRATEGY_ERROR", 0):
            recommended_actions.append(
                AgentCorrectionAction(
                    target="review_only",
                    priority="low",
                    status="collect_more_evidence",
                    correction_type="STRATEGY_ERROR",
                    evidence_count=by_type["STRATEGY_ERROR"],
                    reason="A single strategy correction is useful evidence, but not enough to change scoring or skills.",
                    action="Collect at least one more similar correction before proposing scoring or skill changes.",
                )
            )

        if by_type.get("EXPRESSION_RISK", 0):
            suggested_skill_patch = suggested_skill_patch or expression_skill_patch
            recommended_actions.append(
                AgentCorrectionAction(
                    target="skill",
                    priority="high",
                    status="ready_to_apply",
                    correction_type="EXPRESSION_RISK",
                    evidence_count=by_type["EXPRESSION_RISK"],
                    reason="Risky wording is an agent behavior issue and should be corrected in the Hermes skill.",
                    action="Patch the skill output rules to avoid direct buy/sell/order language.",
                    suggested_patch=expression_skill_patch,
                )
            )
            recommended_next_action = "Patch the Hermes skill wording if this phrasing issue repeats."

        if by_type.get("OTHER", 0):
            recommended_actions.append(
                AgentCorrectionAction(
                    target="review_only",
                    priority="low",
                    status="collect_more_evidence",
                    correction_type="OTHER",
                    evidence_count=by_type["OTHER"],
                    reason="The correction type is not specific enough to route safely.",
                    action="Keep the correction as review evidence until a human reclassifies it.",
                )
            )

        return AgentCorrectionSummary(
            total_count=len(corrections),
            by_type=by_type,
            by_symbol=by_symbol,
            recent_corrections=corrections[:10],
            recommended_actions=recommended_actions,
            suggested_memory=suggested_memory,
            suggested_skill_patch=suggested_skill_patch,
            recommended_next_action=recommended_next_action,
        )


def write_runner_status(status: RunnerStatus, path: str | Path | None = None) -> Path:
    status_path = Path(path).expanduser() if path else default_runner_status_path()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(status.model_dump_json(indent=2))
    return status_path


def read_runner_status(path: str | Path | None = None) -> RunnerStatus | None:
    status_path = Path(path).expanduser() if path else default_runner_status_path()
    if not status_path.exists():
        return None
    return RunnerStatus.model_validate_json(status_path.read_text())


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
