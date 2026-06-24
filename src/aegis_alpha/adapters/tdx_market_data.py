"""TDX (通达信) market data adapter — flat entry point.

Mirrors jvquant_market_data.py in structure:
  - Re-exports the adapter class and key parser utilities
  - Provides a single import path for the TDX data source

Usage:
    from aegis_alpha.adapters.tdx_market_data import TdxMarketDataAdapter
"""
from __future__ import annotations

from aegis_alpha.adapters.tdx.adapter import TdxMarketDataAdapter
from aegis_alpha.adapters.tdx.parsers import (
    change_pct_from_raw,
    float_or_zero,
    int_or_zero,
    is_limit_up,
    market_prefix,
    normalize_quote,
)
from aegis_alpha.symbols import normalize_symbol

__all__ = [
    "TdxMarketDataAdapter",
    "change_pct_from_raw",
    "float_or_zero",
    "int_or_zero",
    "is_limit_up",
    "market_prefix",
    "normalize_quote",
    "normalize_symbol",
]
