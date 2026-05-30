from __future__ import annotations

from datetime import date

import pytest

from aegis_alpha.themes.ladder import LimitUpHistory, classify_height, compute_consecutive_boards


def test_compute_consecutive_boards_three_in_a_row() -> None:
    history = LimitUpHistory("600000", ["2026-05-27", "2026-05-28", "2026-05-29"])

    assert compute_consecutive_boards(history, today=date(2026, 5, 29)) == 3


def test_compute_consecutive_boards_with_gap_resets() -> None:
    history = LimitUpHistory("600000", ["2026-05-27", "2026-05-29"])

    assert compute_consecutive_boards(history, today=date(2026, 5, 29)) == 1


@pytest.mark.parametrize(
    ("boards", "label"),
    [(1, "first_board"), (2, "second_board"), (3, "third_board"), (4, "fourth_board"), (5, "high_height")],
)
def test_classify_height(boards: int, label: str) -> None:
    assert classify_height(boards) == label
