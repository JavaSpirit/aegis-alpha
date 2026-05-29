from __future__ import annotations

from dataclasses import dataclass

from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config
from aegis_alpha.models import MarketEvent, SignalSnapshot
from aegis_alpha.signals.orderbook import estimate_orderbook_metrics


@dataclass(frozen=True)
class OrderbookReplayPoint:
    timestamp: str
    price: float
    change_pct: float
    turnover_cny: float
    big_order_amount_cny: float
    bid_volumes: list[float]
    ask_volumes: list[float]


def second_board_acceleration_fixture() -> list[OrderbookReplayPoint]:
    """Synthetic near-limit-up replay used to validate the local signal pipeline."""

    return [
        OrderbookReplayPoint(
            timestamp="2026-05-29T09:30:00+08:00",
            price=10.00,
            change_pct=0.00,
            turnover_cny=80_000_000,
            big_order_amount_cny=0,
            bid_volumes=[40_000, 36_000, 30_000, 25_000, 20_000],
            ask_volumes=[60_000, 50_000, 42_000, 35_000, 28_000],
        ),
        OrderbookReplayPoint(
            timestamp="2026-05-29T09:31:00+08:00",
            price=10.15,
            change_pct=1.50,
            turnover_cny=120_000_000,
            big_order_amount_cny=4_000_000,
            bid_volumes=[55_000, 45_000, 36_000, 30_000, 24_000],
            ask_volumes=[54_000, 46_000, 38_000, 32_000, 26_000],
        ),
        OrderbookReplayPoint(
            timestamp="2026-05-29T09:32:00+08:00",
            price=10.30,
            change_pct=3.00,
            turnover_cny=180_000_000,
            big_order_amount_cny=7_000_000,
            bid_volumes=[70_000, 58_000, 42_000, 34_000, 26_000],
            ask_volumes=[45_000, 38_000, 34_000, 30_000, 25_000],
        ),
        OrderbookReplayPoint(
            timestamp="2026-05-29T09:33:00+08:00",
            price=10.55,
            change_pct=5.50,
            turnover_cny=260_000_000,
            big_order_amount_cny=11_000_000,
            bid_volumes=[95_000, 70_000, 55_000, 44_000, 34_000],
            ask_volumes=[35_000, 32_000, 28_000, 24_000, 20_000],
        ),
        OrderbookReplayPoint(
            timestamp="2026-05-29T09:34:00+08:00",
            price=10.82,
            change_pct=9.60,
            turnover_cny=380_000_000,
            big_order_amount_cny=15_000_000,
            bid_volumes=[300_000, 160_000, 90_000, 55_000, 40_000],
            ask_volumes=[18_000, 15_000, 12_000, 10_000, 8_000],
        ),
        OrderbookReplayPoint(
            timestamp="2026-05-29T09:35:00+08:00",
            price=10.98,
            change_pct=9.80,
            turnover_cny=500_000_000,
            big_order_amount_cny=18_000_000,
            bid_volumes=[120_000, 90_000, 70_000, 50_000, 36_000],
            ask_volumes=[40_000, 35_000, 30_000, 25_000, 20_000],
        ),
    ]


def run_orderbook_replay_fixture(
    *,
    symbol: str = "TEST2B",
    name: str = "Offline Second Board Fixture",
    theme: str = "offline_replay",
) -> tuple[SignalSnapshot, list[MarketEvent]]:
    buffer = SignalWindowBuffer()
    detector = EventDetector(load_event_scoring_config())
    for point in second_board_acceleration_fixture():
        buffer.add_price(
            symbol,
            point.timestamp,
            point.price,
            point.turnover_cny,
            change_pct=point.change_pct,
        )
        if point.big_order_amount_cny > 0:
            buffer.add_big_order_flow(symbol, point.big_order_amount_cny)
        metrics = estimate_orderbook_metrics(
            price=point.price,
            change_pct=point.change_pct,
            bid_volumes=point.bid_volumes,
            ask_volumes=point.ask_volumes,
            previous_seal_amount_cny=buffer.previous_seal_amount(symbol),
        )
        buffer.set_orderbook_metrics(
            symbol,
            quality_score=metrics.orderbook_quality_score,
            ask_pressure_score=metrics.ask_pressure_score,
            seal_amount_cny=metrics.seal_amount_cny,
            seal_decay_pct=metrics.seal_decay_pct,
            sell_wall_amount_cny=metrics.sell_wall_amount_cny,
            notes=metrics.notes,
        )

    snapshot = buffer.latest_snapshot(
        symbol,
        name=name,
        theme=theme,
        provider="fixture",
        data_mode="offline_replay",
        received_at="2026-05-29T09:35:30+08:00",
    )
    return snapshot, detector.detect_from_snapshot(snapshot)
