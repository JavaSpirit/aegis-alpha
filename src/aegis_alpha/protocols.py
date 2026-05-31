from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aegis_alpha.models import (
    AuctionAnalysis,
    BreakBoardStock,
    CandidateExplanation,
    CandidateOutcomeReview,
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
    RealtimeConnectionStatus,
    SealTimeline,
    SealTimelineEvent,
    SecondBoardCandidate,
    SignalSnapshot,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
    ThemeLeader,
    ThemeStrength,
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

    def get_history_stats(self, symbol: str) -> HistoryStats: ...

    def explain_candidate(self, symbol: str) -> CandidateExplanation: ...

    def explain_second_board_candidate(self, symbol: str) -> CandidateExplanation: ...

    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline: ...

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent: ...

    def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord: ...

    def get_active_seats_today(self, trading_day: str) -> list[dict[str, Any]]: ...
