from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP

from aegis_alpha.mcp.dependencies import get_market_data_adapter, get_store
from aegis_alpha.models import AgentReviewCorrection, CandidateOutcomeReview
from aegis_alpha.runner import status_payload
from aegis_alpha.storage import AegisAlphaStore


mcp = FastMCP("aegis-alpha")


def _call_tool(callback: Callable[[Any], Any]) -> Any:
    try:
        adapter = get_market_data_adapter()
        return callback(adapter)
    except Exception as exc:
        return {
            "data_mode": "unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Data source unavailable. Research output only; do not infer missing market data.",
        }


def _call_store(callback: Callable[[AegisAlphaStore], Any]) -> Any:
    try:
        return callback(get_store())
    except Exception as exc:
        return {
            "data_mode": "unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Data source unavailable. Research output only; do not infer missing market data.",
        }


def _filter_second_board_candidates(candidates: list[Any], break_filter: str = "include") -> list[Any]:
    mode = (break_filter or "include").strip().lower()
    if mode in {"exclude", "no_break", "sealed"}:
        return [item for item in candidates if int(getattr(item, "break_board_count", 0) or 0) == 0]
    if mode in {"only", "break", "break_only"}:
        return [item for item in candidates if int(getattr(item, "break_board_count", 0) or 0) > 0]
    return candidates


def _compact_theme_continuity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "lookback_days": value.get("lookback_trading_days", 0),
        "active_days": value.get("active_days", 0),
        "burst_days": value.get("burst_days", 0),
        "total_limit_ups": value.get("total_limit_ups", 0),
        "max_daily_limit_ups": value.get("max_daily_limit_ups", 0),
        "last_3_counts": value.get("last_3_counts", []),
        "continuity_label": value.get("continuity_label", "unknown"),
        "same_theme_strategy_seed_count": value.get("same_theme_strategy_seed_count", 0),
        "same_theme_first_board_count": value.get("same_theme_first_board_count", 0),
        "off_platform_news_checked": value.get("off_platform_news_checked", False),
        "cls_news_checked": value.get("cls_news_checked", False),
    }


def _compact_strategy_watchlist_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol", ""),
        "name": item.get("name", ""),
        "candidate_sources": item.get("candidate_sources", []),
        "change_pct": item.get("change_pct", 0.0),
        "theme": item.get("theme", "unknown"),
        "avg_turnover_10d_cny": item.get("avg_turnover_10d_cny", 0.0),
        "avg_turnover_10d_pass": item.get("avg_turnover_10d_pass", False),
        "as_of_turnover_cny": item.get("as_of_turnover_cny", 0.0),
        "prev_day_volume_shrink_ratio": item.get("prev_day_volume_shrink_ratio", 0.0),
        "prev_day_shrink": item.get("prev_day_shrink", False),
        "previous_high_price": item.get("previous_high_price", 0.0),
        "broke_previous_high": item.get("broke_previous_high", False),
        "as_of_high_broke_previous_high": item.get("as_of_high_broke_previous_high", False),
        "same_theme_strategy_seed_count": item.get("same_theme_strategy_seed_count", 0),
        "same_theme_first_board_count": item.get("same_theme_first_board_count", 0),
        "theme_continuity": _compact_theme_continuity(item.get("theme_continuity")),
    }


def _daily_strategy_candidate_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **_compact_strategy_watchlist_item(item),
        "as_of_day": item.get("as_of_day", ""),
        "prev_day": item.get("prev_day", ""),
        "target_second_board_day": item.get("target_second_board_day", ""),
        "provider": item.get("provider", ""),
        "data_mode": item.get("data_mode", ""),
        "strategy_data_mode": item.get("strategy_data_mode", ""),
        "strategy_error": item.get("strategy_error", ""),
        "strategy_seed_reasons": item.get("strategy_seed_reasons", []),
        "close_price": item.get("close_price", 0.0),
        "as_of_high_price": item.get("as_of_high_price", 0.0),
        "current_close": item.get("current_close", item.get("close_price", 0.0)),
        "current_high": item.get("current_high", item.get("as_of_high_price", 0.0)),
        "turnover_cny": item.get("turnover_cny", item.get("as_of_turnover_cny", 0.0)),
        "prev_day_turnover_cny": item.get("prev_day_turnover_cny", 0.0),
        "strategy_filter_pass": item.get("strategy_filter_pass", False),
        "strategy_coverage": item.get("strategy_coverage", {}),
        "strategy_notes": item.get("strategy_notes", item.get("notes", [])),
    }


def _time_lte(value: str, boundary: str) -> bool:
    return bool(value and boundary and value <= boundary)


def _packet_theme_copump(
    item: dict[str, Any],
    day_results: list[dict[str, Any]],
    *,
    trigger_time: str,
) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "").split(".", 1)[0]
    theme = str(item.get("theme") or "unknown")
    same_theme = [
        result
        for result in day_results
        if str(result.get("symbol") or "").split(".", 1)[0] != symbol
        and str(result.get("theme") or "unknown") == theme
    ]
    crossed = []
    triggered = []
    opening = []
    for peer in same_theme:
        diagnostics = peer.get("pattern_diagnostics") or {}
        first_cross_time = str(diagnostics.get("first_cross_time") or "")
        first_triggered_at = str(peer.get("first_triggered_at") or "")
        opening_cross_time = str(diagnostics.get("opening_window_cross_time") or "")
        if _time_lte(first_cross_time, trigger_time):
            crossed.append(peer)
        if _time_lte(first_triggered_at, trigger_time):
            triggered.append(peer)
        if _time_lte(opening_cross_time, trigger_time):
            opening.append(peer)

    return {
        "symbol": symbol,
        "theme": theme,
        "data_mode": "packet_selected_results_copump",
        "universe": "symbols_replayed_inside_this_packet",
        "trigger_time": trigger_time,
        "same_theme_candidate_count": len(same_theme),
        "copump": {
            "crossed_previous_high_by_trigger_count": len(crossed),
            "triggered_by_trigger_count": len(triggered),
            "opening_breakout_by_trigger_count": len(opening),
            "crossed_symbols": [str(peer.get("symbol") or "").split(".", 1)[0] for peer in crossed[:10]],
            "triggered_symbols": [str(peer.get("symbol") or "").split(".", 1)[0] for peer in triggered[:10]],
        },
        "notes": [
            "Fast packet co-pump uses only symbols replayed inside this packet.",
            "Call full theme co-pump explicitly when broader same-theme breadth is required.",
        ],
    }


@mcp.tool
def get_market_snapshot() -> dict:
    """Return a read-only A-share market sentiment snapshot."""
    return _call_tool(lambda adapter: adapter.get_market_snapshot().model_dump())


@mcp.tool
def get_market_sentiment_gate() -> dict:
    """Return the board-chasing market sentiment gate."""
    return _call_tool(lambda adapter: adapter.get_market_sentiment_gate().model_dump())


@mcp.tool
def get_limitup_pool() -> list[dict]:
    """Return the current limit-up pool."""
    return _call_tool(lambda adapter: [item.model_dump() for item in adapter.get_limitup_pool()])


@mcp.tool
def get_break_board_pool() -> list[dict]:
    """Return the current break-board pool."""
    return _call_tool(lambda adapter: [item.model_dump() for item in adapter.get_break_board_pool()])


@mcp.tool
def get_stock_realtime_snapshot(symbol: str) -> dict:
    """Return a read-only realtime or latest provider snapshot for one stock."""
    return _call_tool(lambda adapter: adapter.get_stock_realtime_snapshot(symbol).model_dump())


@mcp.tool
def get_stock_orderbook_snapshot(symbol: str) -> dict:
    """Return a read-only orderbook summary for one stock when the provider supports it."""
    return _call_tool(lambda adapter: adapter.get_stock_orderbook_snapshot(symbol).model_dump())


@mcp.tool
def get_stock_minute_replay_snapshot(symbol: str, end_day: str = "", limit_days: int = 1) -> dict:
    """Return read-only jvQuant minute replay data and Aegis-calculated speed windows."""
    safe_limit = max(1, min(int(limit_days or 1), 30))
    safe_end_day = end_day.strip() or None
    return _call_tool(
        lambda adapter: adapter.get_stock_minute_replay_snapshot(symbol, safe_end_day, safe_limit).model_dump()
    )


