from __future__ import annotations

from aegis_alpha.grading import CandidateGradingConfig


def market_score(
    limit_up_count: int,
    break_board_rate: float,
    hot_theme_count: int,
    config: CandidateGradingConfig,
) -> float:
    market = config.market
    score = market.base_score
    score += min(market.limit_up_cap, limit_up_count * market.limit_up_weight)
    score += min(market.hot_theme_cap, hot_theme_count * market.hot_theme_weight)
    score -= break_board_rate * market.break_board_penalty
    return round(max(0.0, min(100.0, score)), 2)


def sentiment_from_score(score: float, config: CandidateGradingConfig) -> str:
    market = config.market
    if score >= market.sentiment_hot:
        return "hot"
    if score >= market.sentiment_warm:
        return "warm"
    if score >= market.sentiment_mixed:
        return "mixed"
    return "cold"


def action_from_score(score: float, break_board_rate: float, config: CandidateGradingConfig) -> str:
    market = config.market
    if break_board_rate >= market.avoid_break_board_rate or score < market.avoid_score_below:
        return "avoid"
    if break_board_rate >= market.defensive_break_board_rate or score < market.defensive_score_below:
        return "defensive"
    if score >= market.active_score_at_least and break_board_rate < market.active_break_board_below:
        return "active"
    return "selective"
