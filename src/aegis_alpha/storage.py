from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from aegis_alpha.clock import SH_TZ, now_dt, now_iso
from aegis_alpha.db_migrations import apply_migrations
from aegis_alpha.models import (
    AgentAlert,
    AgentCorrectionAction,
    AgentCorrectionSummary,
    AgentReview,
    AgentReviewCorrection,
    BacktestRun,
    CandidateOutcomeReview,
    CapitalFlowSlice,
    ContrarianPoolEntry,
    CorrectionActionDecision,
    CorrectionActionProposal,
    DragonTigerRecord,
    HistoricalCandidateSnapshot,
    LadderEntry,
    MarketEvent,
    OutcomeAttribution,
    RejectedCandidate,
    RunnerStatus,
    SealTimelineEvent,
    SelectionAudit,
    SelectionPick,
    SignalSnapshot,
    SuspendedStock,
    ThemeLeader,
    Watchlist,
    WatchlistEntry,
)


def default_data_dir() -> Path:
    return Path(os.environ.get("AEGIS_ALPHA_DATA_DIR", "data")).expanduser()


def default_db_path() -> Path:
    return Path(os.environ.get("AEGIS_ALPHA_DB_PATH", default_data_dir() / "aegis_alpha.db")).expanduser()


def default_runner_status_path() -> Path:
    return Path(
        os.environ.get("AEGIS_ALPHA_RUNNER_STATUS_PATH", default_data_dir() / "runner_status.json")
    ).expanduser()


def _dump_audit_list(items: list) -> str:
    return json.dumps([i.model_dump() for i in items], ensure_ascii=False)


