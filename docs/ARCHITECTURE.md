# Aegis Alpha Architecture

## Design Principle

Aegis Alpha separates reasoning from execution.

Hermes may observe, summarize, ask questions, and propose watchlist conditions. It should not directly hold broker credentials or place real orders. Aegis Alpha exposes a controlled MCP boundary and keeps risky capabilities behind explicit future modules.

## Runtime Shape

```text
Hermes Agent
  -> MCP client
  -> Aegis Alpha MCP Server
  -> MarketDataAdapter
  -> Signal models and explanation contracts
```

The MVP uses `MockMarketDataAdapter`. Real providers should be added behind the same adapter boundary so the MCP tool contracts remain stable.

## MCP Boundary

The MCP server exposes only read-only tools in the MVP:

- Market snapshot.
- Limit-up pool.
- Break-board pool.
- Realtime stock snapshot.
- Historical limit-up stats.
- Theme strength.
- Candidate explanation.

Each tool returns structured JSON-compatible data. Every response that depends on market data must include a timestamp or a clear mock-data note.

## Data Adapter Direction

Future adapters may include:

- jvQuant for Level-1, Level-2, order queue, and depth data.
- StockApi for limit-up pools, break-board pools, capital flow, and early-session signals.
- MyQuant for broker-environment Level-2 data.
- miniQMT or QMT for local terminal data and future trading integration.

Provider-specific quirks should stay inside adapters. MCP tools should expose stable, provider-neutral shapes.

## Hermes Skills

Hermes skills should encode user preferences and review lessons, for example:

- Avoid weak same-theme followers.
- Penalize fast boards without theme confirmation.
- Require order-book quality to remain stable during the observation window.
- Treat mock, delayed, and real-time data differently.

Skills should change how Hermes interprets Aegis Alpha outputs; they should not bypass risk controls.

## Future Binary Packaging

The MVP is a Python package because the contracts are still evolving. Once the MCP interface stabilizes, the server can be distributed as:

- A Docker image for server deployments.
- A standalone binary built from the Python entrypoint.
- A managed local service launched by Hermes.

Packaging must preserve the same safety boundary: no real trading unless explicitly enabled by a future risk-controlled module.

