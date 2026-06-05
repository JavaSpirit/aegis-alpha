from __future__ import annotations

from aegis_alpha.adapters.jvquant.scoring import (
    action_from_score,
    market_score,
    sentiment_from_score,
    third_board_promotion_assessment,
)
from aegis_alpha.grading import CandidateGradingConfig


def test_jvquant_scoring_helpers_match_config_defaults() -> None:
    config = CandidateGradingConfig()

    score = market_score(limit_up_count=60, break_board_rate=0.2, hot_theme_count=4, config=config)

    assert score == 73.0
    assert sentiment_from_score(score, config) == "warm"
    assert action_from_score(score, 0.2, config) == "selective"


def test_third_board_assessment_penalizes_extended_theme_position() -> None:
    config = CandidateGradingConfig()
    common = dict(
        action="selective",
        theme_role="leader",
        theme_recent_active_days=1,
        theme_recent_max_member_count=1,
        free_float_market_cap_cny=4_000_000_000,
        turnover_cny=800_000_000,
        seal_amount_cny=120_000_000,
        seal_to_turnover_ratio=2.0,
        first_limit_up_time="09:40:00",
        break_board_count=0,
        reseal_count=0,
        final_seal_time="unknown",
        big_order_net_inflow_ratio=0.03,
        orderbook_quality=60.0,
        auction_change_pct=2.5,
        auction_turnover_cny=50_000_000,
        weekly_health_score=70.0,
        config=config,
    )

    early = third_board_promotion_assessment(
        theme_position="early",
        theme_max_height=2,
        theme_multi_board_count=1,
        **common,
    )
    extended = third_board_promotion_assessment(
        theme_position="extended",
        theme_max_height=5,
        theme_multi_board_count=4,
        **common,
    )

    assert early["promotion_score"] > extended["promotion_score"]
    assert extended["promotion_reason"].startswith("市场闸门")
    assert "题材阶段=extended" in extended["promotion_reason"]
