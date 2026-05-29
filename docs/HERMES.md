# Hermes Integration

## Role

Aegis Alpha is a Hermes companion. It does not fork Hermes, patch Hermes, or vendor Hermes source code.

Its job is to:

- Help install or verify Hermes.
- Expose Aegis Alpha as a local MCP server.
- Keep the trading capability boundary inside Aegis Alpha.
- Adapt to Hermes MCP configuration changes through documentation and scripts.

## Install And Configure

Install commands and provider setup live in the README and [PROVIDERS.md](PROVIDERS.md). The relevant scripts are:

- `scripts/install_all.sh` — full one-click setup (Python env + Aegis Alpha + jvQuant + Hermes + skill + MCP config + integration check).
- `scripts/install_hermes.sh [--run]` — wraps the official Hermes installer; dry-run by default.
- `scripts/install_hermes_project_config.sh [--replace]` — installs the reproducible project Hermes config from the template under `.hermes/config/config.example.yaml`.
- `scripts/install_hermes_mcp_config.sh` — installs only the Aegis Alpha MCP snippet from `.hermes/config/aegis-alpha-mcp.yaml`.
- `scripts/install_hermes_skill.sh` — copies the project skill at `.hermes/skills/second-board-radar/SKILL.md` into Hermes.
- `scripts/check_hermes_integration.sh` — verifies the local Hermes integration state.

The full Hermes config template (provider policy + fallback + Aegis Alpha MCP) is at:

```text
.hermes/config/config.example.yaml
```

The MCP-only snippet is at:

```text
.hermes/config/aegis-alpha-mcp.yaml
```

Both files use a `__PROJECT_ROOT__` placeholder that the installer scripts expand to the local checkout path. Do not copy these snippets by hand into `~/.hermes/config.yaml` — let the installer render them.

After installing or replacing the Hermes config, restart Hermes or reload MCP if Hermes is running:

```text
/reload-mcp
```

Hermes registers MCP tools with a server prefix, so the tools may appear as `mcp_aegis_alpha_get_market_snapshot`, `mcp_aegis_alpha_explain_candidate`, etc.

The complete tool list lives in `.hermes/config/aegis-alpha-mcp.yaml` and the README's "MCP Tools" section. The list will grow as new phases land; the YAML snippet is the source of truth.

## Safety Boundary

The current MCP server is read-only. It uses mock data by default and can use authorized jvQuant read-only data when configured. It does not expose:

- Broker login.
- Account query.
- Real trading.
- Order proposal.
- Order execution.
- Real Level-2 credentials.

Future trading tools must be added behind risk checks, audit logs, and human confirmation. See [docs/PLAN.md](PLAN.md) Phase 6 for the controlled-real-trading boundary.

## Keeping Up With Hermes

Aegis Alpha tracks Hermes through integration contracts, not source patches. When Hermes changes MCP behavior:

- Update this document.
- Update `scripts/install_hermes.sh` only if official install flags change.
- Keep Aegis Alpha MCP tools provider-neutral.
- Avoid depending on Hermes internals outside documented MCP config.
