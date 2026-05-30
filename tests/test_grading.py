from __future__ import annotations

from aegis_alpha.grading import CandidateGradingConfig, load_candidate_grading_config


def test_candidate_grading_config_loads_defaults_from_yaml() -> None:
    config = load_candidate_grading_config()

    assert config.version == 1
    assert config.market.sentiment_hot == 75.0
    assert config.candidate.strong_change_pct == 9.5
    assert config.seal_quality.early_time == "09:45:00"


def test_candidate_grading_config_has_code_defaults() -> None:
    config = CandidateGradingConfig()

    assert config.market.break_board_penalty == 45.0
    assert config.candidate.a_theme_count == 2
