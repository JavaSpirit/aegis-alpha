"""TDX second-board candidate builder — mirror jvquant/candidates.py pattern.

Provides `build_one_candidate()` to construct a `SecondBoardCandidate` from a
single TDX quote row, and `assemble_candidates()` to orchestrate the full pipeline.
"""
from __future__ import annotations

import logging
from typing import Any

from aegis_alpha.adapters.tdx import client as _tdx
from aegis_alpha.adapters.tdx import parsers as P
from aegis_alpha.models import SecondBoardCandidate

logger = logging.getLogger(__name__)

# TDX data quality evidence — field-level provenance markers
_TDX_UNAVAILABLE = "tdx_unavailable"
_TDX_PROVIDER = "tdx"
_TDX_MODE = "tdx"


def build_one_candidate(
    *,
    raw_quote: dict[str, Any],
    theme: str = "unknown",
    index: int = 0,
) -> SecondBoardCandidate:
    """Construct one SecondBoardCandidate from a raw TDX quote row.

    This mirrors `jvquant/candidates.py:build_one_candidate()` in structure:
    takes a single raw row, extracts/derives fields, returns the model instance.
    """
    code = str(raw_quote.get("code", ""))
    price = P.float_or_zero(raw_quote.get("price"))
    last_close = P.float_or_zero(raw_quote.get("last_close", 1))
    change_pct = ((price - last_close) / last_close * 100) if last_close else 0.0
    amount = P.float_or_zero(raw_quote.get("amount"))
    volume = P.float_or_zero(raw_quote.get("vol"))

    return SecondBoardCandidate(
        symbol=code,
        name=code,  # TDX Level-1 does not carry name; can be enriched later
        data_mode=_TDX_MODE,
        provider=_TDX_PROVIDER,
        theme=theme,
        previous_limit_up_time="unknown",
        first_limit_up_time="unknown",
        theme_lifecycle_stage="unknown",
        theme_role="unknown",
        current_change_pct=round(change_pct, 2),
        five_min_speed_pct=0.0,
        five_min_speed_window=_TDX_UNAVAILABLE,
        five_min_speed_timestamp="",
        one_min_speed_pct=0.0,
        one_min_speed_window=_TDX_UNAVAILABLE,
        three_min_speed_pct=0.0,
        three_min_speed_window=_TDX_UNAVAILABLE,
        ten_min_speed_pct=0.0,
        ten_min_speed_window=_TDX_UNAVAILABLE,
        turnover_cny=amount,
        avg_turnover_10d_cny=0.0,
        ma5_slope_degrees=0.0,
        prev_day_volume_shrink_ratio=1.0,
        free_float_market_cap_cny=0.0,
        big_order_net_inflow_ratio=0.0,
        orderbook_quality_score=50.0,
        break_board_count=0,
        reseal_count=0,
        max_seal_amount_cny=0.0,
        max_seal_volume_shares=0.0,
        final_seal_time="unknown",
        seal_amount_cny=0.0,
        seal_volume_shares=0.0,
        seal_to_turnover_ratio=0.0,
        same_theme_rising_count=0,
        three_year_touch_limit_success_rate=0.0,
        three_year_sealed_next_day_gap_up_rate=0.0,
        auction_change_pct=0.0,
        auction_turnover_cny=0.0,
        auction_turnover_rate=0.0,
        auction_pattern="unknown",
        limitup_driver_type="unknown",
        intraday_pattern="unknown",
        weekly_health_score=50.0,
        concept_tags=[],
        topic_tags=[],
        notes=[
            f"TDX live | chg={change_pct:.1f}% | vol={volume:.0f} | amt={amount/1e8:.1f}亿",
            f"Index in batch: {index}",
        ],
    )


def assemble_candidates(
    *,
    blocks_data: list[dict],
    max_blocks: int = 10,
    stocks_per_block: int = 80,
    max_symbols: int = 300,
    quote_chunk_size: int = 80,
    min_change_pct: float = 5.0,
    max_candidates: int = 10,
) -> list[SecondBoardCandidate]:
    """Build second-board candidates from TDX quotes + blocks.

    Pipeline:
    1. Read active blocks → collect deduplicated stock codes
    2. Batch-query quotes in chunks
    3. Filter for stocks with change% >= min_change_pct
    4. Sort by change% descending, build top-N candidates

    Returns empty list on any error (caller falls back to mock).
    """
    # ── 1. Collect stocks from blocks ──────────────────────────────────
    seen: set[str] = set()
    theme_map: dict[str, str] = {}
    stocks_all: list[str] = []
    for b in blocks_data[:max_blocks]:
        theme_name = str(b.get("blockname", ""))
        for code in b.get("stocks", [])[:stocks_per_block]:
            if code not in seen:
                seen.add(code)
                theme_map[code] = theme_name
                stocks_all.append(code)

    if not stocks_all:
        logger.warning("TDX: no stocks found in blocks data")
        return []

    # ── 2. Format symbols for tdxmcp ───────────────────────────────────
    tdx_symbols = [P.market_prefix(s) for s in stocks_all[:max_symbols]]

    # ── 3. Batch query ────────────────────────────────────────────────
    all_quotes: list[dict] = []
    for i in range(0, len(tdx_symbols), quote_chunk_size):
        chunk = tdx_symbols[i:i + quote_chunk_size]
        try:
            all_quotes.extend(_tdx.quotes(chunk))
        except Exception:
            logger.debug("TDX quote chunk %d failed, continuing", i, exc_info=True)
            continue

    if not all_quotes:
        logger.warning("TDX: all quote chunks failed")
        return []

    # ── 4. Filter & sort ──────────────────────────────────────────────
    movers: list[tuple[dict, float]] = []
    for q in all_quotes:
        chg = P.change_pct_from_raw(q)
        if chg >= min_change_pct:
            movers.append((q, chg))
    movers.sort(key=lambda x: x[1], reverse=True)

    # ── 5. Build candidates ───────────────────────────────────────────
    candidates: list[SecondBoardCandidate] = []
    for idx, (q, _chg) in enumerate(movers[:max_candidates]):
        code = str(q.get("code", ""))
        theme = theme_map.get(code, "unknown")
        candidates.append(build_one_candidate(raw_quote=q, theme=theme, index=idx))

    logger.info("TDX: assembled %d candidates from %d quotes (%d movers)",
                len(candidates), len(all_quotes), len(movers))
    return candidates
