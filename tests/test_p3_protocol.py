from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.models import SealTimelineEvent
from aegis_alpha.protocols import MarketDataAdapter


def test_mock_adapter_satisfies_p3_protocol_extensions() -> None:
    adapter: MarketDataAdapter = MockMarketDataAdapter()
    timeline = adapter.get_seal_timeline("002230.SZ")
    assert timeline.final_status == "sealed"
    assert timeline.events
    recorded = adapter.record_seal_timeline_event(
        SealTimelineEvent(
            symbol="X",
            trading_day="2026-05-31",
            kind="first_seal",
            occurred_at="2026-05-31T09:35:00+08:00",
        )
    )
    assert recorded.symbol == "X"


def test_mock_adapter_unknown_symbol_returns_empty_timeline() -> None:
    adapter = MockMarketDataAdapter()
    timeline = adapter.get_seal_timeline("XXXXXX")
    assert timeline.final_status == "unknown"
    assert not timeline.events
