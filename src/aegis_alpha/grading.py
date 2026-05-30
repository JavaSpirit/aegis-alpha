from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class MarketScoringConfig(BaseModel):
    base_score: float = 35.0
    limit_up_weight: float = 0.65
    limit_up_cap: float = 35.0
    hot_theme_weight: float = 3.0
    hot_theme_cap: float = 15.0
    break_board_penalty: float = 45.0
    sentiment_hot: float = 75.0
    sentiment_warm: float = 60.0
    sentiment_mixed: float = 45.0
    avoid_break_board_rate: float = 0.55
    avoid_score_below: float = 40.0
    defensive_break_board_rate: float = 0.40
    defensive_score_below: float = 55.0
    active_score_at_least: float = 75.0
    active_break_board_below: float = 0.28


class CandidateThresholdConfig(BaseModel):
    reject_change_pct_below: float = 5.0
    strong_change_pct: float = 9.5
    b_change_pct: float = 7.0
    a_five_min_speed_pct: float = 1.5
    a_big_order_ratio: float = 0.03
    a_orderbook_quality: float = 60.0
    a_theme_count: int = 2
    a_seal_quality: float = 55.0
    defensive_orderbook_quality: float = 55.0
    defensive_big_order_ratio: float = 0.03
    defensive_seal_quality: float = 60.0
    b_orderbook_quality: float = 50.0
    b_seal_quality: float = 45.0


class SealQualityConfig(BaseModel):
    early_time: str = "09:45:00"
    early_score: float = 35.0
    morning_time: str = "10:30:00"
    morning_score: float = 22.0
    afternoon_time: str = "14:30:00"
    afternoon_score: float = 10.0
    large_seal_amount_cny: float = 300_000_000.0
    large_seal_score: float = 30.0
    medium_seal_amount_cny: float = 100_000_000.0
    medium_seal_score: float = 20.0
    small_seal_amount_cny: float = 30_000_000.0
    small_seal_score: float = 10.0
    strong_seal_to_turnover_ratio: float = 5.0
    strong_ratio_score: float = 25.0
    medium_seal_to_turnover_ratio: float = 2.0
    medium_ratio_score: float = 16.0
    small_seal_to_turnover_ratio: float = 1.0
    small_ratio_score: float = 8.0


class CandidateGradingConfig(BaseModel):
    version: int = 1
    market: MarketScoringConfig = MarketScoringConfig()
    candidate: CandidateThresholdConfig = CandidateThresholdConfig()
    seal_quality: SealQualityConfig = SealQualityConfig()


def load_candidate_grading_config(path: str | Path | None = None) -> CandidateGradingConfig:
    config_path = Path(path) if path else project_root() / "config" / "candidate_grading.yaml"
    payload = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    return CandidateGradingConfig.model_validate(payload or {})
