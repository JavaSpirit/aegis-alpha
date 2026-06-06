from __future__ import annotations

from dataclasses import dataclass

from aegis_alpha.models import ThemeLifecycleStage


@dataclass(frozen=True)
class ThemeDay:
    limit_up_count: int
    break_board_rate: float
    new_high_member_count: int
    leader_alive: bool


def classify_theme_lifecycle(series: list[ThemeDay]) -> ThemeLifecycleStage:
    """Deterministic stage classifier over measured theme counts.

    Decay states (ebb, divergence) are checked before growth states so a
    peak-then-fall sequence is not misread as a fresh launch. This is a
    measurement over observable counts, not a judgment.
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
            and counts[-1] <= counts[-3] and counts[-3] >= peak * 0.8):
        return "divergence"
    # launch: rose from a low base — check before climax/fermenting so a new
    # series peaking at its own small max is not misread as climax.
    if counts[-3] <= 2 and counts[-1] >= 3:
        return "launch"
    nh = [x.new_high_member_count for x in recent]
    nh_accel = (nh[-1] - nh[-2]) > (nh[-2] - nh[-3])
    if (counts[-1] == peak and recent[-1].new_high_member_count == nh_peak
            and nh_accel):
        return "climax"
    if counts[-1] > counts[-2] > counts[-3]:
        return "fermenting"
    return "unknown"
