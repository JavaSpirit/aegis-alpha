"""TdxMarketDataAdapter — TDX (通达信) data source via tdxmcp HTTP.

Mirrors jvquant/adapter.py in structure:
  - Inherits MockMarketDataAdapter for fallback on unsupported methods
  - Uses dedicated modules: client (HTTP), parsers, candidates
  - Initialized via from_env() classmethod
"""
from __future__ import annotations

import logging
from datetime import datetime

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.adapters.tdx import client as _tdx
from aegis_alpha.adapters.tdx import parsers as P
from aegis_alpha.adapters.tdx import candidates as _candidates
from aegis_alpha.clock import SH_TZ
from aegis_alpha.models import (
    AuctionAnalysis,
    LadderEntry,
    MarketSentimentGate,
    MarketSnapshot,
    MinuteReplayBar,
    MinuteReplaySnapshot,
    SecondBoardCandidate,
    StockRealtimeSnapshot,
    ThemeLeader,
)
from aegis_alpha.themes.ladder import classify_height

logger = logging.getLogger(__name__)


class TdxMarketDataAdapter(MockMarketDataAdapter):
    """Read-only market data from 通达信 via tdxmcp HTTP.

    Overrides methods that TDX can serve with real data.
    Uses _fallback (MockMarketDataAdapter) for graceful degradation
    on unsupported methods or network failures — mirrors jvquant pattern.
    """

    def __init__(self) -> None:
        super().__init__()
        self._today = datetime.now(SH_TZ).date().isoformat()
        self._blocks_cache: list[dict] | None = None
        self._fallback = MockMarketDataAdapter()

    @classmethod
    def from_env(cls) -> "TdxMarketDataAdapter":
        return cls()

    # ═══════════════════════════════════════════════════════════════════════
    # Market
    # ═══════════════════════════════════════════════════════════════════════

    def get_market_snapshot(self) -> MarketSnapshot:
        try:
            status_data = _tdx.status()
            blocks = self._get_blocks_cached()
            return MarketSnapshot(
                trading_day=self._today,
                timestamp=datetime.now(SH_TZ).isoformat(),
                data_mode="tdx",
                provider="tdx",
                limit_up_count=0,
                break_board_rate=0.0,
                hot_theme_count=len(blocks),
                notes=[
                    f"TDX connected: {status_data.get('connected', False)}",
                    f"Active blocks: {len(blocks)}",
                ],
            )
        except Exception:
            logger.warning("TDX market_snapshot failed", exc_info=True)
            return self._fallback.get_market_snapshot()

    def get_market_sentiment_gate(self) -> MarketSentimentGate:
        try:
            blocks = self._get_blocks_cached()
            hot_themes = len({b.get("blockname", "") for b in blocks[:20]})
            return MarketSentimentGate(
                trading_day=self._today,
                timestamp=datetime.now(SH_TZ).isoformat(),
                data_mode="tdx",
                provider="tdx",
                limit_up_count=0,
                break_board_rate=0.0,
                second_board_success_rate=0.0,
                hot_theme_count=hot_themes,
                risk_flags=["limit-up count requires full market scan"],
                positive_signals=[f"TDX connected, {hot_themes} active sectors"],
                conclusion="TDX live data. Selective second-board monitoring based on real quotes.",
                consecutive_boards_alive_rate=0.0,
                first_to_second_promotion_rate=0.0,
                second_to_third_promotion_rate=0.0,
                max_height_today=0,
            )
        except Exception:
            logger.warning("TDX sentiment_gate failed", exc_info=True)
            return self._fallback.get_market_sentiment_gate()

    # ═══════════════════════════════════════════════════════════════════════
    # Single-stock
    # ═══════════════════════════════════════════════════════════════════════

    def get_stock_realtime_snapshot(self, symbol: str) -> StockRealtimeSnapshot:
        try:
            tdx_sym = P.market_prefix(symbol)
            raw = _tdx.quote(tdx_sym)
            nq = P.normalize_quote(raw)
            return StockRealtimeSnapshot(
                symbol=symbol,
                name=nq["name"],
                timestamp=datetime.now(SH_TZ).isoformat(),
                data_mode="tdx",
                provider="tdx",
                last_price=nq["price"],
                change_pct=nq["change_pct"],
                turnover_cny=nq["amount"],
                big_order_net_inflow_cny=0.0,
                bid_quality_score=50.0,
                ask_pressure_score=50.0,
                orderbook_notes=["TDX Level-1, no big-order classification"],
            )
        except Exception:
            return self._fallback.get_stock_realtime_snapshot(symbol)

    def get_stock_minute_replay_snapshot(
        self, symbol: str, trading_day: str = "", window_start: str = "", window_end: str = ""
    ) -> MinuteReplaySnapshot:
        try:
            tdx_sym = P.market_prefix(symbol)
            bars_raw = _tdx.history(tdx_sym, period=8, count=240)
            bars = [
                MinuteReplayBar(
                    time=str(b.get("time", "")),
                    last_price=P.float_or_zero(b.get("close")),
                    average_price=(
                        P.float_or_zero(b.get("amount")) / max(P.float_or_zero(b.get("vol")), 1)
                    ),
                    volume=P.float_or_zero(b.get("vol")),
                )
                for b in (bars_raw or []) if isinstance(b, dict)
            ]
            return MinuteReplaySnapshot(
                symbol=symbol,
                timestamp=datetime.now(SH_TZ).isoformat(),
                data_mode="tdx",
                provider="tdx",
                trading_day=trading_day or self._today,
                minute_count=len(bars),
                bars=bars,
                notes=["TDX 1-min K-line replay"],
            )
        except Exception:
            return self._fallback.get_stock_minute_replay_snapshot(
                symbol, trading_day, window_start, window_end
            )

    # ═══════════════════════════════════════════════════════════════════════
    # Theme / Block
    # ═══════════════════════════════════════════════════════════════════════

    def get_theme_leaders(self, theme: str = "", trading_day: str = "") -> list[ThemeLeader]:
        try:
            blocks = self._get_blocks_cached()
            return [
                ThemeLeader(
                    theme=str(b.get("blockname", "")),
                    trading_day=trading_day or self._today,
                    leader_symbol="",
                    leader_name="",
                    member_count=len(b.get("stocks", [])),
                    notes=[f"TDX block: {b.get('blockname', '')}"],
                )
                for b in blocks[:10]
            ]
        except Exception:
            return self._fallback.get_theme_leaders(theme, trading_day)

    def get_limit_up_ladder(self, symbol: str, trading_day: str = "") -> LadderEntry:
        try:
            tdx_sym = P.market_prefix(symbol)
            bars = _tdx.history(tdx_sym, period=4, count=20)
            consecutive = 0
            for b in (bars or []):
                close_p = P.float_or_zero(b.get("close"))
                high_p = P.float_or_zero(b.get("high"))
                if high_p > 0 and close_p / high_p > 0.98:
                    consecutive += 1
                else:
                    break
            return LadderEntry(
                symbol=symbol,
                trading_day=trading_day or self._today,
                consecutive_boards=consecutive,
                height_label=classify_height(consecutive),
                notes=[f"TDX daily bars, inferred consecutive={consecutive}"],
            )
        except Exception:
            return self._fallback.get_limit_up_ladder(symbol, trading_day)

    def get_auction_analysis(self, symbol: str, trading_day: str = "") -> AuctionAnalysis:
        try:
            tdx_sym = P.market_prefix(symbol)
            raw = _tdx.quote(tdx_sym)
            nq = P.normalize_quote(raw)
            open_p = nq["open"]
            last_close = nq["last_close"]
            auction_change = ((open_p - last_close) / last_close * 100) if last_close else 0.0
            return AuctionAnalysis(
                symbol=symbol,
                trading_day=trading_day or self._today,
                auction_change_pct=round(auction_change, 2),
                auction_turnover_cny=0.0,
                pattern="unknown",
                pattern_reason="TDX Level-1, pattern not classified",
            )
        except Exception:
            return self._fallback.get_auction_analysis(symbol, trading_day)

    # ═══════════════════════════════════════════════════════════════════════
    # Candidates (delegates to tdx/candidates.py — mirrors jvquant)
    # ═══════════════════════════════════════════════════════════════════════

    def get_second_board_candidates(self) -> list[SecondBoardCandidate]:
        return self._get_tdx_candidates()

    def get_second_board_candidates_compact(
        self, limit: int = 10, break_filter: str = ""
    ) -> list[dict]:
        candidates = self._get_tdx_candidates()
        if break_filter == "exclude":
            candidates = [c for c in candidates if c.break_board_count == 0]
        elif break_filter == "only":
            candidates = [c for c in candidates if c.break_board_count > 0]
        return [c.model_dump() for c in candidates[:limit]]

    # ── internal ──────────────────────────────────────────────────────────

    def _get_tdx_candidates(self) -> list[SecondBoardCandidate]:
        try:
            blocks = self._get_blocks_cached()
            result = _candidates.assemble_candidates(blocks_data=blocks)
            if result:
                return result
        except Exception:
            logger.warning("TDX candidate assembly failed", exc_info=True)
        return self._fallback.get_second_board_candidates()

    def _get_blocks_cached(self) -> list[dict]:
        if self._blocks_cache is None:
            try:
                self._blocks_cache = _tdx.blocks()
            except Exception:
                self._blocks_cache = []
        return self._blocks_cache
