from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CandidateGrade = Literal["A", "B", "C", "REJECT"]


class MarketSnapshot(BaseModel):
    market: str
    trading_day: str
    timestamp: str
    sentiment: str
    limit_up_count: int
    break_board_count: int
    break_board_rate: float = Field(ge=0, le=1)
    leading_themes: list[str]
    notes: list[str]


class LimitUpStock(BaseModel):
    symbol: str
    name: str
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
    theme: str
    first_break_time: str
    max_seal_amount_cny: float
    current_change_pct: float
    reason: str


class StockRealtimeSnapshot(BaseModel):
    symbol: str
    name: str
    timestamp: str
    last_price: float
    change_pct: float
    turnover_cny: float
    big_order_net_inflow_cny: float
    bid_quality_score: float = Field(ge=0, le=100)
    ask_pressure_score: float = Field(ge=0, le=100)
    orderbook_notes: list[str]


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


class CandidateExplanation(BaseModel):
    symbol: str
    grade: CandidateGrade
    observations: list[str]
    risks: list[str]
    trigger_conditions: list[str]
    avoid_conditions: list[str]
    data_timestamp: str
    disclaimer: str

