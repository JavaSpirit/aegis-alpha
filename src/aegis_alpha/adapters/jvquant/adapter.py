from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.adapters.jvquant import parsers as P
from aegis_alpha.adapters.jvquant.parsers import float_or_zero as _float_or_zero
from aegis_alpha.adapters.jvquant.parsers import int_or_zero as _int_or_zero
from aegis_alpha.adapters.jvquant.queries import JvQuantQueryClient
from aegis_alpha.adapters.jvquant.scoring import action_from_score, market_score, sentiment_from_score
from aegis_alpha.adapters.jvquant.candidates import build_one_candidate
from aegis_alpha.clock import SH_TZ, now_iso as _now
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
    LimitUpStock,
    MarketEmotion,
    MarketSentimentGate,
    MarketSnapshot,
    MarketEvent,
    MinuteReplaySnapshot,
    OrderbookQueueLevel,
    SealTimeline,
    SealTimelineEvent,
    SecondBoardCandidate,
    SignalSnapshot,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
    ThemeLeader,
    WeeklyPosition,
)
from aegis_alpha.events import EventDetector, freshness_status, load_event_scoring_config
from aegis_alpha.grading import CandidateGradingConfig, load_candidate_grading_config
from aegis_alpha.storage import AegisAlphaStore
from aegis_alpha.adapters.jvquant_websocket import JvQuantRealtimeClient
from aegis_alpha.symbols import daily_limit_pct, normalize_symbol
from aegis_alpha.themes.auction import AuctionAnalyzer
from aegis_alpha.themes.ladder import classify_height
from aegis_alpha.themes.leader import ThemeLeaderResolver



def _inferred_change_pct_for_limit_up(symbol: str) -> float:
    """Return the daily-limit percentage to infer when seal metrics indicate limit-up."""
    return daily_limit_pct(symbol)


