from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aegis_alpha.models import (
    BreakBoardStock,
    CandidateExplanation,
    LimitUpHistoryStats,
    LimitUpStock,
    MarketSentimentGate,
    MarketSnapshot,
    OrderbookQueueLevel,
    SecondBoardCandidate,
    SignalEvidence,
    SignalMetadata,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
    ThemeStrength,
)


SH_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(SH_TZ).isoformat(timespec="seconds")


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

    def get_second_board_candidates(self) -> list[SecondBoardCandidate]:
        return [
            SecondBoardCandidate(
                symbol="002230.SZ",
                name="科大讯飞",
                theme="AI应用",
                previous_limit_up_time="10:18:24",
                first_limit_up_time="09:56:12",
                seal_amount_cny=128_000_000,
                seal_volume_shares=6_880_000,
                seal_to_turnover_ratio=1.65,
                queue_position_note="Mock queue summary only; own-order queue position is unavailable.",
                current_change_pct=8.72,
                auction_change_pct=3.2,
                auction_turnover_cny=92_000_000,
                auction_turnover_rate=1.8,
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
                estimated_seal_probability=0.67,
                grade="B",
                grade_reason=(
                    "评级为 B，因为同题材联动和盘口质量较好，但仍是 mock 数据，"
                    "且没有真实 Level-2 大单净流入与封单排队验证。"
                ),
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
                seal_amount_cny=42_000_000,
                seal_volume_shares=2_300_000,
                seal_to_turnover_ratio=0.82,
                queue_position_note="Mock queue summary only; own-order queue position is unavailable.",
                current_change_pct=6.85,
                auction_change_pct=1.1,
                auction_turnover_cny=31_000_000,
                auction_turnover_rate=0.7,
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
                estimated_seal_probability=0.46,
                grade="C",
                grade_reason=(
                    "评级为 C，因为题材虽活跃，但盘口质量低于偏好阈值，"
                    "模拟封板概率也不足以进入重点观察。"
                ),
                data_quality=self._mock_second_board_data_quality(),
                notes=[
                    "Theme is active, but orderbook quality is below the preferred threshold.",
                    "Mock candidate should remain in observation mode.",
                ],
            ),
        ]

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
                grade="REJECT",
                grade_reason="评级为 REJECT，因为该股票不在昨日有效涨停候选池中，不能按二板模型评分。",
                observations=[
                    "Symbol is not in the mock yesterday-limit-up candidate pool.",
                ],
                risks=[
                    "Second-board model should only score stocks that had a valid previous-day limit-up event.",
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
            grade=candidate.grade,
            grade_reason=candidate.grade_reason,
            observations=[
                f"Five-minute speed is {candidate.five_min_speed_pct:.1f}%.",
                f"Five-minute speed window is {candidate.five_min_speed_window}; timestamp is {candidate.five_min_speed_timestamp}.",
                f"Big-order net inflow ratio is {candidate.big_order_net_inflow_ratio:.2f}.",
                f"Same-theme rising count is {candidate.same_theme_rising_count}.",
                f"Estimated seal probability is {candidate.estimated_seal_probability:.0%} in mock data.",
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
            grade="B",
            grade_reason=(
                "评级为 B，因为 mock 数据显示题材强度、资金方向和买盘质量都偏正面，"
                "但真实行情与历史统计尚未接入。"
            ),
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
