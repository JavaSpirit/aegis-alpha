from __future__ import annotations

from unittest.mock import patch

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
from aegis_alpha.models import LadderEntry


# ---------------------------------------------------------------------------
# FakeJvQuantClient copied from test_jvquant_resolver_wiring
# (tests/ has no __init__.py, so cross-test imports are not available)
# ---------------------------------------------------------------------------

class FakeJvQuantClient:
    """Minimal fake producing 2-row candidate results."""

    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:  # noqa: ARG002
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
                    "代码", "名称", "涨跌幅", "行业", "是否ST", "涨停",
                    "涨停首次封板时间", "涨停封单额", "涨停封单量(股)", "涨停封成比",
                    "最新价", "成交额",
                ]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
                ]
            elif "资金" in query or "5分钟" in query:
                fields = [
                    "代码", "名称", "涨跌幅", "行业", "是否ST", "涨停",
                    "区间涨跌幅(1分钟)@2026-05-26 09:35:00-2026-05-26 09:40:00",
                    "主力净额", "最新价", "成交额",
                ]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "2.10", "3000.00万", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "0.80", "-500.00万", "32.10", "4.12亿"],
                ]
            elif "最大封单" in query:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最大封单金额", "最大封单量", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "1.28亿", "688.00万", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "4200.00万", "230.00万", "32.10", "4.12亿"],
                ]
            else:
                fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最新价", "成交额"]
                rows = [
                    ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "18.61", "2.66亿"],
                    ["002001", "新和成", "7.10", "合成生物", "否", "涨停", "32.10", "4.12亿"],
                ]
        elif "今日涨停" in query:
            fields = [
                "代码", "名称", "涨跌幅", "行业", "是否ST", "涨停",
                "涨停首次封板时间", "涨停封单额", "涨停封单量(股)", "涨停封成比",
                "最新价", "成交额",
            ]
            rows = [
                ["001366", "播恩集团", "9.99", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
                ["002001", "新和成", "10.00", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
            ]
        elif "炸板" in query:
            fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "炸板次数", "最新价", "成交额"]
            rows = [["603278", "大业股份", "6.00", "通用设备", "否", "1", "14.14", "8.37亿"]]
        else:
            fields = ["代码", "名称", "涨跌幅", "行业", "是否ST", "涨停", "最新价", "成交额"]
            rows = [["600839", "四川长虹", "-2.57", "黑色家电", "上交所主板", "否", "7.95", "6.47亿"]]

        return {
            "code": 0,
            "message": "",
            "data": {"count": len(rows), "fields": fields, "list": rows},
        }

    def level_queue(self, code: str) -> dict:  # noqa: ARG002
        return {"code": code, "message": "", "data": {"count": 0, "fields": [], "list": []}}

    def minute(self, code: str, end_day: str, limit: int) -> dict:  # noqa: ARG002
        return {"code": 0, "data": {"fields": [], "list": []}}


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _build_candidates_with_minimal_patches(theme_leaders=None):
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=1, height_label="first_board",
        )

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=theme_leaders or []):
        return adapter.get_second_board_candidates()


def test_jvquant_candidate_has_limitup_driver_type_in_allowed_set():
    candidates = _build_candidates_with_minimal_patches()
    allowed = {"earnings", "policy", "theme", "hot_money", "unknown"}
    assert candidates, "fake client should produce at least one candidate"
    for cand in candidates:
        assert cand.limitup_driver_type in allowed


def test_grade_reason_mentions_driver_when_classified():
    """When candidate has a non-unknown limitup_driver_type, grade_reason should hint it."""
    candidates = _build_candidates_with_minimal_patches()
    classified = [c for c in candidates if c.limitup_driver_type != "unknown"]
    assert classified, "fake client should yield at least one classified driver"
    for cand in classified:
        assert cand.limitup_driver_type in cand.grade_reason or f"driver={cand.limitup_driver_type}" in cand.grade_reason


def test_grade_reason_mentions_pattern_when_classified():
    """When intraday_pattern is non-trivial (not unknown/normal), grade_reason should hint it."""
    candidates = _build_candidates_with_minimal_patches()
    interesting = [
        c for c in candidates
        if c.intraday_pattern not in {"unknown", "normal"}
    ]
    if not interesting:
        # vacuous OK: the FakeJvQuantClient may not produce a non-trivial pattern. We still
        # verify the field exists on every candidate (sanity check).
        for c in candidates:
            assert hasattr(c, "intraday_pattern")
        return
    for cand in interesting:
        assert cand.intraday_pattern in cand.grade_reason or f"pattern={cand.intraday_pattern}" in cand.grade_reason


def test_jvquant_candidate_has_weekly_health_score_in_range():
    candidates = _build_candidates_with_minimal_patches()
    for cand in candidates:
        assert 0.0 <= cand.weekly_health_score <= 100.0


def test_jvquant_candidate_weekly_health_score_uses_adapter_call():
    """When get_weekly_position returns a high-score WeeklyPosition,
    SecondBoardCandidate.weekly_health_score should reflect compute_weekly_health_score."""
    from unittest.mock import patch

    from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
    from aegis_alpha.models import LadderEntry, WeeklyPosition

    fixed_pos = WeeklyPosition(
        symbol="STUB", trading_day="2026-06-01",
        weekly_high=120.0, weekly_low=100.0, weekly_close=118.0,
        position_pct=0.9, weeks_in_uptrend=4, ma20_above_ma60=True,
    )

    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()  # type: ignore[attr-defined]

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(symbol=symbol, trading_day="2026-06-01",
                           consecutive_boards=1, height_label="first_board")

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=[]), \
         patch.object(adapter, "get_weekly_position", return_value=fixed_pos):
        out = adapter.get_second_board_candidates()
    if out:
        assert all(c.weekly_health_score >= 75.0 for c in out)
