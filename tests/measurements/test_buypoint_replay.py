"""Tests for offline buy-point replay (Task 4.3).

TDD: written BEFORE the implementation. Run these first to confirm RED,
then implement replay_buypoint to reach GREEN.

Post-4.3 quality fixes (same commit):
- test_replay_opening_gap_above_high_not_spurious_breakout: pins FIX 1 (circular baseline).
- test_replay_baseline_window_zero_raises: pins FIX 2 (input guard).
"""
from __future__ import annotations

import pytest

from aegis_alpha.measurements.buypoint_replay import replay_buypoint
from aegis_alpha.models import (
    BuyPointThresholds,
    MinuteReplayBar,
    MinuteReplaySnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def b(time: str, price: float, vol: float) -> MinuteReplayBar:
    """Compact bar factory — only the fields replay cares about."""
    return MinuteReplayBar(time=time, last_price=price, average_price=price, volume=vol)


def snapshot(bars: list[MinuteReplayBar], symbol: str = "000001.SZ") -> MinuteReplaySnapshot:
    """Build a minimal MinuteReplaySnapshot from a bar list."""
    return MinuteReplaySnapshot(
        symbol=symbol,
        name="test",
        timestamp="2024-01-15T09:35:00",
        trading_day="2024-01-15",
        bars=bars,
    )


# Thresholds convenient for tests: tighter/looser per test
DEFAULT_THRESHOLDS = BuyPointThresholds(
    breakout_volume_ratio_min=1.5,
    pullback_volume_shrink_max=0.7,
    resurge_strength_min=0.5,
    pullback_max_drawdown_pct=5.0,
)

# ---------------------------------------------------------------------------
# Test 1: full buy-point sequence detected
# ---------------------------------------------------------------------------

def test_replay_detects_full_buypoint():
    """A complete 过前高(带量) → 回踩缩量 → 重新上冲 sequence yields a buy_point_alert signal."""
    previous_high = 10.0

    # Baseline window (first 3 bars): low volume, avg ~100
    baseline_bars = [
        b("09:31", 9.80, 100.0),
        b("09:32", 9.82, 100.0),
        b("09:33", 9.85, 100.0),  # baseline_volume = 100.0
    ]
    # Breakout bar: price > previous_high=10.0 with vol_ratio = 200/100 = 2.0 >= 1.5
    breakout_bar = b("09:34", 10.20, 200.0)
    # Pullback bars: price drops below breakout (10.20) but NOT below previous_high by >5%
    # (previous_high * 0.95 = 9.50; stay above 9.50)
    pullback_bars = [
        b("09:35", 10.05, 60.0),   # shrink_ratio so far = 60/200 = 0.30 <= 0.7 ✓
        b("09:36", 9.90,  50.0),   # shrink_ratio = 50/200 = 0.25 <= 0.7 ✓
    ]
    # Re-surge bar: price turns up from 9.90 (pullback_low)
    # strength = (resurge_price - pullback_low) / (breakout_price - pullback_low)
    #          = (10.10 - 9.90) / (10.20 - 9.90) = 0.20 / 0.30 = 0.667 >= 0.5 ✓
    resurge_bar = b("09:37", 10.10, 80.0)

    bars = baseline_bars + [breakout_bar] + pullback_bars + [resurge_bar]
    snap = snapshot(bars)

    signals = replay_buypoint(
        snap,
        previous_high=previous_high,
        thresholds=DEFAULT_THRESHOLDS,
        baseline_window=3,
    )

    # Must have at least one alert
    alerts = [s for s in signals if s.state == "buy_point_alert"]
    assert len(alerts) >= 1, f"Expected buy_point_alert but got: {[s.state for s in signals]}"

    alert = alerts[0]
    assert alert.triggered_at != "", "triggered_at must be set on alert"
    assert alert.resurge_strength >= 0.5, f"resurge_strength {alert.resurge_strength} < 0.5"
    assert alert.symbol == "000001.SZ"
    assert alert.trading_day == "2024-01-15"
    assert alert.data_mode == "minute_replay"


# ---------------------------------------------------------------------------
# Test 2: no buy_point_alert when price keeps rising after breakout (no pullback)
# ---------------------------------------------------------------------------

def test_replay_no_signal_when_only_breakout_no_pullback():
    """Price breaks the high with volume and keeps rising — no pullback phase,
    so the sequence never completes. Contract: returned list has NO buy_point_alert
    signal. (The list may contain a single terminal-state-summary if nothing fired,
    but it must NOT contain a buy_point_alert.)
    """
    previous_high = 10.0
    bars = [
        b("09:31", 9.80, 100.0),
        b("09:32", 9.82, 100.0),
        b("09:33", 9.85, 100.0),  # baseline = 100.0
        b("09:34", 10.20, 200.0), # breakout ✓
        b("09:35", 10.40, 180.0), # keeps rising — still in broke_high
        b("09:36", 10.60, 160.0), # keeps rising — still in broke_high
        b("09:37", 10.80, 150.0), # keeps rising — still in broke_high
    ]
    snap = snapshot(bars)

    signals = replay_buypoint(snap, previous_high=previous_high, thresholds=DEFAULT_THRESHOLDS)

    alerts = [s for s in signals if s.state == "buy_point_alert"]
    assert alerts == [], f"Expected no buy_point_alert but got: {[s.state for s in signals]}"


# ---------------------------------------------------------------------------
# Test 3: determinism — same input yields identical output
# ---------------------------------------------------------------------------

def test_replay_is_deterministic():
    """Same snapshot replayed twice must produce byte-identical signals."""
    previous_high = 10.0
    bars = [
        b("09:31", 9.80, 100.0),
        b("09:32", 9.82, 100.0),
        b("09:33", 9.85, 100.0),
        b("09:34", 10.20, 200.0),
        b("09:35", 10.00, 60.0),
        b("09:36", 9.90,  50.0),
        b("09:37", 10.10, 80.0),
    ]
    snap = snapshot(bars)

    result_a = replay_buypoint(snap, previous_high=previous_high, thresholds=DEFAULT_THRESHOLDS)
    result_b = replay_buypoint(snap, previous_high=previous_high, thresholds=DEFAULT_THRESHOLDS)

    assert len(result_a) == len(result_b), "Lengths differ between two runs"
    for i, (a, b_sig) in enumerate(zip(result_a, result_b)):
        assert a.model_dump() == b_sig.model_dump(), f"Signal {i} differs between runs"


# ---------------------------------------------------------------------------
# Test 4: multi-setup — morning abort followed by afternoon clean setup
# ---------------------------------------------------------------------------

def test_replay_captures_second_setup_after_morning_abort():
    """Morning: price breaks out but then crashes deep (abort).
    Afternoon: clean 过前高→回踩缩量→重新上冲 sequence.

    A naive single run() would stop at 'aborted' (terminal) and miss the afternoon.
    replay_buypoint must RESTART the state machine after the abort and capture
    the afternoon buy_point_alert.
    """
    previous_high = 10.0
    # --- MORNING: baseline + breakout + deep crash → abort ---
    morning_bars = [
        # baseline window (3 bars)
        b("09:31", 9.80, 100.0),
        b("09:32", 9.82, 100.0),
        b("09:33", 9.85, 100.0),
        # breakout
        b("09:34", 10.20, 200.0),
        # pullback crashes > 5% below previous_high (10.0 * 0.95 = 9.5 → go below 9.5)
        b("09:35", 9.30,  180.0),  # drawdown = (10.0 - 9.30) / 10.0 * 100 = 7.0% > 5% → ABORT
    ]
    # --- AFTERNOON: clean breakout → pullback (no deep crash) → resurge → alert ---
    afternoon_bars = [
        # some quiet bars after the abort
        b("13:01", 9.60,  80.0),
        b("13:02", 9.70,  90.0),
        b("13:03", 9.75,  85.0),
        # breakout again
        b("13:04", 10.30, 220.0),  # vol_ratio = 220 / 100 = 2.2 >= 1.5 ✓ (baseline still 100)
        # pullback but shallow (stays above 9.5)
        b("13:05", 10.05, 55.0),   # shrink = 55/220 = 0.25 <= 0.7 ✓
        b("13:06", 9.95,  45.0),   # shrink = 45/220 = 0.20 <= 0.7 ✓
        # re-surge: strength = (10.20 - 9.95) / (10.30 - 9.95) = 0.25 / 0.35 = 0.714 >= 0.5 ✓
        b("13:07", 10.20, 100.0),
    ]

    bars = morning_bars + afternoon_bars
    snap = snapshot(bars)

    signals = replay_buypoint(snap, previous_high=previous_high, thresholds=DEFAULT_THRESHOLDS)

    alerts = [s for s in signals if s.state == "buy_point_alert"]
    assert len(alerts) >= 1, (
        f"Expected afternoon buy_point_alert but got states: {[s.state for s in signals]}. "
        "The multi-setup restart is likely broken — check that replay resets to idle after abort."
    )
    # The alert should be from the afternoon bars
    alert = alerts[0]
    assert alert.triggered_at.startswith("13:"), (
        f"Expected afternoon alert (13:xx) but triggered_at={alert.triggered_at!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: same_theme_co_pumping_count propagated
# ---------------------------------------------------------------------------

def test_replay_records_same_theme_co_pumping_count():
    """same_theme_rising_count=5 must appear on every emitted signal."""
    previous_high = 10.0
    bars = [
        b("09:31", 9.80, 100.0),
        b("09:32", 9.82, 100.0),
        b("09:33", 9.85, 100.0),
        b("09:34", 10.20, 200.0),  # breakout
        b("09:35", 9.90,  50.0),   # pullback
        b("09:36", 10.10, 80.0),   # resurge → alert
    ]
    snap = snapshot(bars)

    signals = replay_buypoint(
        snap,
        previous_high=previous_high,
        thresholds=DEFAULT_THRESHOLDS,
        same_theme_rising_count=5,
    )

    alerts = [s for s in signals if s.state == "buy_point_alert"]
    assert len(alerts) >= 1, "No alert emitted"
    for alert in alerts:
        assert alert.same_theme_co_pumping_count == 5, (
            f"Expected same_theme_co_pumping_count=5 but got {alert.same_theme_co_pumping_count}"
        )


# ---------------------------------------------------------------------------
# Test 6: empty bars returns empty list
# ---------------------------------------------------------------------------

def test_replay_empty_bars_returns_empty():
    """A snapshot with no bars must return an empty list immediately."""
    snap = snapshot([])
    signals = replay_buypoint(snap, previous_high=10.0, thresholds=DEFAULT_THRESHOLDS)
    assert signals == [], f"Expected [] but got {signals}"


# ---------------------------------------------------------------------------
# Test 7: opening gap above prior high must NOT produce a spurious breakout
# (pins FIX 1 — circular baseline exclusion)
# ---------------------------------------------------------------------------

def test_replay_opening_gap_above_high_not_spurious_breakout():
    """An A-share stock that gaps up OPEN above previous_high on the highest
    volume of the day — a classic opening auction scenario — must NOT fire a
    buy_point_alert because the opening bars (inside the baseline window) are
    excluded from state machine evaluation.

    Without FIX 1 this bar would be simultaneously:
      - the numerator of its own vol_ratio (breakout_volume = 500)
      - part of the baseline denominator → baseline = mean([500, 50, 50]) ≈ 200
      → vol_ratio = 500 / 200 = 2.5 >= 1.5 → spurious broke_high on bar 1

    With FIX 1 the machine only runs over bars[3:], so bar 0 is never evaluated.
    The rest of the day has no further breakout above previous_high, so no alert.
    """
    previous_high = 10.0
    bars = [
        # --- Baseline window (indices 0-2): gap-up opening bar is IN here ---
        b("09:31", 10.50, 500.0),  # gaps up ABOVE previous_high, massive volume
        b("09:32", 10.20,  50.0),  # subsequent quiet auction bars
        b("09:33", 10.10,  50.0),
        # --- Post-baseline bars (indices 3+): machine runs here ---
        # Price stays near 10.10 — never re-breaks 10.0 with volume
        b("09:34",  9.90,  60.0),
        b("09:35",  9.80,  55.0),
        b("09:36",  9.85,  50.0),
        b("09:37",  9.90,  45.0),
    ]
    snap = snapshot(bars)

    signals = replay_buypoint(
        snap,
        previous_high=previous_high,
        thresholds=DEFAULT_THRESHOLDS,
        baseline_window=3,
    )

    alerts = [s for s in signals if s.state == "buy_point_alert"]
    assert alerts == [], (
        f"Opening gap bar must not produce a spurious buy_point_alert, "
        f"but got: {[s.state for s in signals]}. "
        "Check that baseline bars are excluded from state machine evaluation (FIX 1)."
    )


# ---------------------------------------------------------------------------
# Test 8: baseline_window=0 raises ValueError (pins FIX 2 — input guard)
# ---------------------------------------------------------------------------

def test_replay_baseline_window_zero_raises():
    """baseline_window=0 (or negative) must raise ValueError, not ZeroDivisionError."""
    snap = snapshot([b("09:31", 10.0, 100.0)])

    with pytest.raises(ValueError, match="baseline_window must be >= 1"):
        replay_buypoint(snap, previous_high=10.0, baseline_window=0)

    with pytest.raises(ValueError, match="baseline_window must be >= 1"):
        replay_buypoint(snap, previous_high=10.0, baseline_window=-1)


# ---------------------------------------------------------------------------
# Test 9: a FIRED buy_point_alert carries no order-related fields (Task 4.4)
# ---------------------------------------------------------------------------

def test_fired_signal_has_no_order_field():
    """Non-vacuous safety lock: a genuinely FIRED buy_point_alert must carry
    no order-related key or directive language.

    The signal list MUST be non-empty (asserted first) so the per-signal
    assertions cannot pass vacuously on an empty list.

    Checked per signal (model_dump()):
    - no key in {"buy", "sell", "action", "order", "position"}
    - no *action-form* order directives: 卖出, 下单, 全仓, 梭哈, 买入吧, 去买, 立即买
      NOTE: "买入" appears legitimately in the evidence audit trail as the pattern
      label "买入预警" (buy-point alert), which is a MEASUREMENT label, not an order
      instruction. The safety invariant is that no imperative order phrasing is
      present (e.g. 下单/全仓/梭哈/卖出). See state machine comment: "ALERT, never
      a buy/sell instruction."

    Bar sequence reused from test_replay_detects_full_buypoint (known to fire).
    """
    import json

    previous_high = 10.0
    bars = [
        # Baseline window (3 bars): avg volume = 100
        b("09:31", 9.80, 100.0),
        b("09:32", 9.82, 100.0),
        b("09:33", 9.85, 100.0),
        # Breakout: price > 10.0, vol_ratio = 200/100 = 2.0 >= 1.5 ✓
        b("09:34", 10.20, 200.0),
        # Pullback (缩量): stays above previous_high * 0.95 = 9.50
        b("09:35", 10.05, 60.0),
        b("09:36", 9.90,  50.0),
        # Re-surge: strength = (10.10-9.90)/(10.20-9.90) = 0.667 >= 0.5 ✓
        b("09:37", 10.10, 80.0),
    ]
    snap = snapshot(bars)

    signals = replay_buypoint(
        snap,
        previous_high=previous_high,
        thresholds=DEFAULT_THRESHOLDS,
        baseline_window=3,
    )

    # Guard: must have at least one fired alert so the loop below is non-vacuous.
    alerts = [s for s in signals if s.state == "buy_point_alert"]
    assert len(alerts) >= 1, (
        f"Expected at least one buy_point_alert but got states: "
        f"{[s.state for s in signals]}. "
        "Bar sequence must fire a signal for this safety test to be meaningful."
    )

    # Per-signal safety assertions.
    order_keys = {"buy", "sell", "action", "order", "position"}
    # Action-form directives that would constitute an actual trade order instruction.
    # "买入预警" is exempt: it is the technical pattern NAME, not an order.
    # We test for the imperative / action phrases that would instruct a trade.
    order_directives = ("卖出", "下单", "全仓", "梭哈", "买入吧", "去买", "立即买")

    for alert in alerts:
        dumped = alert.model_dump()
        serialised = json.dumps(dumped, ensure_ascii=False)

        # No order-related key present in the model.
        present_order_keys = order_keys & set(dumped.keys())
        assert not present_order_keys, (
            f"Order-related key(s) {present_order_keys} found in fired signal: {dumped}"
        )

        # No imperative order-directive phrase anywhere in the serialised signal.
        for phrase in order_directives:
            assert phrase not in serialised, (
                f"Order directive '{phrase}' found in fired signal JSON: {serialised}"
            )
