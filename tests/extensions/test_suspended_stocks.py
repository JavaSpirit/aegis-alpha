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


def test_jvquant_adapter_get_suspended_stocks_confirmed_empty():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter(token="fake")

    class FakeClient:
        def query(self, query, page, sort_type, sort_key):
            fields = [
                "名称", "代码", "行业分类二级", "停牌起始日期2026-06-01",
                "停牌原因2026-06-01", "停牌@截至2026-06-01最新",
                "复牌@截至2026-06-01最新",
            ]
            return {"code": 0, "data": {"count": 0, "fields": fields, "list": []}}

    adapter._client = FakeClient()
    assert adapter.get_suspended_stocks("2026-06-01") == []


def test_jvquant_suspended_parser_handles_observed_field_shape():
    from aegis_alpha.adapters.jvquant.parsers import parse_suspended_stocks_payload

    payload = {
        "code": 0,
        "data": {
            "fields": [
                "名称", "代码", "行业分类二级", "停牌起始日期2026-06-01",
                "停牌原因2026-06-01", "停牌@截至2026-06-01最新",
                "复牌@截至2026-06-01最新",
            ],
            "list": [["样本股份", "600000", "银行", "2026-06-01", "重大事项", "停牌", "-"]],
        },
    }
    out = parse_suspended_stocks_payload(payload, trading_day="2026-06-01")
    assert len(out) == 1
    assert out[0].symbol == "600000"
    assert out[0].suspension_start_day == "2026-06-01"
    assert out[0].suspension_end_day == ""
    assert out[0].reason == "重大事项"
    assert out[0].data_mode == "live_provider"
