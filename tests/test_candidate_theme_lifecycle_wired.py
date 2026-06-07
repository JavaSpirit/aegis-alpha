from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_some_mock_theme_is_late_stage():
    stages = {c.theme_lifecycle_stage for c in MockMarketDataAdapter().get_second_board_candidates()}
    # at least one fixture resolves to a real (non-unknown) stage
    assert stages - {"unknown"}
    # the 电力-style late-stage case MUST be representable (regression)
    assert stages & {"climax", "divergence", "ebb"}


def test_mock_lifecycle_is_deterministic():
    a = [c.theme_lifecycle_stage for c in MockMarketDataAdapter().get_second_board_candidates()]
    b = [c.theme_lifecycle_stage for c in MockMarketDataAdapter().get_second_board_candidates()]
    assert a == b


def test_two_mock_themes_have_distinct_stages():
    cands = MockMarketDataAdapter().get_second_board_candidates()
    assert len({c.theme_lifecycle_stage for c in cands}) >= 2
