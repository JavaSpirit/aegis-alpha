from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP

from aegis_alpha.adapters.factory import create_market_data_adapter


mcp = FastMCP("aegis-alpha")


def _call_tool(callback: Callable[[Any], Any]) -> Any:
    try:
        adapter = create_market_data_adapter()
        return callback(adapter)
    except Exception as exc:
        return {
            "data_mode": "unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Data source unavailable. Research output only; do not infer missing market data.",
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
def get_stock_history_limitup_stats(symbol: str) -> dict:
    """Return mock historical limit-up success and next-day premium stats."""
    return _call_tool(lambda adapter: adapter.get_stock_history_limitup_stats(symbol).model_dump())


@mcp.tool
def get_theme_strength(symbol: str) -> dict:
    """Return mock theme strength for one stock."""
    return _call_tool(lambda adapter: adapter.get_theme_strength(symbol).model_dump())


@mcp.tool
def get_second_board_candidates() -> list[dict]:
    """Return mock candidates for the second-board radar."""
    return _call_tool(lambda adapter: [item.model_dump() for item in adapter.get_second_board_candidates()])


@mcp.tool
def get_second_board_candidates_compact(limit: int = 12) -> list[dict]:
    """Return compact second-board candidates without verbose evidence."""

    def _compact(adapter: Any) -> list[dict]:
        safe_limit = max(1, min(int(limit or 12), 50))
        items = []
        for candidate in adapter.get_second_board_candidates()[:safe_limit]:
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
                    "estimated_seal_probability": candidate.estimated_seal_probability,
                    "grade": candidate.grade,
                    "grade_reason": candidate.grade_reason,
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
def explain_candidate(symbol: str) -> dict:
    """Explain a watchlist candidate without issuing buy or sell instructions."""
    return _call_tool(lambda adapter: adapter.explain_candidate(symbol).model_dump())


@mcp.tool
def explain_second_board_candidate(symbol: str) -> dict:
    """Explain a second-board candidate without issuing buy or sell instructions."""
    return _call_tool(lambda adapter: adapter.explain_second_board_candidate(symbol).model_dump())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
