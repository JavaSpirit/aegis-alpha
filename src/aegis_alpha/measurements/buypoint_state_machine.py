"""Pure intraday buy-point state machine (Task 4.2).

Detects the 过前高(带量) → 回踩砸盘(缩量) → 重新上冲 = 买入预警点 pattern.

Design principles:
- PURE: no I/O, no datetime.now(), no random. All decisions from inputs + thresholds.
- FROZEN dataclass: state is immutable; transitions return new contexts via dataclasses.replace.
- Thresholds are INJECTED via BuyPointThresholds — never hardcoded.
- The machine outputs an ALERT, never a buy/sell instruction.
- State transitions are FACT determinations (price crossed prior high, volume ratio vs baseline).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from aegis_alpha.models import BuyPointState, BuyPointThresholds, MinuteReplayBar


@dataclass(frozen=True)
class BuyPointContext:
    """Immutable snapshot of the state machine at any point in time.

    Fields split into two groups:
      - "input" fields: set at construction, carry session context (previous_high, baseline_volume)
      - "measured" fields: updated during transitions (prices, volumes, ratios, evidence)
    """
    state: BuyPointState = "idle"
    previous_high: float = 0.0          # the prior-session high to break (input)
    baseline_volume: float = 0.0        # avg volume baseline for ratio calcs (input)
    breakout_price: float = 0.0         # price at the breakout bar
    breakout_volume: float = 0.0        # volume at the breakout bar
    pullback_low: float = 0.0           # lowest price seen during pullback
    pullback_volume: float = 0.0        # representative (min) volume during pullback
    breakout_volume_ratio: float = 0.0  # measured: breakout bar vol / baseline vol
    pullback_volume_shrink_ratio: float = 0.0  # measured: pullback vol / breakout vol
    resurge_strength: float = 0.0       # measured: 0..1 recovery fraction toward breakout price
    triggered_at: str = ""              # bar time when buy_point_alert fired, else ""
    evidence: tuple[str, ...] = ()      # audit trail of transition facts


def step(
    context: BuyPointContext,
    bar: MinuteReplayBar,
    thresholds: BuyPointThresholds,
) -> BuyPointContext:
    """Advance the state machine by one minute bar.

    Pure function: returns a NEW BuyPointContext (never mutates the input).

    Transition table (each condition is a MEASURED fact):
      idle        → broke_high      : price > previous_high AND vol_ratio >= breakout_volume_ratio_min
      broke_high  → pullback        : last_price < breakout_price (retraced)
      broke_high  → aborted         : drawdown from previous_high > pullback_max_drawdown_pct (on first retrace bar)
      pullback    → aborted         : drawdown from previous_high > pullback_max_drawdown_pct
      pullback    → re_surge        : price turned UP from pullback_low AND shrink ratio qualifies
      re_surge    → aborted         : drawdown from previous_high > pullback_max_drawdown_pct (invariant: any state)
      re_surge    → buy_point_alert : resurge_strength >= resurge_strength_min
      buy_point_alert, aborted      : terminal — no further transitions
    """
    state = context.state

    # -----------------------------------------------------------------------
    # Terminal states — no further transitions
    # -----------------------------------------------------------------------
    if state in ("buy_point_alert", "aborted"):
        return context

    # -----------------------------------------------------------------------
    # Transition: idle → broke_high
    # -----------------------------------------------------------------------
    if state == "idle":
        if bar.last_price > context.previous_high:
            vol_ratio = bar.volume / context.baseline_volume if context.baseline_volume > 0 else 0.0
            if vol_ratio >= thresholds.breakout_volume_ratio_min:
                # Volume-confirmed breakout of prior high
                evidence_entry = (
                    f"过前高 at {bar.time}: price {bar.last_price} > prev_high "
                    f"{context.previous_high}, 量比 {vol_ratio:.4f}"
                )
                return replace(
                    context,
                    state="broke_high",
                    breakout_price=bar.last_price,
                    breakout_volume=bar.volume,
                    breakout_volume_ratio=vol_ratio,
                    evidence=context.evidence + (evidence_entry,),
                )
            # Price cleared high but volume insufficient — stay idle, record nothing
        return context

    # -----------------------------------------------------------------------
    # Transition: broke_high → pullback (or stay in broke_high updating context)
    # -----------------------------------------------------------------------
    if state == "broke_high":
        if bar.last_price < context.breakout_price:
            # Price has retraced from the breakout level — enter pullback
            pullback_vol = bar.volume
            shrink_ratio = (
                pullback_vol / context.breakout_volume
                if context.breakout_volume > 0 else 0.0
            )
            # Check abort: did the price crash more than pullback_max_drawdown_pct below previous_high?
            drawdown_pct = (
                (context.previous_high - bar.last_price) / context.previous_high * 100.0
                if context.previous_high > 0 else 0.0
            )
            if drawdown_pct > thresholds.pullback_max_drawdown_pct:
                evidence_entry = (
                    f"砸破位 at {bar.time}: price {bar.last_price} drawdown "
                    f"{drawdown_pct:.2f}% > max {thresholds.pullback_max_drawdown_pct}% — aborted"
                )
                return replace(
                    context,
                    state="aborted",
                    pullback_low=bar.last_price,
                    pullback_volume=pullback_vol,
                    pullback_volume_shrink_ratio=shrink_ratio,
                    evidence=context.evidence + (evidence_entry,),
                )
            evidence_entry = (
                f"回踩 at {bar.time}: price {bar.last_price} < breakout {context.breakout_price}, "
                f"缩量比 {shrink_ratio:.4f}"
            )
            return replace(
                context,
                state="pullback",
                pullback_low=bar.last_price,
                pullback_volume=pullback_vol,
                pullback_volume_shrink_ratio=shrink_ratio,
                evidence=context.evidence + (evidence_entry,),
            )
        # Price still above/at breakout level — stay in broke_high
        return context

    # -----------------------------------------------------------------------
    # Transition: pullback → (update pullback low) → re_surge / aborted / stay
    # -----------------------------------------------------------------------
    if state == "pullback":
        # First: check abort on any bar during pullback
        drawdown_pct = (
            (context.previous_high - bar.last_price) / context.previous_high * 100.0
            if context.previous_high > 0 else 0.0
        )
        if drawdown_pct > thresholds.pullback_max_drawdown_pct:
            evidence_entry = (
                f"砸破位 at {bar.time}: price {bar.last_price} drawdown "
                f"{drawdown_pct:.2f}% > max {thresholds.pullback_max_drawdown_pct}% — aborted"
            )
            return replace(
                context,
                state="aborted",
                evidence=context.evidence + (evidence_entry,),
            )

        # Update pullback tracking: track the minimum price and minimum volume
        new_pullback_low = min(context.pullback_low, bar.last_price)
        new_pullback_volume = min(context.pullback_volume, bar.volume)
        new_shrink_ratio = (
            new_pullback_volume / context.breakout_volume
            if context.breakout_volume > 0 else 0.0
        )

        # Check if price has turned up from the pullback low (started re-surging)
        if bar.last_price > context.pullback_low:
            # Price turning up — check if this qualifies as a clean re-surge
            # (requires that the pullback volume dried up sufficiently)
            if new_shrink_ratio <= thresholds.pullback_volume_shrink_max:
                # Volume dried up during the dip ✓ — measure re-surge strength
                range_span = context.breakout_price - context.pullback_low
                if range_span > 0:
                    strength = (bar.last_price - context.pullback_low) / range_span
                    strength = max(0.0, min(1.0, strength))  # clamp to [0, 1]
                else:
                    strength = 1.0  # degenerate: no range, call it full recovery

                evidence_resurge = (
                    f"重新上冲 at {bar.time}: price {bar.last_price}, "
                    f"strength {strength:.4f}, pullback_low {context.pullback_low}"
                )

                if strength >= thresholds.resurge_strength_min:
                    # Strong enough → buy_point_alert
                    evidence_alert = (
                        f"买入预警 at {bar.time}: resurge_strength {strength:.4f} "
                        f">= {thresholds.resurge_strength_min}"
                    )
                    return replace(
                        context,
                        state="buy_point_alert",
                        pullback_low=new_pullback_low,
                        pullback_volume=new_pullback_volume,
                        pullback_volume_shrink_ratio=new_shrink_ratio,
                        resurge_strength=strength,
                        triggered_at=bar.time,
                        evidence=context.evidence + (evidence_resurge, evidence_alert),
                    )
                else:
                    # Re-surge started but not strong enough yet
                    return replace(
                        context,
                        state="re_surge",
                        pullback_low=new_pullback_low,
                        pullback_volume=new_pullback_volume,
                        pullback_volume_shrink_ratio=new_shrink_ratio,
                        resurge_strength=strength,
                        evidence=context.evidence + (evidence_resurge,),
                    )
            else:
                # Volume did NOT dry up during the pullback — do not advance to re_surge/alert
                # Stay in pullback, update tracking fields
                return replace(
                    context,
                    state="pullback",
                    pullback_low=new_pullback_low,
                    pullback_volume=new_pullback_volume,
                    pullback_volume_shrink_ratio=new_shrink_ratio,
                )

        # Price still declining or flat — update pullback tracking, stay in pullback
        return replace(
            context,
            pullback_low=new_pullback_low,
            pullback_volume=new_pullback_volume,
            pullback_volume_shrink_ratio=new_shrink_ratio,
        )

    # -----------------------------------------------------------------------
    # Transition: re_surge → buy_point_alert (or stay re_surge)
    # -----------------------------------------------------------------------
    if state == "re_surge":
        # BUG 1 FIX: check drawdown abort guard FIRST, same invariant as pullback.
        # In ANY non-terminal state, drawdown > max → abort immediately.
        drawdown_pct = (
            (context.previous_high - bar.last_price) / context.previous_high * 100.0
            if context.previous_high > 0 else 0.0
        )
        if drawdown_pct > thresholds.pullback_max_drawdown_pct:
            evidence_entry = (
                f"砸破位 at {bar.time}: price {bar.last_price} drawdown "
                f"{drawdown_pct:.2f}% > max {thresholds.pullback_max_drawdown_pct}% — aborted"
            )
            return replace(context, state="aborted", evidence=context.evidence + (evidence_entry,))

        # BUG 2 FIX: update pullback_low when a new low is printed in re_surge.
        # A bar below the recorded pullback_low shifts the real recovery anchor;
        # using the stale low would overstate resurge_strength in the denominator.
        new_pullback_low = min(context.pullback_low, bar.last_price)

        # Re-measure resurge strength with the latest bar, anchored from the real low.
        range_span = context.breakout_price - new_pullback_low
        if range_span > 0:
            strength = (bar.last_price - new_pullback_low) / range_span
            strength = max(0.0, min(1.0, strength))
        else:
            # invariant: range_span > 0 in normal flow (pullback requires last_price < breakout_price); defensive only
            strength = 1.0

        if strength >= thresholds.resurge_strength_min:
            evidence_entry = (
                f"买入预警 at {bar.time}: resurge_strength {strength:.4f} "
                f">= {thresholds.resurge_strength_min}"
            )
            return replace(
                context,
                state="buy_point_alert",
                pullback_low=new_pullback_low,
                resurge_strength=strength,
                triggered_at=bar.time,
                evidence=context.evidence + (evidence_entry,),
            )

        # Still building strength — carry updated pullback_low and latest strength
        return replace(context, pullback_low=new_pullback_low, resurge_strength=strength)

    # Fallback — should not normally be reached
    return context


def run(
    bars: list[MinuteReplayBar],
    *,
    previous_high: float,
    baseline_volume: float,
    thresholds: BuyPointThresholds | None = None,
) -> BuyPointContext:
    """Fold `step` over a list of bars starting from idle.

    Args:
        bars: Ordered list of MinuteReplayBar objects (chronological).
        previous_high: The prior-session high price to break.
        baseline_volume: Average volume baseline for ratio calculations.
        thresholds: Injected thresholds. If None, uses BuyPointThresholds() defaults.

    Returns:
        Final BuyPointContext after processing all bars.
    """
    if thresholds is None:
        thresholds = BuyPointThresholds()

    ctx = BuyPointContext(
        previous_high=previous_high,
        baseline_volume=baseline_volume,
    )
    for bar in bars:
        ctx = step(ctx, bar, thresholds)
    return ctx
