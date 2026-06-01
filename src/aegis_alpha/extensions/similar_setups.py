from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from aegis_alpha.models import HistoricalCandidateSnapshot, SimilarSetupResult


_VECTOR_DIM = 5
# Per-axis normalization scale — chosen to keep typical values in [0, 1]
_AXIS_SCALES = (
    5.0,             # previous_consecutive_boards: 5+ 板封顶
    30.0,            # same_theme_rising_count: 30+ 封顶（板块极端火爆）
    500_000_000.0,   # seal_amount_cny: 5 亿封顶（折成 0~1）
    10.0,            # five_min_speed_pct: 10% 算极强涨速
    5.0,             # auction_change_pct: 5% 算极端高开
)


@dataclass(frozen=True)
class SetupVector:
    values: list[float]


def _safe_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def vectorize_setup(payload: dict[str, Any]) -> SetupVector:
    """Convert a candidate snapshot payload (dict) into a 5-dim normalized vector.

    Missing fields default to 0. Returned values are clipped to [0, 1] per axis.
    """
    raw = (
        _safe_float(payload.get("previous_consecutive_boards")),
        _safe_float(payload.get("same_theme_rising_count")),
        _safe_float(payload.get("seal_amount_cny")),
        _safe_float(payload.get("five_min_speed_pct")),
        _safe_float(payload.get("auction_change_pct")),
    )
    normalized = [
        max(0.0, min(1.0, raw[i] / _AXIS_SCALES[i])) for i in range(_VECTOR_DIM)
    ]
    return SetupVector(values=normalized)


def cosine_similarity(a: SetupVector, b: SetupVector) -> float:
    if len(a.values) != len(b.values):
        return 0.0
    dot = sum(x * y for x, y in zip(a.values, b.values))
    norm_a = math.sqrt(sum(x * x for x in a.values))
    norm_b = math.sqrt(sum(y * y for y in b.values))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def find_similar_setups_in_snapshots(
    *,
    query_symbol: str,
    query_vector: SetupVector,
    snapshots: list[HistoricalCandidateSnapshot],
    similarity_threshold: float = 0.7,
    limit: int = 10,
) -> list[SimilarSetupResult]:
    """Score each snapshot against the query and return matches above threshold."""
    results: list[SimilarSetupResult] = []
    for snap in snapshots:
        if snap.symbol == query_symbol:
            continue
        try:
            payload = json.loads(snap.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        snap_vector = vectorize_setup(payload)
        sim = cosine_similarity(query_vector, snap_vector)
        if sim < similarity_threshold:
            continue
        feature_diffs: dict[str, float] = {}
        for i, axis in enumerate(
            ("previous_consecutive_boards", "same_theme_rising_count",
             "seal_amount_cny", "five_min_speed_pct", "auction_change_pct")
        ):
            feature_diffs[axis] = round(
                snap_vector.values[i] - query_vector.values[i], 4
            )
        results.append(
            SimilarSetupResult(
                query_symbol=query_symbol,
                match_symbol=snap.symbol,
                match_trading_day=snap.trading_day,
                similarity=round(sim, 4),
                match_grade_at_pick=snap.grade_at_pick,
                match_outcome_summary="",
                feature_diffs=feature_diffs,
                notes=[],
            )
        )
    results.sort(key=lambda r: r.similarity, reverse=True)
    return results[: max(1, limit)]
