from aegis_alpha.extensions.capital_flow_slices import (
    CapitalFlowSliceInputs,
    compute_capital_flow_slices,
)


def test_compute_pre_first_seal_5m_uses_5_bars_before_first_seal():
    bars = [
        {"minute": m, "big_order_net_inflow_cny": 1_000_000.0,
         "main_capital_net_inflow_cny": 2_000_000.0,
         "retail_capital_net_inflow_cny": -500_000.0}
        for m in range(0, 30)
    ]
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(
            symbol="600519", trading_day="2026-05-30",
            bars=bars, first_seal_minute=20,
        )
    )
    pre = next(s for s in out if s.window == "pre_first_seal_5m")
    # 5 bars (minute 15-19): each big=1M → sum 5M
    assert pre.big_order_net_inflow_cny == 5_000_000.0
    assert pre.main_capital_net_inflow_cny == 10_000_000.0
    assert pre.retail_capital_net_inflow_cny == -2_500_000.0


def test_post_break_1m_when_break_minute_present():
    bars = [
        {"minute": m, "big_order_net_inflow_cny": -3_000_000.0,
         "main_capital_net_inflow_cny": -2_000_000.0,
         "retail_capital_net_inflow_cny": 1_000_000.0}
        for m in range(60, 65)
    ]
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(
            symbol="600519", trading_day="2026-05-30",
            bars=bars, first_seal_minute=50, first_break_minute=60,
        )
    )
    post = next(s for s in out if s.window == "post_break_1m")
    assert post.big_order_net_inflow_cny == -3_000_000.0


def test_tail_30m_aggregates_last_30_bars():
    bars = [
        {"minute": m, "big_order_net_inflow_cny": 100_000.0,
         "main_capital_net_inflow_cny": 200_000.0,
         "retail_capital_net_inflow_cny": -50_000.0}
        for m in range(210, 240)  # 14:30-15:00 (30 分钟)
    ]
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(
            symbol="600519", trading_day="2026-05-30",
            bars=bars, first_seal_minute=10,
        )
    )
    tail = next(s for s in out if s.window == "tail_30m")
    assert tail.big_order_net_inflow_cny == 30 * 100_000.0


def test_no_slices_when_inputs_empty():
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(symbol="X", trading_day="2026-05-30", bars=[])
    )
    assert out == []
