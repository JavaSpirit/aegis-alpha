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


def test_jvquant_adapter_wires_limit_down_and_st_pools_from_observed_fields():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter(token="fake")

    class FakeClient:
        def query(self, query, page, sort_type, sort_key):
            if "跌停" in query:
                fields = [
                    "代码", "名称", "涨跌幅2026-06-01", "行业分类二级",
                    "是否跌停2026-06-01", "连续跌停天数(天)2026-06-01",
                    "收盘价(日线不复权)2026-06-01", "成交额2026-06-01",
                ]
                rows = [["002943", "宇晶股份", "-10.00", "通用设备", "跌停", "1", "74.50", "8.02亿"]]
            else:
                fields = [
                    "代码", "名称", "涨跌幅2026-06-01", "行业分类二级",
                    "是否ST2026-06-01", "收盘价(日线不复权)2026-06-01", "成交额2026-06-01",
                ]
                rows = [["002848", "*ST高斯", "0.00", "黑色家电", "是", "-", "-"]]
            return {"code": 0, "data": {"count": len(rows), "fields": fields, "list": rows}}

    adapter._client = FakeClient()
    limit_down = adapter.get_limit_down_pool("2026-06-01")
    st_pool = adapter.get_st_pool("2026-06-01")

    assert len(limit_down) == 1
    assert limit_down[0].symbol == "002943"
    assert limit_down[0].pool_kind == "limit_down"
    assert limit_down[0].consecutive_days == 1
    assert limit_down[0].change_pct == -10.0
    assert len(st_pool) == 1
    assert st_pool[0].symbol == "002848"
    assert st_pool[0].pool_kind == "st"
    assert "price_missing=true" in st_pool[0].notes


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
