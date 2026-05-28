# AI Integration

## Summary

Aegis Alpha adds AI through Hermes, not by putting an LLM inside the trading signal engine. Hermes should reason over Aegis Alpha MCP outputs, use project skills, remember user preferences, and run scheduled review workflows.

The first project skill is:

```text
.hermes/skills/second-board-radar/SKILL.md
```

It teaches Hermes how to use the Aegis Alpha MCP tools for A-share second-board analysis while preserving the read-only safety boundary.

## Why This Is A Skill

Hermes documentation recommends skills for capabilities that can be expressed as instructions plus existing tools. Second-board analysis fits that shape because:

- Aegis Alpha MCP already provides the tool boundary.
- The skill describes when and how Hermes should use those tools.
- The skill encodes safety rules and output format.
- The skill can evolve as the user corrects judgments.

Real-time Level-2 parsing, orderbook state, and execution logic should remain tools or services, not skill prose.

## Installing The Skill

Hermes skills normally live in `~/.hermes/skills/`. This repository keeps project skills under `.hermes/skills/` so they can be versioned with Aegis Alpha.

Option 1: copy the skill into Hermes:

```bash
scripts/install_hermes_skill.sh
```

Option 2: configure Hermes to scan this repository as an external skill directory if supported by the active Hermes version.

After installing or configuring, ask Hermes to list skills or load the skill:

```text
Use the second-board-radar skill to review today's candidates.
```

## Required MCP Setup

The skill expects Aegis Alpha MCP to expose:

- `get_market_sentiment_gate`
- `get_second_board_candidates`
- `get_second_board_candidates_compact`
- `get_second_board_candidate_data_quality`
- `explain_second_board_candidate`
- `get_stock_realtime_snapshot`
- `get_stock_minute_replay_snapshot`
- `get_recent_market_events`
- `get_signal_snapshot`
- `get_event_scoring_config`
- `get_realtime_connection_status`
- `get_runner_status`
- `explain_market_event`
- `get_theme_strength`
- `record_candidate_outcome`

The Hermes MCP configuration example lives in [HERMES.md](HERMES.md).

## Behavior Contract

Hermes should:

- Check the market sentiment gate before candidates.
- Halt candidate analysis when Aegis Alpha returns timeout, error, or empty data; state `Data source unavailable`.
- Check realtime data timestamps during 09:30-11:30 and 13:00-15:00 Asia/Shanghai.
- Treat minute replay as minute-level replay data: useful for recalculated speed windows, but not equivalent to tick-by-tick Level-2.
- Treat market events as structured context for explanation and re-scoring, not as order instructions.
- Cap maximum grade at `B` when speed, big-order, or orderbook data is delayed by more than 3 minutes during active trading hours.
- Stop or downgrade when the gate is `avoid` or `defensive`.
- Focus on yesterday-limit-up stocks trying to advance to a second board.
- Explain grades using structured Aegis Alpha data.
- Include trigger conditions and avoid conditions grouped by price, volume/big-order/orderbook, and sector/theme action.
- Clearly state mock, delayed, or live data mode.

Hermes should not:

- Ask for broker credentials.
- Issue deterministic buy or sell instructions.
- Create real orders.
- Treat mock data as live data.
- Guess or interpolate missing realtime metrics.
- Request raw WebSocket messages or reason directly over individual ticks.
- Analyze arbitrary symbols as valid second-board candidates without pool membership.

## References

- Hermes Skills: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- Creating Skills: https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills
- Hermes MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- Hermes Memory: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/
- Hermes Cron: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron/
