from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CandidateGrade = Literal["A", "B", "C", "REJECT"]
MarketAction = Literal["active", "selective", "defensive", "avoid"]
SignalConfidence = Literal["high", "medium", "low", "placeholder", "unavailable"]
SignalAuthority = Literal["official_doc", "observed_probe", "internal_inference"]


class SignalEvidence(BaseModel):
    authority: SignalAuthority
    source: str
    detail: str
    observed_at: str = ""


class SignalMetadata(BaseModel):
    source: str
    source_field: str
    timestamp: str
    confidence: SignalConfidence
    usable_for_grading: bool
    limitations: list[str] = Field(default_factory=list)
    evidence: list[SignalEvidence] = Field(default_factory=list)


class MarketSnapshot(BaseModel):
    market: str
    trading_day: str
    timestamp: str
    data_mode: str = "mock"
    provider: str = "mock"
    sentiment: str
    limit_up_count: int
    break_board_count: int
    break_board_rate: float = Field(ge=0, le=1)
    leading_themes: list[str]
    notes: list[str]


class MarketSentimentGate(BaseModel):
    trading_day: str
    timestamp: str
    data_mode: str = "mock"
    provider: str = "mock"
    action: MarketAction
    score: float = Field(ge=0, le=100)
    limit_up_count: int
    break_board_rate: float = Field(ge=0, le=1)
    second_board_success_rate: float = Field(ge=0, le=1)
    hot_theme_count: int
    risk_flags: list[str]
    positive_signals: list[str]
    conclusion: str


class LimitUpStock(BaseModel):
    symbol: str
    name: str
    data_mode: str = "mock"
    provider: str = "mock"
    theme: str
    first_limit_up_time: str
    seal_amount_cny: float
    free_float_market_cap_cny: float
    seal_amount_ratio: float
    reopen_count: int
    status: Literal["sealed", "reopened", "broken"]


class BreakBoardStock(BaseModel):
    symbol: str
    name: str
    data_mode: str = "mock"
    provider: str = "mock"
    theme: str
    first_break_time: str
    max_seal_amount_cny: float
    current_change_pct: float
    reason: str


class StockRealtimeSnapshot(BaseModel):
    symbol: str
    name: str
    timestamp: str
    data_mode: str = "mock"
    provider: str = "mock"
    last_price: float
    change_pct: float
    turnover_cny: float
    big_order_net_inflow_cny: float
    bid_quality_score: float = Field(ge=0, le=100)
    ask_pressure_score: float = Field(ge=0, le=100)
    orderbook_notes: list[str]


class OrderbookQueueLevel(BaseModel):
    side: Literal["bid", "ask", "unknown"]
    level_label: str
    price: float
    volume_count: float
    queue_count: int
    queue_slice: str


class StockOrderbookSnapshot(BaseModel):
    symbol: str
    name: str
    timestamp: str
    data_mode: str
    provider: str
    level_count: int
    best_bid_price: float | None
    best_ask_price: float | None
    bid_levels: list[OrderbookQueueLevel]
    ask_levels: list[OrderbookQueueLevel]
    notes: list[str]


class MinuteReplayBar(BaseModel):
    time: str
    last_price: float
    average_price: float = 0.0
    volume: float = 0.0


class MinuteReplaySnapshot(BaseModel):
    symbol: str
    name: str = "unknown"
    timestamp: str
    data_mode: str = "minute_replay"
    provider: str = "jvQuant"
    trading_day: str
    previous_close: float = 0.0
    last_price: float = 0.0
    minute_count: int = 0
    bars: list[MinuteReplayBar] = Field(default_factory=list)
    speed_pct_by_window: dict[str, float] = Field(default_factory=dict)
    speed_window_by_window: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class LimitUpHistoryStats(BaseModel):
    symbol: str
    sample_size: int
    seal_success_rate: float = Field(ge=0, le=1)
    next_day_positive_rate: float = Field(ge=0, le=1)
    median_next_day_premium_pct: float
    avg_next_day_premium_pct: float
    notes: list[str]


class ThemeStrength(BaseModel):
    symbol: str
    primary_theme: str
    theme_rank: int
    limit_up_count: int
    leading_stock: str
    strength_score: float = Field(ge=0, le=100)
    notes: list[str]


class SecondBoardCandidate(BaseModel):
    symbol: str
    name: str
    data_mode: str = "mock"
    provider: str = "mock"
    theme: str
    previous_limit_up_time: str
    first_limit_up_time: str = "unknown"
    seal_amount_cny: float = 0.0
    seal_volume_shares: float = 0.0
    seal_to_turnover_ratio: float = 0.0
    queue_position_note: str = ""
    current_change_pct: float
    auction_change_pct: float = 0.0
    auction_turnover_cny: float = 0.0
    auction_turnover_rate: float = 0.0
    five_min_speed_pct: float
    five_min_speed_window: str = "unknown"
    five_min_speed_timestamp: str = ""
    minute_replay_timestamp: str = ""
    minute_replay_trading_day: str = ""
    minute_replay_bar_count: int = 0
    one_min_speed_pct: float = 0.0
    one_min_speed_window: str = "unknown"
    one_min_speed_timestamp: str = ""
    three_min_speed_pct: float = 0.0
    three_min_speed_window: str = "unknown"
    three_min_speed_timestamp: str = ""
    ten_min_speed_pct: float = 0.0
    ten_min_speed_window: str = "unknown"
    ten_min_speed_timestamp: str = ""
    big_order_net_inflow_ratio: float = Field(ge=-1, le=1)
    concept_tags: list[str] = Field(default_factory=list)
    topic_tags: list[str] = Field(default_factory=list)
    break_board_count: int = 0
    reseal_count: int = 0
    final_seal_time: str = "unknown"
    max_seal_amount_cny: float = 0.0
    max_seal_volume_shares: float = 0.0
    same_theme_rising_count: int
    orderbook_quality_score: float = Field(ge=0, le=100)
    three_year_touch_limit_success_rate: float = Field(ge=0, le=1)
    three_year_sealed_next_day_gap_up_rate: float = Field(ge=0, le=1)
    estimated_seal_probability: float = Field(ge=0, le=1)
    grade: CandidateGrade
    grade_reason: str = ""
    data_quality: dict[str, SignalMetadata] = Field(default_factory=dict)
    notes: list[str]


class CandidateExplanation(BaseModel):
    symbol: str
    grade: CandidateGrade
    grade_reason: str = ""
    observations: list[str]
    risks: list[str]
    trigger_conditions: list[str]
    avoid_conditions: list[str]
    data_timestamp: str
    disclaimer: str