@mcp.tool
def detect_intraday_buypoint(symbol: str, end_day: str = "", previous_high: float = 0.0) -> dict:
    """Offline-replay detection of the intraday buy-point pattern
    (过前高 → 回踩缩量 → 重新上冲) over a symbol's minute bars.

    Returns {"signals": [...], "count": N, "data_mode": ..., "disclaimer": ...}.
    This is a RESEARCH ALERT, not a buy/sell/order instruction. Thresholds use
    Phase-1 defaults; a strategy prior (Phase 5) will make them switchable.

    previous_high: If > 0, the supplied value is used as the prior-session high
    price threshold that the state machine watches for a volume-confirmed breakout.
    If not provided (or <= 0), it is approximated from the opening-window high
    (the maximum last_price among the first 3 baseline bars of the snapshot).
    Pass an explicit previous_high for accuracy; the fallback is conservative but
    not guaranteed to match the real prior-session high.

    same_theme_rising_count is not derivable from a single-symbol minute snapshot,
    so it is fixed at 0 here and carried verbatim to all emitted signals.
    """
    from aegis_alpha.measurements.buypoint_replay import replay_buypoint

    _BASELINE_WINDOW = 3

    def _run(adapter: Any) -> dict:
        snapshot = adapter.get_stock_minute_replay_snapshot(
            symbol, end_day.strip() or None, 1
        )

        if previous_high > 0:
            resolved_high = previous_high
            previous_high_source = "caller"
        else:
            # Fallback: derive from the maximum last_price of the first
            # baseline_window bars (the opening reference window).
            opening_bars = snapshot.bars[:_BASELINE_WINDOW]
            if opening_bars:
                resolved_high = max(b.last_price for b in opening_bars)
            else:
                # Zero-bar snapshot — use previous_close as last resort.
                resolved_high = snapshot.previous_close
            previous_high_source = "opening_window_fallback"

        signals = replay_buypoint(
            snapshot,
            previous_high=resolved_high,
            same_theme_rising_count=0,
            baseline_window=_BASELINE_WINDOW,
        )
        return {
            "signals": [s.model_dump() for s in signals],
            "count": len(signals),
            "data_mode": snapshot.data_mode,
            "previous_high_source": previous_high_source,
            "disclaimer": "Research alert only; not an order instruction.",
        }

    return _call_tool(_run)


@mcp.tool
def get_recent_market_events(limit: int = 20, event_type: str = "") -> list[dict]:
    """Return recent structured market events generated by Aegis Alpha signal rules."""
    safe_limit = max(1, min(int(limit or 20), 100))
    safe_event_type = event_type.strip() or None
    return _call_tool(
        lambda adapter: [
            event.model_dump()
            for event in adapter.get_recent_market_events(safe_limit, safe_event_type)
        ]
    )


@mcp.tool
def get_signal_snapshot(symbol: str) -> dict:
    """Return the latest structured signal snapshot for one stock."""
    return _call_tool(lambda adapter: adapter.get_signal_snapshot(symbol).model_dump())


@mcp.tool
def get_event_scoring_config() -> dict:
    """Return the active event scoring configuration without secrets."""
    return _call_tool(lambda adapter: adapter.get_event_scoring_config().model_dump())


@mcp.tool
def get_active_strategy_prior() -> dict:
    """Return the active strategy prior as agent GUIDANCE (read-only).

    Switching which prior is active is a human/config action; no tool mutates it.
    The program never rejects or passes a candidate based on a prior — the agent
    weighs the soft ranges against measured facts and overrides with reasoning.
    Not a buy/sell/order instruction."""
    from aegis_alpha.strategy_priors import load_active_strategy_prior

    try:
        prior = load_active_strategy_prior()
    except Exception as exc:
        return {
            "data_mode": "unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Strategy prior config unavailable. Research output only.",
        }
    if prior is None:
        return {
            "data_mode": "unavailable",
            "error": "No active strategy prior configured.",
            "disclaimer": "Strategy prior is agent guidance only, not a program filter and not a buy/sell/order instruction.",
        }
    return prior.model_dump()


@mcp.tool
def get_realtime_connection_status() -> dict:
    """Return realtime provider connection state without starting a raw stream."""
    return _call_tool(lambda adapter: adapter.get_realtime_connection_status().model_dump())


@mcp.tool
def get_runner_status() -> dict:
    """Return launchd-managed runner status from the local status file."""
    try:
        return status_payload()
    except Exception as exc:
        return {
            "state": "STOPPED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Runner status unavailable. Do not infer live market state.",
        }


@mcp.tool
def explain_market_event(event_id: str) -> dict:
    """Explain a structured market event without issuing buy or sell instructions."""
    return _call_tool(lambda adapter: adapter.explain_market_event(event_id))


@mcp.tool
def review_candidate_outcome(symbol: str, trading_day: str) -> dict:
    """Return the stored or provider-derived review outcome for a candidate and trading day."""
    return _call_tool(lambda adapter: adapter.review_candidate_outcome(symbol, trading_day).model_dump())


@mcp.tool
def record_candidate_outcome(
    symbol: str,
    trading_day: str,
    touched_limit_up: bool | None = None,
    sealed_second_board: bool | None = None,
    broke_after_seal: bool | None = None,
    next_day_open_pct: float | None = None,
    next_day_high_pct: float | None = None,
    third_day_premium_pct: float | None = None,
    user_correction: str = "",
    notes: str = "",
) -> dict:
    """Store a read-only review/correction record for later strategy and skill tuning."""
    review = CandidateOutcomeReview(
        symbol=symbol,
        trading_day=trading_day,
        touched_limit_up=touched_limit_up,
        sealed_second_board=sealed_second_board,
        broke_after_seal=broke_after_seal,
        next_day_open_pct=next_day_open_pct,
        next_day_high_pct=next_day_high_pct,
        third_day_premium_pct=third_day_premium_pct,
        user_correction=user_correction,
        notes=[item.strip() for item in notes.split("|") if item.strip()],
    )
    return _call_tool(lambda adapter: adapter.record_candidate_outcome(review).model_dump())


@mcp.tool
def get_recent_agent_reviews(limit: int = 10) -> list[dict] | dict:
    """Return recently stored agent review results for chat-based correction."""
    safe_limit = max(1, min(int(limit or 10), 50))
    return _call_store(lambda store: [review.model_dump() for review in store.recent_agent_reviews(safe_limit)])


@mcp.tool
def record_agent_review_correction(
    review_id: str,
    symbol: str = "",
    correction_type: str = "OTHER",
    expected_grade: str = "",
    comment: str = "",
) -> dict:
    """Store a user correction about an agent review for later memory, skill, or scoring updates."""

    def _record(store: AegisAlphaStore) -> dict:
        normalized_type = correction_type.strip().upper() or "OTHER"
        normalized_grade = expected_grade.strip().upper() or None
        correction = AgentReviewCorrection(
            review_id=review_id.strip(),
            symbol=symbol.strip(),
            correction_type=normalized_type,
            expected_grade=normalized_grade,
            comment=comment.strip(),
        )
        saved = store.save_agent_review_correction(correction)
        summary = store.agent_correction_summary(limit=100)
        proposals = store.save_correction_action_proposals(summary)
        return {
            "correction": saved.model_dump(),
            "summary": summary.model_dump(exclude={"recent_corrections"}),
            "proposals": [proposal.model_dump(exclude={"decisions"}) for proposal in proposals],
            "disclaimer": "Correction stored locally for review. Hermes memory or skill updates are suggested, not automatically applied.",
        }

    return _call_store(_record)


@mcp.tool
def get_agent_correction_summary(limit: int = 100) -> dict:
    """Return correction patterns and suggested Hermes memory or skill updates."""
    safe_limit = max(1, min(int(limit or 100), 200))
    return _call_store(lambda store: store.agent_correction_summary(safe_limit).model_dump())


@mcp.tool
def get_agent_judgment_scorecard(start_day: str, end_day: str = "") -> dict:
    """Score the agent's PAST judgments (grade + promotion_likelihood) against realized
    next-day outcomes over a date window. Returns objective calibration metrics
    (Brier score, likelihood calibration, grade hit-rate) — not a program grade and
    not a buy/sell/order instruction."""
    from aegis_alpha.feedback.agent_scorecard import compute_scorecard

    safe_start = start_day.strip()
    safe_end = (end_day or start_day).strip()
    if not safe_start:
        return {"data_mode": "unavailable", "error": "start_day is required"}

    def _score(store: AegisAlphaStore) -> dict:
        reviews = store.list_agent_reviews_between(safe_start, safe_end)
        outcomes = store.list_review_outcomes(start_day=safe_start, end_day=safe_end)
        scorecard = compute_scorecard(reviews, outcomes, start_day=safe_start, end_day=safe_end)
        return scorecard.model_dump()

    return _call_store(_score)


