from __future__ import annotations

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter, normalize_symbol


class FakeJvQuantClient:
    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
        if "昨日涨停" in query:
            if "封单" in query or "首次涨停" in query:
                fields = [
                    "代码",
                    "名称",
                    "涨跌幅",
                    "行业",
                    "是否ST",
                    "涨停",
                    "涨停首次封板时间",
                    "涨停封单额",
                    "涨停封单量(股)",
                    "涨停封成比",
                    "最新价",
                    "成交额",
                ]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
                ]
            elif "资金" in query or "5分钟" in query:
                fields = [
                    "代码",
                    "名称",
                    "涨跌幅",
                    "行业",
                    "是否ST",
                    "涨停",
                    "区间涨跌幅(1分钟)@2026-05-26 09:35:00-2026-05-26 09:40:00",
                    "主力净额",
                    "最新价",
                    "成交额",
                ]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "2.10", "3000.00万", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "0.80", "-500.00万", "32.10", "4.12亿"],
                ]
            else:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "32.10", "4.12亿"],
                ]
        elif "今日涨停" in query:
            fields = [
                "代码",
                "名称",
                "涨跌幅",
                "行业",
                "是否ST",
                "涨停",
                "涨停首次封板时间",
                "涨停封单额",
                "涨停封单量(股)",
                "涨停封成比",
                "最新价",
                "成交额",
            ]
            rows = [
                ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
                ["002001", "新和成", "10.00", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
            ]
        elif "炸板" in query:
            fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "炸板次数", "最新价", "成交额"]
            rows = [
                ["603278", "大业股份", "6.00", "通用设备", "否", "1", "14.14", "8.37亿"],
            ]
        else:
            fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最新价", "成交额"]
            rows = [["600839", "四川长虹", "-2.57", "黑色家电", "上交所主板", "否", "7.95", "6.47亿"]]

        return {
            "code": 0,
            "message": "",
            "data": {
                "count": len(rows),
                "fields": fields,
                "list": rows,
            },
        }

    def kline(self, code: str, cate: str, fq: str, type: str, limit: int) -> dict:
        return {
            "code": code,
            "message": "",
            "data": {
                "code": code,
                "name": "贵州茅台",
                "type": type,
                "fq": fq,
                "fields": ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"],
                "list": [
                    [
                        "2026-05-26",
                        "1285.35",
                        "1273.38",
                        "1289.89",
                        "1270.01",
                        "45932",
                        "5867830633",
                        "1.55",
                        "-0.97",
                        "-12.5",
                        "0.37",
                    ]
                ],
            },
        }

    def level_queue(self, code: str) -> dict:
        return {
            "code": code,
            "message": "",
            "data": {
                "code": code,
                "count": 4,
                "fields": ["S2", "S1", "B1", "B2"],
                "list": [
                    {
                        "type": "S2",
                        "price": 1306.5,
                        "volume_count": 1200,
                        "queue_count": 3,
                        "queue_slice": "100,200,900",
                    },
                    {
                        "type": "S1",
                        "price": 1306.0,
                        "volume_count": 3300,
                        "queue_count": 23,
                        "queue_slice": "100,100,100",
                    },
                    {
                        "type": "B1",
                        "price": 1305.5,
                        "volume_count": 2500,
                        "queue_count": 18,
                        "queue_slice": "100,300,500",
                    },
                    {
                        "type": "B2",
                        "price": 1305.0,
                        "volume_count": 900,
                        "queue_count": 6,
                        "queue_slice": "100,200,600",
                    },
                ],
            },
        }


def test_normalize_symbol_for_jvquant() -> None:
    assert normalize_symbol("600519.SH") == "600519"
    assert normalize_symbol("000001.sz") == "000001"


def test_jvquant_realtime_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_realtime_snapshot("600519.SH")

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.name == "贵州茅台"
    assert snapshot.last_price == 1273.38
    assert snapshot.change_pct == -0.97
    assert snapshot.turnover_cny == 5867830633
    assert snapshot.bid_quality_score > 0


def test_jvquant_orderbook_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_orderbook_snapshot("600519.SH")

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.level_count == 4
    assert snapshot.best_bid_price == 1305.5
    assert snapshot.best_ask_price == 1306.0
    assert len(snapshot.bid_levels) == 2
    assert len(snapshot.ask_levels) == 2


def test_jvquant_market_gate_from_semantic_query() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_market_snapshot()
    gate = adapter.get_market_sentiment_gate()
    limitup_pool = adapter.get_limitup_pool()
    break_pool = adapter.get_break_board_pool()

    assert snapshot.data_mode == "live_provider"
    assert snapshot.provider == "jvQuant"
    assert snapshot.limit_up_count == 2
    assert snapshot.break_board_count == 1
    assert snapshot.break_board_rate == 0.3333
    assert snapshot.leading_themes
    assert gate.data_mode == "live_provider"
    assert gate.action in {"active", "selective", "defensive", "avoid"}
    assert limitup_pool[0].data_mode == "live_provider"
    assert limitup_pool[0].status == "sealed"
    assert limitup_pool[0].first_limit_up_time == "09:42:18"
    assert limitup_pool[0].seal_amount_cny == 128_000_000
    assert break_pool[0].current_change_pct == 6.0


def test_jvquant_second_board_candidates_from_semantic_query() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    candidates = adapter.get_second_board_candidates()
    explanation = adapter.explain_second_board_candidate(candidates[0].symbol)

    assert candidates
    assert candidates[0].symbol == "001366"
    assert candidates[0].data_mode == "live_provider"
    assert candidates[0].provider == "jvQuant"
    assert candidates[0].current_change_pct == 9.99
    assert candidates[0].five_min_speed_pct == 2.10
    assert candidates[0].five_min_speed_window == "provider_exact_window:2026-05-26 09:35:00-2026-05-26 09:40:00"
    assert candidates[0].five_min_speed_timestamp == "2026-05-26T09:40:00+08:00"
    assert candidates[0].big_order_net_inflow_ratio > 0
    assert candidates[0].data_quality["five_min_speed"].source == "jvquant.semantic_query"
    assert candidates[0].data_quality["five_min_speed"].confidence == "high"
    assert {item.authority for item in candidates[0].data_quality["five_min_speed"].evidence} == {
        "official_doc",
        "observed_probe",
        "internal_inference",
    }
    assert any(
        item.authority == "internal_inference"
        for item in candidates[0].data_quality["seal_metrics"].evidence
    )
    assert candidates[0].data_quality["history_stats"].usable_for_grading is False
    assert candidates[0].first_limit_up_time == "09:42:18"
    assert candidates[0].seal_amount_cny == 128_000_000
    assert candidates[0].seal_volume_shares == 6_880_000
    assert candidates[0].seal_to_turnover_ratio == 1.65
    assert "Own-order queue position unavailable" in candidates[0].queue_position_note
    assert candidates[0].same_theme_rising_count >= 1
    assert candidates[0].grade in {"A", "B", "C", "REJECT"}
    assert candidates[0].grade_reason
    assert explanation.grade_reason
    assert any("Five-minute speed window" in observation for observation in explanation.observations)
    assert "not investment advice" in explanation.disclaimer.lower()
