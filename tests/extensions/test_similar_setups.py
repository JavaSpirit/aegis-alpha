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
