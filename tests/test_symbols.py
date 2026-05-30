from __future__ import annotations

import pytest

from aegis_alpha.symbols import Board, board_of, daily_limit_pct, normalize_symbol


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "600519"),
        ("600519.SH", "600519"),
        (" 000001.SZ ", "000001"),
        ("sz000001", "000001"),
        ("SH600519", "600519"),
    ],
)
def test_normalize_symbol(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "symbol,expected_board",
    [
        ("600519", Board.SH_MAIN),
        ("601318", Board.SH_MAIN),
        ("603259", Board.SH_MAIN),
        ("605588", Board.SH_MAIN),
        ("688981", Board.STAR),
        ("689009", Board.STAR),
        ("000001", Board.SZ_MAIN),
        ("002230", Board.SZ_MAIN),
        ("003816", Board.SZ_MAIN),
        ("300750", Board.CHINEXT),
        ("301029", Board.CHINEXT),
        ("830799", Board.BSE),
        ("872925", Board.BSE),
        ("430564", Board.BSE),
    ],
)
def test_board_of(symbol: str, expected_board: Board) -> None:
    assert board_of(symbol) == expected_board


@pytest.mark.parametrize(
    "symbol,expected_pct",
    [
        ("600519", 10.0),
        ("000001", 10.0),
        ("688981", 20.0),
        ("300750", 20.0),
        ("830799", 30.0),
    ],
)
def test_daily_limit_pct_normal_stocks(symbol: str, expected_pct: float) -> None:
    assert daily_limit_pct(symbol) == expected_pct


def test_board_of_unknown_returns_unknown() -> None:
    assert board_of("999999") == Board.UNKNOWN


def test_daily_limit_pct_unknown_defaults_to_10() -> None:
    assert daily_limit_pct("999999") == 10.0
