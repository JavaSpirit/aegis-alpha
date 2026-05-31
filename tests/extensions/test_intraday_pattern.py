from aegis_alpha.extensions.intraday_pattern import (
    PatternInputs,
    classify_intraday_pattern,
)


def _bars(values):
    """values is a list of (minutes_since_open, change_pct_at_close, is_at_limit)."""
    return [
        {"minute": m, "change_pct": pct, "at_limit": at_limit}
        for m, pct, at_limit in values
    ]


def test_one_word_board_when_open_at_limit_and_no_break():
    bars = _bars([
        (1, 9.95, True), (5, 9.95, True), (60, 9.95, True),
        (120, 9.95, True), (240, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=0, reseal_count=0,
            first_seal_minute=1, sealed_at_open=True, closed_at_limit=True,
        )
    )
    assert out.pattern == "one_word_board"


def test_t_shape_board_when_open_limit_break_then_reseal():
    bars = _bars([
        (1, 9.95, True), (30, 5.0, False), (90, 9.95, True), (240, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=1, reseal_count=1,
            first_seal_minute=1, sealed_at_open=True, closed_at_limit=True,
        )
    )
    assert out.pattern == "t_shape_board"


def test_messy_board_when_break_count_high():
    bars = _bars([
        (60, 7.0, False), (120, 9.95, True), (150, 5.0, False),
        (200, 9.95, True), (220, 4.0, False), (240, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=3, reseal_count=2,
            first_seal_minute=120, sealed_at_open=False, closed_at_limit=True,
        )
    )
    assert out.pattern == "messy_board"


def test_platform_breakout_when_long_consolidation_then_strong_move():
    bars = _bars([
        (5, 1.0, False), (60, 1.5, False), (120, 1.8, False),
        (180, 5.0, False), (220, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=0, reseal_count=0,
            first_seal_minute=220, sealed_at_open=False, closed_at_limit=True,
        )
    )
    assert out.pattern == "platform_breakout"


def test_false_breakout_when_touch_limit_then_close_below():
    bars = _bars([
        (60, 9.5, False), (120, 9.95, True), (130, 9.95, True),
        (180, 5.0, False), (240, 1.0, False),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=2, reseal_count=0,
            first_seal_minute=120, sealed_at_open=False, closed_at_limit=False,
        )
    )
    assert out.pattern == "false_breakout"


def test_normal_when_no_special_signal():
    out = classify_intraday_pattern(
        PatternInputs(
            bars=[], daily_limit_pct=10.0, break_count=0, reseal_count=0,
            first_seal_minute=0, sealed_at_open=False, closed_at_limit=True,
        )
    )
    assert out.pattern in {"normal", "unknown"}
