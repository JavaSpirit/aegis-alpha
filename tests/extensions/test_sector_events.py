from aegis_alpha.models import ThemeLeader
from aegis_alpha.extensions.sector_events import (
    LeaderBreakInputs,
    detect_theme_leader_break_board,
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
