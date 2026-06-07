# Facts-Only Radar + Intraday Buy-Point — Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **This is a MASTER plan spanning multiple subsystems.** Phase 1 is fully specified in bite-sized TDD detail — execute it now. Phases 2–7 are scoped specs; expand each into its own `docs/superpowers/plans/2026-XX-XX-<phase>.md` via `superpowers:writing-plans` when its predecessor lands. Do NOT execute Phases 2–7 from this doc alone.

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

# PHASE 1 — Facts Foundation (FULL DETAIL)

**Goal:** `SecondBoardCandidate` carries every fact the client named (incl. **股本** and **题材位置**) and carries ZERO program judgment.

**Slices (sequenced, shared files):**
- **1A** Remove program grading.
- **1B** Add client-strategy fact fields (10d avg vol, MA5 slope, T-1 shrink, prev-high break, **free-float market cap**).
- **1C** Theme-lifecycle stage as a fact (启动/发酵/高潮/分歧/退潮).

**Read before starting:** `models.py:486-541` (`SecondBoardCandidate`); `adapters/jvquant/scoring.py` (grading core to delete); `adapters/jvquant/candidates.py` `build_one_candidate()`; `adapters/mock_market_data.py`; grade consumers — `watchlists/manager.py`, `feedback/{backtest,backfill,hypothesis,threshold_advice}.py`, `reviews/daily.py`, `agent_eval.py`, `mcp/server.py`.
Single test: `pytest tests/x.py::t -v`. Full + cov: `pytest --cov=aegis_alpha --cov-report=term-missing`.

---

## Slice 1A — Remove Program Grading

### Task 1A.0: Verify the 2-board filter (失败1) and lock the consumer list

**Files:** read-only.

- [ ] **Step 1: Confirm board-filter behavior exists**

Run: `rg -n "previous_consecutive_boards|suspend|炸板|break_board|二板|second_board" src/aegis_alpha/adapters/jvquant/candidates.py | head`
Expected: the candidate builder already filters to genuine 2-boards (the recent commit). If the filter is missing, STOP and raise it — 失败1 is a prerequisite, not part of this plan.

- [ ] **Step 2: Snapshot the grade blast radius**

Run: `rg -n "\.grade\b|grade=|grade_reason|estimated_seal_probability|seal_quality_score|candidate_grade|market_score|action_from_score|sentiment_from_score" src/ | rg -v tests`
Expected: hits only in the files listed under "Read before starting". A new file = add a task before proceeding.

### Task 1A.1: Remove grade fields from `SecondBoardCandidate`

**Files:**
- Modify: `src/aegis_alpha/models.py:486-541`
- Test: `tests/test_models_candidate_no_grade.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_candidate_no_grade.py
from aegis_alpha.models import SecondBoardCandidate


def test_candidate_has_no_program_grade_fields():
    fields = set(SecondBoardCandidate.model_fields)
    assert "grade" not in fields
    assert "grade_reason" not in fields
    assert "estimated_seal_probability" not in fields


def test_candidate_still_carries_measured_facts():
    fields = set(SecondBoardCandidate.model_fields)
    for fact in ("five_min_speed_pct", "big_order_net_inflow_ratio", "seal_to_turnover_ratio"):
        assert fact in fields
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_models_candidate_no_grade.py -v`
Expected: FAIL (`grade` still present).

- [ ] **Step 3: Remove the three lines** (currently 534/535/539):

```python
    estimated_seal_probability: float = Field(ge=0, le=1)
    grade: CandidateGrade
    grade_reason: str = ""
```

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_models_candidate_no_grade.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py tests/test_models_candidate_no_grade.py
git commit -m "refactor: drop program grade fields from SecondBoardCandidate

grade/grade_reason/estimated_seal_probability were hardcoded-threshold
outputs, not facts. The agent judges from measured facts instead."
```

### Task 1A.2: Strip grade from `CandidateExplanation`

**Files:**
- Modify: `src/aegis_alpha/models.py:544-549`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py` (explain builders)
- Test: `tests/test_explanation_facts_only.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explanation_facts_only.py
from aegis_alpha.models import CandidateExplanation


def test_explanation_is_facts_not_grade():
    fields = set(CandidateExplanation.model_fields)
    assert "grade" not in fields
    assert "grade_reason" not in fields
    assert "observations" in fields
    assert "risks" in fields
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_explanation_facts_only.py -v`

