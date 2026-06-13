# Facts-Only Radar + Intraday Buy-Point — Master Implementation Plan

> **STATUS (2026-06-13): Phases 1–7 COMPLETE.** All seven phases shipped to `main` via subagent-driven development with two-stage review per task. Full suite: 533 passed / 7 skipped, 86% coverage. The per-phase implementation detail has been collapsed into the **Completed Record** below; the client spec, constraints, and phase map are retained as the authoritative reference. Remaining work lives in the **Backlog (post-Phase-7)** section.

**Goal:** Turn Aegis Alpha into a *facts-only* data platform — the program measures clean derived numbers and assigns NO buy/sell grade — so a Hermes AI agent can judge both (A) overnight 晋级三板 probability and (B) intraday real-time buy-points, evaluated against real next-day market truth and a live 打板 client's feedback.

**Architecture:** 5 layers. (1) Program **measures facts** (derived numbers LLMs can't compute reliably: speeds, ratios, MA slope, float size, theme-lifecycle stage, buy-point state) and **never pre-judges**. (2) Switchable **strategy priors** injected into the Hermes skill/prompt. (3) **Agent judges freely** via MCP tools. (4) **Ground-truth backfill** scores the agent against actual outcomes. (5) **Human-in-the-loop** client feedback → Hermes memory through the existing disclaimer gate (no auto-apply).

**Tech Stack:** Python 3.11+, Pydantic v2, FastMCP, pytest (strict TDD), deterministic mock data + optional read-only jvQuant adapter, Hermes agent (autonomous MEMORY.md; human-authored skills).

---

## What The Client Actually Said (the spec, verbatim intent)

This plan must satisfy BOTH things the client described — they are **two different products**, and earlier framing conflated them:

### Product A — the CASE (overnight T+1 ranking). Client's complaint, three failures:
- **失败1:** asked "明天溢价率最高的二板?" → AI returned 8 stocks, 里面 4板/3板/炸板 混杂 (garbage filtering). *(Already addressed by the 2-board filter commit — verify, don't rebuild.)*
- **失败2 (most direct):** after fix, 6 stocks were right, **但只给了总结** — did NOT combine **市场情绪 / 题材所在位置 / 股本大小 / 成交量 / 回封力度** into a **晋级三板概率 + 综合评级**.
- **失败3:** AI graded 电力 = B off recent-hotness, **没考虑电力题材已演绎到行情后期** (theme lifecycle gap).

### Product B — the STRATEGY (intraday T-day buy-point). Verbatim:
> 近10日均成交量>50亿；5日均线斜率30°–60°；所属板块近两周多次异动拉升、有持续性（可能需 AI 盘外抓取）；T-1缩量调整；T日早盘拉升快、带量过前期高点（结合盘口实时大单买入占比）、回踩砸盘缩量、重新上冲=买入预警点；同板块共振拉升加分；财联社消息弹窗契合更好。监控时段 9:30–9:50 和 11:10–11:30。

**Mapping failure → phase (so nothing is dropped again):**

| Client item | Type | Phase |
|-------------|------|-------|
| 失败1 board-filter garbage | data | done (verify in 1A.0) |
| 失败2 概率+综合评级 from 情绪/题材位置/**股本**/量能/回封 | **agent judgment structure** | **Phase 3 (skill restructure)** + facts in Phase 1 |
| 失败3 题材后期 (lifecycle) | fact | **Phase 1C** |
| 近10日均量>50亿 | fact | 1B |
| 5日均线斜率30–60° | fact (angle) + prior threshold | 1B + P5 |
| 板块两周持续性 | fact (lifecycle) + 盘外(AI) | 1C + P5(agent) |
| T-1缩量 | fact | 1B |
| T日带量过前高 | fact | 1B |
| 盘口大单占比 | fact (exists) | — / P6 live |
| 回踩缩量→重新上冲=买点 | state machine | **Phase 4** offline → **Phase 6** live |
| 同板块共振 | fact (exists `same_theme_rising_count`) | 4 |
| 财联社弹窗 | OUT this cycle — **placeholder only** (binding decision) | P5 placeholder |
| 9:30–9:50 / 11:10–11:30 监控窗口 | runner config | **Phase 6** |

**Binding decisions (from AskUserQuestion, do not revisit):**
- 交付形态 = **两阶段都要（先离线后实盘）**.
- 财联社 = **本期暂不做，先占位**.
- 程序 grade = **彻底移除评级**.

---

## Non-Negotiable Constraints (ALL phases)

1. **No real trading** — no broker/Level-2 creds, no buy/sell/order. `PROHIBITED_DIRECTIVE_PATTERNS` in `agent_eval.py` stays and keeps blocking 直接买入/全仓/梭哈/下单.
2. **Mock-by-default** — every measurement works deterministically on mock; jvQuant paths read-only/optional.
3. **Disclaimer gate is sacred** — Aegis Alpha NEVER auto-applies memory/skill/config/adapter changes. Disclaimers at `mcp/server.py:208/232/265` stay verbatim.
4. **No LLM model-name edits** — leave `anthropic/claude-opus-4-7`, `deepseek-v4-pro`. `provider` is a data field, not an LLM call.
5. **Immutability** — new objects, never mutate. Functions <50 lines, files <800 lines.
6. **No secrets/PII** in code or logs.
7. **`trash`, never `rm`** for deletions. Clean deletes — no `_unused` renames, no re-export shims.
8. **Strict TDD** RED→GREEN→REFACTOR→commit per task; coverage ≥ 80%.
9. **Agent still emits its own grade as JUDGMENT** — only the *program's* grade is removed. `agent_eval.py`'s validation of the agent's self-reported grade is allowed and stays.
10. **Worktree base = `main` HEAD (`e09ec91`)**; one branch per phase.

---

## Phase Map

| Phase | Subsystem | Ships | Detail here |
|-------|-----------|-------|-------------|
| **1** | **Facts foundation** — remove program grade; add 股本/量/斜率/前高 facts; theme-lifecycle stage | offline, mock | **FULL** |
| 2 | Promotion-probability **inputs** as facts (回封力度/情绪快照/题材位置 bundled into one MCP "judgment dossier" — facts only, no score) | offline | spec |
| 3 | **Skill restructure** — force agent to walk 情绪/题材位置/股本/量能/回封 and output 概率+综合评级 with reasoning (fixes 失败2) | offline (Hermes) | spec |
| 4 | Offline **buy-point state machine** (过前高→回踩缩量→重新上冲) on historical minute data | offline replay | spec |
| 5 | **Strategy-prior injection** — client 10-point strategy as switchable prior; 财联社 placeholder | offline | spec |
| 6 | **Runner monitor windows** (9:30–9:50, 11:10–11:30) + live (paper) buy-point alert | live paper | spec |
| 7 | **Ground-truth eval + feedback→memory** — predicted vs actual; client feedback to Hermes memory (gated) | live paper | spec |

**Sequencing rationale:** facts first (1) — everything assumes them. Promotion dossier (2) and skill restructure (3) fix the client's loudest complaint (失败2) early and offline. Buy-point machine (4) needs Phase-1 facts. Prior (5) references facts + machine. Live runner (6) is highest-risk → after offline proven. Eval + memory wiring (7) last — it touches the agent's memory and the safety gate.

---


# Completed Record — Phases 1–7 (shipped to `main`)

All phases executed via subagent-driven development; every task RED→GREEN→commit with two-stage review (spec + code quality). Philosophy held throughout: **program measures FACTS, agent JUDGES, zero program grading, no buy/sell/order, disclaimer gate never auto-applies.**

| Phase | What shipped | Key artifacts |
|-------|--------------|---------------|
| **1 / 1D** | Facts foundation; removed all program grading; market gate stripped to pure facts | `models.py` (dropped `grade`/`grade_reason`/`estimated_seal_probability`; added free_float/10d-vol/MA5-slope/T-1-shrink/prev-high facts + `theme_lifecycle_stage`); `measurements/client_facts.py`; `measurements/theme_lifecycle.py`; deleted `scoring.py`/`grading.py`/`market_gate.py`; `attribution.py` rewired to break-board-rate fact |
| **2** | Promotion dossier — 5 factor bundles in one call | `PromotionDossier` + 5 sub-models; `measurements/promotion_dossier.py` (pure assembler); `get_promotion_dossier(symbol)` MCP tool. Keys == `agent_eval.REQUIRED_FACTORS` so agent can't forget a factor |
| **3** | SKILL rewrite — forces 5-factor walk + bucketed promotion_likelihood + agent grade | `.hermes/skills/second-board-radar/SKILL.md` rewritten; purged dead Phase-1 refs; late-stage downweight (divergence/ebb/climax ceilings) |
| **4** | Offline buy-point state machine (过前高→回踩缩量→重新上冲) | `measurements/buypoint_state_machine.py` (pure, frozen, injectable thresholds); `measurements/buypoint_replay.py`; `IntradayBuyPointSignal` (alert-only, no order); `detect_intraday_buypoint` MCP tool |
| **5** | Strategy-prior injection — client 10-point strategy as switchable guidance | `StrategyPrior`/`StrategyPriorThreshold` (soft ranges, never filters); `config/strategy_priors/client_10pt.yaml`; `strategy_priors.py` loader; `get_active_strategy_prior` MCP tool; SKILL override-with-reasoning clause |
| **6** | Runner monitor windows + live paper buy-point alert | `config/runner.yaml` `monitor_windows` block; `is_in_monitor_window` gate; `measurements/minute_bars.py` (rolling-points→minute-bars, cumulative-turnover delta); `runner.detect_buypoints_in_window` (window-gated replay, fact-first previous_high, dedup alert via existing AlertStore) |
| **7** | Ground-truth eval + feedback→memory (gated) | `AgentJudgmentScorecard`/`AgentJudgmentRow`; `feedback/agent_scorecard.py` (Brier + calibration + grade hit-rate, pure); `get_agent_judgment_scorecard` MCP tool; `CLIENT_OUTCOME` correction type routed to a human-reviewed memory suggestion; `test_no_auto_mutate_safety_lock.py` pins the no-auto-write guarantee |

**Client failure → resolution (all covered):** 失败1 board-filter (done) · 失败2 概率+综合评级 (Phase 2 dossier + Phase 3 skill) · 失败3 题材后期 (Phase 1C lifecycle) · client's own 10-point strategy (Phase 5 prior) · intraday buy-point (Phase 4 offline → Phase 6 live paper).

---

# Backlog (post-Phase-7)

Discovered during the Phase-6/7 closeout review. Priority order:

### P0 — Wire Phase 2 & 7 tools into the SKILL (agent can't use what it can't see)
**Problem:** `get_promotion_dossier` (Phase 2) and `get_agent_judgment_scorecard` (Phase 7) are registered `@mcp.tool`s but appear **0 times** in `SKILL.md`'s tool list — the agent's behavioral contract never mentions them, so they're effectively undelivered. Root cause: the SKILL rewrite (3.2) landed before the dossier tool (2.3); cross-session seam.
**Deliverable:** add both tools to the SKILL "Required MCP Tools" list; add a short usage note for each — dossier as the one-call 5-factor fetch the agent should prefer; scorecard as the agent's own calibration self-check (`get_agent_judgment_scorecard(start_day,end_day)`). Human-authored edit, no `skill_write`. Cheap, high value.

### P1 — Cross-phase end-to-end integration test
**Problem:** unit coverage is 86% but no single test exercises the Phase 2→3→7 contract chain together (dossier facts → agent 5-factor judgment shape → scorecard scoring). Per-slice tests are green but cross-phase drift is unguarded.
**Deliverable:** `tests/test_facts_to_scorecard_e2e.py` — seed candidates + a market gate, build a dossier, feed a synthetic agent review (5 factors + promotion_likelihood matching `REQUIRED_FACTORS`), record realized outcomes, run the scorecard, assert the chain holds end-to-end and the factor keys line up across dossier ↔ agent_eval ↔ skill.

### P2 — Whole-plan cross-phase consistency check (pre-push体检)
Type/contract sweep across all 7 phases before pushing: confirm no naming drift (`PromotionLikelihood`, `REQUIRED_FACTORS`, `ThemeLifecycleStage`), all disclaimers verbatim, no dead refs. Largely subsumed by P1 if P1 asserts the contracts.

### P3 — 财联社 real integration (Phase 5 left a placeholder)
`caixin_alignment` is a placeholder string by binding decision. Real integration is an external data-source project (feed, parsing, freshness). Medium value, high cost — needs a data source decision first.

### P4 — Calibrate the `theme_lifecycle` nh_accel heuristic against ground truth
`theme_lifecycle.py:48` documents the climax-vs-fermenting `nh_accel` heuristic as "calibrated against ground truth in a later phase." Phase 7's scorecard infra now exists to measure it. Needs accumulated real data. Medium value.

### P5 — Phase 6 real jvQuant deployment dry-run
Logic layer is mock/replay-tested and CI-green. A live dry-run (real `JVQUANT_TOKEN` env var, real WebSocket, observe window-gated alerts during a session) validates the live path. Read-only data, still paper/no-order. Needs the user's environment + token.

---

# Reference — original spec (retained above)

The **What The Client Actually Said**, **Non-Negotiable Constraints**, and **Phase Map** sections above remain the authoritative spec. The detailed per-task TDD steps for Phases 1–7 have been removed now that they are shipped; see the git history (`git log --oneline`, commits tagged `feat(1.x)`…`feat(7.x)`, `feat(6.x)`) for the exact implementation trail.
