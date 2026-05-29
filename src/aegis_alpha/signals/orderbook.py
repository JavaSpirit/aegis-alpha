from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OrderbookMetrics:
    bid_volume: float
    ask_volume: float
    bid_ask_volume_ratio: float
    orderbook_quality_score: float
    ask_pressure_score: float
    seal_amount_cny: float
    seal_decay_pct: float
    sell_wall_amount_cny: float
    notes: list[str] = field(default_factory=list)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def estimate_orderbook_metrics(
    *,
    price: float,
    change_pct: float,
    bid_volumes: list[float],
    ask_volumes: list[float],
    previous_seal_amount_cny: float = 0.0,
    lot_size: int = 100,
) -> OrderbookMetrics:
    """Estimate actionable orderbook signals from ten-level quote volumes.

    jvQuant's observed realtime lv10 callback exposes ten bid and ten ask volume
    attributes in the current adapter. Until a richer schema is confirmed, these
    metrics are conservative estimates rather than exchange-authoritative queue
    position or active buy/sell direction.
    """

    clean_bids = [max(0.0, numeric(value)) for value in bid_volumes[:10]]
    clean_asks = [max(0.0, numeric(value)) for value in ask_volumes[:10]]
    bid_volume = sum(clean_bids)
    ask_volume = sum(clean_asks)
    total_volume = bid_volume + ask_volume
    bid_ratio = bid_volume / total_volume if total_volume else 0.5
    best_bid_volume = clean_bids[0] if clean_bids else 0.0
    best_ask_volume = clean_asks[0] if clean_asks else 0.0

    sell_wall_amount = best_ask_volume * max(price, 0.0) * lot_size
    is_near_limit = change_pct >= 9.5
    seal_amount = best_bid_volume * max(price, 0.0) * lot_size if is_near_limit else 0.0
    seal_decay = 0.0
    if previous_seal_amount_cny > 0 and seal_amount > 0:
        seal_decay = max(0.0, (previous_seal_amount_cny - seal_amount) / previous_seal_amount_cny * 100.0)
    elif previous_seal_amount_cny > 0 and seal_amount <= 0:
        seal_decay = 100.0

    depth_score = clamp(bid_ratio * 100.0)
    best_level_support = best_bid_volume / (best_bid_volume + best_ask_volume) if best_bid_volume + best_ask_volume else 0.5
    best_level_score = clamp(best_level_support * 100.0)
    seal_bonus = 10.0 if seal_amount > 0 else 0.0
    orderbook_quality = clamp(depth_score * 0.65 + best_level_score * 0.25 + seal_bonus)
    ask_pressure = clamp(100.0 - orderbook_quality + min(20.0, seal_decay * 0.4))

    notes = ["orderbook_metrics_estimated_from_lv10_depth"]
    if total_volume <= 0:
        notes.append("empty_orderbook_depth")
    if is_near_limit:
        notes.append("seal_amount_uses_best_bid_when_change_pct_near_limit")
    else:
        notes.append("seal_amount_not_estimated_because_price_not_near_limit")
    if seal_decay > 0:
        notes.append("seal_decay_detected_from_previous_snapshot")

    return OrderbookMetrics(
        bid_volume=round(bid_volume, 4),
        ask_volume=round(ask_volume, 4),
        bid_ask_volume_ratio=round(bid_ratio, 4),
        orderbook_quality_score=round(orderbook_quality, 2),
        ask_pressure_score=round(ask_pressure, 2),
        seal_amount_cny=round(seal_amount, 2),
        seal_decay_pct=round(seal_decay, 2),
        sell_wall_amount_cny=round(sell_wall_amount, 2),
        notes=notes,
    )


def estimate_from_lv10_object(lv10: Any, *, previous_seal_amount_cny: float = 0.0) -> OrderbookMetrics:
    return estimate_orderbook_metrics(
        price=numeric(getattr(lv10, "price", 0.0)),
        change_pct=numeric(getattr(lv10, "ratio", 0.0)),
        bid_volumes=[numeric(getattr(lv10, f"b{index}", 0.0)) for index in range(1, 11)],
        ask_volumes=[numeric(getattr(lv10, f"s{index}", 0.0)) for index in range(1, 11)],
        previous_seal_amount_cny=previous_seal_amount_cny,
    )
