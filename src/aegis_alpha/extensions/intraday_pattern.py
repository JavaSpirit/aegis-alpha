from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis_alpha.models import IntradayPatternFeatures


_MESSY_BREAK_THRESHOLD = 3
_PLATFORM_CONSOLIDATION_MAX_PCT = 3.0  # 平台震荡幅度
_PLATFORM_CONSOLIDATION_MIN_MINUTES = 60  # 平台至少 60 分钟才算平台
_FALSE_BREAKOUT_RETRACE_PCT = 5.0  # 触板后回落 >5% 视为假突破


@dataclass(frozen=True)
class PatternInputs:
    bars: list[dict[str, Any]] = field(default_factory=list)
    daily_limit_pct: float = 10.0
    break_count: int = 0
    reseal_count: int = 0
    first_seal_minute: int = 0
    sealed_at_open: bool = False
    closed_at_limit: bool = False


def _high_pct(bars: list[dict[str, Any]]) -> float:
    if not bars:
        return 0.0
    return max(float(b.get("change_pct", 0.0)) for b in bars)


def _last_pct(bars: list[dict[str, Any]]) -> float:
    if not bars:
        return 0.0
    return float(bars[-1].get("change_pct", 0.0))


def classify_intraday_pattern(inputs: PatternInputs) -> IntradayPatternFeatures:
    if not inputs.bars and not inputs.first_seal_minute:
        return IntradayPatternFeatures(pattern="unknown")

    high = _high_pct(inputs.bars)
    last = _last_pct(inputs.bars)
    drawdown = max(0.0, high - last)

    if (
        inputs.sealed_at_open
        and inputs.break_count == 0
        and inputs.closed_at_limit
    ):
        return IntradayPatternFeatures(
            pattern="one_word_board",
            sealed_at_open=True, closing_at_limit=True,
            break_count=0, open_to_first_seal_minutes=inputs.first_seal_minute,
        )

    if (
        inputs.sealed_at_open
        and inputs.break_count >= 1
        and inputs.reseal_count >= 1
        and inputs.closed_at_limit
    ):
        return IntradayPatternFeatures(
            pattern="t_shape_board",
            sealed_at_open=True, closing_at_limit=True,
            break_count=inputs.break_count,
            open_to_first_seal_minutes=inputs.first_seal_minute,
        )

    if inputs.break_count >= _MESSY_BREAK_THRESHOLD:
        return IntradayPatternFeatures(
            pattern="messy_board",
            break_count=inputs.break_count,
            closing_at_limit=inputs.closed_at_limit,
            open_to_first_seal_minutes=inputs.first_seal_minute,
        )

    # 平台突破：至少 _PLATFORM_CONSOLIDATION_MIN_MINUTES 分钟震荡幅度小于阈值，然后冲板
    early_bars = [
        b for b in inputs.bars
        if int(b.get("minute", 0)) <= _PLATFORM_CONSOLIDATION_MIN_MINUTES * 2
    ]
    if early_bars:
        early_max = max(float(b.get("change_pct", 0.0)) for b in early_bars)
        early_min = min(float(b.get("change_pct", 0.0)) for b in early_bars)
        consolidation_range = early_max - early_min
        if (
            consolidation_range <= _PLATFORM_CONSOLIDATION_MAX_PCT
            and inputs.first_seal_minute >= _PLATFORM_CONSOLIDATION_MIN_MINUTES
            and inputs.closed_at_limit
        ):
            return IntradayPatternFeatures(
                pattern="platform_breakout",
                closing_at_limit=True,
                open_to_first_seal_minutes=inputs.first_seal_minute,
            )

    # 假突破：盘中触板（high 接近涨停），收盘明显回落
    near_limit = high >= inputs.daily_limit_pct - 0.2
    if near_limit and not inputs.closed_at_limit and drawdown >= _FALSE_BREAKOUT_RETRACE_PCT:
        return IntradayPatternFeatures(
            pattern="false_breakout",
            high_to_close_drawdown_pct=drawdown,
            break_count=inputs.break_count,
        )

    return IntradayPatternFeatures(
        pattern="normal",
        closing_at_limit=inputs.closed_at_limit,
        break_count=inputs.break_count,
    )
