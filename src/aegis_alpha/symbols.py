from __future__ import annotations

import re
from enum import Enum


class Board(Enum):
    SH_MAIN = "sh_main"
    SZ_MAIN = "sz_main"
    STAR = "star"
    CHINEXT = "chinext"
    BSE = "bse"
    UNKNOWN = "unknown"


_SH_PREFIX_PATTERN = re.compile(r"^SH")
_SZ_PREFIX_PATTERN = re.compile(r"^SZ")


def normalize_symbol(symbol: str) -> str:
    """Strip whitespace and market prefix/suffix, returning the raw code."""
    text = symbol.strip().upper()
    text = _SH_PREFIX_PATTERN.sub("", text)
    text = _SZ_PREFIX_PATTERN.sub("", text)
    return text.split(".", 1)[0]


def board_of(symbol: str) -> Board:
    code = normalize_symbol(symbol)
    if len(code) != 6 or not code.isdigit():
        return Board.UNKNOWN
    if code.startswith(("600", "601", "603", "605")):
        return Board.SH_MAIN
    if code.startswith(("688", "689")):
        return Board.STAR
    if code.startswith(("000", "001", "002", "003")):
        return Board.SZ_MAIN
    if code.startswith(("300", "301")):
        return Board.CHINEXT
    if code.startswith(("4", "8")):
        return Board.BSE
    return Board.UNKNOWN


_LIMIT_BY_BOARD: dict[Board, float] = {
    Board.SH_MAIN: 10.0,
    Board.SZ_MAIN: 10.0,
    Board.STAR: 20.0,
    Board.CHINEXT: 20.0,
    Board.BSE: 30.0,
    Board.UNKNOWN: 10.0,
}


def daily_limit_pct(symbol: str) -> float:
    """Return the standard daily limit percentage for a non-ST stock."""
    return _LIMIT_BY_BOARD[board_of(symbol)]