@mcp.tool
def create_correction_action_proposals(limit: int = 100) -> dict:
    """Create or update human-reviewable proposals from current correction routing."""
    safe_limit = max(1, min(int(limit or 100), 200))

    def _create(store: AegisAlphaStore) -> dict:
        summary = store.agent_correction_summary(safe_limit)
        proposals = store.save_correction_action_proposals(summary)
        return {
            "created_or_updated": [proposal.model_dump(exclude={"decisions"}) for proposal in proposals],
            "count": len(proposals),
            "disclaimer": "Proposals are pending review. Aegis Alpha does not apply memory, skill, config, or adapter changes automatically.",
        }

    return _call_store(_create)


@mcp.tool
def get_pending_correction_actions(limit: int = 20) -> list[dict] | dict:
    """Return pending correction action proposals waiting for human review."""
    safe_limit = max(1, min(int(limit or 20), 100))
    return _call_store(
        lambda store: [proposal.model_dump() for proposal in store.pending_correction_action_proposals(safe_limit)]
    )


@mcp.tool
def record_correction_action_decision(
    proposal_id: str,
    decision: str,
    note: str = "",
    decided_by: str = "user",
) -> dict:
    """Record a human decision for a correction action proposal without applying code/config changes."""

    def _record(store: AegisAlphaStore) -> dict:
        proposal = store.record_correction_action_decision(
            proposal_id=proposal_id.strip(),
            decision=decision.strip(),
            note=note.strip(),
            decided_by=decided_by.strip() or "user",
        )
        return {
            "proposal": proposal.model_dump(),
            "disclaimer": "Decision recorded only. Applying memory, skill, config, or adapter changes remains a separate explicit step.",
        }

    return _call_store(_record)


@mcp.tool
def get_correction_action_history(limit: int = 20) -> list[dict] | dict:
    """Return correction action proposals and their decision history."""
    safe_limit = max(1, min(int(limit or 20), 100))
    return _call_store(lambda store: [proposal.model_dump() for proposal in store.correction_action_history(safe_limit)])


@mcp.tool
def get_stock_history_limitup_stats(symbol: str) -> dict:
    """Return mock historical limit-up success and next-day premium stats."""
    return _call_tool(lambda adapter: adapter.get_stock_history_limitup_stats(symbol).model_dump())


@mcp.tool
def get_theme_strength(symbol: str) -> dict:
    """Return mock theme strength for one stock."""
    return _call_tool(lambda adapter: adapter.get_theme_strength(symbol).model_dump())


@mcp.tool
def get_theme_leaders(theme: str = "", trading_day: str = "") -> list[dict]:
    """Return resolved theme leaders for a theme or the current market."""
    return _call_tool(
        lambda adapter: [
            leader.model_dump()
            for leader in adapter.get_theme_leaders(theme.strip(), trading_day.strip())
        ]
    )


@mcp.tool
def get_theme_continuity(theme: str, as_of_day: str, lookback_days: int = 14) -> dict:
    """Return market-internal two-week continuity facts for one theme.

    The tool groups historical limit-up pools by theme/industry over recent trading
    days. It does not check off-platform news or CLS popups and does not assign a
    buy/sell score.
    """
    safe_theme = theme.strip()
    safe_day = as_of_day.strip()
    if not safe_theme:
        return {"data_mode": "unavailable", "error": "theme is required"}
    if not safe_day:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    safe_lookback = max(1, min(int(lookback_days or 14), 30))
    return _call_tool(lambda adapter: adapter.get_theme_continuity(safe_theme, safe_day, safe_lookback))


@mcp.tool
def get_limit_up_ladder(symbol: str, trading_day: str = "") -> dict:
    """Return the latest known limit-up ladder height for one stock."""
    return _call_tool(lambda adapter: adapter.get_limit_up_ladder(symbol, trading_day.strip()).model_dump())


@mcp.tool
def get_market_emotion(trading_day: str = "") -> dict:
    """Return the upgraded market emotion gauge."""
    return _call_tool(lambda adapter: adapter.get_market_emotion(trading_day.strip()).model_dump())


@mcp.tool
def get_auction_analysis(symbol: str, trading_day: str = "") -> dict:
    """Return auction pattern analysis for one stock."""
    return _call_tool(lambda adapter: adapter.get_auction_analysis(symbol, trading_day.strip()).model_dump())


@mcp.tool
def get_second_board_candidates(break_filter: str = "include") -> list[dict]:
    """Return mock candidates for the second-board radar."""

    def _items(adapter: Any) -> list[dict]:
        return [
            item.model_dump()
            for item in _filter_second_board_candidates(
                adapter.get_second_board_candidates(),
                break_filter,
            )
        ]

    return _call_tool(_items)


@mcp.tool
def get_second_board_candidates_compact(limit: int = 12, break_filter: str = "include") -> list[dict]:
    """Return compact second-board candidates without verbose evidence."""

    def _compact(adapter: Any) -> list[dict]:
        safe_limit = max(1, min(int(limit or 12), 50))
        items = []
        for candidate in _filter_second_board_candidates(
            adapter.get_second_board_candidates(),
            break_filter,
        )[:safe_limit]:
            items.append(
                {
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "data_mode": candidate.data_mode,
                    "provider": candidate.provider,
                    "theme": candidate.theme,
                    "current_change_pct": candidate.current_change_pct,
                    "auction_change_pct": candidate.auction_change_pct,
                    "auction_turnover_cny": candidate.auction_turnover_cny,
                    "auction_turnover_rate": candidate.auction_turnover_rate,
                    "auction_pattern": candidate.auction_pattern,
                    "previous_consecutive_boards": candidate.previous_consecutive_boards,
                    "previous_height_label": candidate.previous_height_label,
                    "theme_role": candidate.theme_role,
                    "theme_leader_symbol": candidate.theme_leader_symbol,
                    "one_min_speed_pct": candidate.one_min_speed_pct,
                    "three_min_speed_pct": candidate.three_min_speed_pct,
                    "five_min_speed_pct": candidate.five_min_speed_pct,
                    "five_min_speed_window": candidate.five_min_speed_window,
                    "five_min_speed_timestamp": candidate.five_min_speed_timestamp,
                    "minute_replay_timestamp": candidate.minute_replay_timestamp,
                    "minute_replay_trading_day": candidate.minute_replay_trading_day,
                    "minute_replay_bar_count": candidate.minute_replay_bar_count,
                    "ten_min_speed_pct": candidate.ten_min_speed_pct,
                    "big_order_net_inflow_ratio": candidate.big_order_net_inflow_ratio,
                    "first_limit_up_time": candidate.first_limit_up_time,
                    "final_seal_time": candidate.final_seal_time,
                    "seal_amount_cny": candidate.seal_amount_cny,
                    "max_seal_amount_cny": candidate.max_seal_amount_cny,
                    "seal_to_turnover_ratio": candidate.seal_to_turnover_ratio,
                    "break_board_count": candidate.break_board_count,
                    "reseal_count": candidate.reseal_count,
                    "concept_tags": candidate.concept_tags[:8],
                    "topic_tags": candidate.topic_tags[:8],
                    "same_theme_rising_count": candidate.same_theme_rising_count,
                    "orderbook_quality_score": candidate.orderbook_quality_score,
                    "limitup_driver_type": candidate.limitup_driver_type,
                    "intraday_pattern": candidate.intraday_pattern,
                    "weekly_health_score": candidate.weekly_health_score,
                    "theme_lifecycle_stage": candidate.theme_lifecycle_stage,
                    "free_float_market_cap_cny": candidate.free_float_market_cap_cny,
                    "turnover_cny": candidate.turnover_cny,
                    "avg_turnover_10d_cny": candidate.avg_turnover_10d_cny,
                    "prev_day_volume_shrink_ratio": candidate.prev_day_volume_shrink_ratio,
                    "ma5_slope_degrees": candidate.ma5_slope_degrees,
                    "broke_previous_high": candidate.broke_previous_high,
                    "data_quality_summary": {
                        key: {
                            "confidence": value.confidence,
                            "usable_for_grading": value.usable_for_grading,
                        }
                        for key, value in candidate.data_quality.items()
                    },
                }
            )
        return items

    return _call_tool(_compact)


@mcp.tool
def get_historical_second_board_candidates(trading_day: str, limit: int = 50) -> list[dict] | dict:
    """Return facts-only historical second-board candidates for a given trading day.

    The program returns provider facts such as seal amount, first seal time, turnover,
    and theme. It does not assign a promotion probability or grade.
    """
    safe_day = trading_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}
    safe_limit = max(1, min(int(limit or 50), 200))
    return _call_tool(lambda adapter: adapter.get_historical_second_board_candidates(safe_day, safe_limit))


