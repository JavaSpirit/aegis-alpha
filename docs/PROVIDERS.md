# Hermes Providers

## Policy

Aegis Alpha uses Hermes as the AI runtime. Hermes needs at least one inference provider before it can use Aegis Alpha MCP tools or skills.

Current policy:

- Primary provider: DeepSeek direct.
- Optional provider: OpenRouter for contrast or fallback.
- Do not call DeepSeek through OpenRouter when the direct DeepSeek provider is available.

## Files

Provider config example:

```text
.hermes/config/providers.deepseek-openrouter.example.yaml
```

Hermes env example:

```text
.hermes/env.example
```

Install scaffold:

```bash
scripts/install_hermes_provider_config.sh
```

By default this copies supported provider keys from project `.env.local` into `~/.hermes/.env` without printing values:

```text
DEEPSEEK_API_KEY
OPENROUTER_API_KEY
```

Disable copying when needed:

```bash
scripts/install_hermes_provider_config.sh --no-sync-from-local-env
```

Check provider state:

```bash
scripts/check_hermes_provider.sh
```

## Manual Setup

Copy provider keys into Hermes env:

```bash
mkdir -p ~/.hermes
cp .hermes/env.example ~/.hermes/.env
chmod 600 ~/.hermes/.env
```

Then edit:

```text
DEEPSEEK_API_KEY=your-deepseek-key
OPENROUTER_API_KEY=your-openrouter-key
```

`OPENROUTER_API_KEY` is optional. Use it for non-DeepSeek model contrast or fallback.

## Hermes Config

Recommended default:

```yaml
model:
  provider: "deepseek"
  default: "deepseek-chat"
```

Optional fallback:

```yaml
fallback_providers:
  - provider: "openrouter"
    model: "anthropic/claude-sonnet-4"
```

## References

- Hermes AI Providers: https://hermes-agent.nousresearch.com/docs/integrations/providers
- Hermes Fallback Providers: https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers/
