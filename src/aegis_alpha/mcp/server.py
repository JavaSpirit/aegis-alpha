from __future__ import annotations

from fastmcp import FastMCP

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


mcp = FastMCP("aegis-alpha")
adapter = MockMarketDataAdapter()


@mcp.tool
def get_market_snapshot() -> dict:
    """Return a read-only A-share market sentiment snapshot."""
    return adapter.get_market_snapshot().model_dump()


@mcp.tool
def get_market_sentiment_gate() -> dict:
    """Return the mock board-chasing market sentiment gate."""
    return adapter.get_market_sentiment_gate().model_dump()


@mcp.tool
def get_limitup_pool() -> list[dict]:
    """Return the current mock limit-up pool."""
    return [item.model_dump() for item in adapter.get_limitup_pool()]


@mcp.tool
def get_break_board_pool() -> list[dict]:
    """Return the current mock break-board pool."""
    return [item.model_dump() for item in adapter.get_break_board_pool()]


@mcp.tool
def get_stock_realtime_snapshot(symbol: str) -> dict:
    """Return a mock realtime snapshot for one stock."""
    return adapter.get_stock_realtime_snapshot(symbol).model_dump()


@mcp.tool
def get_stock_history_limitup_stats(symbol: str) -> dict:
    """Return mock historical limit-up success and next-day premium stats."""
    return adapter.get_stock_history_limitup_stats(symbol).model_dump()


@mcp.tool
def get_theme_strength(symbol: str) -> dict:
    """Return mock theme strength for one stock."""
    return adapter.get_theme_strength(symbol).model_dump()


@mcp.tool
def get_second_board_candidates() -> list[dict]:
    """Return mock candidates for the second-board radar."""
    return [item.model_dump() for item in adapter.get_second_board_candidates()]


@mcp.tool
def explain_candidate(symbol: str) -> dict:
    """Explain a watchlist candidate without issuing buy or sell instructions."""
    return adapter.explain_candidate(symbol).model_dump()


@mcp.tool
def explain_second_board_candidate(symbol: str) -> dict:
    """Explain a second-board candidate without issuing buy or sell instructions."""
    return adapter.explain_second_board_candidate(symbol).model_dump()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