@mcp.tool
def get_historical_first_board_watchlist(as_of_day: str, limit: int = 50) -> list[dict] | dict:
    """Return facts-only first-board watchlist inputs available as of a historical close.

    Use this for strict replay questions like "standing at YYYY-MM-DD close, choose
    tomorrow's second-board Top3". It returns only as-of-day or earlier provider facts,
    and does not assign a promotion probability or grade.
    """
    safe_day = as_of_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    safe_limit = max(1, min(int(limit or 50), 200))
    return _call_tool(lambda adapter: adapter.get_historical_first_board_watchlist(safe_day, safe_limit))


@mcp.tool
def get_strategy_watchlist(as_of_day: str, limit: int = 50) -> list[dict] | dict:
    """Return facts-only strategy watchlist inputs for a historical close.

    This builds the user's broad trend strategy universe from first-board and
    large-turnover seeds, then returns 10-day turnover baseline, T-1 shrink,
    previous-high break, and partial same-theme breadth. It does not assign a
    score, grade, probability, buy instruction, or sell instruction.
    """
    safe_day = as_of_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    safe_limit = max(1, min(int(limit or 50), 100))
    def _strategy_watchlist(adapter: Any) -> dict[str, Any]:
        items = [
            _compact_strategy_watchlist_item(item)
            for item in adapter.get_strategy_watchlist(safe_day, safe_limit)
            if isinstance(item, dict)
        ]
        return {
            "as_of_day": safe_day,
            "result_count": len(items),
            "candidates": items,
            "data_gaps": [
                "Off-platform sector/news validation is not connected.",
                "Historical CLS popup alignment is not connected.",
                "Historical Level-2 big-order buy ratio is not connected.",
                "MA5 slope is intentionally not part of the active strategy watchlist.",
            ],
        }

    return _call_tool(_strategy_watchlist)


@mcp.tool
def get_daily_strategy_candidate_pool(as_of_day: str, limit: int = 30) -> dict:
    """Prepare the daily facts-only pool for the user's strategy.

    This is the first step of the target workflow:
    as_of_day close -> candidate pool -> agent chooses observation TopN ->
    target_day intraday facts via get_strategy_decision_packet.

    The tool does not rank, grade, score, or assign promotion probability.
    Ordering follows the provider/seed pipeline only and is not an alpha signal.
    """
    safe_day = as_of_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    safe_limit = max(1, min(int(limit or 30), 100))

    def _candidate_pool(adapter: Any) -> dict[str, Any]:
        raw_items = [
            item
            for item in adapter.get_strategy_watchlist(safe_day, safe_limit)
            if isinstance(item, dict)
        ]
        candidates = [_daily_strategy_candidate_item(item) for item in raw_items]
        source_counts: dict[str, int] = {}
        theme_counts: dict[str, int] = {}
        coverage_counts: dict[str, int] = {
            "avg_turnover_10d": 0,
            "prev_day_shrink": 0,
            "previous_high_break": 0,
            "theme_two_week_continuity": 0,
            "intraday_big_order_ratio": 0,
            "cls_news_alignment": 0,
        }
        for item in candidates:
            for source in item.get("candidate_sources", []):
                source_counts[source] = source_counts.get(source, 0) + 1
            theme = str(item.get("theme") or "unknown")
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            coverage = item.get("strategy_coverage") or {}
            for key in coverage_counts:
                if coverage.get(key):
                    coverage_counts[key] += 1

        return {
            "as_of_day": safe_day,
            "data_mode": "daily_strategy_candidate_pool",
            "intended_use": "facts_for_agent_selection",
            "result_count": len(candidates),
            "provider_order_is_not_alpha_rank": True,
            "candidate_generation": {
                "universe_sources": [
                    "first_board_watchlist",
                    "large_turnover_trend_seed",
                ],
                "active_program_filter": "avg_turnover_10d_pass_only",
                "removed_strategy_rules": [
                    "MA5 slope is intentionally not part of the active strategy.",
                ],
                "source_counts": source_counts,
                "theme_counts": theme_counts,
            },
            "coverage_summary": coverage_counts,
            "candidates": candidates,
            "next_step": {
                "agent_action": "Choose observation TopN from this pool using strategy reasoning.",
                "then_call": "get_strategy_decision_packet",
                "when": "When target_day intraday replay/live facts are needed.",
            },
            "data_gaps": [
                "Off-platform sector/news validation is not connected.",
                "Historical CLS popup alignment is not connected.",
                "Historical Level-2 active big-order buy ratio is not connected.",
                "Full-market realtime sector co-pump is not connected.",
            ],
            "notes": [
                "Facts-only daily candidate pool; no program grade, score, or probability is assigned.",
                "The agent must decide which candidates are worth observing.",
            ],
        }

    return _call_tool(_candidate_pool)


def _parse_symbol_list(symbols: str) -> list[str]:
    normalized = symbols.replace("|", ",").replace("，", ",").replace(" ", ",")
    return [item.strip().upper().split(".", 1)[0] for item in normalized.split(",") if item.strip()]


@mcp.tool
def run_historical_strategy_replay(
    as_of_day: str,
    target_day: str,
    symbols: str = "",
    limit: int = 10,
    window_start: str = "",
    window_end: str = "",
) -> dict:
    """Replay the user's intraday trigger pattern over historical minute bars.

    The tool first builds the as-of strategy watchlist, then replays target-day
    minute bars through the buy-point state machine. Optional HH:MM window
    bounds limit the replay to a partial session such as 09:31-10:00. It returns
    research alert facts only and does not include future outcome labels.
    """
    safe_as_of = as_of_day.strip()
    safe_target = target_day.strip()
    if not safe_as_of:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    if not safe_target:
        return {"data_mode": "unavailable", "error": "target_day is required"}
    safe_limit = max(1, min(int(limit or 10), 50))
    parsed_symbols = _parse_symbol_list(symbols)
    return _call_tool(
        lambda adapter: adapter.run_historical_strategy_replay(
            safe_as_of,
            safe_target,
            parsed_symbols or None,
            safe_limit,
            window_start.strip(),
            window_end.strip(),
        )
    )


@mcp.tool
def run_historical_trigger_validation(
    end_day: str,
    lookback_days: int = 5,
    limit: int = 20,
    window_start: str = "09:31",
    window_end: str = "10:00",
) -> dict:
    """Validate the intraday trigger over recent historical trading days.

    For each target day, the tool uses the previous trading day's strategy
    watchlist, replays the target-day time window, and appends post-trigger
    outcome labels for calibration. Post-trigger labels are not valid as
    decision inputs at trigger time.
    """
    safe_end = end_day.strip()
    if not safe_end:
        return {"data_mode": "unavailable", "error": "end_day is required"}
    safe_lookback = max(1, min(int(lookback_days or 5), 10))
    safe_limit = max(1, min(int(limit or 20), 50))
    return _call_tool(
        lambda adapter: adapter.run_historical_trigger_validation(
            safe_end,
            safe_lookback,
            safe_limit,
            window_start.strip() or "09:31",
            window_end.strip() or "10:00",
        )
    )


@mcp.tool
def get_intraday_theme_copump(
    symbol: str,
    as_of_day: str,
    target_day: str,
    trigger_time: str = "",
    window_start: str = "09:31",
    window_end: str = "10:00",
    peer_limit: int = 20,
) -> dict:
    """Return same-theme intraday co-pump facts for a triggered stock.

    This uses the full strategy watchlist as the current representative universe,
    then replays same-theme peers in the requested intraday window. It is a proxy
    for sector co-pump, not full-market realtime sector breadth.
    """
    safe_symbol = symbol.strip()
    safe_as_of = as_of_day.strip()
    safe_target = target_day.strip()
    if not safe_symbol:
        return {"data_mode": "unavailable", "error": "symbol is required"}
    if not safe_as_of:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    if not safe_target:
        return {"data_mode": "unavailable", "error": "target_day is required"}
    safe_peer_limit = max(1, min(int(peer_limit or 20), 50))
    return _call_tool(
        lambda adapter: adapter.get_intraday_theme_copump(
            safe_symbol,
            safe_as_of,
            safe_target,
            trigger_time.strip(),
            window_start.strip() or "09:31",
            window_end.strip() or "10:00",
            safe_peer_limit,
        )
    )


@mcp.tool
def get_intraday_orderflow_confirmation(
    symbol: str,
    trading_day: str,
    trigger_time: str = "",
    window_start: str = "09:31",
    window_end: str = "10:00",
) -> dict:
    """Return order-flow confirmation facts around an intraday trigger.

    Current jvQuant historical wiring has daily semantic capital-flow fields,
    but not verified minute-level active big-order buy ratio. The return value
    separates the unavailable trigger-window fact from weak daily proxy facts.
    """
    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not safe_symbol:
        return {"data_mode": "unavailable", "error": "symbol is required"}
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}
    return _call_tool(
        lambda adapter: adapter.get_intraday_orderflow_confirmation(
            safe_symbol,
            safe_day,
            trigger_time.strip(),
            window_start.strip() or "09:31",
            window_end.strip() or "10:00",
        )
    )


