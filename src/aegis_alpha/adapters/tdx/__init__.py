"""TDX (通达信) market data adapter for Aegis Alpha.

Mirrors jvquant/ module structure:
  - client.py    — HTTP client for tdxmcp REST API
  - parsers.py   — stateless data normalisation utilities
  - candidates.py — candidate assembly from raw TDX quotes
  - adapter.py   — TdxMarketDataAdapter (inherits MockMarketDataAdapter)
"""
from aegis_alpha.adapters.tdx.adapter import TdxMarketDataAdapter

__all__ = ["TdxMarketDataAdapter"]