- [ ] **Step 3: Remove `grade`/`grade_reason` from `CandidateExplanation`; fix builders**

In `models.py` delete those two lines from `CandidateExplanation`. In `adapter.py`, for every `CandidateExplanation(...)` / `explain_*`, drop the `grade=`/`grade_reason=` kwargs; if a `grade_reason` carried a useful *fact* sentence, move it into `observations`.

- [ ] **Step 4: Run — verify PASS** (fix adapter tests that asserted on `grade` → assert on `observations`)

Run: `pytest tests/test_explanation_facts_only.py tests/ -k explain -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py src/aegis_alpha/adapters/jvquant/adapter.py tests/test_explanation_facts_only.py
git commit -m "refactor: CandidateExplanation returns facts, not a program grade"
```

### Task 1A.3: Watchlist grade — agent-set, not program-seeded

**Files:**
- Modify: `src/aegis_alpha/models.py:559-560` (`WatchlistEntry`)
- Modify: `src/aegis_alpha/watchlists/manager.py:41-42,67-68,96,113`
- Test: `tests/test_watchlist_no_program_grade.py` (create)

- [ ] **Step 1: Write the failing test** (adjust to real `WatchlistManager` API — read it first)

```python
# tests/test_watchlist_no_program_grade.py
from aegis_alpha.watchlists.manager import WatchlistManager


def test_new_entry_has_no_program_seeded_grade(tmp_path):
    mgr = WatchlistManager(storage_path=tmp_path / "wl.json")
    entry = mgr.add(symbol="000001", name="平安银行", theme="银行")
    assert entry.agent_grade is None
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_watchlist_no_program_grade.py -v`

- [ ] **Step 3: Implement**

`models.py` `WatchlistEntry`: replace
```python
    initial_grade: CandidateGrade = "C"
    last_grade: CandidateGrade = "C"
```
with
```python
    agent_grade: CandidateGrade | None = None
    agent_grade_history: list[CandidateGrade] = Field(default_factory=list)
```
`manager.py`: remove the `"C"` seeds (41-42, 67-68). In update path (96, 113) set `agent_grade=new_grade` and append to `agent_grade_history`.

- [ ] **Step 4: Run — verify PASS** (update tests asserting `initial_grade`/`last_grade`)

Run: `pytest tests/test_watchlist_no_program_grade.py tests/ -k watchlist -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py src/aegis_alpha/watchlists/manager.py tests/test_watchlist_no_program_grade.py
git commit -m "refactor: watchlist grade is agent-set and optional, not program-seeded"
```

### Task 1A.4: Delete `scoring.py` judgment functions

**Files:**
- Delete: `src/aegis_alpha/adapters/jvquant/scoring.py`
- Modify: `src/aegis_alpha/adapters/jvquant/candidates.py`, `src/aegis_alpha/adapters/mock_market_data.py`
- Test: `tests/test_scoring_removed.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scoring_removed.py
import importlib
import pytest


def test_scoring_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("aegis_alpha.adapters.jvquant.scoring")
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_scoring_removed.py -v`

- [ ] **Step 3: Remove callers, trash file**

Run: `rg -n "scoring import|scoring\.(market_score|action_from_score|candidate_grade|seal_quality_score|estimated_seal_probability|sentiment_from_score)" src/`
Delete each import/call in `candidates.py` and `mock_market_data.py`; drop the now-dead `grade=`/`grade_reason=`/`estimated_seal_probability=` kwargs. Then:
```bash
trash src/aegis_alpha/adapters/jvquant/scoring.py
```

- [ ] **Step 4: Run full suite, fix stragglers**

Run: `pytest tests/test_scoring_removed.py -v && pytest -q`
Expected: green; every failure = a remaining caller, delete that grade path.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: delete scoring.py program-judgment functions

The program measures facts; it does not assign A/B/C/REJECT or a seal
probability. Those were hardcoded thresholds, not measurements."
```

### Task 1A.5: Retire grade-dependent config + feedback

**Files:**
- Modify: `src/aegis_alpha/grading.py`, `config/candidate_grading.yaml`
- Modify: `feedback/threshold_advice.py`, `feedback/backtest.py`, `feedback/hypothesis.py`, `feedback/backfill.py`, `reviews/daily.py`, `agent_eval.py`
- Test: `tests/test_grading_config_unused.py` (create)

- [ ] **Step 1: Map blast radius**

Run: `rg -n "CandidateGradingConfig|MarketScoringConfig|CandidateThresholdConfig|SealQualityConfig|candidate_grading.yaml" src/`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_grading_config_unused.py
import importlib


def test_threshold_advice_no_longer_remaps_program_grades():
    mod = importlib.import_module("aegis_alpha.feedback.threshold_advice")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "promote_b_to_a" not in src
    assert "downgrade_c_to_reject" not in src
```

