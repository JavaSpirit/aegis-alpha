from __future__ import annotations

import os

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.config import load_project_env


def create_market_data_adapter():
    load_project_env()
    provider = os.environ.get("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock").strip().lower()

    if provider == "jvquant":
        return JvQuantMarketDataAdapter.from_env()

    return MockMarketDataAdapter()
