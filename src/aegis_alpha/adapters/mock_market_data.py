from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aegis_alpha.models import (
    BreakBoardStock,
    CandidateExplanation,
    LimitUpHistoryStats,
    LimitUpStock,
    MarketSnapshot,
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

    def explain_candidate(self, symbol: str) -> CandidateExplanation:
        return CandidateExplanation(
            symbol=symbol,
            grade="B",
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

