from __future__ import annotations

from datetime import datetime

from aegis_alpha.clock import SH_TZ, now_iso as _now
from aegis_alpha.models import (
    AuctionAnalysis,
    BreakBoardStock,
    CandidateExplanation,
    CandidateOutcomeReview,
    CapitalFlowSlice,
    ContrarianPoolEntry,
    DragonTigerRecord,
    DragonTigerSeat,
    EventScoringConfig,
    HistoryStats,
    LadderEntry,
    LimitUpHistoryStats,
    LimitUpStock,
    MarketEmotion,
    MarketEvent,
    MarketSentimentGate,
    MarketSnapshot,
    MinuteReplayBar,
    MinuteReplaySnapshot,
    NewStockCandidate,
    OrderbookQueueLevel,
    SealTimeline,
    SealTimelineEvent,
    SecondBoardCandidate,
    SignalEvidence,
    SignalMetadata,
    SignalSnapshot,
    SimilarSetupResult,
    RealtimeConnectionStatus,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
    SuspendedStock,
    ThemeLeader,
    ThemeStrength,
    WeeklyPosition,
)
from aegis_alpha.events import EventDetector, load_event_scoring_config
from aegis_alpha.themes.auction import AuctionAnalyzer


class MockMarketDataAdapter:
    """Deterministic mock data for MCP contract development."""

    def get_market_snapshot(self) -> MarketSnapshot:
        return MarketSnapshot(
            market="A-share",
            trading_day=datetime.now(SH_TZ).date().isoformat(),
            timestamp=_now(),
            sentiment="warm",
            limit_up_count=48,
            break_board_count=17,
            break_board_rate=0.26,
            leading_themes=["AI应用", "机器人", "低空经济"],
            notes=[
                "Mock data only; not connected to exchange Level-2 feeds.",
                "Use this response shape to integrate jvQuant, StockApi, MyQuant, or miniQMT later.",
            ],
        )

    def get_market_sentiment_gate(self) -> MarketSentimentGate:
        return MarketSentimentGate(
            trading_day=datetime.now(SH_TZ).date().isoformat(),
            timestamp=_now(),
            action="selective",
            score=68.0,
            limit_up_count=48,
            break_board_rate=0.26,
            second_board_success_rate=0.43,
            hot_theme_count=3,
            risk_flags=[
                "Break-board rate is not low enough for aggressive board chasing.",
                "High-position stocks show mixed follow-through in mock data.",
            ],
            positive_signals=[
                "Limit-up count is above the defensive threshold.",
                "AI应用 and 机器人 themes both have same-window risers.",
                "Second-board success rate is acceptable for selective monitoring.",
            ],
            conclusion="Mock gate allows selective second-board monitoring, not broad aggressive chasing.",
        )

    def get_limitup_pool(self) -> list[LimitUpStock]:
        return [
            LimitUpStock(
                symbol="600000.SH",
                name="浦发银行",
                theme="金融科技",
                first_limit_up_time="09:42:18",
                seal_amount_cny=186_000_000,
                free_float_market_cap_cny=72_000_000_000,
                seal_amount_ratio=0.0026,
                reopen_count=0,
                status="sealed",
            ),
            LimitUpStock(
                symbol="000001.SZ",
                name="平安银行",
                theme="大金融",
                first_limit_up_time="10:03:41",
                seal_amount_cny=93_000_000,
                free_float_market_cap_cny=198_000_000_000,
                seal_amount_ratio=0.00047,
                reopen_count=1,
                status="reopened",
            ),
        ]

    def get_break_board_pool(self) -> list[BreakBoardStock]:
        return [
            BreakBoardStock(
                symbol="002001.SZ",
                name="新和成",
                theme="合成生物",
                first_break_time="10:11:05",
                max_seal_amount_cny=58_000_000,
                current_change_pct=6.42,
                reason="Seal order decayed quickly after same-theme leader weakened.",
            )
        ]

    def get_stock_realtime_snapshot(self, symbol: str) -> StockRealtimeSnapshot:
        return StockRealtimeSnapshot(
            symbol=symbol,
            name="示例股票",
            timestamp=_now(),
            data_mode="mock",
            provider="mock",
            last_price=12.34,
            change_pct=9.98,
            turnover_cny=714_000_000,
            big_order_net_inflow_cny=82_000_000,
            bid_quality_score=76.0,
            ask_pressure_score=31.5,
            orderbook_notes=[
                "Bid queue is stable in mock data.",
                "Ask pressure is moderate; verify with real Level-2 order queue before live use.",
            ],
        )

    def get_stock_minute_replay_snapshot(
        self,
        symbol: str,
        end_day: str | None = None,
        limit_days: int = 1,
    ) -> MinuteReplaySnapshot:
        trading_day = end_day or "2026-05-26"
        bars = [
            MinuteReplayBar(time="10:10", last_price=12.01, average_price=11.92, volume=210_000),
            MinuteReplayBar(time="10:11", last_price=12.08, average_price=11.95, volume=280_000),
            MinuteReplayBar(time="10:12", last_price=12.16, average_price=11.99, volume=330_000),
            MinuteReplayBar(time="10:13", last_price=12.22, average_price=12.03, volume=410_000),
            MinuteReplayBar(time="10:14", last_price=12.28, average_price=12.06, volume=500_000),
            MinuteReplayBar(time="10:15", last_price=12.34, average_price=12.10, volume=640_000),
        ]
        return MinuteReplaySnapshot(
            symbol=symbol,
            name="示例股票",
            timestamp=f"{trading_day}T10:15:00+08:00",
            data_mode="minute_replay",
            provider="mock",
            trading_day=trading_day,
            previous_close=11.22,
            last_price=12.34,
            minute_count=len(bars),
            bars=bars,
            speed_pct_by_window={
                "1m": 0.4886,
                "3m": 1.4803,
                "5m": 2.7477,
                "10m": 2.7477,
            },
            speed_window_by_window={
                "1m": f"mock_minute_replay_window:{trading_day} 10:14:00-{trading_day} 10:15:00",
                "3m": f"mock_minute_replay_window:{trading_day} 10:12:00-{trading_day} 10:15:00",
                "5m": f"mock_minute_replay_window:{trading_day} 10:10:00-{trading_day} 10:15:00",
                "10m": f"mock_minute_replay_partial_window:{trading_day} 10:10:00-{trading_day} 10:15:00",
            },
            notes=[
                "Mock minute replay data only.",
                f"requested_limit_days={limit_days}",
            ],
        )

    def get_stock_orderbook_snapshot(self, symbol: str) -> StockOrderbookSnapshot:
        return StockOrderbookSnapshot(
            symbol=symbol,
            name="示例股票",
            timestamp=_now(),
            data_mode="mock",
            provider="mock",
            level_count=4,
            best_bid_price=12.33,
            best_ask_price=12.34,
            bid_levels=[
                OrderbookQueueLevel(
                    side="bid",
                    level_label="B1",
                    price=12.33,
                    volume_count=280_000,
                    queue_count=42,
                    queue_slice="1000,2000,5000",
                ),
                OrderbookQueueLevel(
                    side="bid",
                    level_label="B2",
                    price=12.32,
                    volume_count=190_000,
                    queue_count=35,
                    queue_slice="1000,1000,3000",
                ),
            ],
            ask_levels=[
                OrderbookQueueLevel(
                    side="ask",
                    level_label="S1",
                    price=12.34,
                    volume_count=110_000,
                    queue_count=26,
                    queue_slice="1000,1000,2000",
                ),
                OrderbookQueueLevel(
                    side="ask",
                    level_label="S2",
                    price=12.35,
                    volume_count=160_000,
                    queue_count=31,
                    queue_slice="1000,2000,2000",
                ),
            ],
            notes=[
                "Mock orderbook only; not live jvQuant Level-2 data.",
                "Use AEGIS_ALPHA_MARKET_DATA_PROVIDER=jvquant for read-only provider snapshots.",
            ],
        )

    def get_stock_history_limitup_stats(self, symbol: str) -> LimitUpHistoryStats:
        return LimitUpHistoryStats(
            symbol=symbol,
            sample_size=18,
            seal_success_rate=0.72,
            next_day_positive_rate=0.61,
            median_next_day_premium_pct=2.4,
            avg_next_day_premium_pct=3.1,
            notes=[
                "Historical stats are mock values.",
                "Real implementation should define sample window, exclusion rules, and adjusted-price policy.",
            ],
        )

    def get_theme_strength(self, symbol: str) -> ThemeStrength:
        return ThemeStrength(
            symbol=symbol,
            primary_theme="AI应用",
            theme_rank=2,
            limit_up_count=9,
            leading_stock="300000.SZ",
            strength_score=82.0,
            notes=[
                "Theme mapping is mock data.",
                "Future adapters should merge provider themes with an internal normalized theme taxonomy.",
            ],
        )

    def get_theme_leaders(self, theme: str = "", trading_day: str = "") -> list[ThemeLeader]:
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        leaders = [
            ThemeLeader(
                theme="AI应用",
                trading_day=day,
                leader_symbol="002230.SZ",
                leader_name="科大讯飞",
                leader_consecutive_boards=2,
                leader_first_limit_up_time="09:56:12",
                leader_seal_amount_cny=168_000_000,
                leader_status="sealed",
                co_leader_symbols=["300024.SZ"],
                member_count=6,
                notes=["Mock leader resolved from same-theme candidate breadth."],
            ),
            ThemeLeader(
                theme="机器人",
                trading_day=day,
                leader_symbol="300024.SZ",
                leader_name="机器人",
                leader_consecutive_boards=1,
                leader_first_limit_up_time="10:22:31",
                leader_seal_amount_cny=42_000_000,
                leader_status="reopened",
                member_count=3,
                notes=["Mock co-movement leader; use live provider for real ranking."],
            ),
        ]
        return [leader for leader in leaders if not theme or leader.theme == theme]

    def get_limit_up_ladder(self, symbol: str, trading_day: str = "") -> LadderEntry:
        normalized = symbol.strip().upper()
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        if normalized.startswith("002230"):
            return LadderEntry(symbol=normalized, trading_day=day, consecutive_boards=2, height_label="second_board")
        if normalized.startswith("300024"):
            return LadderEntry(symbol=normalized, trading_day=day, consecutive_boards=1, height_label="first_board")
        return LadderEntry(symbol=normalized, trading_day=day, consecutive_boards=0, height_label="unknown")

    def get_market_emotion(self, trading_day: str = "") -> MarketEmotion:
        return MarketEmotion(
            trading_day=trading_day or datetime.now(SH_TZ).date().isoformat(),
            yesterday_limitup_today_premium_pct=2.4,
            yesterday_consecutive_boards_alive_count=7,
            yesterday_consecutive_boards_total=11,
            yesterday_consecutive_boards_alive_rate=0.6364,
            first_to_second_promotion_rate=0.22,
            second_to_third_promotion_rate=0.18,
            first_board_to_consecutive_ratio=3.1,
            max_height_today=4,
            notes=["Mock emotion gauge for MCP contract development."],
        )

    def get_auction_analysis(self, symbol: str, trading_day: str = "") -> AuctionAnalysis:
        normalized = symbol.strip().upper()
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        if normalized.startswith("002230"):
            return AuctionAnalyzer().analyze(
                symbol=normalized,
                trading_day=day,
                auction_change_pct=3.2,
                auction_turnover_cny=92_000_000,
                auction_turnover_rate=1.8,
            )
        return AuctionAnalyzer().analyze(symbol=normalized, trading_day=day)

    def get_event_scoring_config(self) -> EventScoringConfig:
        return load_event_scoring_config()

    def get_realtime_connection_status(self) -> RealtimeConnectionStatus:
        return RealtimeConnectionStatus(
            provider="mock",
            market="ab",
            connected=False,
            subscribed=[],
            notes=[
                "Mock adapter does not open WebSocket connections.",
                "Realtime WebSocket data should feed Aegis Alpha buffers before reaching agents.",
            ],
        )

    def get_signal_snapshot(self, symbol: str) -> SignalSnapshot:
        normalized = symbol.strip().upper()
        for candidate in self.get_second_board_candidates():
            if candidate.symbol == normalized:
                return SignalSnapshot(
                    symbol=candidate.symbol,
                    name=candidate.name,
                    theme=candidate.theme,
                    provider="mock",
                    data_mode="mock",
                    price=12.34,
                    change_pct=candidate.current_change_pct,
                    speed_1m_pct=candidate.one_min_speed_pct,
                    speed_3m_pct=candidate.three_min_speed_pct,
                    speed_5m_pct=candidate.five_min_speed_pct,
                    speed_10m_pct=candidate.ten_min_speed_pct,
                    big_order_net_inflow_cny=82_000_000,
                    big_order_net_inflow_ratio=candidate.big_order_net_inflow_ratio,
                    orderbook_quality_score=candidate.orderbook_quality_score,
                    seal_amount_cny=candidate.seal_amount_cny,
                    data_timestamp=candidate.five_min_speed_timestamp,
                    provider_timestamp=candidate.five_min_speed_timestamp,
                    received_at=_now(),
                    freshness_status="fresh",
                    notes=["Mock signal snapshot for event contract tests."],
                )

        realtime = self.get_stock_realtime_snapshot(symbol)
        return SignalSnapshot(
            symbol=symbol,
            name=realtime.name,
            provider=realtime.provider,
            data_mode=realtime.data_mode,
            price=realtime.last_price,
            change_pct=realtime.change_pct,
            speed_1m_pct=0.5,
            speed_3m_pct=1.6,
            speed_5m_pct=2.9,
            speed_10m_pct=4.2,
            big_order_net_inflow_cny=realtime.big_order_net_inflow_cny,
            big_order_net_inflow_ratio=0.11,
            orderbook_quality_score=realtime.bid_quality_score,
            seal_amount_cny=128_000_000,
            data_timestamp=realtime.timestamp,
            provider_timestamp=realtime.timestamp,
            received_at=_now(),
            freshness_status="fresh",
            notes=["Mock fallback signal snapshot."],
        )

    def get_recent_market_events(self, limit: int = 20, event_type: str | None = None) -> list[MarketEvent]:
        detector = EventDetector(self.get_event_scoring_config())
        snapshots = [self.get_signal_snapshot(candidate.symbol) for candidate in self.get_second_board_candidates()]
        events: list[MarketEvent] = []
        for snapshot in snapshots:
            events.extend(detector.detect_from_snapshot(snapshot))
        events.extend(detector.detect_theme_cluster(snapshots))
        if event_type:
            events = [event for event in events if event.event_type == event_type]
        return events[: max(1, min(int(limit or 20), 100))]

    def explain_market_event(self, event_id: str) -> dict:
        for event in self.get_recent_market_events(limit=100):
            if event.event_id == event_id:
                return {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "symbol": event.symbol,
                    "score": event.score,
                    "confidence": event.confidence,
                    "reason": "Mock event generated by Aegis Alpha event rules for agent interpretation tests.",
                    "evidence": event.evidence,
                    "suggested_agent_action": event.suggested_agent_action,
                    "disclaimer": "Research and watchlist output only. This is not investment advice or an order instruction.",
                }
        return {
            "event_id": event_id,
            "data_mode": "unavailable",
            "error": "Market event not found in mock recent events.",
        }

    def review_candidate_outcome(self, symbol: str, trading_day: str) -> CandidateOutcomeReview:
        return CandidateOutcomeReview(
            symbol=symbol,
            trading_day=trading_day,
            touched_limit_up=True,
            sealed_second_board=True,
            broke_after_seal=False,
            next_day_open_pct=2.1,
            next_day_high_pct=6.4,
            third_day_premium_pct=3.2,
            notes=["Mock review outcome for feedback-loop contract tests."],
        )

    def record_candidate_outcome(self, review: CandidateOutcomeReview) -> CandidateOutcomeReview:
        review.notes.append("Mock adapter accepted review outcome without persistence.")
        return review

    def get_second_board_candidates(self) -> list[SecondBoardCandidate]:
        # Step 1: raw candidates without resolver-derived fields.
        # theme_role / previous_consecutive_boards / previous_height_label /
        # theme_leader_symbol are intentionally omitted here; they are filled
        # by the real resolver logic in Step 2 below.
        raw = [
            SecondBoardCandidate(
                symbol="002230.SZ",
                name="科大讯飞",
                theme="AI应用",
                previous_limit_up_time="10:18:24",
                first_limit_up_time="09:56:12",
                limitup_driver_type="policy",
                intraday_pattern="t_shape_board",
                seal_amount_cny=128_000_000,
                seal_volume_shares=6_880_000,
                seal_to_turnover_ratio=1.65,
                queue_position_note="Mock queue summary only; own-order queue position is unavailable.",
                current_change_pct=8.72,
                auction_change_pct=3.2,
                auction_turnover_cny=92_000_000,
                auction_turnover_rate=1.8,
                auction_pattern="strong_open",
                five_min_speed_pct=4.1,
                five_min_speed_window="mock_latest_rolling_5m",
                five_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                one_min_speed_pct=0.9,
                one_min_speed_window="mock_latest_rolling_1m",
                one_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                three_min_speed_pct=2.3,
                three_min_speed_window="mock_latest_rolling_3m",
                three_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                ten_min_speed_pct=5.2,
                ten_min_speed_window="mock_latest_rolling_10m",
                ten_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                big_order_net_inflow_ratio=0.18,
                concept_tags=["AI大模型", "教育信息化"],
                topic_tags=["国产AI"],
                break_board_count=0,
                reseal_count=0,
                final_seal_time="09:56:12",
                max_seal_amount_cny=168_000_000,
                max_seal_volume_shares=9_020_000,
                same_theme_rising_count=6,
                orderbook_quality_score=78.0,
                three_year_touch_limit_success_rate=0.64,
                three_year_sealed_next_day_gap_up_rate=0.58,
                weekly_health_score=78.0,
                data_quality=self._mock_second_board_data_quality(),
                notes=[
                    "Yesterday limit-up stock with same-theme momentum in mock data.",
                    "Watch for sell-side depletion before any board-chasing decision.",
                ],
            ),
            SecondBoardCandidate(
                symbol="300024.SZ",
                name="机器人",
                theme="机器人",
                previous_limit_up_time="09:47:09",
                first_limit_up_time="10:22:31",
                limitup_driver_type="theme",
                intraday_pattern="one_word_board",
                seal_amount_cny=42_000_000,
                seal_volume_shares=2_300_000,
                seal_to_turnover_ratio=0.82,
                queue_position_note="Mock queue summary only; own-order queue position is unavailable.",
                current_change_pct=6.85,
                auction_change_pct=1.1,
                auction_turnover_cny=31_000_000,
                auction_turnover_rate=0.7,
                auction_pattern="stable",
                five_min_speed_pct=2.7,
                five_min_speed_window="mock_latest_rolling_5m",
                five_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                one_min_speed_pct=-0.2,
                one_min_speed_window="mock_latest_rolling_1m",
                one_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                three_min_speed_pct=0.8,
                three_min_speed_window="mock_latest_rolling_3m",
                three_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                ten_min_speed_pct=2.9,
                ten_min_speed_window="mock_latest_rolling_10m",
                ten_min_speed_timestamp="2026-05-26T10:15:00+08:00",
                big_order_net_inflow_ratio=0.07,
                concept_tags=["机器人", "工业自动化"],
                topic_tags=["具身智能"],
                break_board_count=1,
                reseal_count=1,
                final_seal_time="10:42:08",
                max_seal_amount_cny=55_000_000,
                max_seal_volume_shares=3_000_000,
                same_theme_rising_count=3,
                orderbook_quality_score=59.0,
                three_year_touch_limit_success_rate=0.51,
                three_year_sealed_next_day_gap_up_rate=0.44,
                weekly_health_score=42.0,
                data_quality=self._mock_second_board_data_quality(),
                notes=[
                    "Theme is active, but orderbook quality is below the preferred threshold.",
                    "Mock candidate should remain in observation mode.",
                ],
            ),
        ]

        # Step 2: resolve theme_role / previous_consecutive_boards /
        # previous_height_label / theme_leader_symbol via real resolver
        # methods, exactly as the jvquant adapter will do in Wave 2.
        all_leaders = self.get_theme_leaders()
        leaders_by_theme = {leader.theme: leader for leader in all_leaders}

        resolved: list[SecondBoardCandidate] = []
        for candidate in raw:
            # --- LimitUpLadderResolver: fill board-height fields ---
            ladder_entry = self.get_limit_up_ladder(candidate.symbol)
            previous_consecutive_boards = ladder_entry.consecutive_boards
            previous_height_label = ladder_entry.height_label

            # --- ThemeLeaderResolver: fill theme-role fields ---
            leader = leaders_by_theme.get(candidate.theme)
            if leader is None:
                theme_role = "unknown"
                theme_leader_symbol = ""
            elif candidate.symbol == leader.leader_symbol:
                theme_role = "leader"
                theme_leader_symbol = leader.leader_symbol
            elif candidate.symbol in (leader.co_leader_symbols or []):
                theme_role = "co_leader"
                theme_leader_symbol = leader.leader_symbol
            else:
                theme_role = "follower"
                theme_leader_symbol = leader.leader_symbol

            resolved.append(
                candidate.model_copy(
                    update={
                        "previous_consecutive_boards": previous_consecutive_boards,
                        "previous_height_label": previous_height_label,
                        "theme_role": theme_role,
                        "theme_leader_symbol": theme_leader_symbol,
                    }
                )
            )

        return resolved

    def _mock_second_board_data_quality(self) -> dict[str, SignalMetadata]:
        timestamp = "2026-05-26T10:15:00+08:00"
        mock_evidence = [
            SignalEvidence(
                authority="internal_inference",
                source="aegis_alpha.mock",
                detail="Mock value used for contract tests and demos only.",
                observed_at=timestamp,
            )
        ]
        return {
            "five_min_speed": SignalMetadata(
                source="mock",
                source_field="five_min_speed_pct",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only value for contract tests."],
                evidence=mock_evidence,
            ),
            "capital_flow": SignalMetadata(
                source="mock",
                source_field="big_order_net_inflow_ratio",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only value, not Level-2 trade classification."],
                evidence=mock_evidence,
            ),
            "multi_speed": SignalMetadata(
                source="mock",
                source_field="one_min_speed_pct/three_min_speed_pct/ten_min_speed_pct",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only speed structure."],
                evidence=mock_evidence,
            ),
            "auction_metrics": SignalMetadata(
                source="mock",
                source_field="auction_change_pct/auction_turnover_cny/auction_turnover_rate",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only auction data."],
                evidence=mock_evidence,
            ),
            "theme_tags": SignalMetadata(
                source="mock",
                source_field="concept_tags/topic_tags",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only concept and topic tags."],
                evidence=mock_evidence,
            ),
            "seal_metrics": SignalMetadata(
                source="mock",
                source_field="first_limit_up_time/seal_amount_cny/seal_volume_shares/seal_to_turnover_ratio",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only seal data."],
                evidence=mock_evidence,
            ),
            "max_seal_metrics": SignalMetadata(
                source="mock",
                source_field="max_seal_amount_cny/max_seal_volume_shares",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only max-seal data."],
                evidence=mock_evidence,
            ),
            "break_reseal_metrics": SignalMetadata(
                source="mock",
                source_field="break_board_count/reseal_count/final_seal_time",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only break/reseal data."],
                evidence=mock_evidence,
            ),
            "orderbook_queue": SignalMetadata(
                source="mock",
                source_field="queue_position_note/orderbook_quality_score",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only queue summary; not own-order queue position."],
                evidence=mock_evidence,
            ),
            "history_stats": SignalMetadata(
                source="mock",
                source_field="three_year_touch_limit_success_rate/three_year_sealed_next_day_gap_up_rate",
                timestamp=timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=["Mock-only historical rates."],
                evidence=mock_evidence,
            ),
        }

    def explain_second_board_candidate(self, symbol: str) -> CandidateExplanation:
        candidates = {candidate.symbol: candidate for candidate in self.get_second_board_candidates()}
        candidate = candidates.get(symbol)

        if candidate is None:
            return CandidateExplanation(
                symbol=symbol,
                observations=[
                    "Symbol is not in the mock yesterday-limit-up candidate pool.",
                    "Second-board model only scores stocks that had a valid previous-day limit-up event.",
                ],
                risks=[
                    "Symbols outside the previous-day limit-up pool are silently absent from scoring output, so this is not a verdict on the symbol itself.",
                ],
                trigger_conditions=[
                    "Add the symbol to the previous-day limit-up pool before scoring.",
                ],
                avoid_conditions=[
                    "Avoid scoring arbitrary symbols as second-board candidates.",
                ],
                data_timestamp=_now(),
                disclaimer="Research and watchlist output only. This is not investment advice or an order instruction.",
            )

        return CandidateExplanation(
            symbol=symbol,
            observations=[
                f"Five-minute speed is {candidate.five_min_speed_pct:.1f}%.",
                f"Five-minute speed window is {candidate.five_min_speed_window}; timestamp is {candidate.five_min_speed_timestamp}.",
                f"Big-order net inflow ratio is {candidate.big_order_net_inflow_ratio:.2f}.",
                f"Same-theme rising count is {candidate.same_theme_rising_count}.",
            ],
            risks=[
                "This is mock data, not live jvQuant Level-2 data.",
                "Historical three-year statistics are placeholder values.",
                "Real board-chasing requires queue position, sell pressure, and cancel rules.",
            ],
            trigger_conditions=[
                "Market sentiment gate must be selective or active.",
                "Same-theme risers should expand during the same observation window.",
                "Sell-side limit-up ask orders should be consumed with sustained big-order inflow.",
            ],
            avoid_conditions=[
                "Avoid if break-board rate rises sharply.",
                "Avoid if same-theme leaders break board.",
                "Avoid if orderbook quality falls below the configured threshold.",
            ],
            data_timestamp=_now(),
            disclaimer="Research and watchlist output only. This is not investment advice or an order instruction.",
        )

    def explain_candidate(self, symbol: str) -> CandidateExplanation:
        return CandidateExplanation(
            symbol=symbol,
            observations=[
                "Theme strength is high in mock data.",
                "Big-order net inflow is positive.",
                "Bid quality score is above the watch threshold.",
            ],
            risks=[
                "This is not real market data.",
                "No exchange-authorized Level-2 feed is connected yet.",
                "Historical limit-up statistics are placeholder values.",
            ],
            trigger_conditions=[
                "Only consider after real data shows stable seal orders for a configured observation window.",
                "Require same-theme leaders to remain sealed.",
            ],
            avoid_conditions=[
                "Avoid if the leading theme weakens or breaks board.",
                "Avoid if big-order net inflow turns negative after reconnecting real data.",
            ],
            data_timestamp=_now(),
            disclaimer="Research and watchlist output only. This is not investment advice or an order instruction.",
        )

    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline:
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        normalized = symbol.strip().upper()
        if normalized.startswith("002230"):
            return SealTimeline(
                symbol=normalized,
                trading_day=day,
                events=[
                    SealTimelineEvent(symbol=normalized, trading_day=day, kind="first_seal", occurred_at=f"{day}T09:56:12+08:00", seal_amount_cny=128_000_000),
                ],
                final_status="sealed",
                break_count=0,
                reseal_count=0,
            )
        return SealTimeline(symbol=normalized, trading_day=day, events=[], final_status="unknown")

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent:
        # Mock adapter does not persist; return as-is for contract.
        return event

    def get_history_stats(self, symbol: str) -> HistoryStats:
        normalized = symbol.strip().upper()
        if normalized.startswith("002230"):
            return HistoryStats(
                symbol=normalized,
                sample_size=18,
                sample_window_start="2023-05-31",
                sample_window_end="2026-05-31",
                touch_limit_up_success_rate=0.72,
                sealed_next_day_gap_up_rate=0.61,
                median_next_day_premium_pct=2.4,
                avg_next_day_premium_pct=3.1,
                confidence="high",
                notes=["Mock historical stats for contract tests."],
            )
        return HistoryStats(
            symbol=normalized,
            sample_size=0,
            confidence="insufficient_sample",
            notes=["Mock has no history for this symbol."],
        )

    def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord:
        seat = DragonTigerSeat(
            seat_name="国泰君安证券深圳益田路荣超商务中心证券营业部",
            seat_type="hot_money_known",
            hot_money_alias="章盟主",
            buy_amount_cny=12_000_000.0,
            sell_amount_cny=2_000_000.0,
            net_amount_cny=10_000_000.0,
        )
        return DragonTigerRecord(
            symbol=symbol,
            name=f"mock-{symbol}",
            trading_day=trading_day,
            list_reason="日涨幅偏离值达 7%",
            total_buy_cny=12_000_000.0,
            total_sell_cny=2_000_000.0,
            net_amount_cny=10_000_000.0,
            seats=[seat],
            provider="mock",
            data_mode="mock",
            created_at="2026-05-30T15:30:00+08:00",
        )

    def get_active_seats_today(self, trading_day: str) -> list[dict]:
        return [
            {
                "hot_money_alias": "章盟主",
                "symbol_count": 1,
                "total_net_buy_cny": 10_000_000.0,
                "symbols": ["600519"],
            }
        ]

    def get_limit_down_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
        day = trading_day or "2026-05-30"
        return [
            ContrarianPoolEntry(
                symbol="000099", name="mock-跌停-1", pool_kind="limit_down",
                trading_day=day, consecutive_days=2, change_pct=-9.95,
                notes=["mock 数据"],
            ),
            ContrarianPoolEntry(
                symbol="000100", name="mock-跌停-2", pool_kind="limit_down",
                trading_day=day, consecutive_days=1, change_pct=-9.97,
                notes=["mock 数据"],
            ),
        ]

    def get_st_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
        day = trading_day or "2026-05-30"
        return [
            ContrarianPoolEntry(
                symbol="900998", name="mock-ST-1", pool_kind="st",
                trading_day=day, consecutive_days=0, change_pct=4.92,
                notes=["mock ST"],
            ),
        ]

    def get_capital_flow_slices(
        self, symbol: str, trading_day: str
    ) -> list[CapitalFlowSlice]:
        timestamp = "2026-05-30T15:00:00+08:00"
        return [
            CapitalFlowSlice(
                symbol=symbol, trading_day=trading_day, window="pre_first_seal_5m",
                big_order_net_inflow_cny=8_000_000.0,
                main_capital_net_inflow_cny=12_000_000.0,
                retail_capital_net_inflow_cny=-3_000_000.0,
                provider="mock", data_mode="mock",
                created_at=timestamp,
            ),
            CapitalFlowSlice(
                symbol=symbol, trading_day=trading_day, window="post_break_1m",
                big_order_net_inflow_cny=-2_000_000.0,
                main_capital_net_inflow_cny=-1_500_000.0,
                retail_capital_net_inflow_cny=500_000.0,
                provider="mock", data_mode="mock",
                created_at=timestamp,
            ),
            CapitalFlowSlice(
                symbol=symbol, trading_day=trading_day, window="tail_30m",
                big_order_net_inflow_cny=3_000_000.0,
                main_capital_net_inflow_cny=4_500_000.0,
                retail_capital_net_inflow_cny=-1_000_000.0,
                provider="mock", data_mode="mock",
                created_at=timestamp,
            ),
        ]

    def get_weekly_position(self, symbol: str) -> WeeklyPosition:
        return WeeklyPosition(
            symbol=symbol,
            trading_day="2026-06-01",
            weekly_high=110.0,
            weekly_low=90.0,
            weekly_close=102.0,
            position_pct=0.6,
            weeks_in_uptrend=2,
            ma20_above_ma60=True,
            notes=["mock weekly position"],
            provider="mock",
            data_mode="mock",
        )

    def find_similar_setups(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        similarity_threshold: float = 0.7,
    ) -> list[SimilarSetupResult]:
        return [
            SimilarSetupResult(
                query_symbol=symbol,
                match_symbol="000858",
                match_trading_day="2025-11-12",
                similarity=0.85,
                match_grade_at_pick="A",
                match_outcome_summary="sealed_second_board=True",
                feature_diffs={
                    "previous_consecutive_boards": 0.0,
                    "same_theme_rising_count": -0.05,
                    "seal_amount_cny": -0.10,
                    "five_min_speed_pct": 0.05,
                    "auction_change_pct": 0.0,
                },
                notes=["mock 相似形态"],
            ),
        ]

    def get_suspended_stocks(self, trading_day: str = "") -> list[SuspendedStock]:
        return [
            SuspendedStock(
                symbol="600519", name="mock-停牌-1",
                suspension_start_day="2026-05-25", suspension_end_day="",
                reason="重大事项", provider="mock", data_mode="mock",
            ),
        ]

    def get_new_stock_candidates(self) -> list[NewStockCandidate]:
        from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

        days = 22
        cap = 600_000_000.0
        return [
            NewStockCandidate(
                symbol="688001",
                name="mock-次新-科创",
                listing_date="2026-05-10",
                days_since_listing=days,
                free_float_market_cap_cny=cap,
                current_change_pct=8.4,
                tier=classify_new_stock_tier(
                    days_since_listing=days, free_float_cny=cap,
                ),
                notes=["mock smallcap recent"],
                provider="mock",
                data_mode="mock",
            ),
            NewStockCandidate(
                symbol="301099",
                name="mock-次新-创业",
                listing_date="2026-04-20",
                days_since_listing=42,
                free_float_market_cap_cny=2_500_000_000.0,
                current_change_pct=4.5,
                tier=classify_new_stock_tier(
                    days_since_listing=42, free_float_cny=2_500_000_000.0,
                ),
                notes=["mock midcap"],
                provider="mock",
                data_mode="mock",
            ),
        ]
