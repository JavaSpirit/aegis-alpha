def test_mock_adapter_get_limit_down_pool_returns_entries():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    pool = adapter.get_limit_down_pool("2026-05-30")
    assert isinstance(pool, list)
    assert all(entry.pool_kind == "limit_down" for entry in pool)
    assert all(entry.change_pct < 0 for entry in pool)


def test_mock_adapter_get_st_pool_returns_entries():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    pool = adapter.get_st_pool("2026-05-30")
    assert all(entry.pool_kind == "st" for entry in pool)


def test_jvquant_adapter_returns_empty_pool_when_unwired():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    # 不调真实构造器，避免依赖 jvQuant token；只验证两方法存在并返回 []。
    assert adapter.get_limit_down_pool("2026-05-30") == []
    assert adapter.get_st_pool("2026-05-30") == []


def test_market_bottom_reversal_event_triggered_on_3plus_recovers():
    from aegis_alpha.models import ContrarianPoolEntry
    from aegis_alpha.extensions.contrarian_pool import detect_bottom_reversal

    today = [
        ContrarianPoolEntry(symbol=f"00010{i}", name=f"r{i}",
                            pool_kind="limit_down", trading_day="2026-05-30",
                            consecutive_days=2, change_pct=9.95)
        for i in range(3)
    ]
    yesterday_pool_symbols = {f"00010{i}" for i in range(5)}
    event = detect_bottom_reversal(
        today_recovered_symbols=[e.symbol for e in today],
        yesterday_limit_down_symbols=yesterday_pool_symbols,
        trading_day="2026-05-30",
    )
    assert event is not None
    assert event.event_type == "MARKET_BOTTOM_REVERSAL"
    assert event.score >= 60
    assert "recovered_count=3" in " ".join(event.evidence)


def test_market_bottom_reversal_event_skipped_below_threshold():
    from aegis_alpha.extensions.contrarian_pool import detect_bottom_reversal

    event = detect_bottom_reversal(
        today_recovered_symbols=["000101"],
        yesterday_limit_down_symbols={"000101", "000102"},
        trading_day="2026-05-30",
    )
    assert event is None
