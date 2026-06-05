"""TDD tests for jvquant adapter resolver wiring fixes.

Fix 1+2: Wire ladder + theme-leader resolvers into get_second_board_candidates
Fix 3: Fill emotion fields on get_market_sentiment_gate
Fix 4: Rewrite get_market_emotion to be honest (no circular call to get_second_board_candidates)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
from aegis_alpha.models import LadderEntry, LimitUpStock, MarketEmotion, ThemeLeader


# ---------------------------------------------------------------------------
# Shared fake client (reuses field shapes from test_jvquant_adapter.py)
# ---------------------------------------------------------------------------

def _multi_board_payload(query: str) -> dict:
    if "概念" in query or "题材" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "成交额", "是否ST", "涨停", "概念", "个股题材", "行业", "最新价"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "2.66亿", "否", "涨停", "饲料、乡村振兴", "农业涨价", "饲料", "18.61"],
            ["002001", "新和成", "10.00", "3", "4.12亿", "否", "涨停", "合成生物、维生素", "医药上游", "合成生物", "32.10"],
        ]
    elif "炸板次数" in query or "回封次数" in query or "最后封板" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "涨停最终封板时间", "炸板次数(次)", "涨停回封次数(次)", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "09:42:18", "0", "0", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "10:42:08", "1", "1", "32.10", "4.12亿"],
        ]
    elif "1分钟涨幅" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:39:00-2026-05-26 09:40:00", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "0.90", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "-0.20", "32.10", "4.12亿"],
        ]
    elif "3分钟涨幅" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:37:00-2026-05-26 09:40:00", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "2.30", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "0.80", "32.10", "4.12亿"],
        ]
    elif "10分钟涨幅" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:30:00-2026-05-26 09:40:00", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "5.20", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "2.90", "32.10", "4.12亿"],
        ]
    elif "最大封单" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "最大封单金额", "最大封单量", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "1.28亿", "688.00万", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "4200.00万", "230.00万", "32.10", "4.12亿"],
        ]
    elif "封单" in query or "首次涨停" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "涨停首次封板时间", "涨停封单额", "涨停封单量(股)", "涨停封成比", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "09:42:18", "1.28亿", "688.00万", "1.65", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "10:22:31", "4200.00万", "230.00万", "0.82", "32.10", "4.12亿"],
        ]
    elif "资金" in query or "5分钟" in query:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "区间涨跌幅(1分钟)@2026-05-26 09:35:00-2026-05-26 09:40:00", "主力净额", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "2.10", "3000.00万", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "0.80", "-500.00万", "32.10", "4.12亿"],
        ]
    else:
        fields = ["代码", "名称", "涨跌幅", "连板(天)", "行业", "是否ST", "涨停", "最新价", "成交额"]
        rows = [
            ["001366", "播恩集团", "9.99", "2", "饲料", "否", "涨停", "18.61", "2.66亿"],
            ["002001", "新和成", "10.00", "3", "合成生物", "否", "涨停", "32.10", "4.12亿"],
        ]
    return {"code": 0, "message": "", "data": {"count": len(rows), "fields": fields, "list": rows}}


class FakeJvQuantClient:
    """Minimal fake producing 2-row candidate results."""

    def query(self, query: str, page: int, sort_type: int, sort_key: str) -> dict:  # noqa: ARG002
        if "连板数大于1" in query:
            return _multi_board_payload(query)
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
# Fix 4: get_market_emotion must not call get_second_board_candidates
# ---------------------------------------------------------------------------

def test_get_market_emotion_does_not_call_get_second_board_candidates() -> None:
    """After Fix 4, get_market_emotion must not trigger get_second_board_candidates."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    call_log: list[str] = []
    original_get_second_board_candidates = adapter.get_second_board_candidates

    def spy_get_second_board_candidates():
        call_log.append("get_second_board_candidates called!")
        return original_get_second_board_candidates()

    with patch.object(adapter, "get_second_board_candidates", side_effect=spy_get_second_board_candidates):
        with patch.object(adapter, "get_limitup_pool") as mock_pool, \
             patch.object(adapter, "get_limit_up_ladder") as mock_ladder:
            mock_pool.return_value = [
                LimitUpStock(
                    symbol="001366", name="播恩集团",
                    data_mode="live_provider", provider="jvQuant",
                    theme="饲料", first_limit_up_time="09:42:18",
                    seal_amount_cny=128_000_000, free_float_market_cap_cny=0.0,
                    seal_amount_ratio=1.65, reopen_count=0, status="sealed",
                ),
                LimitUpStock(
                    symbol="002001", name="新和成",
                    data_mode="live_provider", provider="jvQuant",
                    theme="合成生物", first_limit_up_time="10:22:31",
                    seal_amount_cny=42_000_000, free_float_market_cap_cny=0.0,
                    seal_amount_ratio=0.82, reopen_count=0, status="sealed",
                ),
            ]
            mock_ladder.return_value = LadderEntry(
                symbol="001366", trading_day="2026-05-30",
                consecutive_boards=2, height_label="second_board",
            )
            emotion = adapter.get_market_emotion("2026-05-30")

    assert call_log == [], "get_second_board_candidates must NOT be called from get_market_emotion"
    assert isinstance(emotion, MarketEmotion)
    assert emotion.trading_day == "2026-05-30"


