from __future__ import annotations

from aegis_alpha.adapters.jvquant.scoring import action_from_score, market_score, sentiment_from_score
from aegis_alpha.grading import CandidateGradingConfig


def test_jvquant_scoring_helpers_match_config_defaults() -> None:
    config = CandidateGradingConfig()

    score = market_score(limit_up_count=60, break_board_rate=0.2, hot_theme_count=4, config=config)

    assert score == 73.0
    assert sentiment_from_score(score, config) == "warm"
    assert action_from_score(score, 0.2, config) == "selective"
