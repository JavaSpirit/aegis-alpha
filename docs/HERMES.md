# Hermes Integration

## Role

Aegis Alpha is a Hermes companion project. It does not fork Hermes, patch Hermes, or vendor Hermes source code.

Its job is to:

- Help install or verify Hermes.
- Expose Aegis Alpha as a local MCP server.
- Keep the trading capability boundary inside Aegis Alpha.
- Adapt to Hermes MCP configuration changes through documentation and scripts.

## Install Hermes

Hermes official documentation recommends the installer script from `NousResearch/hermes-agent`.

Aegis Alpha wraps that installer in a small helper so the action is visible before execution:

```bash
scripts/install_hermes.sh
```

The default mode is dry-run only. To actually install Hermes:

```bash
scripts/install_hermes.sh --run
```

To install without the interactive setup wizard:

```bash
scripts/install_hermes.sh --run --skip-setup
```

The helper does not modify Hermes. It downloads and runs the official installer only when `--run` is provided.

## Configure Aegis Alpha In Hermes

Install this project first:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Then add Aegis Alpha to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  aegis_alpha:
    command: "/Users/xietian/Documents/trading/.venv/bin/aegis-alpha-mcp"
    args: []
    enabled: true
    supports_parallel_tool_calls: true
    tools:
      include:
        - get_market_snapshot
        - get_limitup_pool
        - get_break_board_pool
        - get_stock_realtime_snapshot
        - get_stock_history_limitup_stats
        - get_theme_strength
        - explain_candidate
      prompts: false
      resources: false
```

Restart Hermes, or reload MCP if Hermes is already running:

```text
/reload-mcp
```

Hermes registers MCP tools with a server prefix, so the tools may appear as names like:

```text
mcp_aegis_alpha_get_market_snapshot
mcp_aegis_alpha_explain_candidate
```

## Safety Boundary

The current MCP server is read-only and uses mock data. It does not expose:

- Broker login.
- Account query.
- Real trading.
- Order proposal.
- Order execution.
- Real Level-2 credentials.

Future trading tools must be added behind risk checks, audit logs, and human confirmation.

## Keeping Up With Hermes

Aegis Alpha should track Hermes through integration contracts, not source patches.

When Hermes changes MCP behavior:

- Update this document.
- Update `scripts/install_hermes.sh` only if official install flags change.
- Keep Aegis Alpha MCP tools provider-neutral.
- Avoid depending on Hermes internals outside documented MCP config.