def test_get_market_emotion_computes_max_height_from_ladder() -> None:
    """max_height_today should come from get_limit_up_ladder consecutive_boards."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    def fake_pool():
        return [
            LimitUpStock(
                symbol="001366", name="播恩集团",
                data_mode="live_provider", provider="jvQuant",
                theme="饲料", first_limit_up_time="09:42:18",
                seal_amount_cny=0.0, free_float_market_cap_cny=0.0,
                seal_amount_ratio=0.0, reopen_count=0, status="sealed",
            ),
            LimitUpStock(
                symbol="002001", name="新和成",
                data_mode="live_provider", provider="jvQuant",
                theme="合成生物", first_limit_up_time="10:22:31",
                seal_amount_cny=0.0, free_float_market_cap_cny=0.0,
                seal_amount_ratio=0.0, reopen_count=0, status="sealed",
            ),
        ]

    ladder_data = {
        "001366": LadderEntry(symbol="001366", trading_day="2026-05-30", consecutive_boards=3, height_label="third_board"),
        "002001": LadderEntry(symbol="002001", trading_day="2026-05-30", consecutive_boards=2, height_label="second_board"),
    }

    with patch.object(adapter, "get_limitup_pool", side_effect=fake_pool), \
         patch.object(adapter, "get_limit_up_ladder", side_effect=lambda sym, day="": ladder_data.get(sym, LadderEntry(symbol=sym, trading_day=day or "2026-05-30", consecutive_boards=1, height_label="first_board"))):
        emotion = adapter.get_market_emotion("2026-05-30")

    assert emotion.max_height_today == 3


def test_get_market_emotion_returns_zeros_for_unimplemented_fields() -> None:
    """Fields requiring historical data must be 0/0.0 and notes must explain why."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    with patch.object(adapter, "get_limitup_pool", return_value=[]), \
         patch.object(adapter, "get_limit_up_ladder", return_value=LadderEntry(symbol="x", trading_day="2026-05-30", consecutive_boards=1, height_label="first_board")):
        emotion = adapter.get_market_emotion("2026-05-30")

    assert emotion.yesterday_limitup_today_premium_pct == 0.0
    assert emotion.yesterday_consecutive_boards_alive_count == 0
    assert emotion.yesterday_consecutive_boards_total == 0
    assert emotion.yesterday_consecutive_boards_alive_rate == 0.0
    assert emotion.first_to_second_promotion_rate == 0.0
    assert emotion.second_to_third_promotion_rate == 0.0
    assert any("not implemented" in note.lower() for note in emotion.notes)


# ---------------------------------------------------------------------------
# Fix 3: get_market_sentiment_gate fills emotion fields
# ---------------------------------------------------------------------------

def test_get_market_sentiment_gate_fills_emotion_fields() -> None:
    """After Fix 3, MarketSentimentGate should have emotion fields populated."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    fake_emotion = MarketEmotion(
        trading_day="2026-05-30",
        yesterday_limitup_today_premium_pct=2.5,
        yesterday_consecutive_boards_alive_count=5,
        yesterday_consecutive_boards_total=8,
        yesterday_consecutive_boards_alive_rate=0.625,
        first_to_second_promotion_rate=0.20,
        second_to_third_promotion_rate=0.15,
        first_board_to_consecutive_ratio=3.0,
        max_height_today=3,
        notes=["test"],
    )

    with patch.object(adapter, "get_market_emotion", return_value=fake_emotion):
        gate = adapter.get_market_sentiment_gate()

    assert gate.yesterday_limitup_today_premium_pct == 2.5
    assert gate.consecutive_boards_alive_rate == 0.625
    assert gate.first_to_second_promotion_rate == 0.20
    assert gate.second_to_third_promotion_rate == 0.15
    assert gate.max_height_today == 3


# ---------------------------------------------------------------------------
# Fix 1+2: Candidates get previous_consecutive_boards from ladder resolver
#           and theme_role from theme_leader resolver
# ---------------------------------------------------------------------------

def test_second_board_candidates_use_ladder_for_previous_consecutive_boards() -> None:
    """Candidates should use real ladder data instead of hardcoded 1."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    ladder_map = {
        "001366": LadderEntry(
            symbol="001366", trading_day="2026-05-30",
            consecutive_boards=2, height_label="second_board",
        ),
        "002001": LadderEntry(
            symbol="002001", trading_day="2026-05-30",
            consecutive_boards=1, height_label="first_board",
        ),
    }

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return ladder_map.get(symbol, LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=0, height_label="unknown",
        ))

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=[]):
        candidates = adapter.get_second_board_candidates()

    # 001366 should have consecutive_boards=2 from ladder
    c = next((c for c in candidates if c.symbol == "001366"), None)
    assert c is not None
    assert c.previous_consecutive_boards == 2
    assert c.previous_height_label == "second_board"


