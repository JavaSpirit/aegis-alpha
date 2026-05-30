from __future__ import annotations

from aegis_alpha.models import LadderEntry, LimitUpStock
from aegis_alpha.themes.leader import ThemeLeaderResolver


def test_theme_leader_prefers_higher_ladder_then_seal_amount() -> None:
    stocks = [
        LimitUpStock(symbol="600001", name="跟随", theme="机器人", first_limit_up_time="09:35:00", seal_amount_cny=200_000_000, free_float_market_cap_cny=0, seal_amount_ratio=0, reopen_count=0, status="sealed"),
        LimitUpStock(symbol="600002", name="龙头", theme="机器人", first_limit_up_time="10:00:00", seal_amount_cny=100_000_000, free_float_market_cap_cny=0, seal_amount_ratio=0, reopen_count=0, status="sealed"),
    ]
    ladder = {
        "600001": LadderEntry(symbol="600001", trading_day="2026-05-29", consecutive_boards=1, height_label="first_board"),
        "600002": LadderEntry(symbol="600002", trading_day="2026-05-29", consecutive_boards=3, height_label="third_board"),
    }

    leaders = ThemeLeaderResolver().resolve(stocks, ladder, trading_day="2026-05-29")

    assert leaders[0].leader_symbol == "600002"
    assert leaders[0].member_count == 2