- [ ] **Step 3: Run — verify FAIL**

Run: `pytest tests/test_grading_config_unused.py -v`

- [ ] **Step 4: Implement — repoint to facts / gate to Phase 7**

- `feedback/backtest.py`: the grade-remap (`_apply_rule_changes`, promote_b_to_a…) operated on *program* grades. The program no longer grades. **Gate it off**: replace the remap body with `raise NotImplementedError("re-homed to Phase 7 ground-truth backtest")` and `@pytest.mark.skip(reason="moved to Phase 7")` its tests. Keep the harness file — Phase 7 reuses it.
- `feedback/threshold_advice.py`: delete `promote_b_to_a`/`downgrade_c_to_reject`/`flip_a_to_b` mappers (advised on dead thresholds).
- `agent_eval.py`: **keep** `grade_present`/`stale_data_caps_grade` — they validate the *agent's* self-reported grade (its judgment), not program output. Add one comment line clarifying provenance.
- `grading.py`: delete a config class only if `rg` shows zero remaining refs.
- `config/candidate_grading.yaml`: `trash` only if zero loaders remain.

- [ ] **Step 5: Run full suite + coverage**

Run: `pytest -q && pytest --cov=aegis_alpha --cov-report=term-missing`
Expected: green (Phase-7-bound tests skipped); cov ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: retire program-grade config and grade-remap feedback

threshold_advice remaps deleted; backtest grade-remap gated to Phase 7;
agent_eval keeps agent-output validation (the agent still judges)."
```

---

## Slice 1B — Client-Strategy Fact Fields

| Client item | Field | Type | Derivation |
|---|---|---|---|
| 股本大小 (失败2!) | `free_float_market_cap_cny` | float | from payload; mirrors `NewStockCandidate:861` |
| 近10日均量>50亿 | `avg_turnover_10d_cny` | float | mean(last 10 daily turnovers) |
| 5日均线斜率30–60° | `ma5_slope_degrees` | float | `degrees(atan2(Δma5/base, 1/n))` |
| T-1缩量 | `prev_day_volume_shrink_ratio` | float | `vol(T-1)/avg_10d` |
| 带量过前高 | `broke_previous_high`,`previous_high_price` | bool,float | current vs prior-high max |
| 盘口大单占比 | `big_order_net_inflow_ratio` | (exists) | — |

### Task 1B.1: Add fact fields to the model

**Files:** Modify `src/aegis_alpha/models.py` `SecondBoardCandidate`; Test `tests/test_candidate_client_facts.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_candidate_client_facts.py
from aegis_alpha.models import SecondBoardCandidate


def test_candidate_carries_client_strategy_facts():
    f = SecondBoardCandidate.model_fields
    for name in (
        "free_float_market_cap_cny",
        "avg_turnover_10d_cny",
        "ma5_slope_degrees",
        "prev_day_volume_shrink_ratio",
        "broke_previous_high",
        "previous_high_price",
    ):
        assert name in f, f"missing {name}"


def test_new_fact_fields_have_safe_defaults():
    f = SecondBoardCandidate.model_fields
    assert f["broke_previous_high"].default is False
    assert f["free_float_market_cap_cny"].default == 0.0
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_candidate_client_facts.py -v`

- [ ] **Step 3: Add fields** (after `big_order_net_inflow_ratio`, ~line 522):

```python
    free_float_market_cap_cny: float = 0.0
    avg_turnover_10d_cny: float = 0.0
    ma5_slope_degrees: float = 0.0
    prev_day_volume_shrink_ratio: float = 0.0
    broke_previous_high: bool = False
    previous_high_price: float = 0.0
```

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_candidate_client_facts.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py tests/test_candidate_client_facts.py
git commit -m "feat: add client-strategy fact fields (incl. free-float cap) to candidate"
```

### Task 1B.2: Pure derivation helpers (TDD)

