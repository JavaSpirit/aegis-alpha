"""TDD guard for PromotionDossier — facts-only model, 5 factor bundles == REQUIRED_FACTORS."""
from __future__ import annotations

import aegis_alpha.agent_eval as _eval
from aegis_alpha.models import (
    FloatSizeFacts,
    MarketEmotionFacts,
    PromotionDossier,
    ResealStrengthFacts,
    ThemePositionFacts,
    VolumeEnergyFacts,
)


def _make_dossier() -> PromotionDossier:
    return PromotionDossier(
        symbol="000001",
        name="平安银行",
        data_mode="mock",
        provider="mock",
        market_emotion=MarketEmotionFacts(
            trading_day="2026-06-09",
            limit_up_count=85,
            break_board_rate=0.15,
            second_board_success_rate=0.60,
            consecutive_boards_alive_rate=0.72,
            first_to_second_promotion_rate=0.55,
            second_to_third_promotion_rate=0.30,
            max_height_today=4,
            hot_theme_count=3,
            conclusion="市场情绪偏暖",
        ),
        theme_position=ThemePositionFacts(
            theme="AI算力",
            theme_lifecycle_stage="fermenting",
            theme_role="leader",
        ),
        float_size=FloatSizeFacts(
            free_float_market_cap_cny=3_500_000_000.0,
        ),
        volume_energy=VolumeEnergyFacts(
            turnover_cny=450_000_000.0,
            avg_turnover_10d_cny=300_000_000.0,
            prev_day_volume_shrink_ratio=0.45,
        ),
        reseal_strength=ResealStrengthFacts(
            break_board_count=1,
            reseal_count=2,
            max_seal_amount_cny=800_000_000.0,
            final_seal_time="14:35",
        ),
    )


def test_dossier_constructs_and_dumps() -> None:
    dossier = _make_dossier()
    dumped = dossier.model_dump()

    # All 5 factor keys must be present
    for key in _eval.REQUIRED_FACTORS:
        assert key in dumped, f"Missing factor key: {key}"


def test_dossier_factor_keys_equal_required_factors() -> None:
    dossier = _make_dossier()
    dumped = dossier.model_dump()

    factor_keys = {k for k in dumped if k in set(_eval.REQUIRED_FACTORS)}
    assert factor_keys == set(_eval.REQUIRED_FACTORS)


def test_dossier_no_grading_or_probability_fields() -> None:
    """Philosophy guard: no program-assigned grade/probability anywhere in the dossier."""
    dossier = _make_dossier()
    dumped = dossier.model_dump()

    banned_suffixes = {"grade", "grade_reason", "probability", "promotion_likelihood", "score", "estimated_seal_probability"}

    def _recursive_keys(obj: object) -> set[str]:
        keys: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k)
                keys |= _recursive_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                keys |= _recursive_keys(item)
        return keys

    all_keys = _recursive_keys(dumped)
    found = banned_suffixes & all_keys
    assert not found, f"Banned fields found in dossier dump: {found}"