def current_freshness_status(provider_timestamp: str, max_age_seconds: int = 180) -> str:
    if not provider_timestamp:
        return "unknown"
    try:
        provider_dt = datetime.fromisoformat(provider_timestamp)
    except ValueError:
        return "unknown"
    if provider_dt.tzinfo is None:
        provider_dt = provider_dt.replace(tzinfo=SH_TZ)
    age_seconds = abs((now_dt() - provider_dt).total_seconds())
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
        apply_migrations(self.db_path)

    def init_db(self) -> None:
        """Public alias for _init_schema; useful in tests that need explicit init."""
        self._init_schema()

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

    def save_theme_leaders(self, leaders: Iterable[ThemeLeader]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO theme_leaders (
                    theme, trading_day, leader_symbol, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        leader.theme,
                        leader.trading_day,
                        leader.leader_symbol,
                        leader.model_dump_json(),
                    )
                    for leader in leaders
                ],
            )

    def latest_theme_leaders(self, theme: str = "", trading_day: str = "", limit: int = 20) -> list[ThemeLeader]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = "SELECT payload_json FROM theme_leaders"
        params: list[object] = []
        clauses = []
        if theme:
            clauses.append("theme = ?")
            params.append(theme)
        if trading_day:
            clauses.append("trading_day = ?")
            params.append(trading_day)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY trading_day DESC, id DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ThemeLeader.model_validate_json(row[0]) for row in rows]

    def save_ladder_entries(self, entries: Iterable[LadderEntry]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO limit_up_ladder (
                    symbol, trading_day, consecutive_boards, height_label, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.symbol,
                        entry.trading_day,
                        entry.consecutive_boards,
                        entry.height_label,
                        entry.model_dump_json(),
                    )
                    for entry in entries
                ],
            )

    def get_ladder_entry(self, symbol: str, trading_day: str) -> LadderEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM limit_up_ladder
                WHERE symbol = ? AND trading_day = ?
                """,
                (symbol, trading_day),
            ).fetchone()
        return LadderEntry.model_validate_json(row[0]) if row else None

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

    def list_review_outcomes(
        self, *, symbol: str = "", start_day: str = "", end_day: str = ""
    ) -> list[CandidateOutcomeReview]:
        clauses: list[str] = []
        params: list[object] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if start_day:
            clauses.append("trading_day >= ?")
            params.append(start_day)
        if end_day:
            clauses.append("trading_day <= ?")
            params.append(end_day)
        query = "SELECT payload_json FROM review_outcomes"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY trading_day ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CandidateOutcomeReview.model_validate_json(row[0]) for row in rows]

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

    def list_agent_reviews_between(self, start_day: str, end_day: str) -> list[AgentReview]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM agent_reviews
                ORDER BY id DESC
                """,
            ).fetchall()
        results: list[AgentReview] = []
        for row in rows:
            review = AgentReview.model_validate_json(row[0])
            target_day = review.target_time[:10] if review.target_time else ""
            if start_day <= target_day <= end_day:
                results.append(review)
        return results

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

        if by_type.get("CLIENT_OUTCOME", 0):
            client_memory = (
                "Client-confirmed outcome feedback: when the client verifies a realized result that "
                "contradicts or confirms an agent judgment, record the durable lesson as project memory "
                "AFTER human confirmation (e.g. a confirmed theme-lifecycle veto). Aegis Alpha only "
                "proposes this note; it does not write memory itself."
            )
            suggested_memory = suggested_memory or client_memory
            recommended_actions.append(
                AgentCorrectionAction(
                    target="memory",
                    priority="medium",
                    status="needs_human_review",   # NOT ready_to_apply — client outcomes need human confirmation
                    correction_type="CLIENT_OUTCOME",
                    evidence_count=by_type["CLIENT_OUTCOME"],
                    reason="Client-confirmed outcomes are durable lessons but must be human-reviewed before becoming memory.",
                    action="On human approval, ask Hermes to save the suggested memory note. Aegis Alpha does not write memory automatically.",
                    suggested_patch=client_memory,
                )
            )
            recommended_next_action = "Review the client-outcome feedback; if valid, ask Hermes to save the suggested memory after confirmation."

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

    def save_correction_action_proposals(
        self,
        summary: AgentCorrectionSummary,
        source: str = "agent_correction_summary",
    ) -> list[CorrectionActionProposal]:
        proposals: list[CorrectionActionProposal] = []
        timestamp = now_iso()
        with self._connect() as conn:
            for action in summary.recommended_actions:
                proposal_id = f"{source}:{action.target}:{action.correction_type}"
                row = conn.execute(
                    """
                    SELECT payload_json FROM correction_action_proposals
                    WHERE proposal_id = ?
                    LIMIT 1
                    """,
                    (proposal_id,),
                ).fetchone()
                if row:
                    proposal = CorrectionActionProposal.model_validate_json(row[0])
                    proposal.priority = action.priority
                    proposal.evidence_count = action.evidence_count
                    proposal.reason = action.reason
                    proposal.action = action.action
                    proposal.suggested_patch = action.suggested_patch
                    proposal.updated_at = timestamp
                else:
                    proposal = CorrectionActionProposal(
                        proposal_id=proposal_id,
                        source=source,
                        target=action.target,
                        priority=action.priority,
                        status="pending",
                        correction_type=action.correction_type,
                        evidence_count=action.evidence_count,
                        reason=action.reason,
                        action=action.action,
                        suggested_patch=action.suggested_patch,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                conn.execute(
                    """
                    INSERT INTO correction_action_proposals (
                        proposal_id, source, target, correction_type, priority,
                        status, created_at, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(proposal_id) DO UPDATE SET
                        priority = excluded.priority,
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        payload_json = excluded.payload_json
                    """,
                    (
                        proposal.proposal_id,
                        proposal.source,
                        proposal.target,
                        proposal.correction_type,
                        proposal.priority,
                        proposal.status,
                        proposal.created_at,
                        proposal.updated_at,
                        proposal.model_dump_json(),
                    ),
                )
                proposals.append(proposal)
        return proposals

    def _decision_history_for_proposal(self, proposal_id: str) -> list[CorrectionActionDecision]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM correction_action_decisions
                WHERE proposal_id = ?
                ORDER BY created_at DESC
                """,
                (proposal_id,),
            ).fetchall()
        return [CorrectionActionDecision.model_validate_json(row[0]) for row in rows]

    def _proposal_from_payload(self, payload_json: str, include_decisions: bool = True) -> CorrectionActionProposal:
        proposal = CorrectionActionProposal.model_validate_json(payload_json)
        if include_decisions:
            proposal.decisions = self._decision_history_for_proposal(proposal.proposal_id)
        return proposal

    def pending_correction_action_proposals(self, limit: int = 20) -> list[CorrectionActionProposal]:
        safe_limit = max(1, min(int(limit or 20), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM correction_action_proposals
                WHERE status = 'pending'
                ORDER BY
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._proposal_from_payload(row[0]) for row in rows]

    def correction_action_history(self, limit: int = 20) -> list[CorrectionActionProposal]:
        safe_limit = max(1, min(int(limit or 20), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM correction_action_proposals
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._proposal_from_payload(row[0]) for row in rows]

    def record_correction_action_decision(
        self,
        proposal_id: str,
        decision: str,
        note: str = "",
        decided_by: str = "user",
    ) -> CorrectionActionProposal:
        decision_to_status = {
            "approve": "approved",
            "reject": "rejected",
            "apply": "applied",
            "supersede": "superseded",
            "reopen": "pending",
        }
        normalized_decision = decision.strip().lower()
        if normalized_decision not in decision_to_status:
            raise ValueError("decision must be one of: approve, reject, apply, supersede, reopen")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM correction_action_proposals
                WHERE proposal_id = ?
                LIMIT 1
                """,
                (proposal_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Correction action proposal not found: {proposal_id}")

            proposal = CorrectionActionProposal.model_validate_json(row[0])
            previous_status = proposal.status
            new_status = decision_to_status[normalized_decision]
            timestamp = now_iso()
            decision_record = CorrectionActionDecision(
                decision_id=f"{proposal_id}:{normalized_decision}:{timestamp}",
                proposal_id=proposal_id,
                decision=normalized_decision,
                note=note.strip(),
                decided_by=decided_by.strip() or "user",
                previous_status=previous_status,
                new_status=new_status,
                created_at=timestamp,
            )
            proposal.status = new_status
            proposal.updated_at = timestamp
            conn.execute(
                """
                INSERT INTO correction_action_decisions (
                    decision_id, proposal_id, decision, note, decided_by,
                    previous_status, new_status, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_record.decision_id,
                    decision_record.proposal_id,
                    decision_record.decision,
                    decision_record.note,
                    decision_record.decided_by,
                    decision_record.previous_status,
                    decision_record.new_status,
                    decision_record.created_at,
                    decision_record.model_dump_json(),
                ),
            )
            conn.execute(
                """
                UPDATE correction_action_proposals
                SET status = ?, updated_at = ?, payload_json = ?
                WHERE proposal_id = ?
                """,
                (proposal.status, proposal.updated_at, proposal.model_dump_json(), proposal_id),
            )
        proposal.decisions = self._decision_history_for_proposal(proposal_id)
        return proposal

    def save_seal_timeline_event(self, event: SealTimelineEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO seal_timeline_events (
                    symbol, trading_day, kind, occurred_at, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.symbol,
                    event.trading_day,
                    event.kind,
                    event.occurred_at,
                    event.model_dump_json(),
                ),
            )

    def list_seal_timeline_events(self, symbol: str, trading_day: str) -> list[SealTimelineEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM seal_timeline_events
                WHERE symbol = ? AND trading_day = ?
                ORDER BY occurred_at ASC
                """,
                (symbol, trading_day),
            ).fetchall()
        return [SealTimelineEvent.model_validate_json(row[0]) for row in rows]

    def save_watchlist(self, watchlist: Watchlist) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlists (
                    watchlist_id, owner, label, status, created_at,
                    expires_at, closed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(watchlist_id) DO UPDATE SET
                    status = excluded.status,
                    closed_at = excluded.closed_at,
                    payload_json = excluded.payload_json
                """,
                (
                    watchlist.watchlist_id,
                    watchlist.owner,
                    watchlist.label,
                    watchlist.status,
                    watchlist.created_at,
                    watchlist.expires_at,
                    watchlist.closed_at,
                    watchlist.model_dump_json(),
                ),
            )
            conn.execute("DELETE FROM watchlist_entries WHERE watchlist_id = ?", (watchlist.watchlist_id,))
            conn.executemany(
                """
                INSERT INTO watchlist_entries (
                    watchlist_id, symbol, added_at, last_action, last_action_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        watchlist.watchlist_id,
                        entry.symbol,
                        entry.added_at,
                        entry.last_action,
                        entry.last_action_at,
                        entry.model_dump_json(),
                    )
                    for entry in watchlist.entries
                ],
            )

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM watchlists WHERE watchlist_id = ?",
                (watchlist_id,),
            ).fetchone()
        return Watchlist.model_validate_json(row[0]) if row else None

    def list_watchlists(self, *, owner: str = "", status: str = "") -> list[Watchlist]:
        clauses = []
        params: list[object] = []
        if owner:
            clauses.append("owner = ?")
            params.append(owner)
        if status:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT payload_json FROM watchlists"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Watchlist.model_validate_json(row[0]) for row in rows]

    def save_alert(self, alert: AgentAlert) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_alerts (
                    alert_id, event_id, symbol, theme, severity, status,
                    created_at, acknowledged_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alert_id) DO UPDATE SET
                    status = excluded.status,
                    acknowledged_at = excluded.acknowledged_at,
                    payload_json = excluded.payload_json
                """,
                (
                    alert.alert_id,
                    alert.event_id,
                    alert.symbol,
                    alert.theme,
                    alert.severity,
                    alert.status,
                    alert.created_at,
                    alert.acknowledged_at,
                    alert.model_dump_json(),
                ),
            )

    def get_alert(self, alert_id: str) -> AgentAlert | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        return AgentAlert.model_validate_json(row[0]) if row else None

    def get_alert_by_event(self, event_id: str) -> AgentAlert | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_alerts WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
        return AgentAlert.model_validate_json(row[0]) if row else None

    def list_alerts(self, *, status: str = "", limit: int = 50) -> list[AgentAlert]:
        safe_limit = max(1, min(int(limit or 50), 200))
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT payload_json FROM agent_alerts"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AgentAlert.model_validate_json(row[0]) for row in rows]

    def save_historical_snapshot(self, snap: HistoricalCandidateSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO historical_candidate_snapshots (
                    symbol, trading_day, grade_at_pick, theme, theme_role,
                    previous_consecutive_boards, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trading_day) DO UPDATE SET
                    grade_at_pick = excluded.grade_at_pick,
                    theme = excluded.theme,
                    theme_role = excluded.theme_role,
                    previous_consecutive_boards = excluded.previous_consecutive_boards,
                    payload_json = excluded.payload_json
                """,
                (
                    snap.symbol,
                    snap.trading_day,
                    snap.grade_at_pick,
                    snap.theme,
                    snap.theme_role,
                    snap.previous_consecutive_boards,
                    snap.model_dump_json(),
                    snap.created_at,
                ),
            )

    def get_historical_snapshot(
        self, symbol: str, trading_day: str
    ) -> HistoricalCandidateSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM historical_candidate_snapshots
                WHERE symbol = ? AND trading_day = ?
                """,
                (symbol, trading_day),
            ).fetchone()
        return HistoricalCandidateSnapshot.model_validate_json(row[0]) if row else None

    def list_historical_snapshots_between(
        self, *, start_day: str, end_day: str, symbol: str = ""
    ) -> list[HistoricalCandidateSnapshot]:
        clauses = ["trading_day BETWEEN ? AND ?"]
        params: list[object] = [start_day, end_day]
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        query = (
            "SELECT payload_json FROM historical_candidate_snapshots "
            "WHERE " + " AND ".join(clauses) + " ORDER BY trading_day ASC, symbol ASC"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [HistoricalCandidateSnapshot.model_validate_json(row[0]) for row in rows]

    def save_attribution(self, attribution: OutcomeAttribution) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outcome_attributions (
                    attribution_id, symbol, trading_day, primary_tag,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(attribution_id) DO UPDATE SET
                    primary_tag = excluded.primary_tag,
                    payload_json = excluded.payload_json
                """,
                (
                    attribution.attribution_id,
                    attribution.symbol,
                    attribution.trading_day,
                    attribution.primary_tag,
                    attribution.model_dump_json(),
                    attribution.created_at,
                ),
            )

    def get_attribution(self, symbol: str, trading_day: str) -> OutcomeAttribution | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM outcome_attributions
                WHERE symbol = ? AND trading_day = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (symbol, trading_day),
            ).fetchone()
        return OutcomeAttribution.model_validate_json(row[0]) if row else None

    def list_attributions(
        self, *, primary_tag: str = "", start_day: str = "", end_day: str = "", symbol: str = ""
    ) -> list[OutcomeAttribution]:
        clauses: list[str] = []
        params: list[object] = []
        if primary_tag:
            clauses.append("primary_tag = ?")
            params.append(primary_tag)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if start_day:
            clauses.append("trading_day >= ?")
            params.append(start_day)
        if end_day:
            clauses.append("trading_day <= ?")
            params.append(end_day)
        query = "SELECT payload_json FROM outcome_attributions"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY trading_day DESC, created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [OutcomeAttribution.model_validate_json(row[0]) for row in rows]

    def save_backtest_run(self, run: BacktestRun) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_runs (
                    run_id, status, start_day, end_day, sample_size,
                    payload_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    sample_size = excluded.sample_size,
                    payload_json = excluded.payload_json,
                    completed_at = excluded.completed_at
                """,
                (
                    run.run_id,
                    run.status,
                    run.start_day,
                    run.end_day,
                    run.sample_size,
                    run.model_dump_json(),
                    run.started_at,
                    run.completed_at,
                ),
            )

    def get_backtest_run(self, run_id: str) -> BacktestRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM backtest_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return BacktestRun.model_validate_json(row[0]) if row else None

    def list_backtest_runs(self, *, status: str = "", limit: int = 50) -> list[BacktestRun]:
        safe_limit = max(1, min(int(limit or 50), 200))
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT payload_json FROM backtest_runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [BacktestRun.model_validate_json(row[0]) for row in rows]

    def save_dragon_tiger(self, record: DragonTigerRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dragon_tiger_records (
                    symbol, trading_day, list_reason,
                    total_buy_cny, total_sell_cny, net_amount_cny,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trading_day) DO UPDATE SET
                    list_reason = excluded.list_reason,
                    total_buy_cny = excluded.total_buy_cny,
                    total_sell_cny = excluded.total_sell_cny,
                    net_amount_cny = excluded.net_amount_cny,
                    payload_json = excluded.payload_json
                """,
                (
                    record.symbol,
                    record.trading_day,
                    record.list_reason,
                    record.total_buy_cny,
                    record.total_sell_cny,
                    record.net_amount_cny,
                    record.model_dump_json(),
                    record.created_at,
                ),
            )

    def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM dragon_tiger_records "
                "WHERE symbol = ? AND trading_day = ?",
                (symbol, trading_day),
            ).fetchone()
        return DragonTigerRecord.model_validate_json(row[0]) if row else None

    def list_active_seats_today(self, trading_day: str) -> list[dict]:
        """Aggregate net buy by hot_money_alias for one trading day."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM dragon_tiger_records WHERE trading_day = ?",
                (trading_day,),
            ).fetchall()

        aggregated: dict[str, dict] = {}
        for row in rows:
            record = DragonTigerRecord.model_validate_json(row[0])
            for seat in record.seats:
                if seat.seat_type != "hot_money_known" or not seat.hot_money_alias:
                    continue
                entry = aggregated.setdefault(
                    seat.hot_money_alias,
                    {
                        "hot_money_alias": seat.hot_money_alias,
                        "symbol_count": 0,
                        "total_net_buy_cny": 0.0,
                        "symbols": [],
                    },
                )
                if record.symbol not in entry["symbols"]:
                    entry["symbols"].append(record.symbol)
                    entry["symbol_count"] += 1
                entry["total_net_buy_cny"] += seat.net_amount_cny
        return sorted(
            aggregated.values(),
            key=lambda x: x["total_net_buy_cny"],
            reverse=True,
        )

    def save_contrarian_pool_entry(
        self, entry: ContrarianPoolEntry, *, created_at: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contrarian_pool_snapshots (
                    trading_day, pool_kind, symbol, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trading_day, pool_kind, symbol) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (
                    entry.trading_day,
                    entry.pool_kind,
                    entry.symbol,
                    entry.model_dump_json(),
                    created_at,
                ),
            )

    def list_contrarian_pool(
        self, trading_day: str, *, pool_kind: str = ""
    ) -> list[ContrarianPoolEntry]:
        clauses = ["trading_day = ?"]
        params: list[object] = [trading_day]
        if pool_kind:
            clauses.append("pool_kind = ?")
            params.append(pool_kind)
        query = (
            "SELECT payload_json FROM contrarian_pool_snapshots WHERE "
            + " AND ".join(clauses)
            + " ORDER BY symbol ASC"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ContrarianPoolEntry.model_validate_json(row[0]) for row in rows]

    def save_capital_flow_slice(self, slice_: CapitalFlowSlice) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO capital_flow_slices (
                    symbol, trading_day, window,
                    big_order_net_inflow_cny, main_capital_net_inflow_cny,
                    retail_capital_net_inflow_cny, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trading_day, window) DO UPDATE SET
                    big_order_net_inflow_cny = excluded.big_order_net_inflow_cny,
                    main_capital_net_inflow_cny = excluded.main_capital_net_inflow_cny,
                    retail_capital_net_inflow_cny = excluded.retail_capital_net_inflow_cny,
                    payload_json = excluded.payload_json
                """,
                (
                    slice_.symbol,
                    slice_.trading_day,
                    slice_.window,
                    slice_.big_order_net_inflow_cny,
                    slice_.main_capital_net_inflow_cny,
                    slice_.retail_capital_net_inflow_cny,
                    slice_.model_dump_json(),
                    slice_.created_at,
                ),
            )

    def list_capital_flow_slices(
        self, symbol: str, trading_day: str
    ) -> list[CapitalFlowSlice]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM capital_flow_slices "
                "WHERE symbol = ? AND trading_day = ? ORDER BY window ASC",
                (symbol, trading_day),
            ).fetchall()
        return [CapitalFlowSlice.model_validate_json(row[0]) for row in rows]


    def save_suspended_stock(
        self, entry: SuspendedStock, *, created_at: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO suspended_stocks (
                    symbol, suspension_start_day, suspension_end_day, reason,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, suspension_start_day) DO UPDATE SET
                    suspension_end_day = excluded.suspension_end_day,
                    reason = excluded.reason,
                    payload_json = excluded.payload_json
                """,
                (
                    entry.symbol,
                    entry.suspension_start_day,
                    entry.suspension_end_day,
                    entry.reason,
                    entry.model_dump_json(),
                    created_at,
                ),
            )

    def list_suspended_stocks(
        self, *, trading_day: str = ""
    ) -> list[SuspendedStock]:
        """List suspended stocks. If trading_day given, only return entries that
        are active on that day (start_day <= trading_day, AND end_day blank or end_day >= trading_day).

        Day-range filtering happens in SQL using idx_suspended_day for efficiency.
        """
        if not trading_day:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM suspended_stocks "
                    "ORDER BY suspension_start_day ASC"
                ).fetchall()
            return [SuspendedStock.model_validate_json(row[0]) for row in rows]

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM suspended_stocks "
                "WHERE suspension_start_day <= ? "
                "AND (suspension_end_day = '' OR suspension_end_day >= ?) "
                "ORDER BY suspension_start_day ASC",
                (trading_day, trading_day),
            ).fetchall()
        return [SuspendedStock.model_validate_json(row[0]) for row in rows]

    def save_selection_audit(self, audit: SelectionAudit) -> SelectionAudit:
        if not audit.created_at:
            audit.created_at = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO selection_audits
                    (audit_id, as_of_day, picks_json, rejected_json, baseline_json,
                     equals_baseline, confidence_label, candidate_pool_size,
                     provider, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    picks_json=excluded.picks_json,
                    rejected_json=excluded.rejected_json,
                    baseline_json=excluded.baseline_json,
                    equals_baseline=excluded.equals_baseline,
                    confidence_label=excluded.confidence_label,
                    candidate_pool_size=excluded.candidate_pool_size,
                    provider=excluded.provider,
                    model=excluded.model
                """,
                (
                    audit.audit_id, audit.as_of_day,
                    _dump_audit_list(audit.picks), _dump_audit_list(audit.rejected),
                    json.dumps(audit.baseline, ensure_ascii=False),
                    1 if audit.equals_baseline else 0,
                    audit.confidence_label, audit.candidate_pool_size,
                    audit.provider, audit.model, audit.created_at,
                ),
            )
        return audit

    def get_selection_audit_by_day(self, as_of_day: str) -> SelectionAudit | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT audit_id, as_of_day, picks_json, rejected_json, baseline_json,
                       equals_baseline, confidence_label, candidate_pool_size,
                       provider, model, created_at
                FROM selection_audits WHERE as_of_day = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (as_of_day,),
            ).fetchone()
        if row is None:
            return None
        return SelectionAudit(
            audit_id=row[0], as_of_day=row[1],
            picks=[SelectionPick.model_validate(p) for p in json.loads(row[2] or "[]")],
            rejected=[RejectedCandidate.model_validate(r) for r in json.loads(row[3] or "[]")],
            baseline=json.loads(row[4] or "{}"),
            equals_baseline=bool(row[5]),
            confidence_label=row[6], candidate_pool_size=row[7],
            provider=row[8], model=row[9], created_at=row[10],
        )

    def count_selection_audit_days(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT as_of_day) FROM selection_audits"
            ).fetchone()
        return int(row[0]) if row else 0


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
