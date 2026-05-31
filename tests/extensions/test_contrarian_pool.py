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
