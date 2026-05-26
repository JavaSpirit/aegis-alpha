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
  -> Signal models and explanation contracts
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
- Historical limit-up stats.
- Theme strength.
- Candidate explanation.
- Second-board candidates and explanation.

Each tool returns structured JSON-compatible data. Every response that depends on market data must include a timestamp or a clear mock-data note.

## Data Adapter Direction

Current jvQuant coverage:

- Semantic-query market snapshot, limit-up pool, and break-board pool.
- Coarse market sentiment gate derived from limit-up count, break-board rate, and theme breadth.
- Single-symbol K-line snapshot.
- Single-symbol level queue / orderbook summary.

Future adapters or jvQuant extensions may include:

- StockApi for limit-up pools, break-board pools, capital flow, and early-session signals.
- MyQuant for broker-environment Level-2 data.
- miniQMT or QMT for local terminal data and future trading integration.

Provider-specific quirks should stay inside adapters. MCP tools should expose stable, provider-neutral shapes.

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
