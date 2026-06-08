"""Offline buy-point replay over a day's minute bars (Task 4.3).

Drives the buy-point state machine over a :class:`MinuteReplaySnapshot`, handles
multi-setup-per-day restarts, and returns a list of
:class:`~aegis_alpha.models.IntradayBuyPointSignal`.

Why a separate module (not in ``buypoint_state_machine.py``):
  The state machine module is pure fold/step logic (~306 lines).  This module
  is orchestration — it computes baseline volume, manages the restart loop, and
  maps ``BuyPointContext`` → ``IntradayBuyPointSignal``.  Keeping them separate
  preserves high cohesion: the state-machine file never imports model-level
  orchestration types, and the replay file never reimplements state logic.

Baseline window vs machine evaluation
--------------------------------------
The opening ``baseline_window`` bars establish the volume baseline (mean volume
used for all ratio calculations) and are **NOT evaluated for breakouts**.  The
state machine only runs over ``bars[baseline_window:]``.

Rationale: A-share stocks frequently gap up open above the prior high with the
day's highest volume.  If opening bars were both used as the volume denominator
AND evaluated by the machine, the first bar could simultaneously inflate the
baseline AND satisfy the breakout threshold — circular self-referential logic
that produces spurious signals before the opening auction even settles.

Returned-list contract
----------------------
* **When at least one buy_point_alert fires**: the list contains exactly one
  ``IntradayBuyPointSignal`` per alert, in chronological order.  ``aborted``
  attempts are NOT included — the list is a "buy-point timeline" of confirmed
  alerts only.

* **When NO alert fires** (including zero-bar snapshots, which return
  immediately): the list is **empty**.  Callers that want to know "the machine
  ran but found nothing" should check ``len(signals) == 0``.

  Rationale: adding a sentinel "nothing happened" signal would force every
  downstream consumer to filter it out.  An empty list is the cleaner contract.

Design guarantees
-----------------
* **Deterministic**: no ``datetime.now()``, no random.  Same snapshot → same
  result every time.
* **Pure**: no I/O, no mutation of input objects.
* **No buy/sell instructions**: this module only emits *signals*.
"""
from __future__ import annotations

from aegis_alpha.measurements.buypoint_state_machine import BuyPointContext, step
from aegis_alpha.models import (
    BuyPointThresholds,
    IntradayBuyPointSignal,
    MinuteReplaySnapshot,
)

__all__ = ["replay_buypoint"]


def replay_buypoint(
    snapshot: MinuteReplaySnapshot,
    *,
    previous_high: float,
    thresholds: BuyPointThresholds | None = None,
    same_theme_rising_count: int = 0,
    baseline_window: int = 3,
) -> list[IntradayBuyPointSignal]:
    """Replay the buy-point state machine over a full day of minute bars.

    Args:
        snapshot: The minute-replay snapshot for one symbol on one trading day.
        previous_high: Prior-session high price.  The state machine watches for
            a volume-confirmed breakout above this level.
        thresholds: Optional injected thresholds.  If *None*, uses
            ``BuyPointThresholds()`` defaults.
        same_theme_rising_count: Fixed count for the session, propagated
            verbatim to all emitted signals as ``same_theme_co_pumping_count``.
        baseline_window: Number of opening bars used to compute the volume
            baseline.  Must be >= 1.  These bars establish the mean volume
            denominator for all ratio calculations and are **not evaluated for
            breakouts** — the state machine runs over ``bars[baseline_window:]``
            only.  If there are fewer total bars than *baseline_window*, the
            mean of all available bars is used as the baseline and the machine
            has no bars to evaluate (returns ``[]``).

    Returns:
        A list of :class:`IntradayBuyPointSignal` objects, one per
        ``buy_point_alert`` that fired during the day, in chronological order.
        Returns ``[]`` if no alert fired (including the case of an empty bar
        list or fewer bars than the baseline window).

        ``aborted`` attempts are NOT included in the list.

    Raises:
        ValueError: If *baseline_window* is 0 or negative.
    """
    if baseline_window <= 0:
        raise ValueError(f"baseline_window must be >= 1, got {baseline_window}")

    bars = snapshot.bars
    if not bars:
        return []

    if thresholds is None:
        thresholds = BuyPointThresholds()

    # ------------------------------------------------------------------
    # Compute baseline volume from the opening window only.
    # These bars are NOT fed to the state machine (see module docstring).
    # ------------------------------------------------------------------
    window = bars[:baseline_window]
    baseline_volume = sum(b.volume for b in window) / len(window)

    # ------------------------------------------------------------------
    # Fold step() over post-baseline bars only; restart on each terminal state
    # ------------------------------------------------------------------
    machine_bars = bars[baseline_window:]
    signals: list[IntradayBuyPointSignal] = []
    ctx = _fresh_context(previous_high=previous_high, baseline_volume=baseline_volume)

    for bar in machine_bars:
        ctx = step(ctx, bar, thresholds)

        if ctx.state in ("buy_point_alert", "aborted"):
            if ctx.state == "buy_point_alert":
                signals.append(
                    _build_signal(
                        ctx=ctx,
                        snapshot=snapshot,
                        same_theme_rising_count=same_theme_rising_count,
                    )
                )
            # Reset to idle for the next potential setup, carrying the same
            # previous_high and baseline_volume (both are session-level inputs).
            ctx = _fresh_context(previous_high=previous_high, baseline_volume=baseline_volume)

    return signals


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _fresh_context(*, previous_high: float, baseline_volume: float) -> BuyPointContext:
    """Return a fresh idle BuyPointContext seeded with session-level inputs."""
    return BuyPointContext(
        previous_high=previous_high,
        baseline_volume=baseline_volume,
    )


def _build_signal(
    ctx: BuyPointContext,
    snapshot: MinuteReplaySnapshot,
    same_theme_rising_count: int,
) -> IntradayBuyPointSignal:
    """Map a terminal BuyPointContext → IntradayBuyPointSignal."""
    return IntradayBuyPointSignal(
        symbol=snapshot.symbol,
        trading_day=snapshot.trading_day,
        data_mode=snapshot.data_mode,
        state=ctx.state,
        triggered_at=ctx.triggered_at,
        previous_high_price=ctx.previous_high,
        breakout_volume_ratio=ctx.breakout_volume_ratio,
        pullback_volume_shrink_ratio=ctx.pullback_volume_shrink_ratio,
        resurge_strength=ctx.resurge_strength,
        same_theme_co_pumping_count=same_theme_rising_count,
        evidence=list(ctx.evidence),
    )
