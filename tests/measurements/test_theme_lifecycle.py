from aegis_alpha.measurements.theme_lifecycle import ThemeDay, classify_theme_lifecycle


def d(lu, bbr, nh, alive):
    return ThemeDay(limit_up_count=lu, break_board_rate=bbr,
                    new_high_member_count=nh, leader_alive=alive)


def test_insufficient_is_unknown():
    assert classify_theme_lifecycle([]) == "unknown"
    assert classify_theme_lifecycle([d(3, 0.1, 1, True)]) == "unknown"
    assert classify_theme_lifecycle([d(3, 0.1, 1, True), d(4, 0.1, 2, True)]) == "unknown"


def test_launch():
    assert classify_theme_lifecycle([d(1, 0.1, 0, True), d(2, 0.1, 1, True), d(4, 0.05, 2, True)]) == "launch"


def test_fermenting():
    assert classify_theme_lifecycle([d(3, 0.1, 1, True), d(5, 0.1, 3, True), d(7, 0.1, 4, True)]) == "fermenting"


def test_climax():
    assert classify_theme_lifecycle([d(5, 0.1, 3, True), d(8, 0.1, 5, True), d(12, 0.1, 9, True)]) == "climax"


def test_divergence():
    assert classify_theme_lifecycle([d(12, 0.1, 9, True), d(11, 0.3, 6, True), d(9, 0.5, 4, True)]) == "divergence"


def test_ebb():
    assert classify_theme_lifecycle([d(9, 0.4, 4, True), d(5, 0.5, 2, False), d(2, 0.6, 0, False)]) == "ebb"


def test_launch_with_high_break_rate_is_not_launch():
    # counts rise from low base (1→2→4) but break_board_rate is high throughout —
    # the launch break-rate guard (_LAUNCH_MAX_BREAK_RATE=0.3) should block the
    # launch branch; the series falls through to fermenting (4>2>1, strictly rising).
    assert classify_theme_lifecycle([d(1, 0.6, 0, True), d(2, 0.7, 1, True), d(4, 0.8, 2, True)]) == "fermenting"


def test_peak_with_linear_nh_is_not_climax():
    # Counts [5,8,12] reach their series peak but new-high membership grows
    # linearly [3,6,9] (delta constant at 3) — nh_accel is False (3 > 3 is False),
    # so the climax guard does NOT fire; result is fermenting (12>8>5).
    # This test locks the nh_accel guard: removing it would cause this to return "climax".
    assert classify_theme_lifecycle([d(5, 0.1, 3, True), d(8, 0.1, 6, True), d(12, 0.1, 9, True)]) == "fermenting"
