"""TDD tests for the pure intraday buy-point state machine (Task 4.2).

Strategy detected:
  过前高(带量) → 回踩砸盘(缩量) → 重新上冲 = 买入预警点

All transitions are MEASURED FACTS; thresholds come from BuyPointThresholds.
Tests written BEFORE implementation (RED → GREEN).
"""
from __future__ import annotations

import pytest
from aegis_alpha.models import BuyPointThresholds, MinuteReplayBar
from aegis_alpha.measurements.buypoint_state_machine import (
    BuyPointContext,
    step,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def b(time: str, price: float, vol: float) -> MinuteReplayBar:
    """Minimal bar factory. average_price not used by the state machine."""
    return MinuteReplayBar(time=time, last_price=price, average_price=price, volume=vol)


THRESHOLDS = BuyPointThresholds()  # defaults: ratio_min=1.5, shrink_max=0.7, strength_min=0.5, drawdown=5.0
PREV_HIGH = 100.0
BASELINE_VOL = 1000.0


def _initial(prev_high: float = PREV_HIGH, baseline: float = BASELINE_VOL) -> BuyPointContext:
    return BuyPointContext(previous_high=prev_high, baseline_volume=baseline)


# ---------------------------------------------------------------------------
# Test 1 — idle stays when breakout volume insufficient
# ---------------------------------------------------------------------------

def test_idle_stays_when_breakout_volume_insufficient():
    """Price clears prev_high but volume ratio < 1.5 → state stays "idle"."""
    # vol = 1400 / 1000 = 1.4  <  1.5  (not confirmed)
    bar = b("09:31", 101.0, 1400.0)
    ctx = _initial()
    result = step(ctx, bar, THRESHOLDS)
    assert result.state == "idle", f"expected idle, got {result.state}"
    # No breakout facts should be recorded
    assert result.breakout_price == 0.0
    assert result.breakout_volume_ratio == 0.0


# ---------------------------------------------------------------------------
# Test 2 — idle → broke_high on volume-confirmed breakout
# ---------------------------------------------------------------------------

def test_idle_to_broke_high_on_volume_confirmed_breakout():
    """price > prev_high AND volume >= baseline*1.5 → state "broke_high"."""
    # vol = 1500 / 1000 = 1.5  >=  1.5  (exactly at threshold → confirmed)
    bar = b("09:32", 101.0, 1500.0)
    ctx = _initial()
    result = step(ctx, bar, THRESHOLDS)
    assert result.state == "broke_high"
    assert result.breakout_price == 101.0
    assert result.breakout_volume == 1500.0
    assert abs(result.breakout_volume_ratio - 1.5) < 1e-9
    assert len(result.evidence) > 0
    assert "过前高" in result.evidence[0]


# ---------------------------------------------------------------------------
# Test 3 — broke_high → pullback on retrace
# ---------------------------------------------------------------------------

def test_broke_high_to_pullback_on_retrace():
    """After breakout, a bar with price < breakout_price → "pullback"."""
    # Breakout at 101, vol ratio 2.0
    bar_breakout = b("09:32", 101.0, 2000.0)   # ratio = 2.0 >= 1.5
    bar_pullback = b("09:33", 99.5, 600.0)      # price < 101, vol 600 < 2000

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    assert ctx.state == "broke_high"

    ctx = step(ctx, bar_pullback, THRESHOLDS)
    assert ctx.state == "pullback"
    assert ctx.pullback_low == 99.5
    assert ctx.pullback_volume == 600.0
    # shrink ratio = 600 / 2000 = 0.3  (well below 0.7)
    assert abs(ctx.pullback_volume_shrink_ratio - 0.3) < 1e-9


# ---------------------------------------------------------------------------
# Test 4 — broke_high aborts when the first retrace bar crashes too deep
# ---------------------------------------------------------------------------

def test_broke_high_aborts_on_deep_retrace():
    """First bar below breakout_price drops > 5% below prev_high → "aborted" via broke_high branch.

    The crash bar routes through the broke_high→pullback transition gate; the drawdown
    guard fires there before the state ever becomes "pullback".

    Abort check: (previous_high - last_price) / previous_high * 100 > 5.0
    prev_high = 100. price = 94.0 → drawdown = (100 - 94)/100*100 = 6.0 > 5.0 → aborted.
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_deep = b("09:34", 94.0, 400.0)   # 6% below prev_high; routes through broke_high branch

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)   # → broke_high
    ctx = step(ctx, bar_deep, THRESHOLDS)       # → aborted (via broke_high abort gate)
    assert ctx.state == "aborted"
    assert any("砸破" in e or "abort" in e.lower() or "aborted" in e.lower() for e in ctx.evidence)


# ---------------------------------------------------------------------------
# Test 4b — pullback STATE aborts when a second bar crashes too deep
# ---------------------------------------------------------------------------

def test_pullback_state_aborts_on_second_bar_crash():
    """Genuinely exercises the pullback→aborted path: state must be "pullback" BEFORE the crash.

    The broke_high test above exercises the broke_high abort gate. This test explicitly
    reaches pullback first (mild retrace within limits), then delivers a second bar that
    exceeds pullback_max_drawdown_pct from previous_high.

    Hand-trace (prev_high=100, baseline=1000):
      Bar 09:32 price=101, vol=2000 → broke_high  (vol_ratio=2.0 ≥ 1.5)
      Bar 09:34 price=98.0, vol=600 → pullback
        drawdown = (100-98)/100*100 = 2.0 ≤ 5.0 → safe, enters pullback state
        shrink_ratio = 600/2000 = 0.30
      Bar 09:36 price=93.0, vol=400 → drawdown = (100-93)/100*100 = 7.0 > 5.0 → aborted
        This bar is processed inside the pullback branch (not broke_high).
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_mild_retrace = b("09:34", 98.0, 600.0)   # drawdown=2% — safe; lands in pullback
    bar_crash = b("09:36", 93.0, 400.0)           # drawdown=7% > 5% — aborted from pullback

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    assert ctx.state == "broke_high"

    ctx = step(ctx, bar_mild_retrace, THRESHOLDS)
    assert ctx.state == "pullback", (
        f"bar_mild_retrace must reach pullback (drawdown=2% safe), got {ctx.state}"
    )  # confirms the crash bar will be processed in the pullback branch, not broke_high

    ctx = step(ctx, bar_crash, THRESHOLDS)
    assert ctx.state == "aborted", (
        f"expected aborted from pullback state on 7% drawdown bar, got {ctx.state}"
    )
    assert any("砸破" in e or "abort" in e.lower() for e in ctx.evidence)


# ---------------------------------------------------------------------------
# Test 5 — full happy path: broke_high → pullback (shrink) → re_surge → buy_point_alert
# ---------------------------------------------------------------------------

def test_pullback_to_resurge_then_buy_point():
    """Full clean sequence → buy_point_alert, triggered_at set, resurge_strength >= 0.5.

    Hand-trace:
      prev_high = 100, baseline = 1000

      Bar 09:32 price=101, vol=2000 → breakout_vol_ratio=2.0 ≥ 1.5 → broke_high
        breakout_price=101, breakout_volume=2000

      Bar 09:34 price=99.0, vol=500 → price < 101 (retrace) → pullback
        pullback_low=99.0, pullback_volume=500
        pullback_vol_shrink_ratio = 500/2000 = 0.25 ≤ 0.7 ✓ (volume dried up)
        drawdown check: (100 - 99)/100*100 = 1.0 ≤ 5.0 → safe

      Bar 09:36 price=100.5, vol=1800 → price > pullback_low (turned up)
        pullback_vol_shrink_ratio = 0.25 ≤ 0.7 ✓ → qualifies
        resurge_strength = (100.5 - 99.0) / (101.0 - 99.0) = 1.5 / 2.0 = 0.75
        re_surge triggered (price > pullback_low)
        0.75 ≥ 0.5 (resurge_strength_min) → buy_point_alert immediately
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_pullback = b("09:34", 99.0, 500.0)
    bar_resurge = b("09:36", 100.5, 1800.0)

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    assert ctx.state == "broke_high"

    ctx = step(ctx, bar_pullback, THRESHOLDS)
    assert ctx.state == "pullback"
    assert abs(ctx.pullback_volume_shrink_ratio - 0.25) < 1e-9

    ctx = step(ctx, bar_resurge, THRESHOLDS)
    assert ctx.state == "buy_point_alert", f"expected buy_point_alert, got {ctx.state}"
    assert ctx.triggered_at == "09:36"
    assert ctx.resurge_strength >= 0.5
    assert abs(ctx.resurge_strength - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# Test 6 — high-volume pullback does NOT trigger buy_point_alert
# ---------------------------------------------------------------------------

def test_high_volume_pullback_does_not_trigger_buypoint():
    """Pullback volume did NOT shrink (ratio > 0.7) → even with a strong re-surge,
    never reaches buy_point_alert.

    Hand-trace:
      Bar 09:32: price=101, vol=2000 → broke_high, breakout_volume=2000
      Bar 09:34: price=99.0, vol=1600 → pullback
        pullback_vol_shrink_ratio = 1600/2000 = 0.80 > 0.7 (NOT dried up)
      Bar 09:36: price=100.8 → re-surge candidate but pullback was high-volume
        Should NOT advance to buy_point_alert because volume condition wasn't met.
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_pullback = b("09:34", 99.0, 1600.0)   # shrink_ratio = 0.80 > 0.70
    bar_resurge = b("09:36", 100.8, 1800.0)   # strong price recovery

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    ctx = step(ctx, bar_pullback, THRESHOLDS)
    assert ctx.state == "pullback"
    assert abs(ctx.pullback_volume_shrink_ratio - 0.8) < 1e-9  # failed to shrink

    ctx = step(ctx, bar_resurge, THRESHOLDS)
    # Must NOT be buy_point_alert — volume condition failed
    assert ctx.state != "buy_point_alert", (
        "Should not alert when pullback volume did not shrink below 0.7"
    )


# ---------------------------------------------------------------------------
# Test 7 — weak re-surge stays in re_surge
# ---------------------------------------------------------------------------

def test_weak_resurge_stays_re_surge():
    """Pullback dried up fine, but re-surge only partially recovers (<0.5) → re_surge, NOT alert.

    Hand-trace:
      Bar 09:32: price=101, vol=2000 → broke_high
      Bar 09:34: price=99.0, vol=400 → pullback, shrink=400/2000=0.20 ≤ 0.7 ✓
      Bar 09:36: price=99.9, vol=1800
        resurge_strength = (99.9 - 99.0) / (101.0 - 99.0) = 0.9 / 2.0 = 0.45
        0.45 < 0.5 (resurge_strength_min) → re_surge but NOT buy_point_alert
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_pullback = b("09:34", 99.0, 400.0)
    bar_weak = b("09:36", 99.9, 1800.0)   # strength = 0.45 < 0.5

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    ctx = step(ctx, bar_pullback, THRESHOLDS)
    assert ctx.state == "pullback"

    ctx = step(ctx, bar_weak, THRESHOLDS)
    assert ctx.state == "re_surge", f"expected re_surge, got {ctx.state}"
    assert abs(ctx.resurge_strength - 0.45) < 1e-9
    assert ctx.triggered_at == ""  # not triggered yet


# ---------------------------------------------------------------------------
# Test 8 — full run via run() convenience function
# ---------------------------------------------------------------------------

def test_full_run_via_run_function():
    """run(bars, previous_high, baseline_volume) → final state buy_point_alert."""
    bars = [
        b("09:31", 99.0, 800.0),    # below prev_high, idle
        b("09:32", 101.0, 2000.0),  # breakout → broke_high
        b("09:33", 100.2, 700.0),   # still above breakout... actually above prev_high but below breakout
        b("09:34", 99.0, 500.0),    # pullback → pullback (shrink=0.25 ≤ 0.7)
        b("09:35", 98.5, 450.0),    # lower still → update pullback_low, stay pullback
        b("09:36", 100.5, 1800.0),  # re-surge → resurge_strength=(100.5-98.5)/(101-98.5)=2.0/2.5=0.8 ≥ 0.5
    ]
    final = run(bars, previous_high=PREV_HIGH, baseline_volume=BASELINE_VOL)
    assert final.state == "buy_point_alert"
    assert final.triggered_at == "09:36"
    assert final.resurge_strength >= 0.5


# ---------------------------------------------------------------------------
# Test 9 — purity: same inputs → identical output (deterministic)
# ---------------------------------------------------------------------------

def test_run_purity_deterministic():
    """run() on the same bars twice must return identical final contexts."""
    bars = [
        b("09:32", 101.0, 2000.0),
        b("09:34", 99.0, 500.0),
        b("09:36", 100.5, 1800.0),
    ]
    result_a = run(bars, previous_high=PREV_HIGH, baseline_volume=BASELINE_VOL)
    result_b = run(bars, previous_high=PREV_HIGH, baseline_volume=BASELINE_VOL)
    assert result_a == result_b
    # Also verify terminal state doesn't change on additional bars
    extra_bar = b("09:37", 105.0, 3000.0)
    result_c = step(result_a, extra_bar, THRESHOLDS)
    assert result_c.state == "buy_point_alert"  # terminal, stays


# ---------------------------------------------------------------------------
# Test 10 (regression) — re_surge must abort on deep drawdown
# ---------------------------------------------------------------------------

def test_resurge_aborts_on_deep_drawdown():
    """Reach re_surge (weak strength), then a bar crashes >5% below previous_high → "aborted".

    This is the BUG 1 regression lock: the old code had no drawdown guard in re_surge,
    so a crash bar would be ignored and a later recovery would fire buy_point_alert falsely.

    Setup (prev_high=100, baseline=1000):
      09:32 price=101, vol=2000  → broke_high  (ratio=2.0 ≥ 1.5)
      09:34 price=99.0, vol=400  → pullback     (shrink=0.20 ≤ 0.7, drawdown=1% safe)
      09:36 price=99.9, vol=1800 → re_surge     (strength=0.45 < 0.5, not yet alert)
      09:38 price=93.0, vol=500  → drawdown=(100-93)/100*100=7.0 > 5.0 → ABORTED

    After abort, even a strong recovery bar must keep state "aborted" (terminal).
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_pullback = b("09:34", 99.0, 400.0)
    bar_weak_surge = b("09:36", 99.9, 1800.0)  # strength=0.45 < 0.5 → re_surge
    bar_crash = b("09:38", 93.0, 500.0)        # drawdown=(100-93)/100=7% > 5% → abort
    bar_recovery = b("09:40", 103.0, 3000.0)   # would trigger alert if bug present

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    assert ctx.state == "broke_high"

    ctx = step(ctx, bar_pullback, THRESHOLDS)
    assert ctx.state == "pullback"

    ctx = step(ctx, bar_weak_surge, THRESHOLDS)
    assert ctx.state == "re_surge", f"expected re_surge, got {ctx.state}"
    assert abs(ctx.resurge_strength - 0.45) < 1e-9

    ctx = step(ctx, bar_crash, THRESHOLDS)
    assert ctx.state == "aborted", (
        f"expected aborted after 7% drawdown in re_surge, got {ctx.state} — "
        "this is the BUG 1 regression: re_surge must check drawdown abort guard"
    )
    assert any("砸破" in e or "abort" in e.lower() for e in ctx.evidence)

    # Terminal: recovery bar must not escape aborted
    ctx = step(ctx, bar_recovery, THRESHOLDS)
    assert ctx.state == "aborted", "aborted is terminal — should not recover to buy_point_alert"


# ---------------------------------------------------------------------------
# Test 10b — degenerate range_span == 0 (defensive branch coverage)
# ---------------------------------------------------------------------------

def test_degenerate_range_span_zero():
    """When pullback_low == breakout_price the range_span is 0.

    The defensive branch (state_machine lines ~174 and ~256) sets strength=1.0
    instead of dividing by zero.  This test exercises that branch and confirms:
    - The machine does NOT crash (no ZeroDivisionError).
    - The resulting state is either buy_point_alert (strength=1.0 >= 0.5) or
      another defined non-error state — never an exception.

    Setup: breakout at price 101, then pullback bar lands exactly AT 101
    (pullback_low == breakout_price == 101), then a bar above 101 turns the
    price up.  When the re-surge bar is processed, range_span = 101 - 101 = 0
    → defensive path fires, strength = 1.0 → buy_point_alert immediately.

    Hand-trace (prev_high=100, baseline=1000):
      09:32 price=101, vol=2000 → broke_high  (breakout_price=101)
      09:34 price=101, vol=600  → retrace: price < breakout? No (equal).
                                   Actually price == breakout_price, NOT < it.
                                   Machine stays in broke_high.
    Adjust: we need price < breakout_price for the pullback transition to fire,
    then have the pullback_low track back up to breakout_price.  Instead we
    directly construct a BuyPointContext already in pullback state with
    pullback_low set equal to breakout_price, then deliver one "turned up" bar.
    """
    from aegis_alpha.measurements.buypoint_state_machine import BuyPointContext, step

    # Directly construct a context in pullback with pullback_low == breakout_price.
    # breakout_price = pullback_low = 101.0  →  range_span = 0 in the next step.
    ctx = BuyPointContext(
        state="pullback",
        previous_high=100.0,
        baseline_volume=1000.0,
        breakout_price=101.0,
        breakout_volume=2000.0,
        breakout_volume_ratio=2.0,
        pullback_low=101.0,       # equal to breakout_price → range_span == 0
        pullback_volume=500.0,
        pullback_volume_shrink_ratio=0.25,
    )

    # A bar above pullback_low (101.0) triggers the "turned up" branch.
    # range_span = 101.0 - 101.0 = 0 → defensive strength = 1.0 → buy_point_alert.
    bar_up = b("09:36", 101.5, 1800.0)

    # Must not raise, and must land in a defined non-error state.
    result = step(ctx, bar_up, THRESHOLDS)

    assert result.state in ("buy_point_alert", "re_surge", "pullback", "aborted"), (
        f"Unexpected state after range_span=0 branch: {result.state}"
    )
    # With strength=1.0 (defensive) >= resurge_strength_min=0.5, expect buy_point_alert.
    assert result.state == "buy_point_alert", (
        f"Expected buy_point_alert via defensive strength=1.0 path, got {result.state}. "
        "Check the range_span==0 defensive branch in buypoint_state_machine.py."
    )
    assert result.resurge_strength == 1.0, (
        f"Expected strength=1.0 from defensive branch, got {result.resurge_strength}"
    )


# ---------------------------------------------------------------------------
# Test 11 (regression) — re_surge updates pullback_low on new low
# ---------------------------------------------------------------------------

def test_resurge_new_low_updates_pullback_low():
    """In re_surge, a bar printing a new low below pullback_low must update pullback_low.

    This is the BUG 2 regression lock: the old code never updated pullback_low in re_surge,
    leaving a stale anchor in the strength denominator.

    Setup (prev_high=100, baseline=1000):
      09:32 price=101, vol=2000 → broke_high
      09:34 price=99.0, vol=400 → pullback (shrink=0.20, pullback_low=99.0)
      09:36 price=99.9, vol=1800 → re_surge (strength=0.45 < 0.5; pullback_low stays 99.0)
      09:37 price=98.0, vol=300  → new low in re_surge; pullback_low should update to 98.0
                                    strength = (98.0 - 98.0) / (101.0 - 98.0) = 0.0

    Assert: after the 09:37 bar, context.pullback_low == 98.0 (updated, not stale 99.0).
    """
    bar_breakout = b("09:32", 101.0, 2000.0)
    bar_pullback = b("09:34", 99.0, 400.0)
    bar_weak_surge = b("09:36", 99.9, 1800.0)   # re_surge, pullback_low=99.0
    bar_new_low = b("09:37", 98.0, 300.0)        # new low — must update pullback_low

    ctx = _initial()
    ctx = step(ctx, bar_breakout, THRESHOLDS)
    ctx = step(ctx, bar_pullback, THRESHOLDS)
    assert ctx.pullback_low == 99.0

    ctx = step(ctx, bar_weak_surge, THRESHOLDS)
    assert ctx.state == "re_surge"
    assert ctx.pullback_low == 99.0  # hasn't gone lower yet

    ctx = step(ctx, bar_new_low, THRESHOLDS)
    assert ctx.pullback_low == 98.0, (
        f"pullback_low should be updated to 98.0 (new low in re_surge), got {ctx.pullback_low} — "
        "this is the BUG 2 regression: stale anchor corrupts resurge_strength denominator"
    )
    # Strength measured from the new real low: (98.0 - 98.0) / (101.0 - 98.0) = 0.0
    assert ctx.resurge_strength == 0.0
