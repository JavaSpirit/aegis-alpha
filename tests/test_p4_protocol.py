from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.protocols import MarketDataAdapter


def test_mock_adapter_satisfies_p4_history_stats() -> None:
    adapter: MarketDataAdapter = MockMarketDataAdapter()
    stats = adapter.get_history_stats("002230.SZ")
    assert stats.symbol == "002230.SZ"
    assert stats.sample_size >= 0
    assert 0.0 <= stats.touch_limit_up_success_rate <= 1.0


def test_mock_adapter_unknown_symbol_returns_zero_sample() -> None:
    adapter = MockMarketDataAdapter()
    stats = adapter.get_history_stats("XXXXXX")
    assert stats.sample_size == 0
    assert stats.confidence == "insufficient_sample"
