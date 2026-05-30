from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from aegis_alpha.models import LadderHeight


@dataclass(frozen=True)
class LimitUpHistory:
    symbol: str
    limit_up_days: list[str]


def classify_height(consecutive_boards: int) -> LadderHeight:
    if consecutive_boards <= 0:
        return "unknown"
    if consecutive_boards == 1:
        return "first_board"
    if consecutive_boards == 2:
        return "second_board"
    if consecutive_boards == 3:
        return "third_board"
    if consecutive_boards == 4:
        return "fourth_board"
    return "high_height"


def compute_consecutive_boards(history: LimitUpHistory, today: date) -> int:
    days = sorted({_parse_day(item) for item in history.limit_up_days if _parse_day(item) is not None})
    if not days:
        return 0

    current = today if today in days else days[-1]
    if current > today:
        current = today
    count = 0
    day_set = set(days)
    while current in day_set:
        count += 1
        current = _previous_trading_day(current)
    return count


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _previous_trading_day(value: date) -> date:
    current = value - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current