@mcp.tool
def sample_realtime_large_trade_proxy(
    symbol: str,
    duration_seconds: float = 8.0,
    threshold_cny: float = 3_000_000.0,
    window_start: str = "",
    window_end: str = "",
) -> dict:
    """Sample realtime lv2 directionless large-trade activity for one symbol.

    This is a weak order-flow proxy. It counts and sums large trades above the
    threshold, but cannot classify active buy/sell direction with current lv2
    fields.
    """
    safe_symbol = symbol.strip()
    if not safe_symbol:
        return {"data_mode": "unavailable", "error": "symbol is required"}
    safe_duration = max(1.0, min(float(duration_seconds or 8.0), 30.0))
    safe_threshold = max(1.0, float(threshold_cny or 3_000_000.0))
    return _call_tool(
        lambda adapter: adapter.sample_realtime_large_trade_proxy(
            safe_symbol,
            safe_duration,
            safe_threshold,
            window_start.strip(),
            window_end.strip(),
        )
    )


@mcp.tool
def simulate_historical_orderflow_proxy(
    symbol: str,
    trading_day: str,
    window_start: str = "09:31",
    window_end: str = "10:00",
    volume_ratio_threshold: float = 1.5,
) -> dict:
    """Simulate weak order-flow activity from historical minute volume.

    This does not reconstruct tick-level large trades or active buy/sell side.
    It flags minute bars whose volume is elevated relative to the opening
    baseline, so agents can test the shape offline without pretending to have
    historical Level-2.
    """
    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not safe_symbol:
        return {"data_mode": "unavailable", "error": "symbol is required"}
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}
    safe_threshold = max(0.1, min(float(volume_ratio_threshold or 1.5), 20.0))
    return _call_tool(
        lambda adapter: adapter.simulate_historical_orderflow_proxy(
            safe_symbol,
            safe_day,
            window_start.strip() or "09:31",
            window_end.strip() or "10:00",
            safe_threshold,
        )
    )


@mcp.tool
def get_strategy_decision_packet(
    as_of_day: str,
    target_day: str,
    symbols: str = "",
    limit: int = 10,
    window_start: str = "09:31",
    window_end: str = "10:00",
    include_minute_volume_proxy: bool = False,
    include_full_theme_copump: bool = False,
) -> dict:
    """Bundle facts needed for the user's strategy without assigning grades.

    The packet reduces agent tool-wandering: it returns the as-of strategy
    candidate facts, target-day replay facts, fast same-theme co-pump facts
    within the packet, and order-flow availability/proxy facts. The agent still
    makes the final Top3/grade/promotion_likelihood judgment.
    """
    safe_as_of = as_of_day.strip()
    safe_target = target_day.strip()
    if not safe_as_of:
        return {"data_mode": "unavailable", "error": "as_of_day is required"}
    if not safe_target:
        return {"data_mode": "unavailable", "error": "target_day is required"}
    requested = [item.strip() for item in symbols.replace(",", "|").split("|") if item.strip()]
    safe_limit = max(1, min(int(limit or 10), 50))
    safe_window_start = window_start.strip() or "09:31"
    safe_window_end = window_end.strip() or "10:00"

    def build(adapter: Any) -> dict:
        from aegis_alpha.measurements.historical_strategy_replay import (
            run_historical_strategy_replay_from_items,
        )

        if requested and hasattr(adapter, "get_strategy_items_for_symbols"):
            strategy_items = adapter.get_strategy_items_for_symbols(safe_as_of, requested)
        else:
            strategy_items = adapter.get_strategy_watchlist(safe_as_of, safe_limit)
        strategy_items = strategy_items[:safe_limit]
        replay = run_historical_strategy_replay_from_items(
            as_of_day=safe_as_of,
            target_day=safe_target,
            strategy_items=strategy_items,
            get_snapshot=lambda symbol, day: adapter.get_stock_minute_replay_snapshot(
                symbol,
                day,
                1,
                max_bars=240,
            ),
            window_start=safe_window_start,
            window_end=safe_window_end,
        )
        results = []
        replay_results = replay.get("results", [])
        for result in replay_results:
            symbol = str(result.get("symbol") or "")
            diagnostics = result.get("pattern_diagnostics") or {}
            trigger_time = str(
                result.get("first_triggered_at")
                or diagnostics.get("first_cross_time")
                or diagnostics.get("max_price_time")
                or ""
            )
            orderflow = adapter.get_intraday_orderflow_confirmation(
                symbol,
                safe_target,
                trigger_time,
                safe_window_start,
                safe_window_end,
            )
            theme_copump = _packet_theme_copump(
                result,
                replay_results,
                trigger_time=trigger_time,
            )
            if include_full_theme_copump:
                theme_copump = {
                    "fast_packet_copump": theme_copump,
                    "full_theme_copump": adapter.get_intraday_theme_copump(
                        symbol,
                        safe_as_of,
                        safe_target,
                        trigger_time,
                        safe_window_start,
                        safe_window_end,
                        20,
                    ),
                }
            item = {
                **result,
                "orderflow_confirmation": orderflow,
                "intraday_theme_copump": theme_copump,
            }
            if include_minute_volume_proxy:
                item["historical_minute_volume_proxy"] = adapter.simulate_historical_orderflow_proxy(
                    symbol,
                    safe_target,
                    safe_window_start,
                    safe_window_end,
                    1.5,
                )
            results.append(item)
        returned = {str(item.get("symbol") or "").split(".", 1)[0] for item in results}
        return {
            "as_of_day": safe_as_of,
            "target_day": safe_target,
            "data_mode": "strategy_decision_packet",
            "window": {"start": safe_window_start, "end": safe_window_end},
            "strategy_candidate_count": len(strategy_items),
            "result_count": len(results),
            "requested_symbols": requested,
            "missing_requested_symbols": [
                item for item in requested
                if item.split(".", 1)[0] not in returned
            ],
            "results": results,
            "notes": [
                "Facts-only packet for agent judgment; no program grade or score is assigned.",
                "Order-flow fields separate unavailable active big-order buy ratio from weak proxies.",
                "Default co-pump is packet-local for speed; full same-theme replay is explicit.",
                "Minute-volume proxy is included only when explicitly requested.",
            ],
        }

    return _call_tool(build)


@mcp.tool
def get_second_board_next_day_outcomes(
    trading_day: str,
    symbols: str = "",
    limit: int = 50,
) -> dict:
    """Return facts-only T+1 outcome labels for historical second-board candidates.

    If `symbols` is blank, the adapter first resolves the historical candidate pool
    for `trading_day` and labels that pool. Pipe-, comma-, and space-separated symbol
    strings are accepted.
    """
    safe_day = trading_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}
    safe_limit = max(1, min(int(limit or 50), 200))
    parsed_symbols = _parse_symbol_list(symbols)
    return _call_tool(
        lambda adapter: adapter.get_second_board_next_day_outcomes(
            safe_day,
            parsed_symbols or None,
            safe_limit,
        )
    )


@mcp.tool
def get_second_board_candidate_data_quality(symbol: str) -> dict:
    """Return compact data-quality evidence for one second-board candidate."""

    def _quality(adapter: Any) -> dict:
        normalized = symbol.strip().upper().split(".", 1)[0]
        for candidate in adapter.get_second_board_candidates():
            if candidate.symbol == symbol or candidate.symbol == normalized:
                return {
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "data_mode": candidate.data_mode,
                    "provider": candidate.provider,
                    "data_quality": {
                        key: value.model_dump()
                        for key, value in candidate.data_quality.items()
                    },
                }
        return {
            "symbol": symbol,
            "data_mode": "unavailable",
            "error": "Candidate not found in current second-board pool.",
        }

    return _call_tool(_quality)


@mcp.tool
def get_promotion_dossier(symbol: str) -> dict:
    """Bundle the five promotion-judgment factors (市场情绪/题材位置/股本/量能/回封力度) for one
    second-board candidate into a single facts-only dossier. No probability or grade is
    assigned — judgment belongs to the agent. Not a buy/sell/order instruction."""
    from aegis_alpha.measurements.promotion_dossier import assemble_promotion_dossier

    def _dossier(adapter: Any) -> dict:
        normalized = symbol.strip().upper().split(".", 1)[0]
        gate = adapter.get_market_sentiment_gate()
        for candidate in adapter.get_second_board_candidates():
            if candidate.symbol == symbol or candidate.symbol == normalized:
                return assemble_promotion_dossier(candidate, gate).model_dump()
        return {
            "symbol": symbol,
            "data_mode": "unavailable",
            "error": "Candidate not found in current second-board pool.",
        }

    return _call_tool(_dossier)


