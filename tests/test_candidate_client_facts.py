from aegis_alpha.models import SecondBoardCandidate


def test_candidate_carries_client_strategy_facts():
    f = SecondBoardCandidate.model_fields
    for name in (
        "free_float_market_cap_cny",
        "avg_turnover_10d_cny",
        "ma5_slope_degrees",
        "prev_day_volume_shrink_ratio",
        "broke_previous_high",
        "previous_high_price",
    ):
        assert name in f, f"missing {name}"


def test_new_fact_fields_have_safe_defaults():
    f = SecondBoardCandidate.model_fields
    assert f["broke_previous_high"].default is False
    assert f["free_float_market_cap_cny"].default == 0.0
    assert f["avg_turnover_10d_cny"].default == 0.0
    assert f["ma5_slope_degrees"].default == 0.0
    assert f["prev_day_volume_shrink_ratio"].default == 0.0
    assert f["previous_high_price"].default == 0.0
