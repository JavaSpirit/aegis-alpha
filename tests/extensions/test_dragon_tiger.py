import pathlib

from aegis_alpha.extensions.dragon_tiger import (
    classify_seat,
    load_seat_whitelist,
    parse_dragon_tiger_payload,
)


CONFIG_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "dragon_tiger_seats.yaml"


def test_load_whitelist_known_alias():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    classification = classify_seat(
        "国泰君安证券深圳益田路荣超商务中心证券营业部",
        whitelist,
    )
    assert classification == ("hot_money_known", "章盟主")


def test_classify_institution_seat():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("机构专用", whitelist)
    assert seat_type == "institution"
    assert alias == ""


def test_classify_unknown_seat_falls_back_to_hot_money_unknown():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("某营业部", whitelist)
    assert seat_type == "hot_money_unknown"
    assert alias == ""


def test_parse_dragon_tiger_payload_extracts_top_seats():
    raw = {
        "symbol": "600519",
        "name": "贵州茅台",
        "trading_day": "2026-05-30",
        "list_reason": "日涨幅偏离值达 7%",
        "buy_seats": [
            {"seat_name": "国泰君安证券深圳益田路荣超商务中心证券营业部", "amount": 12000000},
            {"seat_name": "机构专用", "amount": 8000000},
        ],
        "sell_seats": [
            {"seat_name": "某营业部", "amount": 5000000},
        ],
    }
    record = parse_dragon_tiger_payload(
        raw, whitelist=load_seat_whitelist(str(CONFIG_PATH)), provider="mock"
    )
    assert record.symbol == "600519"
    assert record.total_buy_cny == 20_000_000.0
    assert record.total_sell_cny == 5_000_000.0
    assert record.net_amount_cny == 15_000_000.0
    assert {s.seat_type for s in record.seats} == {
        "hot_money_known",
        "institution",
        "hot_money_unknown",
    }
    aliases = {s.hot_money_alias for s in record.seats if s.hot_money_alias}
    assert "章盟主" in aliases


def test_classify_hk_connect_plain_seat():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("沪股通", whitelist)
    assert seat_type == "hk_connect"
    assert alias == ""


def test_classify_hk_connect_zhuanyong_classifies_as_institution():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("沪股通专用", whitelist)
    assert seat_type == "institution"
    assert alias == ""


def test_mock_adapter_returns_deterministic_dragon_tiger():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    record = adapter.get_dragon_tiger("600519", "2026-05-30")
    assert record.symbol == "600519"
    assert record.trading_day == "2026-05-30"
    assert record.data_mode == "mock"
    assert len(record.seats) >= 1


def test_mock_adapter_active_seats_today_non_empty():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    rows = adapter.get_active_seats_today("2026-05-30")
    assert isinstance(rows, list)
    assert all("hot_money_alias" in r for r in rows)


def test_mock_active_seats_today_returns_multiple_aliases_for_demo():
    """Mock should expose at least 3 aliases and at least one alias covering
    multiple symbols, so SKILL workflow's "板块共振" demo has signal."""
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    rows = adapter.get_active_seats_today("2026-06-01")
    aliases = {r["hot_money_alias"] for r in rows}
    assert len(aliases) >= 3, f"expected >=3 aliases, got {aliases}"
    multi_symbol_rows = [r for r in rows if r.get("symbol_count", 0) >= 2]
    assert multi_symbol_rows, (
        "at least one alias should cover multiple symbols for resonance demo"
    )


def test_jvquant_active_seats_today_returns_placeholder_signal():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    rows = adapter.get_active_seats_today("2026-06-01")
    assert isinstance(rows, list)
    assert rows, "jvquant active_seats placeholder should signal unavailability"
    assert rows[0].get("data_mode") == "placeholder"
    assert "hot_money_alias" in rows[0]


def test_jvquant_adapter_get_dragon_tiger_from_nested_observed_payload():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter(token="fake")

    class FakeClient:
        def query(self, query, page, sort_type, sort_key):
            fields = ["代码", "名称", "龙虎榜2026-06-01"]
            rows = [
                [
                    "920190",
                    "雷神科技",
                    [
                        {
                            "type": "龙虎榜",
                            "date": "2026-06-01",
                            "filter": "上榜原因:当日收盘价涨幅达到20%的前5只股票",
                            "list": [
                                {
                                    "上榜原因": "当日收盘价涨幅达到20%的前5只股票",
                                    "买入额(元)": "9615.32万",
                                    "卖出额(元)": "5988.67万",
                                    "净买额(元)": "3626.65万",
                                    "龙虎榜榜单类型": "单日榜",
                                    "上榜原因解读": "2家机构买入，成功率51.40%",
                                }
                            ],
                        }
                    ],
                ]
            ]
            return {"code": 0, "data": {"count": len(rows), "fields": fields, "list": rows}}

    adapter._client = FakeClient()
    record = adapter.get_dragon_tiger("920190", "2026-06-01")
    assert record.symbol == "920190"
    assert record.name == "雷神科技"
    assert record.data_mode == "live_provider"
    assert record.total_buy_cny == 96_153_200.0
    assert record.total_sell_cny == 59_886_700.0
    assert record.net_amount_cny == 36_266_500.0
    assert len(record.seats) == 1
