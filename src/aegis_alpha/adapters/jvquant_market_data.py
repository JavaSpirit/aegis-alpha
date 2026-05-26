from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.models import (
    BreakBoardStock,
    LimitUpStock,
    MarketSentimentGate,
    MarketSnapshot,
    OrderbookQueueLevel,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
)


SH_TZ = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now(SH_TZ).isoformat(timespec="seconds")


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().split(".", 1)[0]


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class JvQuantMarketDataAdapter:
    """Read-only jvQuant adapter for single-symbol smoke and MCP tools."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("JVQUANT_TOKEN", "")
        if not self.token:
            raise ValueError("JVQUANT_TOKEN missing")
        self._fallback = MockMarketDataAdapter()
        self._client: Any | None = None
        self._query_cache: dict[str, dict[str, Any]] = {}

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
        themes = self._leading_themes(limitup_pool + break_pool)
        score = self._market_score(limit_up_count, break_board_rate, len(themes))
        sentiment = self._sentiment_from_score(score)

        total_payload = self._query(
            "主板,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        total_count = self._query_count(total_payload)

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
                "Limit-up and break-board pools are provider semantic-query results; seal amount and first seal time are not available yet.",
            ],
        )

    def get_market_sentiment_gate(self) -> MarketSentimentGate:
        snapshot = self.get_market_snapshot()
        score = self._market_score(
            snapshot.limit_up_count,
            snapshot.break_board_rate,
            len(snapshot.leading_themes),
        )
        action = self._action_from_score(score, snapshot.break_board_rate)
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
        )

    def get_limitup_pool(self) -> list[LimitUpStock]:
        payload = self._query(
            "今日涨停,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = self._query_rows(payload)
        return [self._limitup_from_row(row) for row in rows]

    def get_break_board_pool(self) -> list[BreakBoardStock]:
        payload = self._query(
            "炸板,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = self._query_rows(payload)
        return [self._break_board_from_row(row) for row in rows]

    def get_stock_history_limitup_stats(self, symbol: str):
        return self._fallback.get_stock_history_limitup_stats(symbol)

    def get_theme_strength(self, symbol: str):
        return self._fallback.get_theme_strength(symbol)

    def get_second_board_candidates(self):
        return self._fallback.get_second_board_candidates()

    def explain_candidate(self, symbol: str):
        return self._fallback.explain_candidate(symbol)

    def explain_second_board_candidate(self, symbol: str):
        return self._fallback.explain_second_board_candidate(symbol)

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

    def get_stock_orderbook_snapshot(self, symbol: str) -> StockOrderbookSnapshot:
        code = normalize_symbol(symbol)
        payload = self.client.level_queue(code)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        rows = data.get("list", []) if isinstance(data, dict) else []

        bid_levels: list[OrderbookQueueLevel] = []
        ask_levels: list[OrderbookQueueLevel] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            level = self._parse_level(row)
            if level.side == "bid":
                bid_levels.append(level)
            elif level.side == "ask":
                ask_levels.append(level)

        bid_levels = sorted(bid_levels, key=lambda item: item.price, reverse=True)[:10]
        ask_levels = sorted(ask_levels, key=lambda item: item.price)[:10]

        return StockOrderbookSnapshot(
            symbol=symbol,
            name=str(data.get("name") or "unknown"),
            timestamp=_now(),
            data_mode="live_provider",
            provider="jvQuant",
            level_count=_int_or_zero(data.get("count") or len(rows)),
            best_bid_price=bid_levels[0].price if bid_levels else None,
            best_ask_price=ask_levels[0].price if ask_levels else None,
            bid_levels=bid_levels,
            ask_levels=ask_levels,
            notes=[
                "Read-only jvQuant level_queue summary.",
                "Only top 10 bid and ask levels are returned to keep MCP output compact.",
                "Do not use this alone for automated trading; queue position and cancellation rules are not implemented.",
            ],
        )

    def _parse_level(self, row: dict[str, Any]) -> OrderbookQueueLevel:
        label = str(row.get("type") or "")
        side = "unknown"
        if label.startswith("B"):
            side = "bid"
        elif label.startswith("S"):
            side = "ask"

        return OrderbookQueueLevel(
            side=side,
            level_label=label,
            price=_float_or_zero(row.get("price")),
            volume_count=_float_or_zero(row.get("volume_count")),
            queue_count=_int_or_zero(row.get("queue_count")),
            queue_slice=str(row.get("queue_slice") or ""),
        )

    def _query(self, query: str, sort_key: str = "") -> dict[str, Any]:
        cache_key = f"{query}|{sort_key}"
        if cache_key not in self._query_cache:
            self._query_cache[cache_key] = self.client.query(query, 1, 1, sort_key)
        return self._query_cache[cache_key]

    def _query_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        fields = data.get("fields", []) if isinstance(data, dict) else []
        rows = data.get("list", []) if isinstance(data, dict) else []
        mapped_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            mapped_rows.append(
                {str(field): row[index] for index, field in enumerate(fields) if index < len(row)}
            )
        return mapped_rows

    def _query_count(self, payload: dict[str, Any]) -> int:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return _int_or_zero(data.get("count")) if isinstance(data, dict) else 0

    def _limitup_from_row(self, row: dict[str, Any]) -> LimitUpStock:
        return LimitUpStock(
            symbol=self._symbol_from_row(row),
            name=self._name_from_row(row),
            data_mode="live_provider",
            provider="jvQuant",
            theme=self._theme_from_row(row),
            first_limit_up_time="unknown",
            seal_amount_cny=0.0,
            free_float_market_cap_cny=0.0,
            seal_amount_ratio=0.0,
            reopen_count=0,
            status="sealed",
        )

    def _break_board_from_row(self, row: dict[str, Any]) -> BreakBoardStock:
        return BreakBoardStock(
            symbol=self._symbol_from_row(row),
            name=self._name_from_row(row),
            data_mode="live_provider",
            provider="jvQuant",
            theme=self._theme_from_row(row),
            first_break_time="unknown",
            max_seal_amount_cny=0.0,
            current_change_pct=_float_or_zero(self._field_value(row, "涨跌幅")),
            reason="jvQuant semantic query matched break-board condition; seal detail is not derived yet.",
        )

    def _symbol_from_row(self, row: dict[str, Any]) -> str:
        return str(self._field_value(row, "代码", "股票代码") or "").strip()

    def _name_from_row(self, row: dict[str, Any]) -> str:
        return str(self._field_value(row, "名称", "股票简称", "股票名称") or "").strip()

    def _theme_from_row(self, row: dict[str, Any]) -> str:
        return str(self._field_value(row, "行业", "行业分类", "所属行业") or "unknown").strip() or "unknown"

    def _field_value(self, row: dict[str, Any], *prefixes: str) -> Any:
        for prefix in prefixes:
            if prefix in row:
                return row[prefix]
        for key, value in row.items():
            if any(key.startswith(prefix) for prefix in prefixes):
                return value
        return None

    def _leading_themes(self, stocks: list[LimitUpStock | BreakBoardStock]) -> list[str]:
        counter = Counter(stock.theme for stock in stocks if stock.theme and stock.theme != "unknown")
        return [theme for theme, _count in counter.most_common(5)]

    def _market_score(self, limit_up_count: int, break_board_rate: float, hot_theme_count: int) -> float:
        score = 35.0
        score += min(35.0, limit_up_count * 0.65)
        score += min(15.0, hot_theme_count * 3.0)
        score -= break_board_rate * 45.0
        return round(max(0.0, min(100.0, score)), 2)

    def _sentiment_from_score(self, score: float) -> str:
        if score >= 75:
            return "hot"
        if score >= 60:
            return "warm"
        if score >= 45:
            return "mixed"
        return "cold"

    def _action_from_score(self, score: float, break_board_rate: float):
        if break_board_rate >= 0.55 or score < 40:
            return "avoid"
        if break_board_rate >= 0.40 or score < 55:
            return "defensive"
        if score >= 75 and break_board_rate < 0.28:
            return "active"
        return "selective"
