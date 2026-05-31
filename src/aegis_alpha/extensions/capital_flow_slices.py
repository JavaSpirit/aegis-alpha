from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis_alpha.clock import now_iso
from aegis_alpha.models import CapitalFlowSlice


@dataclass(frozen=True)
class CapitalFlowSliceInputs:
    symbol: str
    trading_day: str
    bars: list[dict[str, Any]] = field(default_factory=list)
    first_seal_minute: int = 0
    first_break_minute: int = 0
    provider: str = "mock"
    data_mode: str = "mock"


def _aggregate(window_bars: list[dict[str, Any]]) -> tuple[float, float, float]:
    big = sum(float(b.get("big_order_net_inflow_cny", 0.0)) for b in window_bars)
    main = sum(float(b.get("main_capital_net_inflow_cny", 0.0)) for b in window_bars)
    retail = sum(float(b.get("retail_capital_net_inflow_cny", 0.0)) for b in window_bars)
    return big, main, retail


def compute_capital_flow_slices(
    inputs: CapitalFlowSliceInputs,
) -> list[CapitalFlowSlice]:
    if not inputs.bars:
        return []
    timestamp = now_iso()
    output: list[CapitalFlowSlice] = []
    by_minute = {int(b.get("minute", -1)): b for b in inputs.bars if int(b.get("minute", -1)) >= 0}

    # 切片 1: pre_first_seal_5m —— 首封前 5 根 bar
    if inputs.first_seal_minute > 0:
        start = max(0, inputs.first_seal_minute - 5)
        window_bars = [by_minute[m] for m in range(start, inputs.first_seal_minute) if m in by_minute]
        if window_bars:
            big, main, retail = _aggregate(window_bars)
            output.append(
                CapitalFlowSlice(
                    symbol=inputs.symbol, trading_day=inputs.trading_day,
                    window="pre_first_seal_5m",
                    big_order_net_inflow_cny=big,
                    main_capital_net_inflow_cny=main,
                    retail_capital_net_inflow_cny=retail,
                    provider=inputs.provider, data_mode=inputs.data_mode,
                    created_at=timestamp,
                )
            )

    # 切片 2: post_break_1m —— 首次炸板后 1 根 bar
    if inputs.first_break_minute > 0:
        m = inputs.first_break_minute
        if m in by_minute:
            big, main, retail = _aggregate([by_minute[m]])
            output.append(
                CapitalFlowSlice(
                    symbol=inputs.symbol, trading_day=inputs.trading_day,
                    window="post_break_1m",
                    big_order_net_inflow_cny=big,
                    main_capital_net_inflow_cny=main,
                    retail_capital_net_inflow_cny=retail,
                    provider=inputs.provider, data_mode=inputs.data_mode,
                    created_at=timestamp,
                )
            )

    # 切片 3: tail_30m —— 收盘前最后 30 分钟
    minutes_present = sorted(by_minute.keys())
    if minutes_present:
        max_minute = minutes_present[-1]
        tail_bars = [by_minute[m] for m in minutes_present if m > max_minute - 30]
        if tail_bars:
            big, main, retail = _aggregate(tail_bars)
            output.append(
                CapitalFlowSlice(
                    symbol=inputs.symbol, trading_day=inputs.trading_day,
                    window="tail_30m",
                    big_order_net_inflow_cny=big,
                    main_capital_net_inflow_cny=main,
                    retail_capital_net_inflow_cny=retail,
                    provider=inputs.provider, data_mode=inputs.data_mode,
                    created_at=timestamp,
                )
            )
    return output
