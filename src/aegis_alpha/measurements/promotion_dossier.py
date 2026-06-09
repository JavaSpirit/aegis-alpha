"""Assemble a PromotionDossier from existing measured facts.

This module contains ONE pure function: ``assemble_promotion_dossier``.
It copies fields verbatim from a ``SecondBoardCandidate`` and a
``MarketSentimentGate`` into the structured ``PromotionDossier`` bundle.

Philosophy invariants (non-negotiable):
- MEASURES facts; does NOT judge.
- Computes NOTHING new — straight field copy only.
- Never mutates inputs (Pydantic models are read-only here).
- No I/O, no network, no adapter, no randomness.
"""
from __future__ import annotations

from aegis_alpha.models import (
    FloatSizeFacts,
    MarketEmotionFacts,
    MarketSentimentGate,
    PromotionDossier,
    ResealStrengthFacts,
    SecondBoardCandidate,
    ThemePositionFacts,
    VolumeEnergyFacts,
)

__all__ = ["assemble_promotion_dossier"]


def assemble_promotion_dossier(
    candidate: SecondBoardCandidate,
    gate: MarketSentimentGate,
) -> PromotionDossier:
    """Bundle measured facts from *candidate* and *gate* into a PromotionDossier.

    This is a pure assembler: it copies fields from the two source models into
    the nested fact structs and returns a new ``PromotionDossier``.  No field
    is computed, derived, or judged here — every value is taken verbatim from
    the inputs.

    Args:
        candidate: A ``SecondBoardCandidate`` produced by the market-data adapter.
        gate: A ``MarketSentimentGate`` capturing today's market-emotion reading.

    Returns:
        A freshly constructed ``PromotionDossier``.  The disclaimer field is
        left to the model default (see ``PromotionDossier.disclaimer``).
    """
    return PromotionDossier(
        # --- identity fields from candidate ---
        symbol=candidate.symbol,
        name=candidate.name,
        data_mode=candidate.data_mode,
        provider=candidate.provider,
        # --- market emotion facts from gate ---
        market_emotion=MarketEmotionFacts(
            trading_day=gate.trading_day,
            limit_up_count=gate.limit_up_count,
            break_board_rate=gate.break_board_rate,
            second_board_success_rate=gate.second_board_success_rate,
            consecutive_boards_alive_rate=gate.consecutive_boards_alive_rate,
            first_to_second_promotion_rate=gate.first_to_second_promotion_rate,
            second_to_third_promotion_rate=gate.second_to_third_promotion_rate,
            max_height_today=gate.max_height_today,
            hot_theme_count=gate.hot_theme_count,
            conclusion=gate.conclusion,
        ),
        # --- theme position facts from candidate ---
        theme_position=ThemePositionFacts(
            theme=candidate.theme,
            theme_lifecycle_stage=candidate.theme_lifecycle_stage,
            theme_role=candidate.theme_role,
        ),
        # --- float size facts from candidate ---
        float_size=FloatSizeFacts(
            free_float_market_cap_cny=candidate.free_float_market_cap_cny,
        ),
        # --- volume energy facts from candidate ---
        volume_energy=VolumeEnergyFacts(
            turnover_cny=candidate.turnover_cny,
            avg_turnover_10d_cny=candidate.avg_turnover_10d_cny,
            prev_day_volume_shrink_ratio=candidate.prev_day_volume_shrink_ratio,
        ),
        # --- reseal strength facts from candidate ---
        reseal_strength=ResealStrengthFacts(
            break_board_count=candidate.break_board_count,
            reseal_count=candidate.reseal_count,
            max_seal_amount_cny=candidate.max_seal_amount_cny,
            final_seal_time=candidate.final_seal_time,
        ),
        # --- timestamp from gate (the market read time) ---
        data_timestamp=gate.timestamp,
        # disclaimer is intentionally left to the model default
    )
