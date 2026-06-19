from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aegis_alpha.models import (
    AuctionAnalysis,
    BreakBoardStock,
    CandidateExplanation,
    CandidateOutcomeReview,
    CapitalFlowSlice,
    ContrarianPoolEntry,
    DragonTigerRecord,
    EventScoringConfig,
    HistoryStats,
    LadderEntry,
    LimitUpHistoryStats,
    LimitUpStock,
    MarketEmotion,
    MarketEvent,
    MarketSentimentGate,
    MarketSnapshot,
    MinuteReplaySnapshot,
    NewStockCandidate,
    RealtimeConnectionStatus,
    SealTimeline,
    SealTimelineEvent,
    SecondBoardCandidate,
    SignalSnapshot,
    SimilarSetupResult,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
    SuspendedStock,
    ThemeLeader,
    ThemeStrength,
    WeeklyPosition,
)


@runtime_checkable
class MarketDataAdapter(Protocol):
    """Protocol for the read-only market data methods exposed through MCP."""

    def get_market_snapshot(self) -> MarketSnapshot: ...

    def get_market_sentiment_gate(self) -> MarketSentimentGate: ...

    def get_limitup_pool(self) -> list[LimitUpStock]: ...

    def get_break_board_pool(self) -> list[BreakBoardStock]: ...

    def get_stock_realtime_snapshot(self, symbol: str) -> StockRealtimeSnapshot: ...

    def get_stock_orderbook_snapshot(self, symbol: str) -> StockOrderbookSnapshot: ...

    def get_stock_minute_replay_snapshot(
        self,
        symbol: str,
        end_day: str | None = None,
        limit_days: int = 1,
        max_bars: int = 30,
    ) -> MinuteReplaySnapshot: ...

    def get_recent_market_events(self, limit: int = 20, event_type: str | None = None) -> list[MarketEvent]: ...

    def get_signal_snapshot(self, symbol: str) -> SignalSnapshot: ...

    def get_event_scoring_config(self) -> EventScoringConfig: ...

    def get_realtime_connection_status(self) -> RealtimeConnectionStatus: ...

    def explain_market_event(self, event_id: str) -> dict[str, Any]: ...

    def review_candidate_outcome(self, symbol: str, trading_day: str) -> CandidateOutcomeReview: ...

    def record_candidate_outcome(self, review: CandidateOutcomeReview) -> CandidateOutcomeReview: ...

    def get_stock_history_limitup_stats(self, symbol: str) -> LimitUpHistoryStats: ...

    def get_theme_strength(self, symbol: str) -> ThemeStrength: ...

    def get_theme_leaders(self, theme: str = "", trading_day: str = "") -> list[ThemeLeader]: ...

    def get_limit_up_ladder(self, symbol: str, trading_day: str = "") -> LadderEntry: ...

    def get_market_emotion(self, trading_day: str = "") -> MarketEmotion: ...

    def get_auction_analysis(self, symbol: str, trading_day: str = "") -> AuctionAnalysis: ...

    def get_second_board_candidates(self) -> list[SecondBoardCandidate]: ...

    def get_historical_second_board_candidates(self, trading_day: str, limit: int = 50) -> list[dict[str, Any]]: ...

    def get_historical_first_board_watchlist(self, as_of_day: str, limit: int = 50) -> list[dict[str, Any]]: ...

    def get_strategy_watchlist(self, as_of_day: str, limit: int = 50) -> list[dict[str, Any]]: ...

    def get_theme_continuity(self, theme: str, as_of_day: str, lookback_days: int = 14) -> dict[str, Any]: ...

    def run_historical_strategy_replay(
        self,
        as_of_day: str,
        target_day: str,
        symbols: list[str] | None = None,
        limit: int = 10,
        window_start: str = "",
        window_end: str = "",
    ) -> dict[str, Any]: ...

    def run_historical_trigger_validation(
        self,
        end_day: str,
        lookback_days: int = 5,
        limit: int = 20,
        window_start: str = "09:31",
        window_end: str = "10:00",
    ) -> dict[str, Any]: ...

    def get_intraday_theme_copump(
        self,
        symbol: str,
        as_of_day: str,
        target_day: str,
        trigger_time: str = "",
        window_start: str = "09:31",
        window_end: str = "10:00",
        peer_limit: int = 20,
    ) -> dict[str, Any]: ...

    def get_intraday_orderflow_confirmation(
        self,
        symbol: str,
        trading_day: str,
        trigger_time: str = "",
        window_start: str = "09:31",
        window_end: str = "10:00",
    ) -> dict[str, Any]: ...

    def sample_realtime_large_trade_proxy(
        self,
        symbol: str,
        duration_seconds: float = 8.0,
        threshold_cny: float = 3_000_000.0,
        window_start: str = "",
        window_end: str = "",
    ) -> dict[str, Any]: ...

    def simulate_historical_orderflow_proxy(
        self,
        symbol: str,
        trading_day: str,
        window_start: str = "09:31",
        window_end: str = "10:00",
        volume_ratio_threshold: float = 1.5,
    ) -> dict[str, Any]: ...

    def get_second_board_next_day_outcomes(
        self,
        trading_day: str,
        symbols: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]: ...

    def get_history_stats(self, symbol: str) -> HistoryStats: ...

    def explain_candidate(self, symbol: str) -> CandidateExplanation: ...

    def explain_second_board_candidate(self, symbol: str) -> CandidateExplanation: ...

    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline: ...

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent: ...

    def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord: ...

    def get_active_seats_today(self, trading_day: str) -> list[dict[str, Any]]: ...

    def get_limit_down_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]: ...

    def get_st_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]: ...

    def get_capital_flow_slices(
        self, symbol: str, trading_day: str
    ) -> list[CapitalFlowSlice]: ...

    def get_weekly_position(self, symbol: str) -> WeeklyPosition: ...

    def find_similar_setups(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        similarity_threshold: float = 0.7,
    ) -> list[SimilarSetupResult]: ...

    def get_new_stock_candidates(self) -> list[NewStockCandidate]: ...

    def get_suspended_stocks(self, trading_day: str = "") -> list[SuspendedStock]: ...