**Files:** Create `src/aegis_alpha/measurements/__init__.py`, `src/aegis_alpha/measurements/client_facts.py`; Test `tests/measurements/test_client_facts.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/measurements/test_client_facts.py
from aegis_alpha.measurements.client_facts import (
    avg_turnover_10d,
    ma5_slope_degrees,
    prev_day_volume_shrink_ratio,
    broke_previous_high,
)


def test_avg_turnover_10d_uses_last_ten():
    daily = [float(i) for i in range(1, 13)]
    assert avg_turnover_10d(daily) == sum(range(3, 13)) / 10


def test_avg_turnover_10d_short_series():
    assert avg_turnover_10d([10.0, 20.0]) == 15.0


def test_avg_turnover_10d_empty_is_zero():
    assert avg_turnover_10d([]) == 0.0


def test_ma5_slope_flat_is_zero():
    assert ma5_slope_degrees([5.0] * 6) == 0.0


def test_ma5_slope_rising_positive():
    assert ma5_slope_degrees([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]) > 0.0


def test_ma5_slope_short_series_is_zero():
    assert ma5_slope_degrees([1.0, 2.0]) == 0.0


def test_prev_day_volume_shrink_ratio():
    assert prev_day_volume_shrink_ratio(prev_day_volume=30.0, avg_10d=60.0) == 0.5


def test_prev_day_volume_shrink_ratio_zero_avg():
    assert prev_day_volume_shrink_ratio(prev_day_volume=30.0, avg_10d=0.0) == 0.0


def test_broke_previous_high_true():
    assert broke_previous_high(current_price=11.0, prior_highs=[10.0, 10.5]) is True


def test_broke_previous_high_false():
    assert broke_previous_high(current_price=10.0, prior_highs=[10.5]) is False


def test_broke_previous_high_empty():
    assert broke_previous_high(current_price=10.0, prior_highs=[]) is False
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/measurements/test_client_facts.py -v`

- [ ] **Step 3: Implement**

```python
# src/aegis_alpha/measurements/client_facts.py
from __future__ import annotations

import math


def avg_turnover_10d(daily_turnovers: list[float]) -> float:
    """Mean turnover over the last 10 sessions (fewer if short)."""
    if not daily_turnovers:
        return 0.0
    window = daily_turnovers[-10:]
    return round(sum(window) / len(window), 6)


def _ma5_series(prices: list[float]) -> list[float]:
    if len(prices) < 5:
        return []
    return [sum(prices[i - 5 : i]) / 5 for i in range(5, len(prices) + 1)]


def ma5_slope_degrees(prices: list[float]) -> float:
    """Angle (degrees) of the 5-day MA over its last two points.

    x-step normalized to one trading day. Pure measurement convention,
    NOT a threshold judgment — the client's 30-60deg test happens in the
    strategy-prior/agent layer.
    """
    ma5 = _ma5_series(prices)
    if len(ma5) < 2:
        return 0.0
    delta = ma5[-1] - ma5[-2]
    base = abs(ma5[-2]) or 1.0
    return round(math.degrees(math.atan2(delta / base, 1.0 / len(ma5))), 4)


def prev_day_volume_shrink_ratio(*, prev_day_volume: float, avg_10d: float) -> float:
    """T-1 volume relative to the 10-day average. <1 means shrink."""
    if avg_10d <= 0.0:
        return 0.0
    return round(prev_day_volume / avg_10d, 6)


def broke_previous_high(*, current_price: float, prior_highs: list[float]) -> bool:
    """True if current price exceeds the max prior session high."""
    if not prior_highs:
        return False
    return current_price > max(prior_highs)
```

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/measurements/test_client_facts.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/measurements/ tests/measurements/test_client_facts.py
git commit -m "feat: pure derivation helpers for client-strategy facts"
```

### Task 1B.3: Wire helpers into candidate assembly

**Files:** Modify `adapters/mock_market_data.py`, `adapters/jvquant/candidates.py`; Test `tests/test_candidate_assembly_facts.py` (create)

- [ ] **Step 1: Write the failing test** (read real adapter API first)

```python
# tests/test_candidate_assembly_facts.py
from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_mock_candidate_populates_client_facts():
    c = MockMarketDataAdapter().get_second_board_candidates()[0]
    assert c.avg_turnover_10d_cny >= 0.0
    assert c.free_float_market_cap_cny >= 0.0
    assert isinstance(c.broke_previous_high, bool)


