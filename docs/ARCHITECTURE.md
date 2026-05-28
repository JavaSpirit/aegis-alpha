# Aegis Alpha Architecture

## Design Principle

Aegis Alpha separates reasoning from execution and integration from ownership.

Hermes may observe, summarize, ask questions, and propose second-board watchlist conditions. It should not directly hold broker credentials or place real orders. Aegis Alpha exposes a controlled MCP boundary and keeps risky capabilities behind explicit future modules.

Aegis Alpha does not fork or patch Hermes. It treats Hermes as an upstream runtime and integrates through documented MCP configuration.

## Runtime Shape

```text
Hermes Agent
  -> MCP client
  -> Aegis Alpha MCP Server
  -> MarketDataAdapter
  -> Signal models, market events, and explanation contracts
```

The MVP keeps `MockMarketDataAdapter` for contract tests and provides a read-only `JvQuantMarketDataAdapter` for live-provider snapshots. Real providers stay behind the same adapter boundary so the MCP tool contracts remain stable.

## Hermes Companion Boundary

Aegis Alpha may provide:

- Hermes install and verification helpers.
- Hermes MCP configuration examples.
- Trading-specific MCP tools.
- Trading-specific Hermes skill guidance.

Aegis Alpha must not:

- Vendor Hermes source code.
- Patch Hermes internals.
- Depend on undocumented Hermes storage or runtime internals.
- Expose real trading tools without a separate risk-controlled module.

## MCP Boundary

The MCP server exposes only read-only tools in the MVP:

- Market snapshot.
- Market sentiment gate.
- Limit-up pool.
- Break-board pool.
- Realtime stock snapshot.
- Orderbook snapshot.
- Signal snapshot.
- Recent market events.
- Event scoring configuration.
- Market event explanation.
- Candidate outcome review.
- Historical limit-up stats.
- Theme strength.
- Candidate explanation.
- Second-board candidates and explanation.

Each tool returns structured JSON-compatible data. Every response that depends on market data must include a timestamp or a clear mock-data note.

## Data Adapter Direction

Current jvQuant coverage:

- Semantic-query market snapshot, limit-up pool, and break-board pool.
- Coarse market sentiment gate derived from limit-up count, break-board rate, and theme breadth.
- Semantic-query second-board candidate pool based on yesterday limit-up stocks with current strength.
- Semantic-query auction metrics, concept/topic tags, break/reseal counts, final seal time, and max seal metrics for second-board candidates.
- Minute replay via jvQuant `client.minute(..., mode=minute)` for single-symbol intraday bars. Aegis Alpha recalculates 1/3/5/10-minute speed windows from minute bars and marks them as `minute_replay_exact_window:...` or `minute_replay_partial_window:...`.
- Semantic-query five-minute speed remains a fallback for second-board candidates. If jvQuant exposes a range in the returned field name, the adapter marks it as `provider_exact_window:...`; otherwise it falls back to `provider_latest_rolling_5m`.
- Semantic-query capital-flow net inflow ratio for second-board candidates.
- Semantic-query first limit-up time, seal amount, seal volume, and seal-to-turnover ratio.
- Single-symbol K-line snapshot.
- Single-symbol level queue / orderbook summary. True own-order queue position remains unavailable until broker order/trade callbacks are introduced.
- Per-signal `data_quality` metadata for second-board candidates, including source, source field, timestamp, confidence, grading usability, limitations, and evidence. Evidence authority separates `official_doc`, `observed_probe`, and `internal_inference`.

Documentation and discovery are split deliberately:

- [JVQUANT_OFFICIAL_INDEX.md](JVQUANT_OFFICIAL_INDEX.md) records official documentation evidence.
- [JVQUANT_FIELD_MAP.md](JVQUANT_FIELD_MAP.md) records observed semantic-query fields and samples.
- [JVQUANT_CAPABILITY_MATRIX.md](JVQUANT_CAPABILITY_MATRIX.md) summarizes configured probes into a capability matrix.

Future adapters or jvQuant extensions may include:

- jvQuant WebSocket `lv1/lv2/lv10` for realtime market sensing. The current wrapper manages connection/subscription callbacks and feeds local buffers; raw WebSocket messages are not exposed to MCP.
- StockApi for limit-up pools, break-board pools, capital flow, and early-session signals.
- MyQuant for broker-environment Level-2 data.
- miniQMT or QMT for local terminal data and future trading integration.

Provider-specific quirks should stay inside adapters. MCP tools should expose stable, provider-neutral shapes.

## Event And Storage Layer

Aegis Alpha treats events as the boundary between high-frequency data and agent reasoning.

```text
jvQuant WebSocket / query / minute replay
  -> SignalWindowBuffer
  -> SignalSnapshot
  -> EventDetector + config/event_scoring.yaml
  -> MarketEvent
  -> Hermes explanation and review
```

Current storage direction:

- SQLite stores structured market events, signal snapshots, candidate scores, agent reviews, provider runs, and review outcomes.
- Parquet is reserved for high-volume minute bars, Level-2 trades, and orderbook snapshots after a pyarrow-backed writer is added.
- DuckDB remains a future research layer for querying Parquet history and building second-board sample statistics.

Every event must include evidence, timestamps, freshness status, score, confidence, and suggested agent actions. Suggested actions are prompts for analysis, not trading instructions.

## Hermes Skills

Hermes skills should encode user preferences and review lessons, for example:

- Avoid weak same-theme followers.
- Penalize fast boards without theme confirmation.
- Require order-book quality to remain stable during the observation window.
- Prefer second-board candidates only when the market sentiment gate is selective or active.
- Treat mock, delayed, and real-time data differently.

Skills should change how Hermes interprets Aegis Alpha outputs; they should not bypass risk controls.

## Future Binary Packaging

The MVP is a Python package because the contracts are still evolving. Once the MCP interface stabilizes, the server can be distributed as:

- A Docker image for server deployments.
- A standalone binary built from the Python entrypoint.
- A managed local service launched by Hermes.

Packaging must preserve the same safety boundary: no real trading unless explicitly enabled by a future risk-controlled module.
