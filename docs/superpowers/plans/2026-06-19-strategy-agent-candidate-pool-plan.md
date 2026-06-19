# Strategy Agent Candidate Pool Plan

Date: 2026-06-19

## Goal

Move Aegis Alpha from isolated second-board Q&A toward the user's target workflow:

1. Build a daily facts-only candidate pool at the close.
2. Let the agent select observation TopN from facts, not program scores.
3. Use target-day intraday facts only for replay, trigger validation, or live monitoring.
4. Keep missing data explicit instead of fabricating盘口, news, or sector breadth.

WeChat delivery is intentionally out of scope for this commit.

## Completed In This Change

- Added historical jvQuant fact helpers for strict as-of replay, first-board watchlists, large-turnover trend seeds, theme continuity, and next-day outcome labeling.
- Added broad strategy watchlist support that combines first-board candidates with large-turnover trend seeds and computes:
  - 10-day average turnover and pass/fail against 50 Yi.
  - T-1/as-of-day shrink ratio.
  - Previous-high and as-of high facts.
  - Market-internal two-week theme continuity.
  - Candidate source metadata and data coverage.
- Added `get_daily_strategy_candidate_pool(as_of_day, limit)` as the preferred first step for daily agent selection.
- Added `run_historical_strategy_replay` and `get_strategy_decision_packet` for target-day intraday replay facts without assigning grades or probabilities.
- Added order-flow capability separation:
  - Historical active big-order buy ratio is marked unavailable.
  - Daily capital-flow proxy is exposed as weak context.
  - Realtime lv2 large-trade sampling is directionless and must not be described as active buy ratio.
- Added packet-local same-theme co-pump facts, with full same-theme replay gated behind an explicit flag.
- Updated Hermes skill/config so agent workflows prefer `get_daily_strategy_candidate_pool` for close-day TopN selection and `get_strategy_decision_packet` for target-day replay.
- Added mock and adapter tests covering facts-only outputs, missing-data boundaries, replay windows, order-flow proxy semantics, and daily candidate pool metadata.

## Current Evidence

- Full test suite: `581 passed, 9 skipped, 1 warning`.
- Real jvQuant probe for `2026-06-17`:
  - `get_daily_strategy_candidate_pool(..., limit=20)` returned 20 candidates.
  - `get_daily_strategy_candidate_pool(..., limit=60)` returned 55 candidates.
  - The pool included `002491`, `300475`, and `002281`; their positions in the 55-name pool were 1, 4, and 20.
- Real jvQuant `get_strategy_decision_packet` for `002281|002491|300475` returned all three names and separated true facts from unavailable active big-order buy ratio.

## Known Gaps

- Full-market realtime sector breadth is not connected.
- Historical and realtime active big-order buy ratio are not available from the current lv2 payload shape.
- CLS popup alignment and off-platform news validation are not connected.
- Hermes one-shot interaction can be slow or stall in streaming; the MCP tools themselves are callable and tested independently.
- Daily candidate pool generation is usable but still relatively slow on real jvQuant because it enriches many names with kline facts and theme continuity.

## Next Plan

1. Build a repeatable Hermes workflow test:
   - Call `get_daily_strategy_candidate_pool`.
   - Require the agent to select Top5 from close-day facts only.
   - Assert it does not read target-day facts during initial selection.
   - Assert it does not treat provider order as ranking.

2. Add a lightweight candidate-pool mode:
   - Keep the current enriched mode for deep analysis.
   - Add a fast mode that returns seed facts first and enriches selected symbols after the agent narrows the pool.

3. Add agent selection audit output:
   - Capture selected TopN, rejected near-misses, relative reasons, and missing-data caveats.
   - Store enough structured output to compare against target-day replay later.

4. Connect target-day trigger validation:
   - Feed the agent-selected TopN into `get_strategy_decision_packet`.
   - Compare initial selection with 09:31-10:00 trigger facts.
   - Report where the agent's close-day reasoning succeeded or failed.

5. Improve data breadth:
   - Investigate a real source for active buy/sell large-order ratio.
   - Add CLS/news alignment only after a reliable source is found.
   - Replace packet-local co-pump with full-market sector breadth when a reliable source is available.
