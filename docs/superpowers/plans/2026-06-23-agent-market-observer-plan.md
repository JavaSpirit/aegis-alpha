# Agent Market Observer Plan

Date: 2026-06-23

## Context

The current system has a working realtime spine:

- `AegisAlphaRunner` ingests jvQuant realtime feeds.
- The runner writes structured `SignalSnapshot`, `MarketEvent`, and `AgentAlert` records.
- Realtime discovery expands the monitored universe beyond the prior export pool.
- WeClaw can deliver high-value alerts to WeChat after the user has established a ClawBot conversation.

The weak point is not the runner. The weak point is that the agent mostly explains outputs that the program has already decided. That underuses the project's intended advantage: agent-assisted judgment under imperfect data.

This plan shifts the product from:

```text
program triggers -> agent explains
```

to:

```text
program produces facts/events -> agent investigates, classifies, explains, and records observations
```

The runner should remain deterministic and read-only. Agent work should happen through MCP tools, Hermes jobs/webhooks, and recorded observation artifacts.

## Product Goal

Build an agent layer that can:

1. Enrich formal strategy triggers before notification.
2. Notice strategy-adjacent market information even when no buy point fires.
3. Maintain an intraday market-observation stream with evidence, confidence, and data gaps.
4. Push concise WeChat messages only when the agent's synthesis is worth interrupting the user.
5. Create reviewable records so every agent observation can be audited after market close.

## Non-Goals

- Do not let the agent place orders.
- Do not let the agent directly mutate runner subscription state.
- Do not let the agent directly consume raw WebSocket payloads.
- Do not loosen the existing `BUYPOINT_ALERT` state machine.
- Do not pretend missing data is available. Proxy evidence must be labelled.
- Do not spam WeChat with raw high-frequency events.

## Desired Runtime Shape

```text
jvQuant realtime/query facts
  -> runner
  -> snapshots/events/alerts in SQLite
  -> MCP fact tools
  -> Hermes agent workflows
  -> AgentObservation records
  -> WeClaw notification policy
```

The agent consumes structured facts and writes structured observations. The program owns collection, persistence, deterministic triggers, and delivery.

## New Concept: AgentObservation

Add a first-class record for agent-generated market observations.

Suggested fields:

- `observation_id`
- `created_at`
- `trading_day`
- `source`
  - `trigger_enrichment`
  - `periodic_market_scan`
  - `manual_wechat_query`
  - `post_close_review`
- `observation_type`
  - `buy_point_quality`
  - `watchlist_observation`
  - `market_regime_shift`
  - `theme_rotation`
  - `strong_continuation_without_buy_point`
  - `noise_or_rejected_trigger`
  - `data_gap`
- `severity`
  - `info`
  - `watch`
  - `important`
  - `urgent`
- `symbol`
- `theme`
- `title`
- `summary`
- `stance`
  - `actionable_watch`
  - `monitor_only`
  - `reject`
  - `insufficient_data`
- `confidence`
  - `low`
  - `medium`
  - `high`
- `evidence`
- `counter_evidence`
- `data_gaps`
- `linked_event_ids`
- `linked_alert_ids`
- `expires_at`
- `payload_json`

This is not a trade instruction. It is the agent's auditable interpretation of current market facts.

## Phase 1: Fact Packets For Agent Investigation

Create MCP tools that give the agent compact, strategy-relevant context packets.

### Tool: `get_realtime_symbol_context(symbol, lookback_minutes=30)`

Return:

- latest snapshot
- price/change/speed windows
- large-trade proxy stats
- orderbook/seal proxy facts
- recent events for the symbol
- known data gaps
- whether facts are realtime, delayed, current-provider proxy, or historical

### Tool: `get_intraday_theme_context(theme_or_symbol, lookback_minutes=30)`

Return:

- related symbols from current runner universe
- same-theme `APPROACHING_LIMIT_UP`, `BIG_ORDER_INFLOW_SPIKE`, `SEAL_ORDER_DECAY`
- limit-up pool overlap
- active turnover symbols in the same theme/industry
- whether theme evidence is direct or proxy

### Tool: `get_intraday_market_context(lookback_minutes=30)`

Return:

- runner health
- monitored symbol count
- recent event counts by type
- strongest large-order proxy symbols
- approaching-limit-up symbols
- most repeated seal-decay symbols
- theme concentration if available
- data freshness summary

Acceptance criteria:

- Tools are facts-only.
- Each response labels proxy/missing data.
- Tools are fast enough for Hermes calls.
- Unit tests cover empty DB, stale data, and normal intraday data.

## Phase 2: Agent Trigger Enrichment

When the program creates a formal or near-formal alert, Hermes should be able to enrich it.

Trigger sources:

- `BUYPOINT_ALERT`
- high-confidence `APPROACHING_LIMIT_UP`
- repeated `BIG_ORDER_INFLOW_SPIKE`
- repeated `SEAL_ORDER_DECAY` on strategy-relevant names
- `SELECTION_VALIDATION`

