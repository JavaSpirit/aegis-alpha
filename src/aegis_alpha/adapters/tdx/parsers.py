"""TDX data parsers — mirror jvquant/parsers.py pattern.

Stateless utility functions that normalize raw TDX (通达信) quote data
into standard shapes used by the adapter and candidate builder.
"""
from __future__ import annotations

from typing import Any

from aegis_alpha.symbols import normalize_symbol


def float_or_zero(value: Any) -> float:
    """Safe float cast, returns 0.0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def int_or_zero(value: Any) -> int:
    """Safe int cast, returns 0 on failure."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def market_prefix(symbol: str) -> str:
    """Convert 600519 → sh600519; 000001 → sz000001; 430047 → bj430047."""
    s = normalize_symbol(symbol)
    if s.startswith("6"):
        return f"sh{s}"
    if s.startswith(("0", "3")):
        return f"sz{s}"
    if s.startswith(("4", "8")):
        return f"bj{s}"
    return f"sh{s}"


def normalize_quote(raw: dict) -> dict[str, Any]:
    """Extract standard fields from a raw TDX quote dict.

    Handles both single-quote {symbol, quote} and batch element shapes.
    """
    q = raw.get("quote", raw)
    price = float_or_zero(q.get("price"))
    last_close = float_or_zero(q.get("last_close", 1))
    change_pct = ((price - last_close) / last_close * 100) if last_close else 0.0
    return {
        "symbol": str(raw.get("symbol", "")),
        "code": str(q.get("code", "")),
        "name": "",
        "price": price,
        "last_close": last_close,
        "open": float_or_zero(q.get("open")),
        "high": float_or_zero(q.get("high")),
        "low": float_or_zero(q.get("low")),
        "change_pct": round(change_pct, 2),
        "volume": float_or_zero(q.get("vol")),
        "amount": float_or_zero(q.get("amount")),
        "bid1": float_or_zero(q.get("bid1")),
        "ask1": float_or_zero(q.get("ask1")),
        "servertime": str(q.get("servertime", "")),
        "active1": int_or_zero(q.get("active1")),
    }


def is_limit_up(change_pct: float, symbol: str) -> bool:
    """Check if a stock hit its daily limit-up (with 0.5% tolerance)."""
    from aegis_alpha.symbols import daily_limit_pct
    limit = daily_limit_pct(symbol)
    return change_pct >= (limit - 0.5)


def change_pct_from_raw(q: dict) -> float:
    """Compute change% from raw TDX quote dict."""
    price = float_or_zero(q.get("price"))
    last_close = float_or_zero(q.get("last_close", 1))
    if last_close <= 0:
        return 0.0
    return round((price - last_close) / last_close * 100, 2)


def quote_rows_by_code(quotes: list[dict]) -> dict[str, dict]:
    """Index a list of raw TDX quotes by stock code."""
    return {str(q.get("code", "")): q for q in quotes if q.get("code")}
