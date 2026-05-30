from __future__ import annotations

from threading import Lock

from aegis_alpha.adapters.factory import create_market_data_adapter
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


_lock = Lock()
_adapter: MarketDataAdapter | None = None
_store: AegisAlphaStore | None = None


def get_market_data_adapter() -> MarketDataAdapter:
    global _adapter
    with _lock:
        if _adapter is None:
            _adapter = create_market_data_adapter()
        return _adapter


def get_store() -> AegisAlphaStore:
    global _store
    with _lock:
        if _store is None:
            _store = AegisAlphaStore()
        return _store


def reset_singletons() -> None:
    global _adapter, _store
    with _lock:
        _adapter = None
        _store = None
