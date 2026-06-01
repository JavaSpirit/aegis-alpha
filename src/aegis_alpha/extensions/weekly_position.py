from __future__ import annotations

from aegis_alpha.models import WeeklyPosition


def compute_weekly_health_score(pos: WeeklyPosition) -> float:
    """Combine position_pct (40%) + weeks_in_uptrend (40%) + ma_above (20%).

    Returns a 0-100 score where 50 is neutral. The weights are starter values;
    P6 follow-up issue may calibrate against historical limit-up outcomes.
    """
    position_component = max(0.0, min(1.0, pos.position_pct)) * 100.0
    uptrend_normalized = max(0.0, min(1.0, pos.weeks_in_uptrend / 4.0)) * 100.0
    ma_component = 100.0 if pos.ma20_above_ma60 else 0.0
    weighted = (
        0.4 * position_component
        + 0.4 * uptrend_normalized
        + 0.2 * ma_component
    )
    return max(0.0, min(100.0, weighted))
