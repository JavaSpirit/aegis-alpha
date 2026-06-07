# AI Integration

## Summary

Aegis Alpha adds AI through Hermes, not by putting an LLM inside the trading signal engine. Hermes reasons over Aegis Alpha MCP outputs, uses project skills, remembers user preferences, and runs scheduled review workflows.

The program measures facts (derived numbers: float cap, turnover, MA5 slope, T-1 volume ratio, previous-high break, theme lifecycle stage); it also reports raw market facts (limit-up count, break-board rate, theme breadth) and fact-derived risk_flags/positive_signals — it does NOT emit a market sentiment label or an action verdict. The AI agent judges market sentiment and trading action from those facts. No buy/sell grade is assigned by the program.

The first project skill is:

```text
.hermes/skills/second-board-radar/SKILL.md
```

It teaches Hermes how to use the Aegis Alpha MCP tools for A-share second-board analysis while preserving the read-only safety boundary. The skill is the **single source of truth** for Hermes behavior — required tools, freshness rules, output format, and safety constraints all live there.

## Why This Is A Skill

Hermes documentation recommends skills for capabilities that can be expressed as instructions plus existing tools. Second-board analysis fits that shape because:

- Aegis Alpha MCP already provides the tool boundary.
- The skill describes when and how Hermes should use those tools.
- The skill encodes safety rules and output format.
- The skill can evolve as the user corrects judgments.

Real-time Level-2 parsing, orderbook state, and execution logic should remain tools or services, not skill prose. Anything that needs deterministic computation, persistence, or provider credentials belongs on the Aegis Alpha side.

## Install And Use

Install the skill into Hermes:

```bash
scripts/install_hermes_skill.sh
```

Then ask Hermes:

```text
Use the second-board-radar skill to review today's second-board candidates.
```

Hermes MCP setup, the required tool list, and the behavior contract are all defined in [the skill file](../.hermes/skills/second-board-radar/SKILL.md). For the Hermes MCP configuration mechanics, see [HERMES.md](HERMES.md).

## References

- Hermes Skills: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- Creating Skills: https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills
- Hermes MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- Hermes Memory: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/
- Hermes Cron: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron/