def test_second_board_candidates_use_theme_leader_for_theme_role() -> None:
    """Candidates should derive theme_role from ThemeLeaderResolver output."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    # 001366 is in "饲料" theme; make it the leader
    fake_leaders = [
        ThemeLeader(
            theme="饲料",
            trading_day="2026-05-30",
            leader_symbol="001366",
            leader_name="播恩集团",
            leader_consecutive_boards=2,
            leader_first_limit_up_time="09:42:18",
            leader_seal_amount_cny=128_000_000,
            leader_status="sealed",
            co_leader_symbols=[],
            member_count=1,
        ),
    ]

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=1, height_label="first_board",
        )

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=fake_leaders):
        candidates = adapter.get_second_board_candidates()

    c = next((c for c in candidates if c.symbol == "001366"), None)
    assert c is not None
    assert c.theme_role == "leader"
    assert c.theme_leader_symbol == "001366"


def test_second_board_candidate_theme_role_follower_when_not_leader() -> None:
    """Symbol in a theme but not the leader should get theme_role='follower'."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    # 001366 is in "饲料", but the leader is someone else
    fake_leaders = [
        ThemeLeader(
            theme="饲料",
            trading_day="2026-05-30",
            leader_symbol="999999",
            leader_name="虚构龙头",
            leader_consecutive_boards=3,
            leader_first_limit_up_time="09:30:00",
            leader_seal_amount_cny=500_000_000,
            leader_status="sealed",
            co_leader_symbols=[],
            member_count=2,
        ),
    ]

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=1, height_label="first_board",
        )

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=fake_leaders):
        candidates = adapter.get_second_board_candidates()

    c = next((c for c in candidates if c.symbol == "001366"), None)
    assert c is not None
    assert c.theme_role == "follower"
    assert c.theme_leader_symbol == "999999"


def test_second_board_candidate_theme_role_unknown_when_no_leader() -> None:
    """When no theme leader exists for the candidate's theme, theme_role should be 'unknown'."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=0, height_label="unknown",
        )

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=[]):
        candidates = adapter.get_second_board_candidates()

    for c in candidates:
        assert c.theme_role == "unknown"
        assert c.theme_leader_symbol == ""


def test_second_board_candidate_co_leader_theme_role() -> None:
    """Symbol in co_leader_symbols should get theme_role='co_leader'."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    fake_leaders = [
        ThemeLeader(
            theme="饲料",
            trading_day="2026-05-30",
            leader_symbol="999999",
            leader_name="虚构龙头",
            leader_consecutive_boards=3,
            leader_first_limit_up_time="09:30:00",
            leader_seal_amount_cny=500_000_000,
            leader_status="sealed",
            co_leader_symbols=["001366"],
            member_count=3,
        ),
    ]

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=1, height_label="first_board",
        )

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=fake_leaders):
        candidates = adapter.get_second_board_candidates()

    c = next((c for c in candidates if c.symbol == "001366"), None)
    assert c is not None
    assert c.theme_role == "co_leader"
    assert c.theme_leader_symbol == "999999"


# ---------------------------------------------------------------------------
# Fix 4 non-recursion: get_market_emotion -> get_limitup_pool is fine
#                      but get_market_emotion -> get_second_board_candidates forbidden
# ---------------------------------------------------------------------------

def test_no_circular_call_chain_in_get_market_sentiment_gate() -> None:
    """get_market_sentiment_gate calls get_market_emotion which must not call get_second_board_candidates."""
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    call_log: list[str] = []
    original_second_board = adapter.get_second_board_candidates

    def spy_second_board():
        call_log.append("called_from_sentinel")
        return original_second_board()

    with patch.object(adapter, "get_second_board_candidates", side_effect=spy_second_board), \
         patch.object(adapter, "get_limitup_pool", return_value=[]), \
         patch.object(adapter, "get_limit_up_ladder", return_value=LadderEntry(
             symbol="x", trading_day="2026-05-30", consecutive_boards=1, height_label="first_board"
         )):
        # Calling get_market_sentiment_gate should NOT trigger get_second_board_candidates
        adapter.get_market_sentiment_gate()

    assert "called_from_sentinel" not in call_log, (
        "get_market_sentiment_gate -> get_market_emotion must not call get_second_board_candidates"
    )
