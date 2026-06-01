from aegis_alpha.extensions.similar_setups import (
    SetupVector,
    cosine_similarity,
    vectorize_setup,
)


def test_vectorize_setup_produces_5_dim_vector():
    payload = {
        "previous_consecutive_boards": 2,
        "same_theme_rising_count": 5,
        "seal_amount_cny": 200_000_000.0,
        "five_min_speed_pct": 3.5,
        "auction_change_pct": 1.2,
    }
    vec = vectorize_setup(payload)
    assert isinstance(vec, SetupVector)
    assert len(vec.values) == 5
    assert all(isinstance(v, float) for v in vec.values)


def test_cosine_similarity_identical_returns_one():
    payload = {
        "previous_consecutive_boards": 2,
        "same_theme_rising_count": 5,
        "seal_amount_cny": 200_000_000.0,
        "five_min_speed_pct": 3.5,
        "auction_change_pct": 1.2,
    }
    a = vectorize_setup(payload)
    b = vectorize_setup(payload)
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_returns_zero():
    a = SetupVector(values=[1.0, 0.0, 0.0, 0.0, 0.0])
    b = SetupVector(values=[0.0, 1.0, 0.0, 0.0, 0.0])
    assert abs(cosine_similarity(a, b) - 0.0) < 1e-9


def test_cosine_similarity_zero_vector_returns_zero():
    a = SetupVector(values=[0.0, 0.0, 0.0, 0.0, 0.0])
    b = SetupVector(values=[1.0, 1.0, 1.0, 1.0, 1.0])
    assert cosine_similarity(a, b) == 0.0


def test_vectorize_setup_handles_missing_fields_with_zeros():
    vec = vectorize_setup({})
    assert vec.values == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_find_similar_setups_filters_by_threshold(tmp_path):
    """find_similar_setups_in_snapshots filters by threshold and sorts desc."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.extensions.similar_setups import (
        find_similar_setups_in_snapshots,
        SetupVector,
        vectorize_setup,
    )

    query = vectorize_setup(
        {
            "previous_consecutive_boards": 2,
            "same_theme_rising_count": 6,
            "seal_amount_cny": 200_000_000.0,
            "five_min_speed_pct": 4.0,
            "auction_change_pct": 1.0,
        }
    )

    snaps = [
        HistoricalCandidateSnapshot(
            symbol="A", trading_day="2025-11-12", grade_at_pick="A",
            grade_reason="", theme="X", theme_role="leader",
            previous_consecutive_boards=2,
            payload_json=(
                '{"previous_consecutive_boards": 2,'
                ' "same_theme_rising_count": 6,'
                ' "seal_amount_cny": 200000000.0,'
                ' "five_min_speed_pct": 4.0,'
                ' "auction_change_pct": 1.0}'
            ),
            created_at="t",
        ),
        HistoricalCandidateSnapshot(
            symbol="B", trading_day="2025-11-13", grade_at_pick="C",
            grade_reason="", theme="X", theme_role="follower",
            previous_consecutive_boards=0,
            payload_json='{"previous_consecutive_boards": 0}',
            created_at="t",
        ),
    ]

    results = find_similar_setups_in_snapshots(
        query_symbol="QUERY",
        query_vector=query,
        snapshots=snaps,
        similarity_threshold=0.9,
        limit=10,
    )
    symbols = [r.match_symbol for r in results]
    assert symbols == ["A"]
    assert results[0].similarity >= 0.99
    assert results[0].match_grade_at_pick == "A"


def test_mock_adapter_find_similar_setups_returns_list():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    out = adapter.find_similar_setups("600519", lookback_days=30, similarity_threshold=0.5)
    assert isinstance(out, list)
    for item in out:
        assert item.query_symbol == "600519"
        assert 0.0 <= item.similarity <= 1.0
