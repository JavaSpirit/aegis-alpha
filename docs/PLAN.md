# Aegis Alpha Plan

## Summary

Aegis Alpha starts as a Hermes companion plus read-only MCP server. Its first product focus is a second-board radar: decide whether the market is suitable for board-chasing, then monitor yesterday limit-up stocks that may advance to a second board.

The long-term direction is a layered trading assistant:

```text
Hermes memory and skills
  -> Aegis Alpha MCP tools
  -> Market-data adapters
  -> Second-board signal and risk engines
  -> Paper trading
  -> Controlled real trading
```

## Phase 0: Hermes Companion Setup

Provide a thin helper around the official Hermes installer and document how to register Aegis Alpha in `~/.hermes/config.yaml`.

Rules:

- Do not fork Hermes.
- Do not patch Hermes.
- Do not vendor Hermes code.
- Use documented MCP configuration as the integration surface.
- Keep installer execution explicit through `scripts/install_hermes.sh --run`.

## Phase 1: Read-Only MCP

Build a safe second-board watchlist assistant with mock data first, then connect authorized market-data providers.

Initial tools:

- `get_market_snapshot`
- `get_market_sentiment_gate`
- `get_limitup_pool`
- `get_break_board_pool`
- `get_stock_realtime_snapshot`
- `get_stock_orderbook_snapshot`
- `get_stock_minute_replay_snapshot`
- `get_stock_history_limitup_stats`
- `get_theme_strength`
- `get_second_board_candidates`
- `explain_candidate`
- `explain_second_board_candidate`

The output must stay structured, timestamped, and explicit about data quality. `explain_candidate` must describe observations, risks, trigger conditions, and avoid conditions instead of issuing buy or sell instructions.

## Phase 2: Morning Second-Board Radar

Add real-time adapters for providers such as jvQuant, StockApi, MyQuant, or miniQMT.

Current jvQuant-backed coverage includes market gate, limit-up pool, break-board pool, single-symbol snapshots, orderbook snapshots, minute replay snapshots, a coarse second-board candidate pool, semantic-query auction metrics, Aegis-calculated 1/3/5/10-minute speed structure from minute replay when available, semantic-query speed fallback with parsed provider windows, semantic-query capital-flow net inflow ratio, concept/topic tags, first/final seal time, seal amount, max seal amount, seal volume, break/reseal counts, and seal-to-turnover ratio. Tick-level recalculation is still pending. True own-order queue position still requires broker order/trade callbacks, so Aegis Alpha currently exposes a read-only queue-position note instead of a real order position. The next gaps are tick-level big-order classification and historical follow-through statistics.

The candidate contract now includes `data_quality` metadata per core signal. Keep expanding this layer before making strategy decisions stricter: every signal should declare its provider source, raw field name, timestamp, confidence, grading usability, limitations, and evidence. Evidence authority must distinguish official docs, observed API probes, and internal inference.

Capability discovery now has two tracks:

- Official documentation index: [JVQUANT_OFFICIAL_INDEX.md](JVQUANT_OFFICIAL_INDEX.md)
- Observed semantic-query capability matrix: [JVQUANT_CAPABILITY_MATRIX.md](JVQUANT_CAPABILITY_MATRIX.md)

Core indicators:

- Market sentiment gate.
- Yesterday limit-up pool.
- Second-board candidate pool.
- First limit-up time, seal amount, seal volume, and seal-to-turnover ratio.
- Queue-position note from orderbook summary; real queue position only after broker order tracking exists.
- Limit-up pool and break-board pool.
- Break-board rate.
- 5-minute speed.
- Big-order net inflow.
- Order-book quality.
- Theme strength.
- Same-theme rising count and leader status.
- Historical limit-up success rate.
- Historical next-day premium.
- Historical third-day premium after sealed second board.

The first production-grade scoring output should use grades such as `A`, `B`, `C`, and `REJECT`.

## Phase 2.5: Realtime Events And Local Data Layer

WebSocket should drive the local market engine, not the agent directly. The first event-driven layer includes:

- jvQuant WebSocket wrapper for `lv1`, `lv2`, and `lv10` subscription management.
- `SignalWindowBuffer` for rolling 1/3/5/10-minute speed and big-order flow calculations.
- `MarketEvent` and `SignalSnapshot` contracts for agent-safe structured outputs.
- `config/event_scoring.yaml` for configurable event triggers, weights, freshness limits, and suggested agent actions.
- SQLite storage for `market_events`, `signal_snapshots`, `candidate_scores`, `agent_reviews`, `agent_review_corrections`, `provider_runs`, and `review_outcomes`.
- Parquet storage boundary for future minute bars, Level-2 trades, and orderbook snapshots. Parquet writing is reserved until a dedicated pyarrow-backed persistence step.

Initial event types:

- `THEME_CLUSTER_RISING`
- `APPROACHING_LIMIT_UP`
- `SEAL_ORDER_DECAY`
- `BIG_ORDER_INFLOW_SPIKE`
- `SECOND_BOARD_CANDIDATE_REPRICE`

Agent-facing tools:

- `get_recent_market_events`
- `get_signal_snapshot`
- `get_event_scoring_config`
- `get_realtime_connection_status`
- `get_runner_status`
- `explain_market_event`
- `review_candidate_outcome`
- `record_candidate_outcome`
- `get_recent_agent_reviews`
- `record_agent_review_correction`
- `get_agent_correction_summary`

Raw WebSocket messages must not be exposed through MCP. Hermes should only consume events, signal snapshots, and explanations.

Agent review corrections should be chat-first. Hermes can record a user's correction through MCP, then inspect repeated patterns and decide whether to update memory, patch the Aegis Alpha skill, adjust scoring config, or send the issue back to adapter code. Aegis Alpha stores correction evidence and returns structured `recommended_actions`; it does not automatically mutate Hermes memory, skills, or scoring config.

## Phase 2.6: Launchd-Managed Runner

The realtime engine should run as a macOS LaunchAgent, not as a Hermes child process.

- `aegis-alpha-runner` is the long-lived process entrypoint.
- `config/runner.yaml` controls trading sessions, subscription symbols, levels, loop interval, reconnect interval, and storage paths.
- `.launchd/com.aegis-alpha.runner.plist.template` is rendered into `~/Library/LaunchAgents/com.aegis-alpha.runner.plist`.
- `scripts/install_launchd_runner.sh` installs and bootstraps the service; `--no-load` installs without starting.
- `scripts/uninstall_launchd_runner.sh` unloads the service.
- `scripts/check_runner_status.sh` reports both launchd state and `data/runner_status.json`.

Lifecycle boundary:

- launchd keeps the runner process alive.
- The runner opens jvQuant subscriptions only during configured trading sessions.
- The runner writes local status, snapshots, events, and provider run records.
- MCP reads runner-produced SQLite events and snapshots first; provider queries are fallback paths when the local store is empty.
- MCP and Hermes only read local state; they do not own the realtime process.

## Phase 3: Review And Correction

Add daily review records so Hermes can learn user preferences through skills.

Examples:

- Which candidates were promoted.
- Which candidates were rejected.
- Whether a board stayed sealed.
- Next-day premium.
- User corrections.
- Rule changes extracted into Hermes skills.

This phase turns Aegis Alpha from a static screener into a feedback-driven assistant.

Second-board reviews should record:

- Whether the candidate reached the limit-up price.
- Whether the second board sealed.
- Whether it broke board after sealing.
- Next-day open and intraday high.
- Third-day premium after a sealed second board.

## Phase 4: Medium And Long-Term Module

Add a separate research path for medium and long-term analysis. It should not reuse short-term limit-up scoring.

Candidate tools:

- Fundamentals.
- Valuation history.
- Industry comparison.
- Financial statements.
- News and event risk.
- Factor screening through Qlib, Hikyuu, or custom research code.

## Phase 5: Paper Trading

Add paper-trading tools before any real order integration.

Candidate tools:

- `create_paper_order`
- `close_paper_position`
- `get_paper_portfolio`
- `review_paper_trade`

Paper trading validates signal quality, user preference learning, risk rules, and operational workflow.

## Phase 6: Controlled Real Trading

Real trading is out of scope for the MVP. If added later, it must be a narrow, auditable, two-step flow:

```text
Hermes proposes
  -> risk engine validates
  -> user confirms
  -> trading adapter executes
```

Required controls:

- Real trading disabled by default.
- Single-position limits.
- Daily loss limits.
- Daily order count limits.
- Symbol blacklist.
- Duplicate-order prevention.
- Price deviation checks.
- Global kill switch.
- Human confirmation.
