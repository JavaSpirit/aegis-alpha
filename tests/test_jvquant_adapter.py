from __future__ import annotations

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter, normalize_symbol


class FakeJvQuantClient:
    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:
        if "昨日涨停" in query:
            if "竞价" in query:
                fields = ["代码", "名称", "行业", "是否ST", "涨停", "集合竞价涨跌幅", "集合竞价成交额", "集合竞价换手率", "开盘价", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "饲料", "否", "涨停", "3.20", "9200.00万", "1.80", "17.90", "18.61", "2.66亿"],
                    ["002001", "新和成", "合成生物", "否", "涨停", "1.10", "3100.00万", "0.70", "31.50", "32.10", "4.12亿"],
                ]
            elif "概念" in query or "题材" in query:
                fields = ["代码", "名称", "涨跌幅", "成交额", "是否ST", "涨停", "概念", "个股题材", "行业", "最新价"]
                rows = [
                    ["001366", "播恩集团", "9.99", "2.66亿", "否", "涨停", "饲料、乡村振兴", "农业涨价", "饲料", "18.61"],
                    ["002001", "新和成", "7.10", "4.12亿", "否", "涨停", "合成生物、维生素", "医药上游", "合成生物", "32.10"],
                ]
            elif "炸板次数" in query or "回封次数" in query or "最后封板" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "涨停最终封板时间", "炸板次数(次)", "涨停回封次数(次)", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "0", "0", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "10:42:08", "1", "1", "32.10", "4.12亿"],
                ]
            elif "1分钟涨幅" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:39:00-2026-05-26 09:40:00", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "0.90", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "-0.20", "32.10", "4.12亿"],
                ]
            elif "3分钟涨幅" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:37:00-2026-05-26 09:40:00", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "2.30", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "0.80", "32.10", "4.12亿"],
                ]
            elif "10分钟涨幅" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:30:00-2026-05-26 09:40:00", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "5.20", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "2.90", "32.10", "4.12亿"],
                ]
            elif "封单" in query or "首次涨停" in query:
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

    def minute(self, code: str, end_day: str, limit: int) -> dict:
        return {
            "code": 0,
            "cnt": 1,
            "msg": "",
            "data": {
                "code": code,
                "start": "2026-05-26",
                "end": "2026-05-26",
                "count": 1,
                "days": ["2026-05-26"],
                "fields": ["时间", "最新价", "均价", "成交量"],
                "list": [
                    {
                        "date": "2026-05-26",
                        "last_price": 16.92,
                        "list": [
                            ["09:30", 17.30, 17.30, 100000],
                            ["09:31", 17.70, 17.50, 150000],
                            ["09:32", 17.82, 17.62, 160000],
                            ["09:33", 18.00, 17.75, 170000],
                            ["09:34", 18.18, 17.91, 190000],
                            ["09:35", 18.61, 18.05, 230000],
                        ],
                    }
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


def test_jvquant_minute_replay_snapshot_from_fake_client() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    snapshot = adapter.get_stock_minute_replay_snapshot("001366.SZ", end_day="2026-05-26", limit_days=1)

    assert snapshot.data_mode == "minute_replay"
    assert snapshot.provider == "jvQuant"
    assert snapshot.trading_day == "2026-05-26"
    assert snapshot.timestamp == "2026-05-26T09:35:00+08:00"
    assert snapshot.minute_count == 6
    assert snapshot.speed_pct_by_window["1m"] == 2.3652
    assert snapshot.speed_pct_by_window["5m"] == 7.5723
    assert snapshot.speed_window_by_window["5m"] == (
        "minute_replay_exact_window:2026-05-26 09:30:00-2026-05-26 09:35:00"
    )


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


def test_jvquant_second_board_candidates_use_minute_replay_when_available() -> None:
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    candidates = adapter.get_second_board_candidates()
    explanation = adapter.explain_second_board_candidate(candidates[0].symbol)

    assert candidates
    assert candidates[0].symbol == "001366"
    assert candidates[0].data_mode == "live_provider"
    assert candidates[0].provider == "jvQuant"
    assert candidates[0].current_change_pct == 9.99
    assert candidates[0].auction_change_pct == 3.20
    assert candidates[0].auction_turnover_cny == 92_000_000
    assert candidates[0].auction_turnover_rate == 1.80
    assert candidates[0].five_min_speed_pct == 7.5723
    assert candidates[0].five_min_speed_window == "minute_replay_exact_window:2026-05-26 09:30:00-2026-05-26 09:35:00"
    assert candidates[0].five_min_speed_timestamp == "2026-05-26T09:35:00+08:00"
    assert candidates[0].minute_replay_trading_day == "2026-05-26"
    assert candidates[0].minute_replay_bar_count == 6
    assert candidates[0].one_min_speed_pct == 2.3652
    assert candidates[0].three_min_speed_pct == 4.4332
    assert candidates[0].ten_min_speed_pct == 7.5723
    assert candidates[0].big_order_net_inflow_ratio > 0
    assert candidates[0].concept_tags == ["饲料", "乡村振兴"]
    assert candidates[0].topic_tags == ["农业涨价"]
    assert candidates[0].break_board_count == 0
    assert candidates[0].reseal_count == 0
    assert candidates[0].final_seal_time == "09:42:18"
    assert candidates[0].max_seal_amount_cny == 128_000_000
    assert candidates[0].data_quality["five_min_speed"].source == "jvquant.minute_replay"
    assert candidates[0].data_quality["five_min_speed"].confidence == "high"
    assert candidates[0].data_quality["auction_metrics"].usable_for_grading is True
    assert candidates[0].data_quality["theme_tags"].usable_for_grading is True
    assert candidates[0].data_quality["break_reseal_metrics"].usable_for_grading is True
    assert candidates[0].data_quality["multi_speed"].usable_for_grading is True
    assert {item.authority for item in candidates[0].data_quality["five_min_speed"].evidence} == {
        "official_doc",
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


def test_jvquant_second_board_candidates_can_fallback_to_semantic_speed(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_ALPHA_ENABLE_MINUTE_REPLAY", "false")
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    candidates = adapter.get_second_board_candidates()

    assert candidates[0].five_min_speed_pct == 2.10
    assert candidates[0].five_min_speed_window == "provider_exact_window:2026-05-26 09:35:00-2026-05-26 09:40:00"
    assert candidates[0].five_min_speed_timestamp == "2026-05-26T09:40:00+08:00"
    assert candidates[0].data_quality["five_min_speed"].source == "jvquant.semantic_query"
    assert {item.authority for item in candidates[0].data_quality["five_min_speed"].evidence} == {
        "official_doc",
        "observed_probe",
        "internal_inference",
    }
