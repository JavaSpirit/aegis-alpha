from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from aegis_alpha.models import (
    EventScoringConfig,
    EventScoringRule,
    FreshnessStatus,
    MarketEvent,
    MarketEventType,
    SignalSnapshot,
)


SH_TZ = ZoneInfo("Asia/Shanghai")


def now_iso() -> str:
    return datetime.now(SH_TZ).isoformat(timespec="seconds")


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_event_scoring_config(path: str | Path | None = None) -> EventScoringConfig:
    config_path = Path(path) if path else project_root() / "config" / "event_scoring.yaml"
    payload = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    rules = {
        key: EventScoringRule.model_validate(value or {})
        for key, value in (payload.get("rules") or {}).items()
    }
    return EventScoringConfig(
        version=int(payload.get("version") or 1),
        default_freshness_limit_seconds=int(payload.get("default_freshness_limit_seconds") or 180),
        rules=rules,
    )


def freshness_status(provider_timestamp: str, received_at: str, max_age_seconds: int = 180) -> FreshnessStatus:
    if not provider_timestamp:
        return "unknown"
    try:
        provider_dt = datetime.fromisoformat(provider_timestamp)
        received_dt = datetime.fromisoformat(received_at)
    except ValueError:
        return "unknown"
    if provider_dt.tzinfo is None:
        provider_dt = provider_dt.replace(tzinfo=SH_TZ)
    if received_dt.tzinfo is None:
        received_dt = received_dt.replace(tzinfo=SH_TZ)
    return "fresh" if abs((received_dt - provider_dt).total_seconds()) <= max_age_seconds else "stale"


class SignalWindowBuffer:
    """In-memory rolling signal window for realtime handlers and deterministic tests."""

    def __init__(self, max_points_per_symbol: int = 600) -> None:
        self.max_points_per_symbol = max_points_per_symbol
        self._points: dict[str, deque[tuple[str, float, float]]] = defaultdict(
            lambda: deque(maxlen=max_points_per_symbol)
        )
        self._big_order_amount: dict[str, float] = defaultdict(float)
        self._change_pct: dict[str, float] = defaultdict(float)
        self._orderbook_quality: dict[str, float] = defaultdict(lambda: 50.0)
        self._ask_pressure: dict[str, float] = defaultdict(lambda: 50.0)
        self._seal_amount: dict[str, float] = defaultdict(float)
        self._seal_decay: dict[str, float] = defaultdict(float)
        self._sell_wall_amount: dict[str, float] = defaultdict(float)
        self._notes: dict[str, list[str]] = defaultdict(list)

    def add_price(
        self,
        symbol: str,
        timestamp: str,
        price: float,
        turnover_cny: float = 0.0,
        change_pct: float | None = None,
    ) -> None:
        if price <= 0:
            return
        self._points[symbol].append((timestamp, price, turnover_cny))
        if change_pct is not None:
            self._change_pct[symbol] = change_pct

    def add_big_order_flow(self, symbol: str, amount_cny: float) -> None:
        self._big_order_amount[symbol] += amount_cny

    def set_orderbook_quality(self, symbol: str, quality_score: float) -> None:
        self._orderbook_quality[symbol] = round(max(0.0, min(100.0, quality_score)), 2)

    def set_orderbook_metrics(
        self,
        symbol: str,
        *,
        quality_score: float,
        seal_amount_cny: float,
        seal_decay_pct: float,
        ask_pressure_score: float = 50.0,
        sell_wall_amount_cny: float = 0.0,
        notes: list[str] | None = None,
    ) -> None:
        self.set_orderbook_quality(symbol, quality_score)
        self._ask_pressure[symbol] = round(max(0.0, min(100.0, ask_pressure_score)), 2)
        self._seal_amount[symbol] = max(0.0, seal_amount_cny)
        self._seal_decay[symbol] = max(0.0, seal_decay_pct)
        self._sell_wall_amount[symbol] = max(0.0, sell_wall_amount_cny)
        self._notes[symbol] = list(notes or [])

    def previous_seal_amount(self, symbol: str) -> float:
        return self._seal_amount.get(symbol, 0.0)

    def speed_pct(self, symbol: str, minutes: int) -> float:
        points = list(self._points.get(symbol, []))
        if len(points) < 2:
            return 0.0
        latest_index = len(points) - 1
        base_index = max(0, latest_index - minutes)
        base_price = points[base_index][1]
        latest_price = points[latest_index][1]
        if base_price <= 0:
            return 0.0
        return round((latest_price / base_price - 1.0) * 100.0, 4)

    def latest_snapshot(
        self,
        symbol: str,
        *,
        name: str = "unknown",
        theme: str = "unknown",
        provider: str = "jvQuant",
        data_mode: str = "realtime_buffer",
        change_pct: float = 0.0,
        orderbook_quality_score: float | None = None,
        seal_amount_cny: float = 0.0,
        received_at: str | None = None,
    ) -> SignalSnapshot:
        points = list(self._points.get(symbol, []))
        timestamp = points[-1][0] if points else (received_at or now_iso())
        price = points[-1][1] if points else 0.0
        turnover = points[-1][2] if points else 0.0
        big_order_net = self._big_order_amount.get(symbol, 0.0)
        received = received_at or now_iso()
        return SignalSnapshot(
            symbol=symbol,
            name=name,
            theme=theme,
            provider=provider,
            data_mode=data_mode,
            price=price,
            change_pct=change_pct if change_pct != 0.0 else self._change_pct.get(symbol, 0.0),
            speed_1m_pct=self.speed_pct(symbol, 1),
            speed_3m_pct=self.speed_pct(symbol, 3),
            speed_5m_pct=self.speed_pct(symbol, 5),
            speed_10m_pct=self.speed_pct(symbol, 10),
            big_order_net_inflow_cny=big_order_net,
            big_order_net_inflow_ratio=round(big_order_net / turnover, 4) if turnover else 0.0,
            orderbook_quality_score=(
                orderbook_quality_score
                if orderbook_quality_score is not None
                else self._orderbook_quality.get(symbol, 50.0)
            ),
            ask_pressure_score=self._ask_pressure.get(symbol, 50.0),
            seal_amount_cny=seal_amount_cny or self._seal_amount.get(symbol, 0.0),
            seal_decay_pct=self._seal_decay.get(symbol, 0.0),
            sell_wall_amount_cny=self._sell_wall_amount.get(symbol, 0.0),
            data_timestamp=timestamp,
            provider_timestamp=timestamp,
            received_at=received,
            freshness_status=freshness_status(timestamp, received),
            notes=[
                "Realtime buffer snapshot; raw WebSocket messages are not exposed to agents.",
                *self._notes.get(symbol, []),
            ],
        )


