from __future__ import annotations

import logging
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.models import (
    BreakBoardStock,
    CandidateExplanation,
    CandidateOutcomeReview,
    EventScoringConfig,
    LimitUpStock,
    MarketSentimentGate,
    MarketSnapshot,
    MarketEvent,
    MinuteReplayBar,
    MinuteReplaySnapshot,
    OrderbookQueueLevel,
    SecondBoardCandidate,
    SignalEvidence,
    SignalMetadata,
    SignalSnapshot,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
)
from aegis_alpha.events import EventDetector, freshness_status, load_event_scoring_config, now_iso
from aegis_alpha.storage import AegisAlphaStore
from aegis_alpha.adapters.jvquant_websocket import JvQuantRealtimeClient


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
                "Limit-up pool includes jvQuant semantic-query first seal time and seal amount when available.",
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
            "今日涨停,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单金额,封单量,涨停封成比,价格,成交额,行业",
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
        rows = self._query_rows(payload)
        seal_rows = self._rows_by_symbol(self._query_rows(seal_payload))
        speed_1m_rows = self._rows_by_symbol(self._query_rows(speed_1m_payload))
        speed_3m_rows = self._rows_by_symbol(self._query_rows(speed_3m_payload))
        speed_10m_rows = self._rows_by_symbol(self._query_rows(speed_10m_payload))
        auction_rows = self._rows_by_symbol(self._query_rows(auction_payload))
        theme_rows = self._rows_by_symbol(self._query_rows(theme_payload))
        break_reseal_rows = self._rows_by_symbol(self._query_rows(break_reseal_payload))
        max_seal_rows = self._rows_by_symbol(self._query_rows(max_seal_payload))
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
        theme_counts = Counter(self._theme_from_row(row) for row in rows)
        gate = self.get_market_sentiment_gate()

        candidates: list[SecondBoardCandidate] = []
        for index, row in enumerate(rows[:max_candidates]):
            symbol = self._symbol_from_row(row)
            seal_row = seal_rows.get(symbol, {})
            speed_1m_row = speed_1m_rows.get(symbol, {})
            speed_3m_row = speed_3m_rows.get(symbol, {})
            speed_10m_row = speed_10m_rows.get(symbol, {})
            auction_row = auction_rows.get(symbol, {})
            theme_row = theme_rows.get(symbol, {})
            break_reseal_row = break_reseal_rows.get(symbol, {})
            max_seal_row = max_seal_rows.get(symbol, {})
            change_pct = _float_or_zero(
                self._first_field_value(
                    [row, seal_row, break_reseal_row, theme_row, max_seal_row],
                    "涨跌幅",
                )
            )
            speed_field, speed_value = self._field_entry(row, "涨速", "区间涨跌幅")
            five_min_speed_pct = _float_or_zero(speed_value)
            speed_window, speed_timestamp, has_exact_speed_window = self._speed_window_from_field(
                speed_field,
                query_timestamp,
            )
            one_min_speed_pct, one_min_speed_window, one_min_speed_timestamp, has_exact_1m_window = (
                self._speed_from_row(speed_1m_row, query_timestamp)
            )
            three_min_speed_pct, three_min_speed_window, three_min_speed_timestamp, has_exact_3m_window = (
                self._speed_from_row(speed_3m_row, query_timestamp)
            )
            ten_min_speed_pct, ten_min_speed_window, ten_min_speed_timestamp, has_exact_10m_window = (
                self._speed_from_row(speed_10m_row, query_timestamp)
            )
            minute_replay_timestamp = ""
            minute_replay_trading_day = ""
            minute_replay_bar_count = 0
            minute_replay_notes: list[str] = []
            minute_replay_used = False
            if minute_replay_enabled and index < minute_replay_limit:
                try:
                    minute_replay = self.get_stock_minute_replay_snapshot(symbol)
                    minute_replay_timestamp = minute_replay.timestamp
                    minute_replay_trading_day = minute_replay.trading_day
                    minute_replay_bar_count = minute_replay.minute_count
                    if minute_replay.minute_count >= 2 and minute_replay.speed_pct_by_window:
                        one_min_speed_pct = minute_replay.speed_pct_by_window.get("1m", one_min_speed_pct)
                        three_min_speed_pct = minute_replay.speed_pct_by_window.get("3m", three_min_speed_pct)
                        five_min_speed_pct = minute_replay.speed_pct_by_window.get("5m", five_min_speed_pct)
                        ten_min_speed_pct = minute_replay.speed_pct_by_window.get("10m", ten_min_speed_pct)
                        one_min_speed_window = minute_replay.speed_window_by_window.get("1m", one_min_speed_window)
                        three_min_speed_window = minute_replay.speed_window_by_window.get("3m", three_min_speed_window)
                        speed_window = minute_replay.speed_window_by_window.get("5m", speed_window)
                        ten_min_speed_window = minute_replay.speed_window_by_window.get("10m", ten_min_speed_window)
                        one_min_speed_timestamp = minute_replay.timestamp
                        three_min_speed_timestamp = minute_replay.timestamp
                        speed_timestamp = minute_replay.timestamp
                        ten_min_speed_timestamp = minute_replay.timestamp
                        has_exact_speed_window = True
                        has_exact_1m_window = True
                        has_exact_3m_window = True
                        has_exact_10m_window = True
                        minute_replay_used = True
                    minute_replay_notes.extend(minute_replay.notes)
                except Exception as exc:
                    minute_replay_notes.append(f"minute_replay_unavailable={type(exc).__name__}")
            turnover_cny = self._parse_cny_amount(self._field_value(row, "成交额"))
            main_net_inflow_cny = self._parse_cny_amount(
                self._field_value(row, "主力净额", "大单净额", "超大单净额")
            )
            big_order_net_inflow_ratio = self._ratio(main_net_inflow_cny, turnover_cny)
            first_limit_up_time = self._time_or_unknown(
                self._field_value(seal_row, "涨停首次封板时间", "首次涨停时间", "首次封板时间", "涨停时间")
            )
            seal_amount_cny = self._parse_cny_amount(self._field_value(seal_row, "涨停封单额", "封单金额", "封单额"))
            seal_volume_shares = self._parse_share_amount(
                self._field_value(seal_row, "涨停封单量", "封单量", "封单量(股)")
            )
            seal_to_turnover_ratio = _float_or_zero(self._field_value(seal_row, "涨停封成比", "封成比"))
            change_pct_inferred = False
            if change_pct == 0 and (first_limit_up_time != "unknown" or seal_amount_cny > 0):
                change_pct = 10.0
                change_pct_inferred = True
            auction_change_pct = _float_or_zero(self._field_value(auction_row, "集合竞价涨跌幅", "竞价涨幅"))
            auction_turnover_cny = self._parse_cny_amount(self._field_value(auction_row, "集合竞价成交额", "竞价成交额"))
            auction_turnover_rate = _float_or_zero(self._field_value(auction_row, "集合竞价换手率", "竞价换手率"))
            concept_tags = self._tags_from_row(theme_row, "概念", "所属概念")
            topic_tags = self._tags_from_row(theme_row, "个股题材", "题材")
            break_board_count = _int_or_zero(self._field_value(break_reseal_row, "炸板次数", "炸板次数(次)"))
            reseal_count = _int_or_zero(self._field_value(break_reseal_row, "涨停回封次数", "回封次数"))
            final_seal_time = self._time_or_unknown(
                self._field_value(break_reseal_row, "涨停最终封板时间", "最后封板时间", "最终封板时间")
            )
            max_seal_amount_cny = self._parse_cny_amount(
                self._field_value(max_seal_row, "最大封单金额", "涨停封单额", "封单金额")
            )
            max_seal_volume_shares = self._parse_share_amount(
                self._field_value(max_seal_row, "最大封单量", "涨停封单量", "封单量")
            )
            theme = self._theme_from_row(row)
            orderbook_quality = 50.0
            orderbook_notes: list[str] = []
            orderbook_timestamp = query_timestamp
            orderbook_has_rows = False
            queue_position_note = "Own-order queue position unavailable; no live order has been placed or tracked."
            if index < orderbook_limit:
                try:
                    orderbook = self.get_stock_orderbook_snapshot(symbol)
                    orderbook_timestamp = orderbook.timestamp
                    bid_volume = sum(level.volume_count for level in orderbook.bid_levels)
                    ask_volume = sum(level.volume_count for level in orderbook.ask_levels)
                    total_volume = bid_volume + ask_volume
                    orderbook_has_rows = bool(total_volume)
                    if total_volume:
                        orderbook_quality = round(100 * bid_volume / total_volume, 2)
                    if orderbook.best_bid_price is None and orderbook.best_ask_price is None:
                        queue_position_note = (
                            "Orderbook queue unavailable from provider; own-order queue position cannot be inferred."
                        )
                        orderbook_notes.append("jvQuant orderbook returned no queue rows for this candidate.")
                    else:
                        queue_position_note = self._queue_position_note(orderbook)
                        orderbook_notes.append(
                            f"jvQuant orderbook best_bid={orderbook.best_bid_price}, best_ask={orderbook.best_ask_price}."
                        )
                except Exception as exc:
                    queue_position_note = (
                        "Orderbook queue unavailable because provider request failed; "
                        "own-order queue position cannot be inferred."
                    )
                    orderbook_notes.append(f"Orderbook unavailable for candidate scoring: {type(exc).__name__}.")

            grade = self._candidate_grade(
                gate.action,
                change_pct,
                five_min_speed_pct,
                big_order_net_inflow_ratio,
                orderbook_quality,
                theme_counts[theme],
                first_limit_up_time,
                seal_amount_cny,
                seal_to_turnover_ratio,
            )
            estimated = self._estimated_seal_probability(
                gate.action,
                change_pct,
                five_min_speed_pct,
                big_order_net_inflow_ratio,
                orderbook_quality,
                theme_counts[theme],
                first_limit_up_time,
                seal_amount_cny,
                seal_to_turnover_ratio,
            )
            grade_reason = self._candidate_grade_reason(
                action=gate.action,
                grade=grade,
                change_pct=change_pct,
                five_min_speed_pct=five_min_speed_pct,
                big_order_net_inflow_ratio=big_order_net_inflow_ratio,
                orderbook_quality=orderbook_quality,
                theme_count=theme_counts[theme],
                first_limit_up_time=first_limit_up_time,
                seal_amount_cny=seal_amount_cny,
                seal_to_turnover_ratio=seal_to_turnover_ratio,
                queue_position_note=queue_position_note,
            )
            data_quality = self._second_board_data_quality(
                speed_timestamp=speed_timestamp,
                speed_window=speed_window,
                has_exact_speed_window=has_exact_speed_window,
                has_exact_multi_speed_windows=has_exact_1m_window or has_exact_3m_window or has_exact_10m_window,
                query_timestamp=query_timestamp,
                has_capital_flow=main_net_inflow_cny != 0,
                has_auction_data=bool(auction_row),
                has_theme_tags=bool(concept_tags or topic_tags),
                has_break_reseal_data=bool(break_reseal_row),
                has_max_seal_data=max_seal_amount_cny > 0 or max_seal_volume_shares > 0,
                has_seal_data=first_limit_up_time != "unknown" or seal_amount_cny > 0 or seal_volume_shares > 0,
                has_orderbook_rows=orderbook_has_rows,
                orderbook_timestamp=orderbook_timestamp,
                minute_replay_used=minute_replay_used,
                minute_replay_timestamp=minute_replay_timestamp,
                minute_replay_bar_count=minute_replay_bar_count,
            )

            candidates.append(
                SecondBoardCandidate(
                    symbol=symbol,
                    name=self._name_from_row(row),
                    data_mode="live_provider",
                    provider="jvQuant",
                    theme=theme,
                    previous_limit_up_time="unknown",
                    first_limit_up_time=first_limit_up_time,
                    seal_amount_cny=seal_amount_cny,
                    seal_volume_shares=seal_volume_shares,
                    seal_to_turnover_ratio=seal_to_turnover_ratio,
                    queue_position_note=queue_position_note,
                    current_change_pct=change_pct,
                    auction_change_pct=auction_change_pct,
                    auction_turnover_cny=auction_turnover_cny,
                    auction_turnover_rate=auction_turnover_rate,
                    five_min_speed_pct=five_min_speed_pct,
                    five_min_speed_window=speed_window,
                    five_min_speed_timestamp=speed_timestamp,
                    minute_replay_timestamp=minute_replay_timestamp,
                    minute_replay_trading_day=minute_replay_trading_day,
                    minute_replay_bar_count=minute_replay_bar_count,
                    one_min_speed_pct=one_min_speed_pct,
                    one_min_speed_window=one_min_speed_window,
                    one_min_speed_timestamp=one_min_speed_timestamp,
                    three_min_speed_pct=three_min_speed_pct,
                    three_min_speed_window=three_min_speed_window,
                    three_min_speed_timestamp=three_min_speed_timestamp,
                    ten_min_speed_pct=ten_min_speed_pct,
                    ten_min_speed_window=ten_min_speed_window,
                    ten_min_speed_timestamp=ten_min_speed_timestamp,
                    big_order_net_inflow_ratio=big_order_net_inflow_ratio,
                    concept_tags=concept_tags,
                    topic_tags=topic_tags,
                    break_board_count=break_board_count,
                    reseal_count=reseal_count,
                    final_seal_time=final_seal_time,
                    max_seal_amount_cny=max_seal_amount_cny,
                    max_seal_volume_shares=max_seal_volume_shares,
                    same_theme_rising_count=theme_counts[theme],
                    orderbook_quality_score=orderbook_quality,
                    three_year_touch_limit_success_rate=0.0,
                    three_year_sealed_next_day_gap_up_rate=0.0,
                    estimated_seal_probability=estimated,
                    grade=grade,
                    grade_reason=grade_reason,
                    data_quality=data_quality,
                    notes=[
                        "jvQuant live-provider candidate: yesterday limit-up and today gain above 5%.",
                        (
                            "current_change_pct was inferred as 10.0 because jvQuant omitted the raw change field while seal metrics were present."
                            if change_pct_inferred
                            else "current_change_pct comes from a jvQuant semantic field."
                        ),
                        (
                            "five_min_speed_pct comes from jvQuant minute replay bars recalculated by Aegis Alpha."
                            if minute_replay_used
                            else "five_min_speed_pct comes from a jvQuant semantic interval field; use five_min_speed_window for its time meaning."
                        ),
                        (
                            "minute replay was used to recalculate 1m/3m/5m/10m speed windows."
                            if minute_replay_used
                            else "minute replay was unavailable or disabled; speed fields use jvQuant semantic query values."
                        ),
                        "capital-flow ratio comes from jvQuant semantic fields, not tick-by-tick trade classification.",
                        "Historical limit-up rates are not derived yet.",
                        f"five_min_speed_window={speed_window}",
                        f"five_min_speed_timestamp={speed_timestamp}",
                        f"minute_replay_timestamp={minute_replay_timestamp}",
                        f"minute_replay_trading_day={minute_replay_trading_day}",
                        f"minute_replay_bar_count={minute_replay_bar_count}",
                        f"one_min_speed_pct={one_min_speed_pct:.2f}",
                        f"three_min_speed_pct={three_min_speed_pct:.2f}",
                        f"ten_min_speed_pct={ten_min_speed_pct:.2f}",
                        f"auction_change_pct={auction_change_pct:.2f}",
                        f"auction_turnover_cny={auction_turnover_cny:.0f}",
                        f"auction_turnover_rate={auction_turnover_rate:.2f}",
                        f"concept_tags={','.join(concept_tags[:5])}",
                        f"topic_tags={','.join(topic_tags[:5])}",
                        f"break_board_count={break_board_count}",
                        f"reseal_count={reseal_count}",
                        f"final_seal_time={final_seal_time}",
                        f"max_seal_amount_cny={max_seal_amount_cny:.0f}",
                        f"first_limit_up_time={first_limit_up_time}",
                        f"seal_amount_cny={seal_amount_cny:.0f}",
                        f"seal_volume_shares={seal_volume_shares:.0f}",
                        f"seal_to_turnover_ratio={seal_to_turnover_ratio:.2f}",
                        f"queue_position_note={queue_position_note}",
                        f"turnover_cny={turnover_cny:.0f}",
                        f"main_net_inflow_cny={main_net_inflow_cny:.0f}",
                        *orderbook_notes,
                        *minute_replay_notes[:5],
                    ],
                )
            )

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

        selected_day = self._latest_minute_day(days)
        trading_day = str(selected_day.get("date") or data.get("end") or safe_end_day)
        previous_close = _float_or_zero(selected_day.get("last_price"))
        raw_bars = selected_day.get("list", [])
        bars = self._minute_bars_from_rows(raw_bars, fields)
        last_bar = bars[-1] if bars else None
        timestamp = (
            self._iso_from_provider_datetime(f"{trading_day} {self._time_with_seconds(last_bar.time)}")
            if last_bar is not None
            else _now()
        )
        speed_pct_by_window, speed_window_by_window = self._minute_speed_windows(trading_day, bars)

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
            level = self._parse_level(row)
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

    def _candidate_note_float(self, candidate: SecondBoardCandidate, key: str) -> float:
        prefix = f"{key}="
        for note in candidate.notes:
            if note.startswith(prefix):
                return _float_or_zero(note.removeprefix(prefix))
        return 0.0

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

    def _rows_by_symbol(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {symbol: row for row in rows if (symbol := self._symbol_from_row(row))}

    def _query_count(self, payload: dict[str, Any]) -> int:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return _int_or_zero(data.get("count")) if isinstance(data, dict) else 0

    def _latest_minute_day(self, days: Any) -> dict[str, Any]:
        if not isinstance(days, list):
            return {}
        valid_days = [day for day in days if isinstance(day, dict) and isinstance(day.get("list"), list) and day["list"]]
        if not valid_days:
            return {}
        return sorted(valid_days, key=lambda item: str(item.get("date") or ""))[-1]

    def _minute_bars_from_rows(self, rows: Any, fields: list[Any]) -> list[MinuteReplayBar]:
        if not isinstance(rows, list):
            return []
        time_index = self._field_index(fields, "时间", "time")
        price_index = self._field_index(fields, "最新价", "价格", "last_price")
        average_index = self._field_index(fields, "均价", "average_price", "avg_price")
        volume_index = self._field_index(fields, "成交量", "volume")

        bars: list[MinuteReplayBar] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            time_value = self._row_value(row, time_index)
            price_value = self._row_value(row, price_index)
            if time_value in (None, "") or price_value in (None, ""):
                continue
            bar = MinuteReplayBar(
                time=str(time_value),
                last_price=_float_or_zero(price_value),
                average_price=_float_or_zero(self._row_value(row, average_index)),
                volume=_float_or_zero(self._row_value(row, volume_index)),
            )
            if bar.last_price > 0:
                bars.append(bar)
        return sorted(bars, key=lambda item: item.time)

    def _field_index(self, fields: list[Any], *prefixes: str) -> int:
        normalized_prefixes = tuple(prefix.lower() for prefix in prefixes)
        for index, field in enumerate(fields):
            field_text = str(field).strip()
            field_lower = field_text.lower()
            if field_text in prefixes or any(field_lower.startswith(prefix) for prefix in normalized_prefixes):
                return index
        return -1

    def _row_value(self, row: list[Any], index: int) -> Any:
        if index < 0 or index >= len(row):
            return None
        return row[index]

    def _minute_speed_windows(self, trading_day: str, bars: list[MinuteReplayBar]) -> tuple[dict[str, float], dict[str, str]]:
        speed_pct_by_window: dict[str, float] = {}
        speed_window_by_window: dict[str, str] = {}
        if len(bars) < 2:
            return speed_pct_by_window, speed_window_by_window

        latest_index = len(bars) - 1
        latest = bars[latest_index]
        for minutes in (1, 3, 5, 10):
            base_index = max(0, latest_index - minutes)
            base = bars[base_index]
            label = f"{minutes}m"
            if base.last_price <= 0:
                speed = 0.0
            else:
                speed = round((latest.last_price / base.last_price - 1.0) * 100.0, 4)
            exactness = "exact" if latest_index - base_index == minutes else "partial"
            speed_pct_by_window[label] = speed
            speed_window_by_window[label] = (
                f"minute_replay_{exactness}_window:"
                f"{trading_day} {self._time_with_seconds(base.time)}-"
                f"{trading_day} {self._time_with_seconds(latest.time)}"
            )
        return speed_pct_by_window, speed_window_by_window

    def _time_with_seconds(self, value: str) -> str:
        text = str(value or "").strip()
        if re.fullmatch(r"\d{2}:\d{2}", text):
            return f"{text}:00"
        return text

    def _limitup_from_row(self, row: dict[str, Any]) -> LimitUpStock:
        turnover_cny = self._parse_cny_amount(self._field_value(row, "成交额"))
        seal_amount_cny = self._parse_cny_amount(self._field_value(row, "涨停封单额", "封单金额", "封单额"))
        seal_to_turnover_ratio = _float_or_zero(self._field_value(row, "涨停封成比", "封成比"))
        if seal_to_turnover_ratio == 0:
            seal_to_turnover_ratio = self._ratio(seal_amount_cny, turnover_cny)
        return LimitUpStock(
            symbol=self._symbol_from_row(row),
            name=self._name_from_row(row),
            data_mode="live_provider",
            provider="jvQuant",
            theme=self._theme_from_row(row),
            first_limit_up_time=self._time_or_unknown(
                self._field_value(row, "涨停首次封板时间", "首次涨停时间", "首次封板时间", "涨停时间")
            ),
            seal_amount_cny=seal_amount_cny,
            free_float_market_cap_cny=0.0,
            seal_amount_ratio=seal_to_turnover_ratio,
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
        _key, value = self._field_entry(row, *prefixes)
        return value

    def _field_entry(self, row: dict[str, Any], *prefixes: str) -> tuple[str, Any]:
        for prefix in prefixes:
            if prefix in row:
                return prefix, row[prefix]
        for key, value in row.items():
            if any(key.startswith(prefix) for prefix in prefixes):
                return key, value
        return "", None

    def _first_field_value(self, rows: list[dict[str, Any]], *prefixes: str) -> Any:
        for row in rows:
            value = self._field_value(row, *prefixes)
            if value not in (None, ""):
                return value
        return None

    def _parse_cny_amount(self, value: Any) -> float:
        text = str(value or "").strip().replace(",", "")
        if not text:
            return 0.0
        negative = text.startswith("-")
        text = text.removeprefix("-")
        multiplier = 1.0
        if text.endswith("亿"):
            multiplier = 100_000_000.0
            text = text[:-1]
        elif text.endswith("万"):
            multiplier = 10_000.0
            text = text[:-1]
        amount = _float_or_zero(text) * multiplier
        return -amount if negative else amount

    def _parse_share_amount(self, value: Any) -> float:
        text = str(value or "").strip().replace(",", "")
        text = text.replace("股", "")
        return self._parse_cny_amount(text)

    def _time_or_unknown(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text or text in {"0", "None", "nan", "NaN"}:
            return "unknown"
        return text

    def _speed_window_from_field(self, field_name: str, query_timestamp: str) -> tuple[str, str, bool]:
        match = re.search(
            r"@(?P<start>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})-(?P<end>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
            field_name,
        )
        if not match:
            return "provider_latest_rolling_5m", query_timestamp, False

        start = match.group("start")
        end = match.group("end")
        timestamp = self._iso_from_provider_datetime(end) or query_timestamp
        return f"provider_exact_window:{start}-{end}", timestamp, True

    def _speed_from_row(self, row: dict[str, Any], query_timestamp: str) -> tuple[float, str, str, bool]:
        field, value = self._field_entry(row, "涨速", "区间涨跌幅")
        window, timestamp, has_exact_window = self._speed_window_from_field(field, query_timestamp)
        return _float_or_zero(value), window, timestamp, has_exact_window

    def _iso_from_provider_datetime(self, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SH_TZ)
        except ValueError:
            return ""
        return parsed.isoformat(timespec="seconds")

    def _queue_position_note(self, orderbook: StockOrderbookSnapshot) -> str:
        if not orderbook.bid_levels and not orderbook.ask_levels:
            return "Orderbook queue unavailable from provider; own-order queue position cannot be inferred."
        best_bid = orderbook.bid_levels[0] if orderbook.bid_levels else None
        best_ask = orderbook.ask_levels[0] if orderbook.ask_levels else None
        parts = ["Own-order queue position unavailable until Aegis Alpha tracks a submitted order."]
        if best_bid is not None:
            parts.append(
                f"best_bid_queue price={best_bid.price}, volume={best_bid.volume_count:.0f}, queue_count={best_bid.queue_count}."
            )
        if best_ask is not None:
            parts.append(
                f"best_ask_queue price={best_ask.price}, volume={best_ask.volume_count:.0f}, queue_count={best_ask.queue_count}."
            )
        return " ".join(parts)

    def _tags_from_row(self, row: dict[str, Any], *prefixes: str) -> list[str]:
        values: list[str] = []
        for prefix in prefixes:
            value = self._field_value(row, prefix)
            if value is None:
                continue
            if isinstance(value, list):
                values.extend(str(item).strip() for item in value)
            else:
                text = str(value).strip()
                bracket_tags = re.findall(r"【([^】]+)】", text)
                if bracket_tags:
                    values.extend(part.strip() for part in bracket_tags)
                else:
                    text = re.sub(r"[\[\]\"'【】]", "", text)
                    values.extend(part.strip() for part in re.split(r"[,，;；、|/]+", text))
        seen: set[str] = set()
        tags: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            tags.append(value)
        return tags[:20]

    def _second_board_data_quality(
        self,
        *,
        speed_timestamp: str,
        speed_window: str,
        has_exact_speed_window: bool,
        has_exact_multi_speed_windows: bool,
        query_timestamp: str,
        has_capital_flow: bool,
        has_auction_data: bool,
        has_theme_tags: bool,
        has_break_reseal_data: bool,
        has_max_seal_data: bool,
        has_seal_data: bool,
        has_orderbook_rows: bool,
        orderbook_timestamp: str,
        minute_replay_used: bool,
        minute_replay_timestamp: str,
        minute_replay_bar_count: int,
    ) -> dict[str, SignalMetadata]:
        semantic_query_doc = SignalEvidence(
            authority="official_doc",
            source="https://jvquant.com/wiki/",
            detail="jvQuant documentation lists semantic analysis database and comprehensive data query capabilities.",
            observed_at=query_timestamp,
        )
        level_queue_doc = SignalEvidence(
            authority="official_doc",
            source="https://jvquant.com/wiki/",
            detail="jvQuant documentation lists沪深Level2千档盘口队列 / level queue capabilities.",
            observed_at=query_timestamp,
        )
        minute_replay_doc = SignalEvidence(
            authority="official_doc",
            source="https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1%E5%88%86%E6%97%B6%E6%95%B0%E6%8D%AE.html",
            detail="jvQuant documentation lists mode=minute minute replay data with time, latest price, average price, and volume fields.",
            observed_at=query_timestamp,
        )
        speed_source = "jvquant.minute_replay" if minute_replay_used else "jvquant.semantic_query"
        speed_source_field = (
            "client.minute(mode=minute) bars recalculated into 1m/3m/5m/10m speeds"
            if minute_replay_used
            else "5分钟涨幅/区间涨跌幅"
        )
        speed_evidence = (
            [
                minute_replay_doc,
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail=(
                        "Aegis Alpha recalculates speed windows from jvQuant minute replay bars; "
                        f"minute_replay_bar_count={minute_replay_bar_count}."
                    ),
                    observed_at=minute_replay_timestamp or query_timestamp,
                ),
            ]
            if minute_replay_used
            else [
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_FIELD_MAP.md",
                    detail=(
                        f"Observed jvQuant speed field returned a parseable window: {speed_window}."
                        if has_exact_speed_window
                        else "Observed jvQuant speed field returned without a parseable window."
                    ),
                    observed_at=speed_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Confidence is high only when a provider window is parsed; otherwise medium.",
                    observed_at=query_timestamp,
                ),
            ]
        )
        return {
            "five_min_speed": SignalMetadata(
                source=speed_source,
                source_field=speed_source_field,
                timestamp=speed_timestamp,
                confidence="high" if has_exact_speed_window else "medium",
                usable_for_grading=True,
                limitations=[
                    f"window={speed_window}",
                    (
                        "Speed was independently recalculated from minute replay bars."
                        if minute_replay_used
                        else (
                            "Exact provider interval parsed from returned field name."
                            if has_exact_speed_window
                            else "Provider did not expose exact five-minute window start/end in the field name."
                        )
                    ),
                    (
                        "Still minute-level replay, not tick-by-tick realtime Level-2."
                        if minute_replay_used
                        else "Not independently recalculated from minute bars or ticks yet."
                    ),
                ],
                evidence=speed_evidence,
            ),
            "capital_flow": SignalMetadata(
                source="jvquant.semantic_query",
                source_field="主力净额/大单净额/超大单净额 divided by 成交额",
                timestamp=query_timestamp,
                confidence="medium" if has_capital_flow else "low",
                usable_for_grading=True,
                limitations=[
                    "Provider semantic aggregation, not Aegis Alpha tick-by-tick big-order classification.",
                    "Zero may mean neutral flow or provider field unavailable for the candidate.",
                ],
                evidence=[
                    semantic_query_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_FIELD_MAP.md",
                        detail="Observed jvQuant semantic query returns 主力净额 fields for current candidates.",
                        observed_at=query_timestamp,
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Ratio is computed by Aegis Alpha as capital-flow amount divided by turnover.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "multi_speed": SignalMetadata(
                source=speed_source,
                source_field=(
                    "client.minute(mode=minute) bars recalculated into 1m/3m/5m/10m speeds"
                    if minute_replay_used
                    else "1分钟涨幅/3分钟涨幅/10分钟涨幅"
                ),
                timestamp=minute_replay_timestamp or query_timestamp,
                confidence="high" if has_exact_multi_speed_windows else "medium",
                usable_for_grading=True,
                limitations=[
                    (
                        "Recalculated from jvQuant minute replay bars."
                        if minute_replay_used
                        else "Observed semantic-query interval fields; not independently recalculated from minute bars or ticks."
                    ),
                    "Aegis Alpha treats this as speed-structure context rather than a standalone decision signal.",
                ],
                evidence=[
                    minute_replay_doc if minute_replay_used else semantic_query_doc,
                    (
                        SignalEvidence(
                            authority="internal_inference",
                            source="aegis_alpha.adapter",
                            detail=(
                                "Aegis Alpha recalculates multi-speed structure from minute bars; "
                                f"minute_replay_bar_count={minute_replay_bar_count}."
                            ),
                            observed_at=minute_replay_timestamp or query_timestamp,
                        )
                        if minute_replay_used
                        else SignalEvidence(
                            authority="observed_probe",
                            source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                            detail="Observed jvQuant semantic queries return 1m, 3m, and 10m interval speed fields.",
                            observed_at=query_timestamp,
                        )
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Multi-speed structure is used to judge whether the latest pull is accelerating or fading.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "auction_metrics": SignalMetadata(
                source="jvquant.semantic_query",
                source_field="集合竞价涨跌幅/集合竞价成交额/集合竞价换手率",
                timestamp=query_timestamp,
                confidence="medium" if has_auction_data else "unavailable",
                usable_for_grading=has_auction_data,
                limitations=[
                    "Observed semantic-query fields, not official field-level definitions.",
                    "Auction quality still needs calibration by market cap and float turnover.",
                ],
                evidence=[
                    semantic_query_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                        detail="Observed jvQuant semantic query returns auction change, auction turnover, and auction turnover-rate fields.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "theme_tags": SignalMetadata(
                source="jvquant.semantic_query",
                source_field="概念/个股题材",
                timestamp=query_timestamp,
                confidence="medium" if has_theme_tags else "unavailable",
                usable_for_grading=has_theme_tags,
                limitations=[
                    "Observed concept/topic tags may not be normalized to Aegis Alpha's future theme taxonomy.",
                    "Same-theme strength still requires group-level aggregation.",
                ],
                evidence=[
                    semantic_query_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                        detail="Observed jvQuant semantic query returns concept and topic fields.",
                        observed_at=query_timestamp,
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Concept and topic tags are context signals until a normalized theme-strength model exists.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "seal_metrics": SignalMetadata(
                source="jvquant.semantic_query",
                source_field="涨停首次封板时间/涨停封单额/涨停封单量/涨停封成比",
                timestamp=query_timestamp,
                confidence="medium" if has_seal_data else "unavailable",
                usable_for_grading=has_seal_data,
                limitations=[
                    "Provider semantic snapshot; Aegis Alpha does not yet verify whether this is current, max, or close seal amount.",
                    "Missing values should not be interpolated.",
                ],
                evidence=[
                    semantic_query_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_FIELD_MAP.md",
                        detail="Observed jvQuant semantic query returns first seal time, seal amount, seal volume, and seal-to-turnover fields.",
                        observed_at=query_timestamp,
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Seal metrics are medium confidence until current/max/close seal semantics are confirmed from official docs or tick replay.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "max_seal_metrics": SignalMetadata(
                source="jvquant.semantic_query",
                source_field="最大封单金额/最大封单量",
                timestamp=query_timestamp,
                confidence="medium" if has_max_seal_data else "unavailable",
                usable_for_grading=has_max_seal_data,
                limitations=[
                    "Observed semantic-query fields; official exact max-seal semantics are not yet confirmed.",
                    "Do not confuse max seal amount with current own-order queue position.",
                ],
                evidence=[
                    semantic_query_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                        detail="Observed jvQuant semantic query maps max-seal wording to seal amount and seal volume fields.",
                        observed_at=query_timestamp,
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Max-seal metrics are medium confidence until official or replay evidence confirms the exact window.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "break_reseal_metrics": SignalMetadata(
                source="jvquant.semantic_query",
                source_field="炸板次数/涨停回封次数/涨停最终封板时间",
                timestamp=query_timestamp,
                confidence="medium" if has_break_reseal_data else "unavailable",
                usable_for_grading=has_break_reseal_data,
                limitations=[
                    "Observed semantic-query fields; not yet cross-checked with tick or replay data.",
                    "Break/reseal counts should reduce confidence when nonzero until strategy calibration exists.",
                ],
                evidence=[
                    semantic_query_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                        detail="Observed jvQuant semantic query returns break-board count, reseal count, and final seal time fields.",
                        observed_at=query_timestamp,
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Break and reseal metrics are used as risk context, not deterministic rejection rules yet.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "orderbook_queue": SignalMetadata(
                source="jvquant.level_queue",
                source_field="bid/ask queue summary",
                timestamp=orderbook_timestamp,
                confidence="medium" if has_orderbook_rows else "unavailable",
                usable_for_grading=has_orderbook_rows,
                limitations=[
                    "Read-only orderbook summary, not own-order queue position.",
                    "True queue position requires broker order and trade callbacks.",
                ],
                evidence=[
                    level_queue_doc,
                    SignalEvidence(
                        authority="observed_probe",
                        source="jvquant.level_queue",
                        detail=(
                            "Observed level_queue rows for this candidate."
                            if has_orderbook_rows
                            else "Provider returned no level_queue rows for this candidate at request time."
                        ),
                        observed_at=orderbook_timestamp,
                    ),
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail="Own-order queue position cannot be inferred without broker order/trade callbacks.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
            "history_stats": SignalMetadata(
                source="aegis_alpha.placeholder",
                source_field="three_year_touch_limit_success_rate/three_year_sealed_next_day_gap_up_rate",
                timestamp=query_timestamp,
                confidence="placeholder",
                usable_for_grading=False,
                limitations=[
                    "Historical second-board sample library is not implemented yet.",
                    "Do not use zero placeholder rates as real historical probabilities.",
                ],
                evidence=[
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.placeholder",
                        detail="Historical fields are present in the contract but not yet backed by a sample database.",
                        observed_at=query_timestamp,
                    ),
                ],
            ),
        }

    def _ratio(self, numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return round(max(-1.0, min(1.0, numerator / denominator)), 4)

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

    def _candidate_grade(
        self,
        action: str,
        change_pct: float,
        five_min_speed_pct: float,
        big_order_net_inflow_ratio: float,
        orderbook_quality: float,
        theme_count: int,
        first_limit_up_time: str,
        seal_amount_cny: float,
        seal_to_turnover_ratio: float,
    ):
        if action == "avoid":
            return "REJECT"
        if change_pct < 5:
            return "REJECT"
        seal_quality = self._seal_quality_score(first_limit_up_time, seal_amount_cny, seal_to_turnover_ratio)
        if action == "defensive":
            return (
                "B"
                if change_pct >= 9.5
                and theme_count >= 2
                and (orderbook_quality >= 55 or big_order_net_inflow_ratio >= 0.03 or seal_quality >= 60)
                else "C"
            )
        if (
            change_pct >= 9.5
            and five_min_speed_pct >= 1.5
            and big_order_net_inflow_ratio >= 0.03
            and orderbook_quality >= 60
            and theme_count >= 2
            and seal_quality >= 55
        ):
            return "A"
        if change_pct >= 7 and (orderbook_quality >= 50 or big_order_net_inflow_ratio > 0 or seal_quality >= 45):
            return "B"
        return "C"

    def _candidate_grade_reason(
        self,
        action: str,
        grade: str,
        change_pct: float,
        five_min_speed_pct: float,
        big_order_net_inflow_ratio: float,
        orderbook_quality: float,
        theme_count: int,
        first_limit_up_time: str,
        seal_amount_cny: float,
        seal_to_turnover_ratio: float,
        queue_position_note: str,
    ) -> str:
        seal_text = (
            f"首次封板时间为 {first_limit_up_time}，封单额约 {seal_amount_cny / 100_000_000:.2f} 亿元，"
            f"封成比为 {seal_to_turnover_ratio:.2f}"
        )
        if grade == "REJECT":
            return (
                "评级为 REJECT，因为当前市场闸门或个股强度不满足二板候选的最低观察条件，"
                "不应按打板候选处理。"
            )
        if grade == "C":
            if action == "defensive":
                return (
                    f"评级为 C，主要因为市场闸门为 defensive，说明炸板率或市场风险偏高；"
                    f"虽然个股当前涨幅为 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
                    f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，但盘口质量评分为 {orderbook_quality:.1f}，"
                    f"同题材候选数为 {theme_count}；{seal_text}。{queue_position_note}"
                )
            return (
                f"评级为 C，因为个股当前涨幅为 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
                f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，但盘口质量、题材联动或数据完整性不足，"
                f"暂时只能作为观察对象；{seal_text}。"
            )
        if grade == "B":
            return (
                f"评级为 B，因为个股当前涨幅达到 {change_pct:.2f}%，五分钟涨速为 {five_min_speed_pct:.2f}%，"
                f"资金净流入占比为 {big_order_net_inflow_ratio:.2%}，同题材候选数为 {theme_count}，具备观察价值；"
                f"盘口质量评分为 {orderbook_quality:.1f}，{seal_text}；但真实委托排队位置和历史溢价数据仍未接入，"
                "不能提高到 A。"
            )
        return (
            f"评级为 A，因为市场闸门允许进攻，个股涨幅为 {change_pct:.2f}%，五分钟涨速为 "
            f"{five_min_speed_pct:.2f}%，资金净流入占比为 {big_order_net_inflow_ratio:.2%}，"
            f"盘口质量评分为 {orderbook_quality:.1f}，同题材候选数为 {theme_count}，且{seal_text}；"
            "仍需在实盘时继续核验数据时效和封单稳定性。"
        )

    def _estimated_seal_probability(
        self,
        action: str,
        change_pct: float,
        five_min_speed_pct: float,
        big_order_net_inflow_ratio: float,
        orderbook_quality: float,
        theme_count: int,
        first_limit_up_time: str,
        seal_amount_cny: float,
        seal_to_turnover_ratio: float,
    ) -> float:
        probability = 0.25
        probability += min(0.30, max(0.0, change_pct - 5.0) * 0.05)
        probability += min(0.10, max(0.0, five_min_speed_pct) * 0.025)
        probability += min(0.15, max(0.0, big_order_net_inflow_ratio) * 1.5)
        probability += min(0.20, max(0.0, orderbook_quality - 50.0) / 100.0)
        probability += min(0.15, theme_count * 0.03)
        probability += min(0.12, self._seal_quality_score(first_limit_up_time, seal_amount_cny, seal_to_turnover_ratio) / 1000.0)
        if action == "active":
            probability += 0.10
        elif action == "defensive":
            probability -= 0.12
        elif action == "avoid":
            probability -= 0.25
        return round(max(0.0, min(0.95, probability)), 4)

    def _seal_quality_score(self, first_limit_up_time: str, seal_amount_cny: float, seal_to_turnover_ratio: float) -> float:
        score = 0.0
        if first_limit_up_time != "unknown":
            if first_limit_up_time <= "09:45:00":
                score += 35.0
            elif first_limit_up_time <= "10:30:00":
                score += 22.0
            elif first_limit_up_time <= "14:30:00":
                score += 10.0
        if seal_amount_cny >= 300_000_000:
            score += 30.0
        elif seal_amount_cny >= 100_000_000:
            score += 20.0
        elif seal_amount_cny >= 30_000_000:
            score += 10.0
        if seal_to_turnover_ratio >= 5:
            score += 25.0
        elif seal_to_turnover_ratio >= 2:
            score += 16.0
        elif seal_to_turnover_ratio >= 1:
            score += 8.0
        return round(min(100.0, score), 2)
