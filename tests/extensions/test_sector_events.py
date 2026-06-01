from aegis_alpha.models import ThemeLeader
from aegis_alpha.extensions.sector_events import (
    LeaderBreakInputs,
    SectorRotationInputs,
    detect_theme_leader_break_board,
    detect_sector_rotation,
)


def _leader(symbol="600519", theme="AI", consecutive=3, status="sealed", co=None):
    return ThemeLeader(
        theme=theme,
        trading_day="2026-06-01",
        leader_symbol=symbol,
        leader_name=f"L-{symbol}",
        leader_consecutive_boards=consecutive,
        leader_first_limit_up_time="09:32:00",
        leader_seal_amount_cny=300_000_000.0,
        leader_status=status,
        co_leader_symbols=co or [],
        member_count=4,
    )


def test_break_board_event_when_high_height_leader_breaks():
    leader = _leader(consecutive=3, status="broken")
    inputs = LeaderBreakInputs(
        leaders=[leader],
        trading_day="2026-06-01",
        min_consecutive_boards=2,
    )
    events = detect_theme_leader_break_board(inputs)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "THEME_LEADER_BREAK_BOARD"
    assert ev.symbol == "600519"
    assert ev.theme == "AI"
    assert ev.score >= 60
    assert any("consecutive=3" in e for e in ev.evidence)


def test_break_board_event_skipped_when_below_height_threshold():
    leader = _leader(consecutive=1, status="broken")
    inputs = LeaderBreakInputs(
        leaders=[leader],
        trading_day="2026-06-01",
        min_consecutive_boards=2,
    )
    events = detect_theme_leader_break_board(inputs)
    assert events == []


def test_break_board_event_skipped_when_leader_still_sealed():
    leader = _leader(consecutive=4, status="sealed")
    inputs = LeaderBreakInputs(
        leaders=[leader],
        trading_day="2026-06-01",
        min_consecutive_boards=2,
    )
    events = detect_theme_leader_break_board(inputs)
    assert events == []


def _strong_leader(theme="AI", member_count=5):
    return ThemeLeader(
        theme=theme,
        trading_day="2026-06-01",
        leader_symbol=f"L-{theme}",
        leader_name=theme,
        leader_consecutive_boards=2,
        leader_first_limit_up_time="09:31:00",
        leader_seal_amount_cny=200_000_000.0,
        leader_status="sealed",
        co_leader_symbols=[],
        member_count=member_count,
    )


def _weak_leader(theme="军工"):
    return ThemeLeader(
        theme=theme,
        trading_day="2026-06-01",
        leader_symbol=f"L-{theme}",
        leader_name=theme,
        leader_consecutive_boards=3,
        leader_first_limit_up_time="09:30:30",
        leader_seal_amount_cny=120_000_000.0,
        leader_status="broken",
        co_leader_symbols=[],
        member_count=2,
    )


def test_sector_rotation_event_when_one_breaks_and_other_strengthens():
    inputs = SectorRotationInputs(
        leaders=[_weak_leader("军工"), _strong_leader("AI", member_count=5)],
        trading_day="2026-06-01",
        min_strengthening_alive=3,
    )
    events = detect_sector_rotation(inputs)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "SECTOR_ROTATION"
    assert ev.theme == "AI"
    assert ev.data["weakening_theme"] == "军工"
    assert ev.data["strengthening_theme"] == "AI"
    assert ev.score >= 65


def test_sector_rotation_event_skipped_when_no_strong_leader():
    inputs = SectorRotationInputs(
        leaders=[_weak_leader("军工"), _strong_leader("AI", member_count=2)],
        trading_day="2026-06-01",
        min_strengthening_alive=3,
    )
    events = detect_sector_rotation(inputs)
    assert events == []


def test_sector_rotation_event_skipped_when_no_weak_leader():
    inputs = SectorRotationInputs(
        leaders=[_strong_leader("AI", member_count=5)],
        trading_day="2026-06-01",
        min_strengthening_alive=3,
    )
    events = detect_sector_rotation(inputs)
    assert events == []