def test_mock_facts_are_deterministic():
    a = MockMarketDataAdapter().get_second_board_candidates()[0]
    b = MockMarketDataAdapter().get_second_board_candidates()[0]
    assert a.ma5_slope_degrees == b.ma5_slope_degrees
    assert a.avg_turnover_10d_cny == b.avg_turnover_10d_cny
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_candidate_assembly_facts.py -v`

- [ ] **Step 3: Populate**

Mock adapter: give each fixture symbol a deterministic daily-turnover series, price series, prev-day vol, prior highs, and float cap; compute facts via `client_facts` helpers; pass into `SecondBoardCandidate(...)`. `candidates.py` `build_one_candidate()`: same from jvQuant payload; missing series → keep default AND add a `data_quality` `SignalMetadata` marked `unavailable` (follow existing pattern).

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_candidate_assembly_facts.py -v`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: populate client-strategy facts in mock + jvquant candidates"
```

### Task 1B.4: Cite facts in explain output (numbers only, no judgment words)

**Files:** Modify `adapters/jvquant/adapter.py`; Test `tests/test_explain_includes_client_facts.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explain_includes_client_facts.py
from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_explain_observations_mention_client_facts():
    a = MockMarketDataAdapter()
    c = a.get_second_board_candidates()[0]
    blob = " ".join(a.explain_second_board_candidate(c.symbol).observations)
    assert "10" in blob and ("斜率" in blob or "slope" in blob.lower())
    assert "流通市值" in blob or "股本" in blob
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_explain_includes_client_facts.py -v`

- [ ] **Step 3: Append neutral fact sentence** (NO "好/强/买"):

```python
observations.append(
    f"流通市值约 {candidate.free_float_market_cap_cny / 1e8:.1f} 亿元，"
    f"近10日均成交额约 {candidate.avg_turnover_10d_cny / 1e8:.2f} 亿元，"
    f"5日均线斜率 {candidate.ma5_slope_degrees:.1f}°，"
    f"T-1量比 {candidate.prev_day_volume_shrink_ratio:.2f}，"
    f"{'已' if candidate.broke_previous_high else '未'}破前高 {candidate.previous_high_price:.2f}。"
)
```

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_explain_includes_client_facts.py -v`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: explain output cites client facts incl. free-float cap (no judgment)"
```

---

## Slice 1C — Theme-Lifecycle Stage as a FACT (fixes 失败3)

The 电力=B failure happened because nothing measured *where the theme is in its cycle*. Add `theme_lifecycle_stage` as a **measured** fact.

**Measurement definition (follow exactly).** Given a theme's recent daily series of `(limit_up_count, break_board_rate, new_high_member_count, leader_alive)`:
- `launch` 启动: count rose from low base (≤2 → ≥3), break rate low.
- `fermenting` 发酵: count rising multiple days, leader alive.
- `climax` 高潮: count at global max AND new-high members at global max.
- `divergence` 分歧: break rate rising while count flat/falling from a recent peak.
- `ebb` 退潮: count falling ≥2 days AND leader not alive.
- `unknown`: <3 days.

A deterministic state classifier over measured counts — a fact, like a thermometer reading.

### Task 1C.1: Add enum + field

**Files:** Modify `src/aegis_alpha/models.py` (enum near line 83; field on `SecondBoardCandidate`); Test `tests/test_theme_lifecycle_field.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme_lifecycle_field.py
from aegis_alpha.models import SecondBoardCandidate


def test_candidate_has_theme_lifecycle_stage():
    field = SecondBoardCandidate.model_fields.get("theme_lifecycle_stage")
    assert field is not None
    assert field.default == "unknown"
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_theme_lifecycle_field.py -v`

- [ ] **Step 3: Add enum + field**

near line 83:
```python
ThemeLifecycleStage = Literal[
    "launch", "fermenting", "climax", "divergence", "ebb", "unknown",
]
```
on `SecondBoardCandidate` (near `theme_role`):
```python
    theme_lifecycle_stage: ThemeLifecycleStage = "unknown"
```

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_theme_lifecycle_field.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py tests/test_theme_lifecycle_field.py
git commit -m "feat: add theme_lifecycle_stage fact field + enum"
```

### Task 1C.2: Lifecycle classifier (table-driven TDD)

**Files:** Create `src/aegis_alpha/measurements/theme_lifecycle.py`; Test `tests/measurements/test_theme_lifecycle.py` (create)

- [ ] **Step 1: Write the failing tests (one per stage + edge)**