class MarketEventBuffer:
    def __init__(self, max_events: int = 500) -> None:
        self._events: deque[MarketEvent] = deque(maxlen=max_events)

    def add(self, event: MarketEvent) -> None:
        self._events.appendleft(event)

    def recent(self, limit: int = 20, event_type: str | None = None) -> list[MarketEvent]:
        safe_limit = max(1, min(limit, 100))
        events = list(self._events)
        if event_type:
            events = [event for event in events if event.event_type == event_type]
        return events[:safe_limit]


class EventDetector:
    def __init__(self, config: EventScoringConfig | None = None) -> None:
        self.config = config or load_event_scoring_config()

    def detect_from_snapshot(self, snapshot: SignalSnapshot) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        for event_type in (
            "APPROACHING_LIMIT_UP",
            "SEAL_ORDER_DECAY",
            "BIG_ORDER_INFLOW_SPIKE",
            "SECOND_BOARD_CANDIDATE_REPRICE",
        ):
            rule = self.config.rules.get(event_type)
            if rule and rule.enabled:
                event = self._detect_single(event_type, rule, snapshot)
                if event is not None:
                    events.append(event)
        return events

    def detect_theme_cluster(self, snapshots: list[SignalSnapshot]) -> list[MarketEvent]:
        rule = self.config.rules.get("THEME_CLUSTER_RISING")
        if not rule or not rule.enabled:
            return []
        min_symbols = int(rule.trigger.get("min_symbols") or 3)
        min_speed = float(rule.trigger.get("min_5m_change_pct") or 5.0)
        by_theme: dict[str, list[SignalSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            if snapshot.theme != "unknown" and snapshot.speed_5m_pct >= min_speed:
                by_theme[snapshot.theme].append(snapshot)
        events = []
        for theme, members in by_theme.items():
            if len(members) < min_symbols:
                continue
            score = min(100.0, 45.0 + len(members) * 10.0 + max(item.speed_5m_pct for item in members) * 2.0)
            evidence = [
                f"{len(members)} symbols in theme {theme} have 5m speed >= {min_speed:.2f}%.",
                "Aegis Alpha detected a theme cluster from structured snapshots, not raw agent inference.",
            ]
            events.append(
                self._event(
                    "THEME_CLUSTER_RISING",
                    score=score,
                    snapshot=members[0],
                    evidence=evidence,
                    suggested_agent_action=rule.agent_action,
                    data={"symbols": [item.symbol for item in members], "theme": theme},
                )
            )
        return events

    def _detect_single(
        self,
        event_type: MarketEventType,
        rule: EventScoringRule,
        snapshot: SignalSnapshot,
    ) -> MarketEvent | None:
        trigger = rule.trigger
        if event_type == "APPROACHING_LIMIT_UP":
            min_change = float(trigger.get("min_change_pct") or 8.5)
            min_speed = float(trigger.get("min_5m_speed_pct") or 1.5)
            if snapshot.change_pct < min_change or snapshot.speed_5m_pct < min_speed:
                return None
            score = min(100.0, 35.0 + snapshot.change_pct * 3.0 + snapshot.speed_5m_pct * 4.0)
            evidence = [
                f"change_pct={snapshot.change_pct:.2f} >= {min_change:.2f}",
                f"speed_5m_pct={snapshot.speed_5m_pct:.2f} >= {min_speed:.2f}",
            ]
        elif event_type == "BIG_ORDER_INFLOW_SPIKE":
            min_ratio = float(trigger.get("min_big_order_net_inflow_ratio") or 0.08)
            min_amount = float(trigger.get("min_big_order_net_inflow_cny") or 30_000_000)
            if snapshot.big_order_net_inflow_ratio < min_ratio or snapshot.big_order_net_inflow_cny < min_amount:
                return None
            score = min(100.0, 40.0 + snapshot.big_order_net_inflow_ratio * 300.0)
            evidence = [
                f"big_order_net_inflow_ratio={snapshot.big_order_net_inflow_ratio:.2%} >= {min_ratio:.2%}",
                f"big_order_net_inflow_cny={snapshot.big_order_net_inflow_cny:.0f} >= {min_amount:.0f}",
            ]
        elif event_type == "SEAL_ORDER_DECAY":
            min_decay = float(trigger.get("min_decay_pct") or 30.0)
            if snapshot.seal_decay_pct < min_decay:
                return None
            score = min(100.0, 35.0 + snapshot.seal_decay_pct * 1.4 + max(0.0, 50.0 - snapshot.orderbook_quality_score) * 0.5)
            evidence = [
                f"seal_decay_pct={snapshot.seal_decay_pct:.2f} >= {min_decay:.2f}",
                f"orderbook_quality={snapshot.orderbook_quality_score:.1f}.",
            ]
        else:
            min_change = float(trigger.get("min_current_change_pct") or 7.0)
            if snapshot.change_pct < min_change:
                return None
            score = min(
                100.0,
                30.0
                + snapshot.change_pct * 2.5
                + snapshot.speed_5m_pct * 3.0
                + max(0.0, snapshot.orderbook_quality_score - 50.0) * 0.4,
            )
            if score < 55:
                return None
            evidence = [
                f"candidate current change is {snapshot.change_pct:.2f}%.",
                f"speed_5m_pct={snapshot.speed_5m_pct:.2f}; orderbook_quality={snapshot.orderbook_quality_score:.1f}.",
            ]
        return self._event(
            event_type,
            score=score,
            snapshot=snapshot,
            evidence=evidence,
            suggested_agent_action=rule.agent_action,
            data=snapshot.model_dump(),
        )

    def _event(
        self,
        event_type: MarketEventType,
        *,
        score: float,
        snapshot: SignalSnapshot,
        evidence: list[str],
        suggested_agent_action: list[str],
        data: dict[str, Any],
    ) -> MarketEvent:
        received_at = snapshot.received_at or now_iso()
        seed = json.dumps(
            [event_type, snapshot.symbol, snapshot.provider_timestamp, round(score, 4), evidence],
            ensure_ascii=False,
            sort_keys=True,
        )
        event_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return MarketEvent(
            event_id=event_id,
            event_type=event_type,
            symbol=snapshot.symbol,
            name=snapshot.name,
            theme=snapshot.theme,
            confidence="high" if snapshot.freshness_status == "fresh" and score >= 70 else "medium",
            score=round(max(0.0, min(100.0, score)), 2),
            evidence=evidence,
            provider_timestamp=snapshot.provider_timestamp or snapshot.data_timestamp,
            received_at=received_at,
            freshness_status=snapshot.freshness_status,
            suggested_agent_action=suggested_agent_action,
            data=data,
        )
