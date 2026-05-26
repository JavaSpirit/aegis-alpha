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