```python
# tests/measurements/test_theme_lifecycle.py
from aegis_alpha.measurements.theme_lifecycle import ThemeDay, classify_theme_lifecycle


def d(lu, bbr, nh, alive):
    return ThemeDay(limit_up_count=lu, break_board_rate=bbr,
                    new_high_member_count=nh, leader_alive=alive)


def test_insufficient_is_unknown():
    assert classify_theme_lifecycle([]) == "unknown"
    assert classify_theme_lifecycle([d(3, .1, 1, True)]) == "unknown"


def test_launch():
    assert classify_theme_lifecycle([d(1, .1, 0, True), d(2, .1, 1, True), d(4, .05, 2, True)]) == "launch"


def test_fermenting():
    assert classify_theme_lifecycle([d(3, .1, 1, True), d(5, .1, 3, True), d(7, .1, 4, True)]) == "fermenting"


def test_climax():
    assert classify_theme_lifecycle([d(5, .1, 3, True), d(8, .1, 5, True), d(12, .1, 9, True)]) == "climax"


def test_divergence():
    assert classify_theme_lifecycle([d(12, .1, 9, True), d(11, .3, 6, True), d(9, .5, 4, True)]) == "divergence"


def test_ebb():
    assert classify_theme_lifecycle([d(9, .4, 4, True), d(5, .5, 2, False), d(2, .6, 0, False)]) == "ebb"
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/measurements/test_theme_lifecycle.py -v`