@mcp.tool
def explain_candidate(symbol: str) -> dict:
    """Explain a watchlist candidate without issuing buy or sell instructions."""
    return _call_tool(lambda adapter: adapter.explain_candidate(symbol).model_dump())


@mcp.tool
def explain_second_board_candidate(symbol: str) -> dict:
    """Explain a second-board candidate without issuing buy or sell instructions."""
    return _call_tool(lambda adapter: adapter.explain_second_board_candidate(symbol).model_dump())


@mcp.tool
def get_seal_timeline(symbol: str, trading_day: str = "") -> dict:
    """Return the intraday seal/break timeline for one stock."""
    return _call_tool(lambda adapter: adapter.get_seal_timeline(symbol, trading_day.strip()).model_dump())


@mcp.tool
def generate_daily_review(trading_day: str) -> dict:
    """Generate today's review aggregating candidates and outcomes."""
    from aegis_alpha.reviews.daily import generate_daily_review as _gen

    safe_day = trading_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}

    def _build(adapter: Any) -> dict:
        return _gen(adapter, get_store(), trading_day=safe_day).model_dump()

    return _call_tool(_build)


@mcp.tool
def generate_weekly_pattern_report(start_day: str, end_day: str) -> dict:
    """Generate grade x outcome report between start_day and end_day (inclusive)."""
    from aegis_alpha.reviews.weekly import generate_weekly_pattern_report as _gen

    safe_start = start_day.strip()
    safe_end = end_day.strip()
    if not (safe_start and safe_end):
        return {"data_mode": "unavailable", "error": "start_day and end_day are required"}
    return _call_store(lambda store: _gen(store, start_day=safe_start, end_day=safe_end).model_dump())


@mcp.tool
def get_pending_alerts(limit: int = 20) -> list[dict] | dict:
    """Return pending alerts that have not been acknowledged."""
    from aegis_alpha.alerts.store import AlertStore

    safe_limit = max(1, min(int(limit or 20), 100))
    return _call_store(lambda store: [a.model_dump() for a in AlertStore(store).list_pending(limit=safe_limit)])


@mcp.tool
def acknowledge_alert(alert_id: str, note: str = "") -> dict:
    """Acknowledge a pending alert."""
    from aegis_alpha.alerts.store import AlertStore

    safe_id = alert_id.strip()
    if not safe_id:
        return {"data_mode": "unavailable", "error": "alert_id is required"}
    return _call_store(lambda store: AlertStore(store).acknowledge(safe_id, note=note.strip()).model_dump())


@mcp.tool
def create_watchlist(owner: str, label: str, symbols: str = "", expires_at: str = "") -> dict:
    """Create a new watchlist for `owner` with optional pipe-separated `symbols`."""
    from aegis_alpha.watchlists.manager import WatchlistManager

    safe_symbols = [item.strip() for item in symbols.split("|") if item.strip()]
    return _call_store(
        lambda store: WatchlistManager(store)
        .create(
            owner=owner.strip(),
            label=label.strip(),
            symbols=safe_symbols,
            expires_at=expires_at.strip(),
        )
        .model_dump()
    )


@mcp.tool
def update_watchlist_state(
    watchlist_id: str,
    symbol: str,
    new_grade: str,
    action: str,
    note: str = "",
) -> dict:
    """Update one entry's grade and action history in a watchlist."""
    from aegis_alpha.watchlists.manager import WatchlistManager

    return _call_store(
        lambda store: WatchlistManager(store)
        .update_state(
            watchlist_id.strip(),
            symbol.strip(),
            new_grade=new_grade.strip().upper(),
            action=action.strip().lower(),
            note=note.strip(),
        )
        .model_dump()
    )


@mcp.tool
def close_watchlist(watchlist_id: str, note: str = "") -> dict:
    """Close an active watchlist."""
    from aegis_alpha.watchlists.manager import WatchlistManager

    return _call_store(
        lambda store: WatchlistManager(store).close(watchlist_id.strip(), note=note.strip()).model_dump()
    )


@mcp.tool
def list_active_watchlists(owner: str = "") -> list[dict] | dict:
    """List active watchlists for an owner (or all owners if blank)."""
    from aegis_alpha.watchlists.manager import WatchlistManager

    return _call_store(
        lambda store: [item.model_dump() for item in WatchlistManager(store).list_active(owner=owner.strip())]
    )


@mcp.tool
def get_top_themes_today(trading_day: str = "", limit: int = 10) -> list[dict]:
    """Return today's top themes ranked by member count and leader height."""
    from aegis_alpha.themes.ranking import compute_top_themes

    safe_day = trading_day.strip()
    safe_limit = max(1, min(int(limit or 10), 50))

    def _build(adapter: Any) -> list[dict]:
        leaders = adapter.get_theme_leaders(trading_day=safe_day)
        return [r.model_dump() for r in compute_top_themes(leaders, trading_day=safe_day or "", limit=safe_limit)]

    return _call_tool(_build)


@mcp.tool
def backfill_candidates(trading_days: str) -> dict:
    """Capture today's candidate pool snapshot for each given trading day (pipe-separated)."""
    from aegis_alpha.feedback.backfill import backfill_candidates as _backfill

    safe_days = [d.strip() for d in trading_days.split("|") if d.strip()]
    if not safe_days:
        return {"data_mode": "unavailable", "error": "trading_days is required (pipe-separated)"}

    def _run(adapter: Any) -> dict:
        store = get_store()
        persisted = _backfill(adapter, store, trading_days=safe_days)
        return {"persisted": persisted, "trading_days": safe_days}

    return _call_tool(_run)


@mcp.tool
def attribute_outcome(symbol: str, trading_day: str) -> dict:
    """Attribute a failed candidate outcome from stored data."""
    from aegis_alpha.feedback.attribution import attribute_from_stored_data

    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable", "error": "symbol and trading_day are required"}

    def _run(adapter: Any) -> dict:
        attribution = attribute_from_stored_data(
            adapter=adapter,
            store=get_store(),
            symbol=safe_symbol,
            trading_day=safe_day,
        )
        if attribution is None:
            return {
                "data_mode": "unavailable",
                "error": "No outcome record or historical snapshot for this symbol/day.",
            }
        return attribution.model_dump()

    return _call_tool(_run)


@mcp.tool
def get_history_stats(symbol: str) -> dict:
    """Return three-year historical limit-up stats for one stock."""
    return _call_tool(lambda adapter: adapter.get_history_stats(symbol).model_dump())


@mcp.tool
def run_backtest(rule_changes_json: str, start_day: str, end_day: str) -> dict:
    """Run a backtest with rule_changes (JSON string) over historical snapshots."""
    import json

    from aegis_alpha.feedback.backtest import BacktestInputs, run_backtest_and_advise

    safe_start = start_day.strip()
    safe_end = end_day.strip()
    if not (safe_start and safe_end):
        return {"data_mode": "unavailable", "error": "start_day and end_day are required"}
    try:
        rule_changes = json.loads(rule_changes_json or "{}")
    except json.JSONDecodeError as exc:
        return {"data_mode": "unavailable", "error": f"rule_changes_json invalid: {exc}"}

    def _run(_store: AegisAlphaStore) -> dict:
        run, advice = run_backtest_and_advise(
            BacktestInputs(
                store=_store,
                rule_changes=rule_changes,
                start_day=safe_start,
                end_day=safe_end,
            )
        )
        return {"run": run.model_dump(), "advice": advice.model_dump()}

    return _call_store(_run)


@mcp.tool
def get_dragon_tiger(symbol: str, trading_day: str) -> dict:
    """Return one symbol's dragon-tiger record for the given day (mock or jvquant placeholder)."""
    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable", "error": "symbol and trading_day are required"}
    return _call_tool(lambda adapter: adapter.get_dragon_tiger(safe_symbol, safe_day).model_dump())


@mcp.tool
def get_active_seats_today(trading_day: str) -> list[dict] | dict:
    """Aggregate hot-money seats by alias for a single trading day."""
    safe_day = trading_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}
    return _call_tool(lambda adapter: adapter.get_active_seats_today(safe_day))


@mcp.tool
def get_limit_down_pool(trading_day: str = "") -> list[dict]:
    """Return today's limit-down stocks (contrarian pool)."""
    safe_day = trading_day.strip()
    return _call_tool(
        lambda adapter: [e.model_dump() for e in adapter.get_limit_down_pool(safe_day)]
    )


