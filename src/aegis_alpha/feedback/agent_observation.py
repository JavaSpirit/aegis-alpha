from __future__ import annotations

import hashlib

from aegis_alpha.models import AgentObservation, ObservationNotificationGrade


def compute_observation_id(
    *,
    trading_day: str,
    source: str,
    observation_type: str,
    symbol: str = "",
    theme: str = "",
) -> str:
    """Deterministic dedup key.

    Two observations of the same type, on the same day, about the same
    symbol/theme, from the same source collapse to one id. The store treats a
    colliding id as already-seen, so the periodic observer cannot re-notify the
    same observation within a day.
    """
    key = "::".join(
        [
            trading_day.strip(),
            source.strip(),
            observation_type.strip(),
            symbol.strip().upper(),
            theme.strip(),
        ]
    )
    return "ob_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def observation_notification_grade(
    observation: AgentObservation,
) -> ObservationNotificationGrade:
    """Deterministically map an observation to a notification grade.

    The agent authors stance + confidence + observation_type; it never sets the
    grade itself. This keeps notification urgency reproducible and auditable
    rather than dependent on unstable LLM self-rating.

    Grades:
      urgent    -> interrupt the user now
      important -> strategy-adjacent and notable; selectively pushed
      watch     -> useful, not worth interrupting
      suppress  -> noise / insufficient / rejected; never pushed
    """
    stance = observation.stance
    confidence = observation.confidence
    obs_type = observation.observation_type

    # Insufficient or rejected interpretations are never notifications.
    if stance in ("insufficient_data", "reject"):
        return "suppress"

    if obs_type == "noise_or_rejected_trigger":
        return "suppress"

    # Pure data gaps only matter when confidence is high enough to act on the
    # gap itself (e.g. a feed degradation). Otherwise they are background noise.
    if obs_type == "data_gap":
        return "watch" if confidence == "high" else "suppress"

    if stance == "actionable_watch":
        if obs_type == "buy_point_quality":
            if confidence == "high":
                return "urgent"
            if confidence == "medium":
                return "important"
            return "watch"
        if obs_type in ("market_regime_shift", "theme_rotation", "strong_continuation_without_buy_point"):
            if confidence in ("high", "medium"):
                return "important"
            return "watch"
        # watchlist_observation and anything else actionable
        return "watch"

    # stance == "monitor_only": useful context, but not an interruption.
    return "watch"
