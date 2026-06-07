from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CandidateGrade = Literal["A", "B", "C", "REJECT"]
AgentCorrectionType = Literal["DATA_ERROR", "UNIT_ERROR", "STRATEGY_ERROR", "EXPRESSION_RISK", "OTHER"]
AgentCorrectionActionTarget = Literal["adapter", "scoring_config", "memory", "skill", "review_only"]
AgentCorrectionActionPriority = Literal["high", "medium", "low"]
AgentCorrectionActionStatus = Literal["needs_human_review", "ready_to_apply", "collect_more_evidence"]
CorrectionActionProposalStatus = Literal["pending", "approved", "rejected", "applied", "superseded"]
CorrectionActionDecisionType = Literal["approve", "reject", "apply", "supersede", "reopen"]
SignalConfidence = Literal["high", "medium", "low", "placeholder", "unavailable"]
SignalAuthority = Literal["official_doc", "observed_probe", "internal_inference"]
FreshnessStatus = Literal["fresh", "stale", "unknown"]
LadderHeight = Literal[
    "first_board",
    "second_board",
    "third_board",
    "fourth_board",
    "high_height",
    "broken",
    "unknown",
]
ThemeLeaderRole = Literal["leader", "co_leader", "follower", "unknown"]
AuctionPattern = Literal["strong_open", "exit_liquidity", "weak_open", "stable", "unknown"]
MarketEventType = Literal[
    "THEME_CLUSTER_RISING",
    "APPROACHING_LIMIT_UP",
    "SEAL_ORDER_DECAY",
    "BIG_ORDER_INFLOW_SPIKE",
    "SECOND_BOARD_CANDIDATE_REPRICE",
    "THEME_DIVERGENCE",
    "MARKET_BOTTOM_REVERSAL",
    "THEME_LEADER_BREAK_BOARD",
    "SECTOR_ROTATION",
]
WatchlistStatus = Literal["active", "closed", "expired"]
WatchlistEntryAction = Literal["added", "promoted", "downgraded", "dropped", "noted"]
SealTimelineKind = Literal["first_seal", "break", "reseal", "final_break"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["pending", "acknowledged", "expired"]
OutcomeAttributionTag = Literal[
    "leader_break_down",
    "high_break_board_environment",
    "auction_high_open_too_far",
    "first_seal_too_late",
    "seal_amount_decay",
    "theme_breadth_collapsed",
    "no_clear_attribution",
]
BacktestStatus = Literal["pending", "running", "completed", "failed"]
HistoryStatsConfidence = Literal["high", "medium", "low", "insufficient_sample"]
RunnerState = Literal[
    "STOPPED",
    "STARTING",
    "WAITING",
    "CONNECTED",
    "SUBSCRIBING",
    "RUNNING",
    "DEGRADED",
    "RECONNECTING",
    "STOPPING",
]
DragonTigerSeatType = Literal[
    "hot_money_known",
    "hot_money_unknown",
    "institution",
    "hk_connect",
    "retail_proxy",
    "unknown",
]
LimitupDriverType = Literal[
    "earnings",
    "policy",
    "theme",
    "hot_money",
    "unknown",
]
IntradayPattern = Literal[
    "one_word_board",
    "t_shape_board",
    "messy_board",
    "platform_breakout",
    "false_breakout",
    "normal",
    "unknown",
]
ThemeLifecycleStage = Literal[
    "launch",      # 启动
    "fermenting",  # 发酵
    "climax",      # 高潮
    "divergence",  # 分歧
    "ebb",         # 退潮
    "unknown",
]
ContrarianPoolKind = Literal["limit_down", "st"]
CapitalFlowSliceWindow = Literal[
    "daily",
    "pre_first_seal_5m",
    "post_break_1m",
    "tail_30m",
]
NewStockTier = Literal[
    "tier_a_smallcap_recent",
    "tier_b_midcap_recent",
    "tier_c_largecap",
    "tier_aged_out",
    "unknown",
]


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
    limit_up_count: int
    break_board_rate: float = Field(ge=0, le=1)
    second_board_success_rate: float = Field(ge=0, le=1)
    hot_theme_count: int
    risk_flags: list[str]
    positive_signals: list[str]
    conclusion: str
    yesterday_limitup_today_premium_pct: float = 0.0
    consecutive_boards_alive_rate: float = Field(default=0.0, ge=0, le=1)
    first_to_second_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    second_to_third_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    max_height_today: int = 0


class LadderEntry(BaseModel):
    symbol: str
    trading_day: str
    consecutive_boards: int = Field(ge=0)
    height_label: LadderHeight = "unknown"
    last_limit_up_day: str = ""
    history_window_days: int = 10
    notes: list[str] = Field(default_factory=list)


class ThemeLeader(BaseModel):
    theme: str
    trading_day: str
    leader_symbol: str
    leader_name: str
    leader_consecutive_boards: int = 0
    leader_first_limit_up_time: str = "unknown"
    leader_seal_amount_cny: float = 0.0
    leader_status: Literal["sealed", "broken", "reopened", "unknown"] = "unknown"
    co_leader_symbols: list[str] = Field(default_factory=list)
    member_count: int = 0
    notes: list[str] = Field(default_factory=list)


class AuctionAnalysis(BaseModel):
    symbol: str
    trading_day: str
    auction_change_pct: float = 0.0
    auction_turnover_cny: float = 0.0
    auction_turnover_rate: float = 0.0
    pattern: AuctionPattern = "unknown"
    pattern_reason: str = ""
    pre_open_change_pct: float = 0.0
    final_open_change_pct: float = 0.0
    cancellation_rate: float = Field(default=0.0, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class MarketEmotion(BaseModel):
    trading_day: str
    yesterday_limitup_today_premium_pct: float = 0.0
    yesterday_consecutive_boards_alive_count: int = 0
    yesterday_consecutive_boards_total: int = 0
    yesterday_consecutive_boards_alive_rate: float = Field(default=0.0, ge=0, le=1)
    first_to_second_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    second_to_third_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    first_board_to_consecutive_ratio: float = Field(default=0.0, ge=0, le=10)
    max_height_today: int = 0
    notes: list[str] = Field(default_factory=list)


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


class SignalSnapshot(BaseModel):
    symbol: str
    name: str = "unknown"
    theme: str = "unknown"
    provider: str = "mock"
    data_mode: str = "mock"
    price: float = 0.0
    change_pct: float = 0.0
    speed_1m_pct: float = 0.0
    speed_3m_pct: float = 0.0
    speed_5m_pct: float = 0.0
    speed_10m_pct: float = 0.0
    big_order_net_inflow_cny: float = 0.0
    big_order_net_inflow_ratio: float = Field(default=0.0, ge=-1, le=1)
    orderbook_quality_score: float = Field(default=50.0, ge=0, le=100)
    ask_pressure_score: float = Field(default=50.0, ge=0, le=100)
    seal_amount_cny: float = 0.0
    seal_decay_pct: float = 0.0
    sell_wall_amount_cny: float = 0.0
    data_timestamp: str
    provider_timestamp: str = ""
    received_at: str = ""
    freshness_status: FreshnessStatus = "unknown"
    notes: list[str] = Field(default_factory=list)


class MarketEvent(BaseModel):
    event_id: str
    event_type: MarketEventType
    symbol: str = ""
    name: str = ""
    theme: str = "unknown"
    confidence: SignalConfidence = "medium"
    score: float = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    provider_timestamp: str = ""
    received_at: str
    freshness_status: FreshnessStatus = "unknown"
    suggested_agent_action: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class EventScoringRule(BaseModel):
    enabled: bool = True
    trigger: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    freshness_limits: dict[str, int] = Field(default_factory=dict)
    agent_action: list[str] = Field(default_factory=list)


class EventScoringConfig(BaseModel):
    version: int = 1
    default_freshness_limit_seconds: int = 180
    rules: dict[str, EventScoringRule] = Field(default_factory=dict)


class RealtimeConnectionStatus(BaseModel):
    provider: str
    market: str = "ab"
    connected: bool = False
    subscribed: list[str] = Field(default_factory=list)
    last_message_at: str = ""
    last_error: str = ""
    notes: list[str] = Field(default_factory=list)


class RunnerStatus(BaseModel):
    state: RunnerState
    pid: int | None = None
    started_at: str = ""
    updated_at: str
    trading_session_active: bool = False
    next_action: str = ""
    provider: str = "jvQuant"
    subscribed: list[str] = Field(default_factory=list)
    last_event_at: str = ""
    last_error: str = ""
    connection: RealtimeConnectionStatus | None = None
    notes: list[str] = Field(default_factory=list)


class CandidateOutcomeReview(BaseModel):
    symbol: str
    trading_day: str
    touched_limit_up: bool | None = None
    sealed_second_board: bool | None = None
    broke_after_seal: bool | None = None
    next_day_open_pct: float | None = None
    next_day_high_pct: float | None = None
    third_day_premium_pct: float | None = None
    user_correction: str = ""
    notes: list[str] = Field(default_factory=list)


class AgentReview(BaseModel):
    review_id: str = ""
    run_type: str
    target_time: str = ""
    symbols: list[str] = Field(default_factory=list)
    provider: str = "deepseek"
    model: str = ""
    passed: bool = False
    grades: list[CandidateGrade] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class AgentReviewCorrection(BaseModel):
    correction_id: str = ""
    review_id: str
    symbol: str = ""
    correction_type: AgentCorrectionType = "OTHER"
    expected_grade: CandidateGrade | None = None
    comment: str = ""
    created_at: str = ""


class AgentCorrectionAction(BaseModel):
    target: AgentCorrectionActionTarget
    priority: AgentCorrectionActionPriority = "medium"
    status: AgentCorrectionActionStatus = "needs_human_review"
    correction_type: AgentCorrectionType = "OTHER"
    evidence_count: int = 0
    reason: str = ""
    action: str = ""
    suggested_patch: str = ""


class AgentCorrectionSummary(BaseModel):
    total_count: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_symbol: dict[str, int] = Field(default_factory=dict)
    recent_corrections: list[AgentReviewCorrection] = Field(default_factory=list)
    recommended_actions: list[AgentCorrectionAction] = Field(default_factory=list)
    suggested_memory: str = ""
    suggested_skill_patch: str = ""
    recommended_next_action: str = ""


class CorrectionActionDecision(BaseModel):
    decision_id: str = ""
    proposal_id: str
    decision: CorrectionActionDecisionType
    note: str = ""
    decided_by: str = "user"
    previous_status: CorrectionActionProposalStatus | None = None
    new_status: CorrectionActionProposalStatus
    created_at: str = ""


class CorrectionActionProposal(BaseModel):
    proposal_id: str = ""
    source: str = "agent_correction_summary"
    target: AgentCorrectionActionTarget
    priority: AgentCorrectionActionPriority = "medium"
    status: CorrectionActionProposalStatus = "pending"
    correction_type: AgentCorrectionType = "OTHER"
    evidence_count: int = 0
    reason: str = ""
    action: str = ""
    suggested_patch: str = ""
    created_at: str = ""
    updated_at: str = ""
    decisions: list[CorrectionActionDecision] = Field(default_factory=list)


class LimitUpHistoryStats(BaseModel):
    """Provider-shaped per-symbol historical stats. See HistoryStats for the
    P4 computed counterpart sourced from review_outcomes."""
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
    previous_consecutive_boards: int = 0
    previous_height_label: LadderHeight = "unknown"
    theme_role: ThemeLeaderRole = "unknown"
    theme_lifecycle_stage: ThemeLifecycleStage = "unknown"
    theme_leader_symbol: str = ""
    auction_pattern: AuctionPattern = "unknown"
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
    free_float_market_cap_cny: float = 0.0
    turnover_cny: float = 0.0
    main_net_inflow_cny: float = 0.0
    avg_turnover_10d_cny: float = 0.0
    ma5_slope_degrees: float = 0.0
    prev_day_volume_shrink_ratio: float = 0.0
    broke_previous_high: bool = False
    previous_high_price: float = 0.0
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
    limitup_driver_type: LimitupDriverType = "unknown"
    intraday_pattern: IntradayPattern = "unknown"
    weekly_health_score: float = Field(default=50.0, ge=0.0, le=100.0)
    data_quality: dict[str, SignalMetadata] = Field(default_factory=dict)
    notes: list[str]


class CandidateExplanation(BaseModel):
    symbol: str
    observations: list[str]
    risks: list[str]
    trigger_conditions: list[str]
    avoid_conditions: list[str]
    data_timestamp: str
    disclaimer: str


class WatchlistEntry(BaseModel):
    symbol: str
    added_at: str
    agent_grade: CandidateGrade | None = None
    agent_grade_history: list[CandidateGrade] = Field(default_factory=list)
    last_action: WatchlistEntryAction = "added"
    last_action_at: str = ""
    notes: list[str] = Field(default_factory=list)


class Watchlist(BaseModel):
    watchlist_id: str
    owner: str
    label: str
    status: WatchlistStatus = "active"
    created_at: str
    expires_at: str = ""
    closed_at: str = ""
    entries: list[WatchlistEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WatchlistDiff(BaseModel):
    watchlist_id: str
    from_timestamp: str
    to_timestamp: str
    added_symbols: list[str] = Field(default_factory=list)
    dropped_symbols: list[str] = Field(default_factory=list)
    grade_changes: dict[str, dict[str, str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class SealTimelineEvent(BaseModel):
    symbol: str
    trading_day: str
    kind: SealTimelineKind
    occurred_at: str
    seal_amount_cny: float = 0.0
    notes: list[str] = Field(default_factory=list)


class SealTimeline(BaseModel):
    symbol: str
    trading_day: str
    events: list[SealTimelineEvent] = Field(default_factory=list)
    final_status: Literal["sealed", "broken", "reopened", "unknown"] = "unknown"
    break_count: int = 0
    reseal_count: int = 0


class DailyReviewItem(BaseModel):
    symbol: str
    grade_at_pick: CandidateGrade | None = None
    theme: str = ""
    theme_role: ThemeLeaderRole = "unknown"
    previous_consecutive_boards: int = 0
    touched_limit_up: bool | None = None
    sealed_second_board: bool | None = None
    next_day_open_pct: float | None = None
    notes: list[str] = Field(default_factory=list)


class DailyReview(BaseModel):
    trading_day: str
    generated_at: str
    candidate_count: int = 0
    grade_distribution: dict[str, int] = Field(default_factory=dict)
    sealed_count: int = 0
    items: list[DailyReviewItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WeeklyPatternReport(BaseModel):
    start_day: str
    end_day: str
    generated_at: str
    grade_outcome_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_themes: list[str] = Field(default_factory=list)
    sample_size: int = 0
    notes: list[str] = Field(default_factory=list)


class AgentAlert(BaseModel):
    alert_id: str
    event_id: str = ""
    symbol: str = ""
    theme: str = ""
    severity: AlertSeverity = "info"
    status: AlertStatus = "pending"
    title: str
    body: str = ""
    created_at: str
    acknowledged_at: str = ""
    notes: list[str] = Field(default_factory=list)


class ThemeRanking(BaseModel):
    theme: str
    trading_day: str
    rank: int
    member_count: int
    leader_symbol: str = ""
    leader_consecutive_boards: int = 0
    score: float = Field(ge=0, le=100)
    notes: list[str] = Field(default_factory=list)


class ThemeRotationEntry(BaseModel):
    trading_day: str
    top_themes: list[str] = Field(default_factory=list)
    new_themes: list[str] = Field(default_factory=list)
    fading_themes: list[str] = Field(default_factory=list)


class OutcomeAttribution(BaseModel):
    attribution_id: str
    symbol: str
    trading_day: str
    primary_tag: OutcomeAttributionTag = "no_clear_attribution"
    secondary_tags: list[OutcomeAttributionTag] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    created_at: str = ""
    notes: list[str] = Field(default_factory=list)


class HistoryStats(BaseModel):
    """Per-symbol historical limit-up statistics computed from review_outcomes.

    Distinct from LimitUpHistoryStats: that one is the read-only Protocol return
    type for get_stock_history_limitup_stats (provider-shaped); this one is the
    computed P4 contract that aggregates stored CandidateOutcomeReview rows.
    """
    symbol: str
    sample_size: int = 0
    sample_window_start: str = ""
    sample_window_end: str = ""
    touch_limit_up_success_rate: float = Field(default=0.0, ge=0, le=1)
    sealed_next_day_gap_up_rate: float = Field(default=0.0, ge=0, le=1)
    median_next_day_premium_pct: float = 0.0
    avg_next_day_premium_pct: float = 0.0
    confidence: HistoryStatsConfidence = "insufficient_sample"
    notes: list[str] = Field(default_factory=list)


class HistoricalCandidateSnapshot(BaseModel):
    symbol: str
    trading_day: str
    grade_at_pick: CandidateGrade | None = None
    grade_reason: str = ""
    theme: str = ""
    theme_role: ThemeLeaderRole = "unknown"
    previous_consecutive_boards: int = 0
    payload_json: str = ""
    created_at: str = ""


class BacktestCandidateRow(BaseModel):
    symbol: str
    trading_day: str
    original_grade: CandidateGrade | None = None
    new_grade: CandidateGrade | None = None
    sealed_second_board: bool | None = None
    next_day_open_pct: float | None = None


class BacktestRun(BaseModel):
    run_id: str
    rule_changes: dict[str, Any] = Field(default_factory=dict)
    start_day: str
    end_day: str
    status: BacktestStatus = "pending"
    sample_size: int = 0
    grade_distribution_before: dict[str, int] = Field(default_factory=dict)
    grade_distribution_after: dict[str, int] = Field(default_factory=dict)
    sealed_rate_before: float = Field(default=0.0, ge=0, le=1)
    sealed_rate_after: float = Field(default=0.0, ge=0, le=1)
    rows: list[BacktestCandidateRow] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    notes: list[str] = Field(default_factory=list)


class ThresholdProposal(BaseModel):
    proposal_id: str
    field_path: str
    current_value: float
    suggested_value: float
    rationale: str = ""
    backtest_run_id: str = ""
    sample_size: int = 0
    sealed_rate_delta: float = Field(default=0.0, ge=-1, le=1)
    confidence: HistoryStatsConfidence = "low"
    created_at: str = ""


class ThresholdAdviceReport(BaseModel):
    backtest_run_id: str
    generated_at: str
    proposals: list[ThresholdProposal] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DragonTigerSeat(BaseModel):
    seat_name: str
    seat_type: DragonTigerSeatType = "unknown"
    hot_money_alias: str = ""
    buy_amount_cny: float = 0.0
    sell_amount_cny: float = 0.0
    net_amount_cny: float = 0.0


class DragonTigerRecord(BaseModel):
    symbol: str
    name: str
    trading_day: str
    list_reason: str = ""
    total_buy_cny: float = 0.0
    total_sell_cny: float = 0.0
    net_amount_cny: float = 0.0
    seats: list[DragonTigerSeat] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
    created_at: str = ""


class ContrarianPoolEntry(BaseModel):
    symbol: str
    name: str
    pool_kind: ContrarianPoolKind
    trading_day: str
    consecutive_days: int = 0
    change_pct: float = 0.0
    notes: list[str] = Field(default_factory=list)


class CapitalFlowSlice(BaseModel):
    symbol: str
    trading_day: str
    window: CapitalFlowSliceWindow
    big_order_net_inflow_cny: float = 0.0
    main_capital_net_inflow_cny: float = 0.0
    retail_capital_net_inflow_cny: float = 0.0
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
    created_at: str = ""


class IntradayPatternFeatures(BaseModel):
    """形态识别中间产物，调试用，不直接暴露 MCP。"""
    pattern: IntradayPattern = "unknown"
    open_to_first_seal_minutes: int = 0
    break_count: int = 0
    sealed_at_open: bool = False
    closing_at_limit: bool = False
    high_to_close_drawdown_pct: float = 0.0
    notes: list[str] = Field(default_factory=list)


class SectorRotationEvidence(BaseModel):
    """SECTOR_ROTATION 事件的结构化证据。"""

    weakening_theme: str
    weakening_leader_status: str = "unknown"
    strengthening_theme: str
    strengthening_leader_status: str = "unknown"
    weakening_alive_count: int = 0
    strengthening_alive_count: int = 0
    notes: list[str] = Field(default_factory=list)


class WeeklyPosition(BaseModel):
    """从周线视角衡量个股位置健康度。"""

    symbol: str
    trading_day: str
    weekly_high: float = 0.0
    weekly_low: float = 0.0
    weekly_close: float = 0.0
    position_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    weeks_in_uptrend: int = 0
    ma20_above_ma60: bool = False
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"


class SimilarSetupResult(BaseModel):
    """find_similar_setups 的单条返回。"""

    query_symbol: str
    match_symbol: str
    match_trading_day: str
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    match_grade_at_pick: CandidateGrade | None = None
    match_outcome_summary: str = ""
    feature_diffs: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class NewStockCandidate(BaseModel):
    symbol: str
    name: str
    listing_date: str
    days_since_listing: int = 0
    free_float_market_cap_cny: float = 0.0
    current_change_pct: float = 0.0
    tier: NewStockTier = "unknown"
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"


class SuspendedStock(BaseModel):
    symbol: str
    name: str = ""
    suspension_start_day: str
    suspension_end_day: str = ""
    reason: str = ""
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"


class HypothesisOutcome(BaseModel):
    symbol: str
    trading_day: str
    original_grade: str = "C"
    hypothetical_grade: str = "C"
    applied_hypothesis: dict[str, Any] = Field(default_factory=dict)
    payload_diff: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
