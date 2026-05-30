from __future__ import annotations

from aegis_alpha.themes.auction import AuctionAnalyzer, classify_auction_pattern


def test_classify_auction_pattern_strong_open() -> None:
    pattern, _reason = classify_auction_pattern(auction_change_pct=3.2, auction_turnover_rate=1.8)

    assert pattern == "strong_open"


def test_auction_analyzer_returns_model() -> None:
    analysis = AuctionAnalyzer().analyze(
        symbol="600000",
        trading_day="2026-05-29",
        auction_change_pct=6.1,
        auction_turnover_rate=6.0,
    )

    assert analysis.pattern == "exit_liquidity"
