from __future__ import annotations

from typing import cast

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.protocols import MarketDataAdapter


class IncompleteAdapter:
    def get_market_snapshot(self) -> object:
        return object()


def test_mock_adapter_satisfies_market_data_protocol() -> None:
    adapter = MockMarketDataAdapter()

    assert isinstance(adapter, MarketDataAdapter)


def test_incomplete_adapter_does_not_satisfy_protocol() -> None:
    assert not isinstance(IncompleteAdapter(), MarketDataAdapter)


def test_protocol_assignment_allows_market_data_calls() -> None:
    adapter = cast(MarketDataAdapter, MockMarketDataAdapter())

    snapshot = adapter.get_market_snapshot()
    candidates = adapter.get_second_board_candidates()

    assert snapshot.market == "A-share"
    assert candidates