Agent workflow:

1. Read alert/event.
2. Call `get_realtime_symbol_context`.
3. Call `get_intraday_theme_context`.
4. Call `get_intraday_market_context`.
5. Produce an `AgentObservation`.
6. Decide notification grade:
   - `urgent`: formal buy-point quality is high.
   - `important`: no formal buy point, but strategy-adjacent information is notable.
   - `watch`: useful but not urgent.
   - `suppress`: noisy or insufficient.

Acceptance criteria:

- Agent output must explicitly separate:
  - trigger facts
  - confirming evidence
  - counter-evidence
  - missing data
  - conclusion
- Agent cannot output buy/sell instructions.
- WeClaw only receives `urgent` and selected `important` observations.

## Phase 3: Periodic Market Observer

Add a periodic Hermes job during trading sessions.

Suggested schedule:

- `09:42`
- `10:15`
- `11:18`
- `13:35`
- `14:20`
- `14:55`

The observer asks:

```text
Given the latest intraday market context, is there anything strategy-relevant or market-relevant that did not become a formal buy-point alert?
```

Agent should look for:

- theme rotation
- same-theme multi-symbol movement
- large-order proxy clusters
- strong continuation without buy-point
- important symbols that nearly triggered but failed
- market regime shift
- repeated data-quality failures

Acceptance criteria:

- It may output zero observations.
- It should not force a conclusion.
- It must not re-notify the same observation repeatedly.
- It must use `AgentObservation` records for deduplication.

## Phase 4: WeClaw Notification Policy

Current WeClaw push is intentionally conservative. Keep raw event pushes disabled.

New notification flow:

```text
AgentObservation
  -> notification policy
  -> WeClaw /api/send
```

Notification candidates:

- `urgent` buy-point quality observations
- `important` market-regime shifts
- `important` theme-rotation observations
- post-close summary if the day produced meaningful observations

Do not notify:

- raw `SEAL_ORDER_DECAY`
- repeated raw `BIG_ORDER_INFLOW_SPIKE`
- low-confidence data gaps unless they affect liveness

Message format:

```text
[Aegis] 观察/预警标题
结论：...
依据：...
风险/缺口：...
下一步观察：...
```

Acceptance criteria:

- WeClaw failures do not affect runner liveness.
- Notification target remains env-only.
- Messages are short enough for WeChat.
- A notification has a linked `AgentObservation`.

## Phase 5: Post-Close Observation Review

Replace the current "Top3 is the center" review mindset with "real triggered/observed situations are the center".

Post-close agent should review:

- all `BUYPOINT_ALERT`
- all notified `AgentObservation`
- all suppressed but high-signal observations
- near misses

Review questions:

- Did the observation identify useful market information?
- Did the evidence age well by close?
- Was the confidence too high or too low?
- Which data gaps mattered?
- Should the program add a new event detector or MCP context field?

Acceptance criteria:

- Review writes structured records, not just prose.
- The review can be queried from WeChat.
- The review can produce concrete follow-up issues without automatically changing strategy.

## Phase 6: Keep Top3, But Demote It

Keep daily Top3 audit as a research and calibration tool, not as the main product path.

Top3 remains useful for:

- checking whether the agent can reason from prior-day facts
- building a small human-review slate
- comparing agent expectations with next-day reality

But product priority should be:

1. Realtime trigger enrichment.
2. Strategy-adjacent market observations.
3. Post-close review of actual observations.
4. Daily Top3 audit.

## Implementation Order

1. Add `AgentObservation` model, storage, and tests.
2. Add MCP tools for realtime symbol/theme/market context.
3. Add a manual CLI/script to run one market-observer pass against current DB.
4. Add Hermes prompt/job for trigger enrichment.
5. Add Hermes prompt/job for periodic market observer.
6. Add WeClaw notification policy for `AgentObservation`.
7. Add post-close observation review.
8. Update docs and WeChat command surface.

## Suggested Tests

- Storage round-trip tests for `AgentObservation`.
- MCP context tests for empty/stale/fresh data.
- Notification policy tests for urgent/important/watch/suppress.
- Golden-output tests for prompt inputs and required JSON shape.
- End-to-end dry run:
  - seed snapshots/events
  - run market observer
  - record observations
  - verify only eligible observations notify

## Manual Verification Path

During a trading day:

1. Confirm runner `RUNNING`.
2. Confirm realtime discovery has `runtime_symbols > base`.
3. Ask WeChat:
   - `/aegis 今日观察`
   - `/aegis 异动`
   - `/aegis 002167`
4. Run one observer pass manually.
5. Verify an `AgentObservation` is created.
6. Verify WeClaw notification only fires for selected severity.

## Definition Of Done

- The system can produce an agent observation even when no `BUYPOINT_ALERT` fires.
- The observation includes evidence, counter-evidence, confidence, and data gaps.
- The observation is persisted and reviewable.
- WeChat receives only concise, high-value summaries.
- Post-close review focuses on real observations and triggers, not only daily Top3.