class JvQuantMarketDataAdapter:
    """Read-only jvQuant adapter for single-symbol smoke and MCP tools."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("JVQUANT_TOKEN", "")
        if not self.token:
            raise ValueError("JVQUANT_TOKEN missing")
        self._fallback = MockMarketDataAdapter()
        self._client: Any | None = None
        cache_ttl = _float_or_zero(os.environ.get("AEGIS_ALPHA_JVQUANT_CACHE_TTL_SECONDS")) or 30.0
        query_rate = _float_or_zero(os.environ.get("AEGIS_ALPHA_JVQUANT_QUERY_RATE_PER_SECOND")) or 3.0
        query_burst = _float_or_zero(os.environ.get("AEGIS_ALPHA_JVQUANT_QUERY_BURST")) or 6.0
        query_timeout = _float_or_zero(os.environ.get("AEGIS_ALPHA_JVQUANT_QUERY_TIMEOUT_SECONDS")) or 10.0
        self._query_client = JvQuantQueryClient(
            cache_ttl_seconds=cache_ttl,
            query_rate_per_second=query_rate,
            query_burst=query_burst,
            timeout_seconds=query_timeout,
        )
        self._query_cache = self._query_client.cache
        self._query_limiter = self._query_client.limiter
        self.grading_config: CandidateGradingConfig = load_candidate_grading_config()

    @classmethod
    def from_env(cls) -> "JvQuantMarketDataAdapter":
        return cls(token=os.environ.get("JVQUANT_TOKEN", ""))

    @property
    def client(self) -> Any:
        if self._client is None:
            from jvQuant import sql_client

            self._client = sql_client.Construct(token=self.token, log_level=logging.ERROR)
        return self._client

    def get_market_snapshot(self) -> MarketSnapshot:
        limitup_pool = self.get_limitup_pool()
        break_pool = self.get_break_board_pool()
        limit_up_count = len(limitup_pool)
        break_board_count = len(break_pool)
        denominator = limit_up_count + break_board_count
        break_board_rate = round(break_board_count / denominator, 4) if denominator else 0.0
        themes = P._leading_themes(limitup_pool + break_pool)
        score = market_score(limit_up_count, break_board_rate, len(themes), self.grading_config)
        sentiment = sentiment_from_score(score, self.grading_config)

        total_payload = self._query(
            "主板,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        total_count = P._query_count(total_payload)

        return MarketSnapshot(
            market="A-share",
            trading_day=datetime.now(SH_TZ).date().isoformat(),
            timestamp=_now(),
            data_mode="live_provider",
            provider="jvQuant",
            sentiment=sentiment,
            limit_up_count=limit_up_count,
            break_board_count=break_board_count,
            break_board_rate=break_board_rate,
            leading_themes=themes,
            notes=[
                "Read-only jvQuant semantic query snapshot.",
                f"main_board_non_st_count={total_count}",
                "Limit-up pool includes jvQuant semantic-query first seal time and seal amount when available.",
            ],
        )

    def get_market_sentiment_gate(self) -> MarketSentimentGate:
        snapshot = self.get_market_snapshot()
        score = market_score(
            snapshot.limit_up_count,
            snapshot.break_board_rate,
            len(snapshot.leading_themes),
            self.grading_config,
        )
        action = action_from_score(score, snapshot.break_board_rate, self.grading_config)
        risk_flags: list[str] = []
        positive_signals: list[str] = []

        if snapshot.break_board_rate >= 0.45:
            risk_flags.append("Break-board rate is high; board-chasing should be defensive.")
        elif snapshot.break_board_rate >= 0.30:
            risk_flags.append("Break-board rate is elevated; only selective monitoring is reasonable.")
        else:
            positive_signals.append("Break-board rate is controlled by the current provider snapshot.")

        if snapshot.limit_up_count >= 60:
            positive_signals.append("Limit-up count is strong.")
        elif snapshot.limit_up_count >= 35:
            positive_signals.append("Limit-up count supports selective watchlist work.")
        else:
            risk_flags.append("Limit-up count is not strong enough for broad board-chasing.")

        if len(snapshot.leading_themes) >= 3:
            positive_signals.append("Leading themes are not overly narrow.")
        else:
            risk_flags.append("Theme breadth is narrow in the current snapshot.")

        if not risk_flags:
            risk_flags.append("Provider semantic-query data should still be cross-checked during active trading.")

        emotion = self.get_market_emotion(snapshot.trading_day)

        return MarketSentimentGate(
            trading_day=snapshot.trading_day,
            timestamp=snapshot.timestamp,
            data_mode="live_provider",
            provider="jvQuant",
            action=action,
            score=score,
            limit_up_count=snapshot.limit_up_count,
            break_board_rate=snapshot.break_board_rate,
            second_board_success_rate=0.0,
            hot_theme_count=len(snapshot.leading_themes),
            risk_flags=risk_flags,
            positive_signals=positive_signals,
            conclusion=(
                "jvQuant read-only market gate is usable for coarse filtering. "
                "Second-board success rate and intraday seal-time quality are not derived yet."
            ),
            yesterday_limitup_today_premium_pct=emotion.yesterday_limitup_today_premium_pct,
            consecutive_boards_alive_rate=emotion.yesterday_consecutive_boards_alive_rate,
            first_to_second_promotion_rate=emotion.first_to_second_promotion_rate,
            second_to_third_promotion_rate=emotion.second_to_third_promotion_rate,
            max_height_today=emotion.max_height_today,
        )

    def get_limitup_pool(self) -> list[LimitUpStock]:
        payload = self._query(
            "今日涨停,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单金额,封单量,涨停封成比,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = P._query_rows(payload)
        return [P._limitup_from_row(row) for row in rows]

    def get_break_board_pool(self) -> list[BreakBoardStock]:
        payload = self._query(
            "炸板,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = P._query_rows(payload)
        return [P._break_board_from_row(row) for row in rows]

    def get_stock_history_limitup_stats(self, symbol: str):
        return self._fallback.get_stock_history_limitup_stats(symbol)

    def get_history_stats(self, symbol: str) -> HistoryStats:
        from datetime import timedelta
        from aegis_alpha.feedback.history_stats import compute_history_stats

        normalized = normalize_symbol(symbol)
        end = datetime.now(SH_TZ).date()
        start = end - timedelta(days=365 * 3)
        return compute_history_stats(
            store=AegisAlphaStore(),
            symbol=normalized,
            start_day=start.isoformat(),
            end_day=end.isoformat(),
        )

    def get_theme_strength(self, symbol: str):
        return self._fallback.get_theme_strength(symbol)

    def get_theme_leaders(self, theme: str = "", trading_day: str = "") -> list[ThemeLeader]:
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        store = AegisAlphaStore()
        stored = store.latest_theme_leaders(theme=theme, trading_day=day, limit=20)
        if stored:
            return stored
        pool = self.get_limitup_pool()
        ladder = {
            stock.symbol: LadderEntry(
                symbol=stock.symbol,
                trading_day=day,
                consecutive_boards=1,
                height_label="first_board",
                last_limit_up_day=day,
            )
            for stock in pool
        }
        leaders = ThemeLeaderResolver().resolve(pool, ladder, trading_day=day)
        if theme:
            leaders = [leader for leader in leaders if leader.theme == theme]
        store.save_theme_leaders(leaders)
        return leaders

    def get_limit_up_ladder(self, symbol: str, trading_day: str = "") -> LadderEntry:
        normalized = normalize_symbol(symbol)
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        store = AegisAlphaStore()
        stored = store.get_ladder_entry(normalized, day)
        if stored is not None:
            return stored
        is_limit_up = any(normalize_symbol(item.symbol) == normalized for item in self.get_limitup_pool())
        consecutive = 1 if is_limit_up else 0
        entry = LadderEntry(
            symbol=normalized,
            trading_day=day,
            consecutive_boards=consecutive,
            height_label=classify_height(consecutive),
            last_limit_up_day=day if is_limit_up else "",
            notes=["Live jvQuant ladder uses current limit-up pool only until historical replay is connected."],
        )
        store.save_ladder_entries([entry])
        return entry

    def get_market_emotion(self, trading_day: str = "") -> MarketEmotion:
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        limitup_pool = self.get_limitup_pool()
        ladder_entries = [
            self.get_limit_up_ladder(stock.symbol, day) for stock in limitup_pool
        ]
        max_height = max(
            (entry.consecutive_boards for entry in ladder_entries),
            default=0,
        )
        return MarketEmotion(
            trading_day=day,
            yesterday_limitup_today_premium_pct=0.0,
            yesterday_consecutive_boards_alive_count=0,
            yesterday_consecutive_boards_total=0,
            yesterday_consecutive_boards_alive_rate=0.0,
            first_to_second_promotion_rate=0.0,
            second_to_third_promotion_rate=0.0,
            first_board_to_consecutive_ratio=0.0,
            max_height_today=max_height,
            notes=[
                "yesterday_limitup_today_premium_pct: requires yesterday limit-up cohort with today's change; not implemented yet.",
                "yesterday_consecutive_boards_*: requires yesterday session history; not implemented yet.",
                "first_to_second / second_to_third promotion rates: requires multi-day ladder history; not implemented yet.",
                "max_height_today computed from ladder of today's limit-up pool.",
            ],
        )

    def get_auction_analysis(self, symbol: str, trading_day: str = "") -> AuctionAnalysis:
        normalized = normalize_symbol(symbol)
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        for candidate in self.get_second_board_candidates():
            if normalize_symbol(candidate.symbol) == normalized:
                return AuctionAnalyzer().analyze(
                    symbol=normalized,
                    trading_day=day,
                    auction_change_pct=candidate.auction_change_pct,
                    auction_turnover_cny=candidate.auction_turnover_cny,
                    auction_turnover_rate=candidate.auction_turnover_rate,
                )
        return AuctionAnalyzer().analyze(symbol=normalized, trading_day=day)

    def get_event_scoring_config(self) -> EventScoringConfig:
        return load_event_scoring_config()

    def get_realtime_connection_status(self):
        return JvQuantRealtimeClient(token=self.token, market=os.environ.get("JVQUANT_MARKET", "ab")).status()

    def get_signal_snapshot(self, symbol: str) -> SignalSnapshot:
        normalized = normalize_symbol(symbol)
        store = AegisAlphaStore()
        stored = store.latest_signal_snapshot(normalized)
        if stored is not None:
            return stored

        for candidate in self.get_second_board_candidates():
            if candidate.symbol == normalized or normalize_symbol(candidate.symbol) == normalized:
                snapshot = self._signal_snapshot_from_candidate(candidate)
                store.save_signal_snapshot(snapshot)
                return snapshot

        realtime = self.get_stock_realtime_snapshot(symbol)
        snapshot = SignalSnapshot(
            symbol=normalized,
            name=realtime.name,
            provider=realtime.provider,
            data_mode=realtime.data_mode,
            price=realtime.last_price,
            change_pct=realtime.change_pct,
            big_order_net_inflow_cny=realtime.big_order_net_inflow_cny,
            orderbook_quality_score=realtime.bid_quality_score,
            data_timestamp=realtime.timestamp,
            provider_timestamp=realtime.timestamp,
            received_at=_now(),
            freshness_status="fresh",
            notes=[
                "Single-symbol signal snapshot built from realtime snapshot fallback.",
                "Speed windows are unavailable unless the symbol is in the second-board candidate pool or realtime buffer.",
            ],
        )
        store.save_signal_snapshot(snapshot)
        return snapshot

    def get_recent_market_events(self, limit: int = 20, event_type: str | None = None) -> list[MarketEvent]:
        store = AegisAlphaStore()
        stored = store.recent_market_events(limit, event_type)
        if stored:
            return stored

        snapshots = [self._signal_snapshot_from_candidate(candidate) for candidate in self.get_second_board_candidates()]
        detector = EventDetector(self.get_event_scoring_config())
        events: list[MarketEvent] = []
        for snapshot in snapshots:
            events.extend(detector.detect_from_snapshot(snapshot))
        events.extend(detector.detect_theme_cluster(snapshots))
        from aegis_alpha.seal_timeline.divergence import detect_theme_divergence
        from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
        tracker = SealTimelineTracker(store)
        trading_day = datetime.now(SH_TZ).date().isoformat()
        leaders = self.get_theme_leaders(trading_day=trading_day)
        divergence_events = detect_theme_divergence(leaders, tracker, trading_day=trading_day)
        store.save_market_events(divergence_events)
        events.extend(divergence_events)
        store.save_market_events(events)
        recent = store.recent_market_events(limit, event_type)
        if not recent:
            recent = events[: max(1, min(int(limit or 20), 100))]
        return recent

    def explain_market_event(self, event_id: str) -> dict:
        events = {event.event_id: event for event in self.get_recent_market_events(limit=100)}
        event = events.get(event_id)
        if event is None:
            return {
                "event_id": event_id,
                "data_mode": "unavailable",
                "error": "Market event not found in recent event store.",
                "disclaimer": "Data source unavailable. Do not infer missing market data.",
            }
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "symbol": event.symbol,
            "theme": event.theme,
            "score": event.score,
            "confidence": event.confidence,
            "freshness_status": event.freshness_status,
            "reason": (
                f"{event.event_type} scored {event.score:.1f}. "
                "The event is generated by Aegis Alpha signal rules before agent interpretation."
            ),
            "evidence": event.evidence,
            "suggested_agent_action": event.suggested_agent_action,
            "provider_timestamp": event.provider_timestamp,
            "received_at": event.received_at,
            "disclaimer": "Research and watchlist output only. This is not investment advice or an order instruction.",
        }

    def review_candidate_outcome(self, symbol: str, trading_day: str) -> CandidateOutcomeReview:
        return AegisAlphaStore().get_review_outcome(normalize_symbol(symbol), trading_day)

    def record_candidate_outcome(self, review: CandidateOutcomeReview) -> CandidateOutcomeReview:
        review.symbol = normalize_symbol(review.symbol)
        return AegisAlphaStore().save_review_outcome(review)

    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline:
        from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
        normalized = normalize_symbol(symbol)
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        return SealTimelineTracker(AegisAlphaStore()).get_timeline(normalized, day)

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent:
        from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
        return SealTimelineTracker(AegisAlphaStore()).record(event)

    def get_second_board_candidates(self):
        payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,5分钟涨幅,资金流向,主力资金,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        seal_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单量,封单金额,涨停封成比,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        speed_1m_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,1分钟涨幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        speed_3m_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,3分钟涨幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        speed_10m_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,10分钟涨幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        auction_payload = self._query(
            "昨日涨停,非ST,股票代码,股票简称,竞价涨幅,竞价成交额,竞价换手率,开盘价,价格,成交额,行业",
            sort_key="竞价涨幅",
        )
        theme_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,所属概念,概念,题材,行业,价格,成交额",
            sort_key="涨跌幅",
        )
        break_reseal_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,炸板次数,首次炸板时间,回封次数,最后封板时间,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        max_seal_payload = self._query(
            "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,最大封单金额,最大封单量,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = P._query_rows(payload)
        seal_rows = P._rows_by_symbol(P._query_rows(seal_payload))
        speed_1m_rows = P._rows_by_symbol(P._query_rows(speed_1m_payload))
        speed_3m_rows = P._rows_by_symbol(P._query_rows(speed_3m_payload))
        speed_10m_rows = P._rows_by_symbol(P._query_rows(speed_10m_payload))
        auction_rows = P._rows_by_symbol(P._query_rows(auction_payload))
        theme_rows = P._rows_by_symbol(P._query_rows(theme_payload))
        break_reseal_rows = P._rows_by_symbol(P._query_rows(break_reseal_payload))
        max_seal_rows = P._rows_by_symbol(P._query_rows(max_seal_payload))
        query_timestamp = _now()
        max_candidates = _int_or_zero(os.environ.get("AEGIS_ALPHA_SECOND_BOARD_MAX_CANDIDATES")) or 12
        orderbook_limit = _int_or_zero(os.environ.get("AEGIS_ALPHA_SECOND_BOARD_ORDERBOOK_LIMIT")) or 5
        minute_replay_enabled = os.environ.get("AEGIS_ALPHA_ENABLE_MINUTE_REPLAY", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
        minute_replay_limit = _int_or_zero(os.environ.get("AEGIS_ALPHA_SECOND_BOARD_MINUTE_REPLAY_LIMIT")) or 12
        theme_counts = Counter(P._theme_from_row(row) for row in rows)
        gate = self.get_market_sentiment_gate()

        trading_day = query_timestamp[:10]
        ladder_entries: dict[str, LadderEntry] = {}
        for row in rows[:max_candidates]:
            row_symbol = P._symbol_from_row(row)
            if not row_symbol:
                continue
            ladder_entries[row_symbol] = self.get_limit_up_ladder(row_symbol, trading_day)

        theme_leaders_list = self.get_theme_leaders(trading_day=trading_day)
        theme_leaders_by_theme: dict[str, ThemeLeader] = {
            leader.theme: leader for leader in theme_leaders_list
        }

        history_stats_by_symbol: dict[str, HistoryStats] = {}
        for row in rows[:max_candidates]:
            row_symbol = P._symbol_from_row(row)
            if not row_symbol:
                continue
            history_stats_by_symbol[row_symbol] = self.get_history_stats(row_symbol)

        candidates: list[SecondBoardCandidate] = []
        for index, row in enumerate(rows[:max_candidates]):
            candidate = build_one_candidate(
                index=index,
                row=row,
                seal_rows=seal_rows,
                speed_1m_rows=speed_1m_rows,
                speed_3m_rows=speed_3m_rows,
                speed_10m_rows=speed_10m_rows,
                auction_rows=auction_rows,
                theme_rows=theme_rows,
                break_reseal_rows=break_reseal_rows,
                max_seal_rows=max_seal_rows,
                query_timestamp=query_timestamp,
                theme_counts=theme_counts,
                gate_action=gate.action,
                orderbook_limit=orderbook_limit,
                minute_replay_enabled=minute_replay_enabled,
                minute_replay_limit=minute_replay_limit,
                grading_config=self.grading_config,
                get_minute_replay=self.get_stock_minute_replay_snapshot,
                get_orderbook=self.get_stock_orderbook_snapshot,
                ladder_entries=ladder_entries,
                theme_leaders_by_theme=theme_leaders_by_theme,
                history_stats_by_symbol=history_stats_by_symbol,
            )
            candidates.append(candidate)

        return candidates

    def explain_candidate(self, symbol: str):
        return self._fallback.explain_candidate(symbol)

    def explain_second_board_candidate(self, symbol: str) -> CandidateExplanation:
        candidates = {candidate.symbol: candidate for candidate in self.get_second_board_candidates()}
        normalized = normalize_symbol(symbol)
        candidate = candidates.get(symbol) or candidates.get(normalized)
        if candidate is None:
            return CandidateExplanation(
                symbol=symbol,
                grade="REJECT",
                grade_reason=(
                    "评级为 REJECT，因为该股票不在当前 jvQuant 二板候选池中；"
                    "当前候选池只覆盖昨日涨停且今日涨幅大于 5% 的非 ST 股票。"
                ),
                observations=[
                    "Symbol is not in the current jvQuant live-provider second-board candidate pool.",
                ],
                risks=[
                    "The current candidate pool only covers yesterday limit-up stocks with today's gain above 5%.",
                ],
                trigger_conditions=[
                    "Add the symbol to the valid previous-day limit-up and current strength pool before scoring.",
                ],
                avoid_conditions=[
                    "Avoid treating arbitrary symbols as second-board candidates.",
                ],
                data_timestamp=_now(),
                disclaimer="Research and watchlist output only. This is not investment advice or an order instruction.",
            )

        return CandidateExplanation(
            symbol=candidate.symbol,
            grade=candidate.grade,
            grade_reason=candidate.grade_reason,
            observations=[
                f"Current change is {candidate.current_change_pct:.2f}%.",
                f"Auction change is {candidate.auction_change_pct:.2f}%; auction turnover is {candidate.auction_turnover_cny:.0f} CNY.",
                f"Five-minute speed is {candidate.five_min_speed_pct:.2f}%.",
                f"Five-minute speed window is {candidate.five_min_speed_window}; timestamp is {candidate.five_min_speed_timestamp}.",
                f"Minute replay trading day is {candidate.minute_replay_trading_day or 'unknown'}; bar count is {candidate.minute_replay_bar_count}.",
                f"Multi-speed structure is 1m={candidate.one_min_speed_pct:.2f}%, 3m={candidate.three_min_speed_pct:.2f}%, 10m={candidate.ten_min_speed_pct:.2f}%.",
                f"Capital-flow net inflow ratio is {candidate.big_order_net_inflow_ratio:.2f}.",
                f"First limit-up time is {candidate.first_limit_up_time}.",
                f"Final seal time is {candidate.final_seal_time}; break-board count is {candidate.break_board_count}; reseal count is {candidate.reseal_count}.",
                f"Max seal amount is {candidate.max_seal_amount_cny:.0f} CNY; max seal volume is {candidate.max_seal_volume_shares:.0f} shares.",
                f"Seal amount is {candidate.seal_amount_cny:.0f} CNY; seal volume is {candidate.seal_volume_shares:.0f} shares.",
                f"Seal-to-turnover ratio is {candidate.seal_to_turnover_ratio:.2f}.",
                f"Queue position note: {candidate.queue_position_note}",
                f"Concept tags: {', '.join(candidate.concept_tags[:6]) or 'unknown'}.",
                f"Topic tags: {', '.join(candidate.topic_tags[:6]) or 'unknown'}.",
                f"Data quality keys: {', '.join(candidate.data_quality.keys())}.",
                f"Theme is {candidate.theme}; same-theme candidate count is {candidate.same_theme_rising_count}.",
                f"Orderbook quality score is {candidate.orderbook_quality_score:.2f}.",
                f"Estimated seal probability is {candidate.estimated_seal_probability:.0%} from current coarse factors.",
            ],
            risks=[
                "Candidate pool is live-provider jvQuant; capital-flow fields are semantic-query values, not tick-by-tick order classification.",
                "Minute replay speed is minute-level historical/replay data, not tick-by-tick realtime Level-2.",
                "Auction, concept, topic, break/reseal, and max-seal fields are observed semantic-query values, not official field-level definitions.",
                "Historical three-year limit-up success and next-day premium are placeholders.",
                "True own-order queue position and cancellation rules require broker order/trade callbacks and are not implemented.",
            ],
            trigger_conditions=[
                "Market sentiment gate should improve from defensive to selective or active for aggressive board-chasing.",
                "First seal time should be early and seal amount should remain strong versus turnover.",
                "Orderbook quality should remain strong during active trading hours.",
                "Same-theme candidates should expand or the theme leader should remain sealed.",
            ],
            avoid_conditions=[
                "Avoid if break-board rate remains high.",
                "Avoid if seal amount decays quickly or first seal time is late without same-theme support.",
                "Avoid if orderbook quality deteriorates or best ask expands sharply.",
                "Avoid if the candidate falls out of the yesterday-limit-up strength pool.",
            ],
            data_timestamp=_now(),
            disclaimer="Research and watchlist output only. This is not investment advice or an order instruction.",
        )

    def get_stock_realtime_snapshot(self, symbol: str) -> StockRealtimeSnapshot:
        code = normalize_symbol(symbol)
        kline_payload = self.client.kline(code, "stock", "前复权", "day", 2)
        orderbook = self.get_stock_orderbook_snapshot(symbol)

        data = kline_payload.get("data", {}) if isinstance(kline_payload, dict) else {}
        rows = data.get("list", []) if isinstance(data, dict) else []
        fields = data.get("fields", []) if isinstance(data, dict) else []
        latest = rows[0] if rows else []
        field_map = {field: latest[index] for index, field in enumerate(fields) if index < len(latest)}

        bid_volume = sum(level.volume_count for level in orderbook.bid_levels)
        ask_volume = sum(level.volume_count for level in orderbook.ask_levels)
        total_volume = bid_volume + ask_volume
        bid_quality = 50.0 if total_volume == 0 else min(100.0, round(100 * bid_volume / total_volume, 2))
        ask_pressure = 50.0 if total_volume == 0 else min(100.0, round(100 * ask_volume / total_volume, 2))

        return StockRealtimeSnapshot(
            symbol=symbol,
            name=str(data.get("name") or "unknown"),
            timestamp=_now(),
            data_mode="live_provider",
            provider="jvQuant",
            last_price=_float_or_zero(field_map.get("收盘")),
            change_pct=_float_or_zero(field_map.get("涨跌幅")),
            turnover_cny=_float_or_zero(field_map.get("成交额")),
            big_order_net_inflow_cny=0.0,
            bid_quality_score=bid_quality,
            ask_pressure_score=ask_pressure,
            orderbook_notes=[
                "Read-only jvQuant kline and level_queue data.",
                "big_order_net_inflow_cny is not derived yet; Level-2 trade classification is pending.",
                f"orderbook_level_count={orderbook.level_count}",
                f"best_bid_price={orderbook.best_bid_price}",
                f"best_ask_price={orderbook.best_ask_price}",
            ],
        )

    def get_stock_minute_replay_snapshot(
        self,
        symbol: str,
        end_day: str | None = None,
        limit_days: int = 1,
    ) -> MinuteReplaySnapshot:
        code = normalize_symbol(symbol)
        safe_limit = max(1, min(int(limit_days or 1), 30))
        safe_end_day = (end_day or datetime.now(SH_TZ).date().isoformat()).strip()
        payload = self.client.minute(code, safe_end_day, safe_limit)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        fields = data.get("fields", []) if isinstance(data, dict) else []
        days = data.get("list", []) if isinstance(data, dict) else []
        if not isinstance(fields, list):
            fields = []
        if not fields:
            fields = ["时间", "最新价", "均价", "成交量"]

        selected_day = P._latest_minute_day(days)
        trading_day = str(selected_day.get("date") or data.get("end") or safe_end_day)
        previous_close = _float_or_zero(selected_day.get("last_price"))
        raw_bars = selected_day.get("list", [])
        bars = P._minute_bars_from_rows(raw_bars, fields)
        last_bar = bars[-1] if bars else None
        timestamp = (
            P._iso_from_provider_datetime(f"{trading_day} {P._time_with_seconds(last_bar.time)}")
            if last_bar is not None
            else _now()
        )
        speed_pct_by_window, speed_window_by_window = P._minute_speed_windows(trading_day, bars)

        return MinuteReplaySnapshot(
            symbol=symbol,
            name=str(data.get("name") or selected_day.get("name") or "unknown") if isinstance(data, dict) else "unknown",
            timestamp=timestamp or _now(),
            data_mode="minute_replay",
            provider="jvQuant",
            trading_day=trading_day,
            previous_close=previous_close,
            last_price=last_bar.last_price if last_bar else 0.0,
            minute_count=len(bars),
            bars=bars[-30:],
            speed_pct_by_window=speed_pct_by_window,
            speed_window_by_window=speed_window_by_window,
            notes=[
                "Read-only jvQuant minute replay data from client.minute(mode=minute).",
                "Speed windows are recalculated by Aegis Alpha from minute bars, not from semantic-query speed fields.",
                "Minute replay is minute-level historical/replay data; it is not tick-by-tick realtime Level-2.",
                f"requested_end_day={safe_end_day}",
                f"requested_limit_days={safe_limit}",
            ],
        )

    def get_stock_orderbook_snapshot(self, symbol: str) -> StockOrderbookSnapshot:
        code = normalize_symbol(symbol)
        payload = self.client.level_queue(code)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if isinstance(data, dict):
            rows = data.get("list", [])
            name = str(data.get("name") or "unknown")
            level_count = _int_or_zero(data.get("count") or len(rows))
        elif isinstance(data, list):
            rows = data
            name = "unknown"
            level_count = len(rows)
        else:
            rows = []
            name = "unknown"
            level_count = 0

        bid_levels: list[OrderbookQueueLevel] = []
        ask_levels: list[OrderbookQueueLevel] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            level = P._parse_level(row)
            if level.side == "bid":
                bid_levels.append(level)
            elif level.side == "ask":
                ask_levels.append(level)

        bid_levels = sorted(bid_levels, key=lambda item: item.price, reverse=True)[:10]
        ask_levels = sorted(ask_levels, key=lambda item: item.price)[:10]

        return StockOrderbookSnapshot(
            symbol=symbol,
            name=name,
            timestamp=_now(),
            data_mode="live_provider",
            provider="jvQuant",
            level_count=level_count,
            best_bid_price=bid_levels[0].price if bid_levels else None,
            best_ask_price=ask_levels[0].price if ask_levels else None,
            bid_levels=bid_levels,
            ask_levels=ask_levels,
            notes=[
                "Read-only jvQuant level_queue summary.",
                "Only top 10 bid and ask levels are returned to keep MCP output compact.",
                "Empty orderbook levels mean the provider returned no queue rows for this symbol at request time.",
                "Do not use this alone for automated trading; queue position and cancellation rules are not implemented.",
            ],
        )

    def _signal_snapshot_from_candidate(self, candidate: SecondBoardCandidate) -> SignalSnapshot:
        timestamp = candidate.five_min_speed_timestamp or candidate.minute_replay_timestamp or _now()
        received_at = _now()
        turnover_cny = self._candidate_note_float(candidate, "turnover_cny")
        big_order_ratio = candidate.big_order_net_inflow_ratio
        return SignalSnapshot(
            symbol=normalize_symbol(candidate.symbol),
            name=candidate.name,
            theme=candidate.theme,
            provider=candidate.provider,
            data_mode=candidate.data_mode,
            price=0.0,
            change_pct=candidate.current_change_pct,
            speed_1m_pct=candidate.one_min_speed_pct,
            speed_3m_pct=candidate.three_min_speed_pct,
            speed_5m_pct=candidate.five_min_speed_pct,
            speed_10m_pct=candidate.ten_min_speed_pct,
            big_order_net_inflow_cny=round(big_order_ratio * turnover_cny, 2) if turnover_cny else 0.0,
            big_order_net_inflow_ratio=big_order_ratio,
            orderbook_quality_score=candidate.orderbook_quality_score,
            seal_amount_cny=candidate.seal_amount_cny,
            data_timestamp=timestamp,
            provider_timestamp=timestamp,
            received_at=received_at,
            freshness_status=freshness_status(timestamp, received_at),
            notes=[
                "Signal snapshot derived from second-board candidate structured fields.",
                "Use data_quality on the candidate for source-level evidence before high-confidence analysis.",
            ],
        )

    def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord:
        # P5 starter: jvQuant 龙虎榜端点尚未对齐契约，先返回 placeholder 记录。
        # 真实接入在 P5 Wave 2 单独 issue 内完成（参考 docs/JVQUANT_OFFICIAL_INDEX.md）。
        return DragonTigerRecord(
            symbol=symbol,
            name="",
            trading_day=trading_day,
            list_reason="placeholder: jvQuant dragon-tiger endpoint not wired",
            total_buy_cny=0.0,
            total_sell_cny=0.0,
            net_amount_cny=0.0,
            seats=[],
            provider="jvquant",
            data_mode="placeholder",
            created_at=_now(),
        )

    def get_active_seats_today(self, trading_day: str) -> list[dict]:
        return []

    def get_limit_down_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
        # P5 starter: 跌停池 semantic query 尚未确定字段映射，先返回空列表。
        return []

    def get_st_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
        # P5 starter: ST 池接入待 jvQuant 字段确认。
        return []

    def get_capital_flow_slices(
        self, symbol: str, trading_day: str
    ) -> list[CapitalFlowSlice]:
        # P5 starter: minute-level capital flow detail not yet exposed by jvQuant
        # semantic queries; return [] until dedicated probe lands.
        return []

    def get_weekly_position(self, symbol: str) -> WeeklyPosition:
        # P6 starter: jvQuant 周线接口尚未对齐契约，placeholder 起步。
        return WeeklyPosition(
            symbol=symbol,
            trading_day="",
            weekly_high=0.0,
            weekly_low=0.0,
            weekly_close=0.0,
            position_pct=0.0,
            weeks_in_uptrend=0,
            ma20_above_ma60=False,
            notes=["placeholder: jvQuant weekly endpoint not wired"],
            provider="jvquant",
            data_mode="placeholder",
        )

    def _candidate_note_float(self, candidate: SecondBoardCandidate, key: str) -> float:
        prefix = f"{key}="
        for note in candidate.notes:
            if note.startswith(prefix):
                return _float_or_zero(note.removeprefix(prefix))
        return 0.0

    def _query(self, query: str, sort_key: str = "") -> dict[str, Any]:
        return self._query_client.query(self.client, query, sort_key)
