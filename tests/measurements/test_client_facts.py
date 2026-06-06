from aegis_alpha.measurements.client_facts import (
    avg_turnover_10d,
    ma5_slope_degrees,
    prev_day_volume_shrink_ratio,
    broke_previous_high,
)


def test_avg_turnover_10d_uses_last_ten():
    daily = [float(i) for i in range(1, 13)]  # 1..12
    assert avg_turnover_10d(daily) == sum(range(3, 13)) / 10  # last 10 = 3..12


def test_avg_turnover_10d_short_series():
    assert avg_turnover_10d([10.0, 20.0]) == 15.0


def test_avg_turnover_10d_empty_is_zero():
    assert avg_turnover_10d([]) == 0.0


def test_ma5_slope_flat_is_zero():
    assert ma5_slope_degrees([5.0] * 6) == 0.0


def test_ma5_slope_rising_positive():
    assert ma5_slope_degrees([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]) > 0.0


def test_ma5_slope_short_series_is_zero():
    assert ma5_slope_degrees([1.0, 2.0]) == 0.0


def test_prev_day_volume_shrink_ratio():
    assert prev_day_volume_shrink_ratio(prev_day_volume=30.0, avg_10d=60.0) == 0.5


def test_prev_day_volume_shrink_ratio_zero_avg():
    assert prev_day_volume_shrink_ratio(prev_day_volume=30.0, avg_10d=0.0) == 0.0


def test_broke_previous_high_true():
    assert broke_previous_high(current_price=11.0, prior_highs=[10.0, 10.5]) is True


def test_broke_previous_high_false():
    assert broke_previous_high(current_price=10.0, prior_highs=[10.5]) is False


def test_broke_previous_high_empty():
    assert broke_previous_high(current_price=10.0, prior_highs=[]) is False
