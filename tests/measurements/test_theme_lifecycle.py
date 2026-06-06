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
