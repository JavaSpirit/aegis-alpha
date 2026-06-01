from __future__ import annotations

from aegis_alpha.models import NewStockTier


# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.aged_out_days
_AGED_OUT_DAYS = 180
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.smallcap_threshold_cny
_SMALLCAP_THRESHOLD_CNY = 1_000_000_000.0
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.largecap_threshold_cny
_LARGECAP_THRESHOLD_CNY = 5_000_000_000.0
# CALIBRATE: see config/p6_thresholds.yaml § new_stocks.recent_days
_RECENT_DAYS = 30


def classify_new_stock_tier(
    *, days_since_listing: int, free_float_cny: float
) -> NewStockTier:
    if days_since_listing > _AGED_OUT_DAYS:
        return "tier_aged_out"
    if free_float_cny >= _LARGECAP_THRESHOLD_CNY:
        return "tier_c_largecap"
    if days_since_listing <= _RECENT_DAYS and free_float_cny < _SMALLCAP_THRESHOLD_CNY:
        return "tier_a_smallcap_recent"
    return "tier_b_midcap_recent"
