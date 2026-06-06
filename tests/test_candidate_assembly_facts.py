from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_mock_candidate_populates_client_facts():
    c = MockMarketDataAdapter().get_second_board_candidates()[0]
    assert c.avg_turnover_10d_cny > 0.0
    assert c.free_float_market_cap_cny > 0.0
    assert isinstance(c.broke_previous_high, bool)
    assert c.previous_high_price > 0.0


def test_mock_facts_are_deterministic():
    a = MockMarketDataAdapter().get_second_board_candidates()[0]
    b = MockMarketDataAdapter().get_second_board_candidates()[0]
    assert a.ma5_slope_degrees == b.ma5_slope_degrees
    assert a.avg_turnover_10d_cny == b.avg_turnover_10d_cny
    assert a.prev_day_volume_shrink_ratio == b.prev_day_volume_shrink_ratio


def test_two_mock_candidates_are_distinct_on_facts():
    cands = MockMarketDataAdapter().get_second_board_candidates()
    assert len(cands) >= 2
    # the two fixtures should differ on at least the break-prev-high fact
    assert cands[0].broke_previous_high != cands[1].broke_previous_high
