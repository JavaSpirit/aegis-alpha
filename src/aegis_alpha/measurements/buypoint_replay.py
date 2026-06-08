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
        same_theme_rising_count: Number of same-theme names that were rising at
            the time of the replay.  Propagated verbatim to every emitted signal
            as ``same_theme_co_pumping_count``.
        baseline_window: Number of opening bars used to compute the baseline
            volume.  The mean volume of the first *baseline_window* bars is used.
            If there are fewer bars than *baseline_window*, the mean of all
            available bars is used.

    Returns:
        A list of :class:`IntradayBuyPointSignal` objects, one per
        ``buy_point_alert`` that fired during the day, in chronological order.
        Returns ``[]`` if no alert fired (including the case of an empty bar
        list).

        ``aborted`` attempts are NOT included in the list.
    """
    bars = snapshot.bars
    if not bars:
        return []

    if thresholds is None:
        thresholds = BuyPointThresholds()

    # ------------------------------------------------------------------
    # Compute baseline volume from the opening window
    # ------------------------------------------------------------------
    window = bars[:baseline_window]
    baseline_volume = sum(b.volume for b in window) / len(window)

    # ------------------------------------------------------------------
    # Fold step() over bars; restart on each terminal state
    # ------------------------------------------------------------------
    signals: list[IntradayBuyPointSignal] = []
    ctx = _fresh_context(previous_high=previous_high, baseline_volume=baseline_volume)

    for bar in bars:
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