@mcp.tool
def get_st_pool(trading_day: str = "") -> list[dict]:
    """Return today's ST stocks active today."""
    safe_day = trading_day.strip()
    return _call_tool(
        lambda adapter: [e.model_dump() for e in adapter.get_st_pool(safe_day)]
    )


@mcp.tool
def get_capital_flow_slices(symbol: str, trading_day: str) -> list[dict] | dict:
    """Return per-symbol per-day capital flow slices: pre_first_seal_5m / post_break_1m / tail_30m."""
    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable", "error": "symbol and trading_day are required"}
    return _call_tool(
        lambda adapter: [
            s.model_dump() for s in adapter.get_capital_flow_slices(safe_symbol, safe_day)
        ]
    )


@mcp.tool
def get_recent_backtests(limit: int = 10) -> list[dict] | dict:
    """List recent backtest runs."""
    safe_limit = max(1, min(int(limit or 10), 50))
    return _call_store(lambda store: [r.model_dump() for r in store.list_backtest_runs(limit=safe_limit)])


@mcp.tool
def find_similar_setups(
    symbol: str,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[dict] | dict:
    """Find historical candidate snapshots structurally similar to the most
    recent snapshot of `symbol` (5-dim cosine similarity)."""
    from datetime import date, timedelta
    import json as _json

    from aegis_alpha.extensions.similar_setups import (
        find_similar_setups_in_snapshots,
        vectorize_setup,
    )

    safe_symbol = symbol.strip()
    if not safe_symbol:
        return {"data_mode": "unavailable", "error": "symbol is required"}
    safe_lookback = max(1, min(int(lookback_days or 90), 365))
    safe_threshold = max(0.0, min(float(similarity_threshold or 0.7), 1.0))

    def _run(store: AegisAlphaStore) -> list[dict]:
        today = date.today()
        start_day = (today - timedelta(days=safe_lookback)).isoformat()
        end_day = today.isoformat()
        snaps_for_symbol = store.list_historical_snapshots_between(
            start_day=start_day, end_day=end_day, symbol=safe_symbol
        )
        if not snaps_for_symbol:
            return []
        latest = snaps_for_symbol[-1]
        try:
            latest_payload = _json.loads(latest.payload_json or "{}")
        except Exception:
            latest_payload = {}
        query_vec = vectorize_setup(latest_payload)
        pool = store.list_historical_snapshots_between(
            start_day=start_day, end_day=end_day
        )
        results = find_similar_setups_in_snapshots(
            query_symbol=safe_symbol,
            query_vector=query_vec,
            snapshots=pool,
            similarity_threshold=safe_threshold,
            limit=10,
        )
        return [r.model_dump() for r in results]

    return _call_store(_run)


@mcp.tool
def get_new_stock_candidates() -> list[dict]:
    """Return today's new-stock candidates classified by free-float and listing days."""
    return _call_tool(
        lambda adapter: [c.model_dump() for c in adapter.get_new_stock_candidates()]
    )


@mcp.tool
def get_suspended_stocks(trading_day: str = "") -> list[dict]:
    """Return suspended stocks active on the given trading day."""
    safe_day = trading_day.strip()
    return _call_tool(
        lambda adapter: [
            s.model_dump() for s in adapter.get_suspended_stocks(safe_day)
        ]
    )


@mcp.tool
def query_minute_bars(symbol: str, start_day: str, end_day: str) -> list[dict] | dict:
    """Query Parquet-stored minute bars for a symbol over a date range.

    Returns a list of bar dicts. If history-store extras (pyarrow + duckdb)
    are not installed, returns {"data_mode": "unavailable", "error": ...}.
    """
    from aegis_alpha.history_store import (
        history_store_unavailable_error,
        is_history_store_available,
    )

    safe_symbol = symbol.strip()
    safe_start = start_day.strip()
    safe_end = end_day.strip()
    if not (safe_symbol and safe_start and safe_end):
        return {
            "data_mode": "unavailable",
            "error": "symbol / start_day / end_day are required",
        }
    if not is_history_store_available():
        return {
            "data_mode": "unavailable",
            "error": history_store_unavailable_error(),
        }

    from aegis_alpha.history_store.parquet_reader import MinuteBarReader

    reader = MinuteBarReader(root_dir="data")
    return reader.read_minute_bars(
        symbol=safe_symbol, start_day=safe_start, end_day=safe_end,
    )


@mcp.tool
def simulate_outcome(
    symbol: str, trading_day: str, hypothesis_json: str
) -> dict:
    """Apply a hypothesis (JSON-encoded dict of field overrides) to the
    historical snapshot for (symbol, trading_day) and return structured diff."""
    import json as _json

    from aegis_alpha.feedback.hypothesis import simulate_outcome as _simulate
    from aegis_alpha.feedback.hypothesis import HypothesisInputs

    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable",
                "error": "symbol and trading_day are required"}
    try:
        hypothesis = _json.loads(hypothesis_json or "{}")
    except _json.JSONDecodeError as exc:
        return {"data_mode": "unavailable",
                "error": f"hypothesis_json invalid: {exc}"}
    if not isinstance(hypothesis, dict):
        return {"data_mode": "unavailable",
                "error": "hypothesis_json must decode to an object"}

    def _run(store: AegisAlphaStore) -> dict:
        snap = store.get_historical_snapshot(safe_symbol, safe_day)
        if snap is None:
            return {"data_mode": "unavailable",
                    "error": "no historical snapshot for given symbol/day"}
        out = _simulate(HypothesisInputs(snapshot=snap, hypothesis=hypothesis))
        if out is None:
            return {"data_mode": "unavailable",
                    "error": "snapshot payload not valid JSON"}
        return out.model_dump()

    return _call_store(_run)


@mcp.tool
def get_market_sector_breadth(trading_day: str, theme: str) -> dict:
    """全市场板块宽度 facts(THS 体系, 成分股×涨停池 join)。失败降级 unavailable。"""
    from aegis_alpha.adapters.sector_breadth import compute_sector_breadth
    from aegis_alpha.adapters.sector_breadth.akshare_source import fetch_theme_members

    def _run(adapter: Any) -> dict:
        members_payload = fetch_theme_members(theme)
        if members_payload["data_mode"] != "ok":
            return {
                "theme": theme,
                "trading_day": trading_day,
                "data_mode": "unavailable",
                "data_source": "akshare.ths",
                "notes": ["板块成分股取数失败,无法计算宽度。"],
            }
        try:
            limitups = {str(item.symbol) for item in adapter.get_limitup_pool()}
        except Exception:
            limitups = set()
        result = compute_sector_breadth(
            theme=theme,
            members=members_payload["members"],
            limitup_symbols=limitups,
            concept_system="ths",
            data_source="akshare",
        )
        return {**result, "trading_day": trading_day}

    return _call_tool(_run)


@mcp.tool
def get_sector_breadth_continuity(theme: str, as_of_day: str, lookback_days: int = 14) -> dict:
    """板块两周持续性 facts。用市场内 theme_continuity 的每日涨停计数喂入。"""
    from aegis_alpha.adapters.sector_breadth import compute_breadth_continuity

    def _run(adapter: Any) -> dict:
        continuity = adapter.get_theme_continuity(theme, as_of_day, lookback_days)
        raw = continuity if isinstance(continuity, dict) else continuity.model_dump()
        daily_raw = raw.get("daily_counts", [])
        daily_counts: list[int] = []
        for x in daily_raw:
            if isinstance(x, dict):
                daily_counts.append(int(x.get("limit_up_count", 0)))
            else:
                daily_counts.append(int(x))
        result = compute_breadth_continuity(theme=theme, daily_limitup_counts=daily_counts)
        return {**result, "as_of_day": as_of_day, "lookback_days": lookback_days}

    return _call_tool(_run)


@mcp.tool
def get_news_alignment(symbol_or_theme: str, lookback_days: int = 7) -> dict:
    """题材/个股合规新闻对齐 facts(巨潮公告)。明标非财联社电报。失败降级。"""
    from aegis_alpha.adapters.news_alignment import compute_news_alignment
    from aegis_alpha.adapters.news_alignment.cninfo_source import fetch_recent_docs

    fetched = fetch_recent_docs(symbol_or_theme, lookback_days=lookback_days)
    return compute_news_alignment(
        query=symbol_or_theme,
        docs=fetched.get("docs", []),
        source="cninfo",
    )


