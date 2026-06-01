from aegis_alpha.models import NewStockCandidate


def test_new_stock_candidate_model_construct():
    cand = NewStockCandidate(
        symbol="688001",
        name="mock-次新-1",
        listing_date="2026-04-15",
        days_since_listing=47,
        free_float_market_cap_cny=2_500_000_000.0,
        current_change_pct=8.4,
        notes=["mock 次新"],
    )
    assert cand.days_since_listing == 47
    assert cand.free_float_market_cap_cny == 2_500_000_000.0


def test_classify_new_stock_tier_smallcap_recent():
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    tier = classify_new_stock_tier(days_since_listing=20, free_float_cny=500_000_000)
    assert tier == "tier_a_smallcap_recent"


def test_classify_new_stock_tier_largecap():
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    tier = classify_new_stock_tier(days_since_listing=60, free_float_cny=10_000_000_000.0)
    assert tier == "tier_c_largecap"


def test_classify_new_stock_tier_aged_out():
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    tier = classify_new_stock_tier(days_since_listing=200, free_float_cny=2_000_000_000.0)
    assert tier == "tier_aged_out"


def test_mock_adapter_get_new_stock_candidates_returns_list():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    out = adapter.get_new_stock_candidates()
    assert isinstance(out, list)
    assert all(isinstance(c, NewStockCandidate) for c in out)
    assert all(c.days_since_listing < 365 for c in out)


def test_jvquant_adapter_get_new_stock_candidates_placeholder():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    out = adapter.get_new_stock_candidates()
    assert out == []
