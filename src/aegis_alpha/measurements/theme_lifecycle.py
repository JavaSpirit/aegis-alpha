from __future__ import annotations

from dataclasses import dataclass

from aegis_alpha.models import ThemeLifecycleStage

# Human-readable Chinese labels for theme lifecycle stages — used in explain output.
# This is the classifier's own vocabulary; keep it co-located with the classifier.
STAGE_LABELS_CN: dict[str, str] = {
    "launch": "启动",
    "fermenting": "发酵",
    "climax": "高潮",
    "divergence": "分歧",
    "ebb": "退潮",
    "unknown": "未知",
}

# Break-board rate ceiling for a clean launch: a theme rising from a low base
# but shedding >30 % of its members counts as distressed, not nascent.
# Calibrate against win-rate data once sufficient history exists.
_LAUNCH_MAX_BREAK_RATE = 0.3


@dataclass(frozen=True)
class ThemeDay:
    limit_up_count: int
    break_board_rate: float
    new_high_member_count: int
    leader_alive: bool


def classify_theme_lifecycle(series: list[ThemeDay]) -> ThemeLifecycleStage:
    """Deterministic stage classifier over measured theme counts.

    Evaluation order: ebb → divergence → launch → climax → fermenting → unknown.

    Decay states (ebb, divergence) are checked first so a peak-then-fall
    sequence is not misread as a fresh growth phase.

    Within the growth states, launch is checked before climax because the
    low-base signal (counts[-3] ≤ 2) is a definitive early-stage marker
    that would otherwise collide with the climax heuristic on a short series.

    The climax/fermenting boundary is APPROXIMATE when the series is only
    3 days long: on a purely ascending 3-day window both counts[-1] and
    nh[-1] equal their respective series maxima, so an additional heuristic
    is required — accelerating new-high membership (nh_accel). This
    heuristic is calibrated against ground truth in a later phase and is
    NOT definitive; it should be revisited once longer series are available.

    This function is a pure measurement over observable counts. No I/O,
    no randomness, no side effects.
    """
    if len(series) < 3:
        return "unknown"
    recent = series[-3:]
    counts = [x.limit_up_count for x in recent]
    peak = max(x.limit_up_count for x in series)
    nh_peak = max(x.new_high_member_count for x in series)

    falling_two = counts[-1] < counts[-2] and counts[-1] <= counts[-3]

    if falling_two and not recent[-1].leader_alive:
        return "ebb"
    if (recent[-1].break_board_rate > recent[-3].break_board_rate
            and counts[-1] <= counts[-3]
            and counts[-3] >= peak * 0.8):  # still within 80% of peak — a divergence near the top, not a routine decline
        return "divergence"
    if (counts[-3] <= 2 and counts[-1] >= 3  # rose from a low base (<3 = embryonic) to meaningful breadth (>=3)
            and recent[-1].break_board_rate < _LAUNCH_MAX_BREAK_RATE):
        return "launch"
    nh = [x.new_high_member_count for x in recent]
    # climax heuristic: new-high membership ACCELERATING (a fresh wave of entrants), not just rising —
    # distinguishes the blow-off top from steady fermenting
    nh_accel = (nh[-1] - nh[-2]) > (nh[-2] - nh[-3])
    if (counts[-1] == peak and recent[-1].new_high_member_count == nh_peak
            and nh_accel):
        return "climax"
    if counts[-1] > counts[-2] > counts[-3]:
        return "fermenting"
    return "unknown"
