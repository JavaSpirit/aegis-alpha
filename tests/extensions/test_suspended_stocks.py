def test_is_symbol_suspended_returns_true_when_present():
    from aegis_alpha.models import SuspendedStock
    from aegis_alpha.extensions.suspended_stocks import is_symbol_suspended

    rows = [
        SuspendedStock(symbol="600519", suspension_start_day="2026-05-20",
                       suspension_end_day=""),
    ]
    assert is_symbol_suspended("600519", trading_day="2026-05-25", suspended=rows)


def test_is_symbol_suspended_false_when_resumed():
    from aegis_alpha.models import SuspendedStock
    from aegis_alpha.extensions.suspended_stocks import is_symbol_suspended

    rows = [
        SuspendedStock(symbol="600519", suspension_start_day="2026-05-20",
                       suspension_end_day="2026-05-22"),
    ]
    assert not is_symbol_suspended("600519", trading_day="2026-05-25", suspended=rows)


def test_mock_adapter_get_suspended_stocks():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    out = adapter.get_suspended_stocks(trading_day="2026-06-01")
    assert isinstance(out, list)
    assert all(s.data_mode == "mock" for s in out)