- [ ] **Step 3: Implement** (decay checks first so peak-then-fall isn't misread as launch)

```python
# src/aegis_alpha/measurements/theme_lifecycle.py
from __future__ import annotations

from dataclasses import dataclass

from aegis_alpha.models import ThemeLifecycleStage


@dataclass(frozen=True)
class ThemeDay:
    limit_up_count: int
    break_board_rate: float
    new_high_member_count: int
    leader_alive: bool


def classify_theme_lifecycle(series: list[ThemeDay]) -> ThemeLifecycleStage:
    """Deterministic stage over measured theme counts. Decay checked first."""
    if len(series) < 3:
        return "unknown"
    recent = series[-3:]
    counts = [x.limit_up_count for x in recent]
    peak = max(x.limit_up_count for x in series)
    nh_peak = max(x.new_high_member_count for x in series)

    falling_two = counts[-1] < counts[-2] and counts[-1] <= counts[-3]

    if falling_two and not recent[-1].leader_alive:
        return "ebb"
    if (recent[-1].break_board_rate > recent[-3].break_board_rate
            and counts[-1] <= counts[-3] and counts[-3] >= peak * 0.8):
        return "divergence"
    if counts[-1] == peak and recent[-1].new_high_member_count == nh_peak:
        return "climax"
    if counts[-1] > counts[-2] > counts[-3]:
        return "fermenting"
    if counts[-3] <= 2 and counts[-1] >= 3:
        return "launch"
    return "unknown"
```

- [ ] **Step 4: Run — verify PASS** (if climax/fermenting collide, climax runs first by design)

Run: `pytest tests/measurements/test_theme_lifecycle.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/measurements/theme_lifecycle.py tests/measurements/test_theme_lifecycle.py
git commit -m "feat: deterministic theme-lifecycle classifier (fact, not judgment)"
```

### Task 1C.3: Wire lifecycle into assembly (reproduce 电力 late-stage case)

**Files:** Modify `adapters/mock_market_data.py`, `adapters/jvquant/candidates.py`; Test `tests/test_candidate_theme_lifecycle_wired.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_candidate_theme_lifecycle_wired.py
from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter


def test_some_mock_theme_is_late_stage():
    stages = {c.theme_lifecycle_stage for c in MockMarketDataAdapter().get_second_board_candidates()}
    assert stages - {"unknown"}
    # the 电力-style late-stage case must be representable
    assert stages & {"climax", "divergence", "ebb"}
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_candidate_theme_lifecycle_wired.py -v`

- [ ] **Step 3: Implement**

Mock: attach a deterministic 3+ day `ThemeDay` series per fixture theme; classify; pass `theme_lifecycle_stage=`. Make one fixture theme (e.g. an "电力"-like theme) classify to `divergence`/`ebb` so 失败3 is a regression test. `candidates.py`: build `ThemeDay` from theme daily aggregates; <3 days → `"unknown"` + `data_quality` `unavailable`.

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_candidate_theme_lifecycle_wired.py -v`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: wire theme-lifecycle stage into candidates (electricity late-stage regression)"
```

### Task 1C.4: Report lifecycle in explain output

**Files:** Modify `adapters/jvquant/adapter.py`; Test: extend `tests/test_explain_includes_client_facts.py`

- [ ] **Step 1: Add the failing assertion**

```python
def test_explain_mentions_theme_lifecycle():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
    a = MockMarketDataAdapter()
    c = a.get_second_board_candidates()[0]
    blob = " ".join(a.explain_second_board_candidate(c.symbol).observations)
    assert "题材阶段" in blob
```

- [ ] **Step 2: Run — verify FAIL**

Run: `pytest tests/test_explain_includes_client_facts.py::test_explain_mentions_theme_lifecycle -v`

- [ ] **Step 3: Implement**

```python
_STAGE_CN = {"launch": "启动", "fermenting": "发酵", "climax": "高潮",
             "divergence": "分歧", "ebb": "退潮", "unknown": "未知"}
observations.append(f"题材阶段（测量值）：{_STAGE_CN[candidate.theme_lifecycle_stage]}。")
```

- [ ] **Step 4: Run — verify PASS**

Run: `pytest tests/test_explain_includes_client_facts.py -v`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: explain reports theme-lifecycle stage as a measurement"
```

### Task 1C.5: Phase 1 closeout

**Files:** Modify `README.md`, `docs/AI_INTEGRATION.md`

- [ ] **Step 1: Full suite + coverage**

Run: `pytest --cov=aegis_alpha --cov-report=term-missing`
Expected: green, ≥ 80%.

- [ ] **Step 2: Grep for leftover program judgment**

Run: `rg -n "candidate_grade|seal_quality_score|estimated_seal_probability|grade_reason" src/`
Expected: ZERO (agent_eval's *agent-output* `grade` validation uses the bare word "grade" — confirm each remaining hit is agent-output, not program judgment).

- [ ] **Step 3: Update docs**

`README.md` safety boundary: "The program measures facts and never assigns a buy/sell grade; the AI agent judges." List the 7 new facts (incl. 股本/题材阶段). `docs/AI_INTEGRATION.md`: one-line facts-vs-judgment statement.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/AI_INTEGRATION.md
git commit -m "docs: Phase 1 — program measures facts, agent judges (grade removed)"
```

- [ ] **Step 5: Phase 1 DONE** — candidates carry 股本/量/斜率/前高/题材阶段 + zero program judgment. 失败3 (电力 late-stage) is now measurable. Hand to Phase 2.

---

# PHASE 2 — Promotion Dossier (SCOPED SPEC)

**Goal:** Bundle the 失败2 factors the agent must see into ONE MCP "judgment dossier" — **facts only, no score**: 市场情绪快照 (existing gate fields), 题材位置 (`theme_lifecycle_stage`), 股本 (`free_float_market_cap_cny`), 成交量 (`avg_turnover_10d_cny`/turnover), 回封力度 (`break_board_count`/`reseal_count`/`max_seal_amount_cny`/`final_seal_time`).
**Deliverables:** `get_promotion_dossier(symbol)` MCP tool returning a `PromotionDossier` model (all measured facts, NO probability/grade); it just *assembles* what the agent needs in one call so the agent can't "forget" a factor.
**Why before skill restructure:** Phase 3's skill tells the agent to walk these factors — the dossier guarantees they're all fetchable in one tool.

---

# PHASE 3 — Skill Restructure (SCOPED SPEC) — fixes 失败2 directly

**Goal:** Rewrite `.hermes/skills/second-board-radar/SKILL.md` so the agent MUST walk 市场情绪 → 题材位置 → 股本 → 量能 → 回封力度 and output **晋级三板概率 + 综合评级 + 逐项理由** — never "只给总结".
**Deliverables:** SKILL.md factor-checklist section; the agent emits its OWN grade+probability (validated by existing `agent_eval.py`); an offline replay test that fails if the agent output lacks any of the 5 factors or the probability. 财联社 = placeholder mention only.
**Constraint:** skill is human-authored (no `skill_write`); this phase edits it by hand. The agent's grade is *judgment*, allowed.

---

# PHASE 4 — Offline Buy-Point State Machine (SCOPED SPEC)

**Goal:** Detect 过前高→回踩缩量→重新上冲=买点 on **historical minute data** (offline replay).
**Deliverables:** `src/aegis_alpha/measurements/buypoint_state_machine.py` — pure, table-tested per transition; states `idle → broke_high(vol-confirmed) → pullback(vol-shrink) → re_surge → BUY_POINT_ALERT`, each transition a measured condition over minute bars + Phase-1 facts; `IntradayBuyPointSignal` model (state, triggered_at, evidence facts, NO buy instruction); offline replay CLI/MCP tool emitting the signal timeline; `same_theme_co_pumping_count` at surge (reuse `same_theme_rising_count`).
**Constraint:** alert ≠ order; `PROHIBITED_DIRECTIVE_PATTERNS` must still pass.

---

# PHASE 5 — Strategy-Prior Injection (SCOPED SPEC)

**Goal:** Client's 10-point strategy becomes a **switchable prior** injected into skill/prompt — thresholds (斜率30–60°, 均量>50亿) live here as *agent guidance*, never hardcoded filters in the program.
**Deliverables:** `config/strategy_priors/` (natural-language priors); `get_active_strategy_prior()` MCP tool (read-only; switching is human/config, gated); SKILL.md references prior while preserving agent override-with-reasoning. 板块两周持续性盘外抓取 = agent task guided by prior. 财联社 = placeholder field only.
**Constraint:** priors are guidance; program never rejects on a prior.

---

# PHASE 6 — Runner Monitor Windows + Live Alert (SCOPED SPEC, HIGHEST RISK)

**Goal:** Runner watches 9:30–9:50 and 11:10–11:30, runs the Phase-4 machine live, emits (paper) buy-point alerts.
**Deliverables:** `config/runner.yaml` `monitor_windows` block (open_drive 09:30–09:50, late_morning 11:10–11:30); runner runs the state machine only inside windows; alerts via existing P8 runner alert plumbing; existing `stale_after_seconds: 180` enforced on live minute data.
**Constraint:** PAPER only; no order; live data read-only.

---

# PHASE 7 — Ground-Truth Eval + Feedback→Memory (SCOPED SPEC, LAST)

**Goal:** Score the agent's calls against actual next-day truth, and wire client feedback into Hermes memory — human-in-the-loop, through the disclaimer gate.
**Deliverables:**
- Re-home the gated `feedback/backtest.py` harness to **agent prediction vs realized outcome** (did predicted buy-point precede a real surge? is promotion-probability calibrated to realized sealed/gap-up?); `feedback/agent_scorecard.py` (Brier/hit-rate vs `feedback/backfill.py` truth); `get_agent_judgment_scorecard(window)` MCP tool.
- Extend correction pipeline (`record_agent_review_correction` → `create_correction_action_proposals` → `get_pending_correction_actions` → `record_correction_action_decision`) to accept *client-outcome* feedback; a proposal that, **on human approval**, surfaces a suggested MEMORY.md note (e.g. "client confirms theme_lifecycle_stage=ebb is a strong veto"). Aegis Alpha only *proposes*; human/agent writes memory.
**Constraints (safety-critical):** keep "Aegis Alpha does NOT apply memory/skill/config/adapter changes automatically" verbatim. NO `skill_write`; skill self-rewrite stays human-authored (terminal-tool backdoor out of scope). Add a test asserting no code path auto-mutates MEMORY.md/USER.md/SKILL.md/config.

---

## Master Self-Review

1. **Spec coverage** — every client item maps to a phase (see the mapping table at top). The previously-dropped **股本 (free_float_market_cap_cny)** is now Phase 1B.1; 失败2 (概率+综合评级 judgment structure) is now its own Phase 3; the two products (overnight case vs intraday strategy) are split into Phases 2-3 vs 4-6. ✓
2. **Placeholder scan** — Phase 1 has full code; Phases 2-7 are explicitly scoped specs to be expanded before execution (stated in header). 财联社 placeholder-only is honored. ✓
3. **Type consistency** — `ThemeLifecycleStage` enum (1C.1) used by `theme_lifecycle.py` (1C.2) + field (1C.3) under one name; `client_facts.py` helper names match tests + call sites; removed `grade`/`grade_reason`/`estimated_seal_probability` dropped from BOTH `SecondBoardCandidate` and `CandidateExplanation`; `free_float_market_cap_cny` named identically to `NewStockCandidate:861`. ✓

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-05-facts-and-buypoint-radar.md`. **Phase 1 is ready now**; Phases 2–7 expand into their own plans as Phase 1 lands.

Two options for **Phase 1**:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — Phase 1 tasks in this session via executing-plans, batched with checkpoints.

Which approach?
