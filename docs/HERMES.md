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

Aegis Alpha provides a project-level one-click installer:

```bash
scripts/install_all.sh
```

This installs the Python environment, Aegis Alpha, jvQuant dependency, Hermes, project skill, MCP config, and final integration check.

The full reproducible Hermes config template lives in:

```text
.hermes/config/config.example.yaml
```

Install or replace local Hermes config from the project template:

```bash
scripts/install_hermes_project_config.sh --replace
```

For Hermes-only integration:

```bash
scripts/install_hermes_all.sh
```

This runs Hermes installation, project skill installation, MCP config installation, and the final integration check.

Aegis Alpha also wraps the Hermes installer in a small helper so the action is visible before execution:

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
python -m pip install ".[dev]"
```

Then install the reproducible project Hermes config:

```bash
scripts/install_hermes_project_config.sh --replace
```

This includes the provider policy, DeepSeek fallback, and Aegis Alpha MCP server. The installer resolves the MCP command path from the current checkout, so the template can be reused on another computer.

For advanced partial setup, install only the bundled MCP config snippet:

```bash
scripts/install_hermes_mcp_config.sh
```

The source snippet lives at:

```text
.hermes/config/aegis-alpha-mcp.yaml
```

It contains:

```yaml
mcp_servers:
  aegis_alpha:
    command: "/Users/xietian/Documents/trading/.venv/bin/python"
    args:
      - "/Users/xietian/Documents/trading/scripts/run_mcp.py"
    enabled: true
    supports_parallel_tool_calls: true
    tools:
      include:
        - get_market_snapshot
        - get_market_sentiment_gate
        - get_limitup_pool
        - get_break_board_pool
        - get_stock_realtime_snapshot
        - get_stock_history_limitup_stats
        - get_theme_strength
        - get_second_board_candidates
        - get_second_board_candidates_compact
        - get_second_board_candidate_data_quality
        - explain_candidate
        - explain_second_board_candidate
      prompts: false
      resources: false
```

Check the local integration state:

```bash
scripts/check_hermes_integration.sh
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

## Install Project Skill

Aegis Alpha includes a Hermes skill at:

```text
.hermes/skills/second-board-radar/SKILL.md
```

Copy it into Hermes:

```bash
scripts/install_hermes_skill.sh
```

Then ask Hermes to use it:

```text
Use the second-board-radar skill to review today's second-board candidates.
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
