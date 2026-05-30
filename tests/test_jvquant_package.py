from __future__ import annotations

from aegis_alpha.adapters.jvquant import JvQuantMarketDataAdapter as PackagedAdapter
from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter as ShimAdapter


def test_jvquant_market_data_shim_reexports_packaged_adapter() -> None:
    assert ShimAdapter is PackagedAdapter