@mcp.tool
def get_tick_rule_orderflow_proxy(
    symbol: str,
    window_start: str = "",
    window_end: str = "",
    big_trade_threshold_cny: float = 1_000_000.0,
    limit_up_price: float = 0.0,
) -> dict:
    """大单主动买入占比 tick-rule 代理(明标非真值,封板虚高警告)。

    与 sample_realtime_large_trade_proxy(directionless 金额)互补:
    本工具给推断方向占比,那个给无方向金额。两者都是代理,非交易所真值。
    """
    from aegis_alpha.measurements.tick_rule_orderflow import tick_rule_big_buy_ratio_proxy

    def _run(adapter: Any) -> dict:
        sample = adapter.sample_realtime_large_trade_proxy(
            symbol, threshold_cny=big_trade_threshold_cny,
            window_start=window_start, window_end=window_end,
        )
        raw = sample if isinstance(sample, dict) else sample.model_dump()
        trades = raw.get("stats", {}).get("sample_trades", [])
        result = tick_rule_big_buy_ratio_proxy(
            [{"price": float(t.get("price", 0.0)), "volume": float(t.get("volume", 0.0))} for t in trades],
            big_trade_threshold_cny=big_trade_threshold_cny,
            limit_up_price=limit_up_price,
        )
        return {
            **result,
            "symbol": symbol,
            "window": {"start": window_start, "end": window_end},
            "upstream_sample_available": bool(raw.get("sample_available", False)),
        }

    return _call_tool(_run)


def _build_naive_baselines(as_of_day: str, top_n: int) -> dict:
    """三朴素基准 TopN(封单额/封成比/首封时间)。任一不可用→[]。失败降级,不抛。"""
    n = max(1, int(top_n or 1))
    try:
        rows = get_historical_second_board_candidates(as_of_day, limit=50)
        items = rows if isinstance(rows, list) else (rows.get("candidates", []) if isinstance(rows, dict) else [])
    except Exception:
        return {"seal_amount": [], "seal_ratio": [], "first_seal_time": []}

    def _top(key: str, reverse: bool) -> list[str]:
        try:
            ranked = sorted(
                [i for i in items if isinstance(i, dict) and i.get(key) is not None],
                key=lambda i: i.get(key), reverse=reverse,
            )
            return [str(i.get("symbol")) for i in ranked[:n]]
        except Exception:
            return []

    return {
        "seal_amount": _top("seal_amount_cny", True),
        "seal_ratio": _top("seal_to_turnover_ratio", True),
        "first_seal_time": _top("first_limit_up_time", False),
    }


@mcp.tool
def record_selection_audit(
    as_of_day: str,
    picks_json: str,
    rejected_json: str = "",
    candidate_pool_size: int = 0,
    provider: str = "",
    model: str = "",
) -> dict:
    """记录 agent 收盘选股决策 (facts-only)。自动算三朴素基准对比 + confidence 守卫 + 即时反机械排序提醒。"""
    import json as _json
    from aegis_alpha.models import SelectionAudit, SelectionPick, RejectedCandidate
    from aegis_alpha.feedback.selection_audit import (
        compute_audit_id, compute_equals_baseline, compute_confidence_label,
    )

    picks = [SelectionPick.model_validate(p) for p in _json.loads(picks_json or "[]")]
    rejected = [RejectedCandidate.model_validate(r) for r in _json.loads(rejected_json or "[]")]
    pick_symbols = [p.symbol for p in picks]

    def _run(store):
        baseline = _build_naive_baselines(as_of_day, len(pick_symbols))
        equals = compute_equals_baseline(pick_symbols, baseline)
        accumulated = store.count_selection_audit_days()
        confidence = compute_confidence_label(accumulated_days=accumulated)
        audit = SelectionAudit(
            audit_id=compute_audit_id(as_of_day, pick_symbols),
            as_of_day=as_of_day, picks=picks, rejected=rejected,
            baseline=baseline, equals_baseline=equals,
            confidence_label=confidence, candidate_pool_size=candidate_pool_size,
            provider=provider, model=model,
        )
        saved = store.save_selection_audit(audit)
        result = saved.model_dump()
        if equals:
            result["anti_mechanical_warning"] = (
                "你的 TopN 等同某朴素基准(封单额/封成比/首封时间),未体现额外 alpha;请重新评估或明确标注。"
            )
        return result

    return _call_store(_run)


@mcp.tool
def get_selection_audit(as_of_day: str) -> dict:
    """取某收盘日的选股审计 (facts-only)。无记录返回 unavailable。"""
    def _run(store):
        audit = store.get_selection_audit_by_day(as_of_day)
        if audit is None:
            return {"as_of_day": as_of_day, "data_mode": "unavailable",
                    "notes": ["该日无选股审计记录。"]}
        return {**audit.model_dump(), "data_mode": "ok"}

    return _call_store(_run)


def _validation_intraday_trigger(symbol: str, as_of_day: str, target_day: str,
                                 window_start: str, window_end: str) -> dict:
    """从 decision packet 取该 symbol 目标日盘中触发事实。失败降级。"""
    try:
        packet = get_strategy_decision_packet(
            as_of_day, target_day, symbol, 1, window_start, window_end,
        )
        raw = packet if isinstance(packet, dict) else {}
        if raw.get("data_mode") == "unavailable":
            return {"triggered": None, "trigger_time": "", "data_mode": "unavailable"}
        for it in raw.get("results", []):
            if not isinstance(it, dict):
                continue
            if str(it.get("symbol", "")).split(".")[0] == symbol.split(".")[0]:
                diag = it.get("pattern_diagnostics") or {}
                triggered = bool(it.get("first_triggered_at") or diag.get("opening_window_crossed_previous_high"))
                return {"triggered": triggered,
                        "trigger_time": str(it.get("first_triggered_at", "")),
                        "data_mode": "ok"}
        return {"triggered": False, "trigger_time": "", "data_mode": "ok"}
    except Exception:
        return {"triggered": None, "trigger_time": "", "data_mode": "unavailable"}


def _validation_next_day_outcome(symbol: str, target_day: str) -> dict:
    """取触发后次日结果。失败降级。"""
    try:
        out = get_second_board_next_day_outcomes(target_day, symbol)
        if isinstance(out, dict) and out.get("data_mode") == "unavailable":
            return {"sealed_second_board": None, "next_day_open_pct": None, "data_mode": "unavailable"}
        items = out.get("outcomes", []) if isinstance(out, dict) else (out if isinstance(out, list) else [])
        for o in items:
            if not isinstance(o, dict):
                continue
            if str(o.get("symbol", "")).split(".")[0] == symbol.split(".")[0]:
                return {"sealed_second_board": o.get("sealed_second_board"),
                        "next_day_open_pct": o.get("next_day_open_pct"),
                        "data_mode": "ok"}
        return {"sealed_second_board": None, "next_day_open_pct": None, "data_mode": "ok"}
    except Exception:
        return {"sealed_second_board": None, "next_day_open_pct": None, "data_mode": "unavailable"}


@mcp.tool
def get_selection_trigger_validation(
    as_of_day: str, target_day: str,
    window_start: str = "09:31", window_end: str = "10:00",
) -> dict:
    """闭环对照 (#4):收盘选的 TopN vs 目标日盘中触发 + 次日结果。只读纯组合,facts-only。"""
    def _run(store):
        audit = store.get_selection_audit_by_day(as_of_day)
        if audit is None:
            return {"as_of_day": as_of_day, "target_day": target_day,
                    "data_mode": "unavailable", "notes": ["该日无选股审计,无法对照。"]}
        per_pick = []
        triggered = 0
        for pick in audit.picks:
            trig = _validation_intraday_trigger(pick.symbol, as_of_day, target_day, window_start, window_end)
            outcome = _validation_next_day_outcome(pick.symbol, target_day)
            if trig.get("triggered") is True:
                triggered += 1
            per_pick.append({
                "symbol": pick.symbol, "rank": pick.rank,
                "relative_reason": pick.relative_reason,
                "triggered": trig.get("triggered"),
                "trigger_time": trig.get("trigger_time", ""),
                "sealed_second_board": outcome.get("sealed_second_board"),
                "next_day_open_pct": outcome.get("next_day_open_pct"),
                "trigger_data_mode": trig.get("data_mode"),
                "outcome_data_mode": outcome.get("data_mode"),
            })
        total = len(audit.picks)
        return {
            "as_of_day": as_of_day, "target_day": target_day,
            "data_mode": "ok", "total": total,
            "triggered_count": triggered,
            "trigger_rate": round(triggered / total, 4) if total else 0.0,
            "equals_baseline": audit.equals_baseline,
            "confidence_label": audit.confidence_label,
            "window": {"start": window_start, "end": window_end},
            "per_pick": per_pick,
            "notes": [
                "盘中触发=09:31-10:00 过前高/买点;次日结果=封板/开盘涨幅。",
                "样本不足时 confidence_label=exploratory,勿过度解读。",
            ],
        }

    return _call_store(_run)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
