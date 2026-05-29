# Aegis Alpha Architecture

## Design Principle

Aegis Alpha separates reasoning from execution and integration from ownership.

Hermes may observe, summarize, ask questions, and propose second-board watchlist conditions. It must not directly hold broker credentials or place real orders. Aegis Alpha exposes a controlled MCP boundary and keeps risky capabilities behind explicit future modules.

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

The MCP server exposes only read-only tools in the MVP. Each tool returns structured JSON-compatible data. Every response that depends on market data must include a timestamp or a clear mock-data note.

The current tool set lives in `.hermes/config/aegis-alpha-mcp.yaml` and the README's "MCP Tools" section. New tools land there as phases progress; this document captures the boundary, not the inventory.

## Data Adapter Direction

Provider-specific quirks stay inside adapters. MCP tools expose stable, provider-neutral shapes.

Each candidate signal carries `data_quality` metadata: provider source, raw field name, timestamp, confidence, grading usability, limitations, and evidence. Evidence authority distinguishes:

- `official_doc` — confirmed by jvQuant official documentation. See [JVQUANT_OFFICIAL_INDEX.md](JVQUANT_OFFICIAL_INDEX.md).
- `observed_probe` — observed in actual API responses. See [JVQUANT_FIELD_MAP.md](JVQUANT_FIELD_MAP.md) and [JVQUANT_CAPABILITY_MATRIX.md](JVQUANT_CAPABILITY_MATRIX.md).
- `internal_inference` — derived by Aegis Alpha (e.g. ratios, scores, recalculated speed windows).

Current jvQuant coverage and known gaps are tracked in the README. The adapter is layered so future providers (StockApi, MyQuant, miniQMT, broker terminals) plug in without changing MCP shapes.

## Event And Storage Layer

Events are the boundary between high-frequency provider data and agent reasoning. Agents never see raw WebSocket payloads.

```text
jvQuant WebSocket / query / minute replay
  -> SignalWindowBuffer
  -> SignalSnapshot
  -> EventDetector + config/event_scoring.yaml
  -> MarketEvent
  -> Hermes explanation and review
```

Storage:

- SQLite stores structured market events, signal snapshots, candidate scores, agent reviews, agent review corrections, correction action proposals and decisions, provider runs, and review outcomes.
- Parquet is reserved for high-volume minute bars, Level-2 trades, and orderbook snapshots until a pyarrow-backed writer is added.
- DuckDB remains a future research layer for Parquet history and second-board sample statistics.

Every event carries evidence, timestamps, freshness status, score, confidence, and suggested agent actions. Suggested actions are prompts for analysis, not trading instructions.

## Launchd Runner

On macOS the realtime engine is supervised by launchd:

```text
launchd
  -> aegis-alpha-runner
  -> trading-session scheduler
  -> jvQuant WebSocket subscriptions
  -> local buffers, events, and SQLite status
  -> MCP read-only queries
```

`launchd` owns process lifetime. Aegis Alpha owns market-session lifetime: outside configured trading sessions the runner stays alive but does not keep market subscriptions open. The runner writes `data/runner_status.json`, provider run records, signal snapshots, and market events; Hermes reads these through MCP and never starts or inspects raw streams. MCP tools prefer runner-produced SQLite events and snapshots, falling back to provider queries only when the local store is empty.

## Hermes Skills

Hermes skills encode user preferences and review lessons. Skills change how Hermes interprets Aegis Alpha outputs; they must not bypass risk controls. The first skill is `.hermes/skills/second-board-radar/SKILL.md`.
