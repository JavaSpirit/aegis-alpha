from __future__ import annotations

from aegis_alpha.models import LimitUpStock, ThemeLeader
from aegis_alpha.themes.ranking import compute_top_themes, theme_rotation_diff


def test_compute_top_themes_ranks_by_member_then_leader_height() -> None:
    leaders = [
        ThemeLeader(theme="A", trading_day="2026-05-31", leader_symbol="x", leader_name="x", leader_consecutive_boards=1, member_count=3),
        ThemeLeader(theme="B", trading_day="2026-05-31", leader_symbol="y", leader_name="y", leader_consecutive_boards=4, member_count=2),
        ThemeLeader(theme="C", trading_day="2026-05-31", leader_symbol="z", leader_name="z", leader_consecutive_boards=2, member_count=5),
    ]
    rankings = compute_top_themes(leaders, trading_day="2026-05-31", limit=3)
    assert [r.theme for r in rankings] == ["C", "A", "B"]  # member_count first
    assert rankings[0].rank == 1


def test_compute_top_themes_filters_zero_members() -> None:
    leaders = [
        ThemeLeader(theme="empty", trading_day="2026-05-31", leader_symbol="", leader_name="", member_count=0),
    ]
    rankings = compute_top_themes(leaders, trading_day="2026-05-31", limit=5)
    assert rankings == []


def test_theme_rotation_diff_finds_new_and_fading() -> None:
    today = ["A", "B", "C"]
    yesterday = ["B", "D"]
    rotation = theme_rotation_diff(today_themes=today, yesterday_themes=yesterday, trading_day="2026-05-31")
    assert rotation.new_themes == ["A", "C"]
    assert rotation.fading_themes == ["D"]
