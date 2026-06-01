# P8 — Runner Alerts + Hypothesis Real Re-grade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修一个真实 bug（P6 新加的 3 个事件类型从来不会通知）+ 把 P7 starter `simulate_outcome` 升级到接 `candidate_grade()` 真重算 + 顺手收尾 P7 reviewer 的 4 条小尾巴。

**Architecture:**
本期不引入新子系统、不动架构、不接 jvQuant 真实端点。所有改动都是局部修补：runner 的 alert 集合 + try/except 拆分 + adapter 缓存；`simulate_outcome` 改成 candidate_grade 桥接；mock 数据 + 测试断言加严；docs 微调。

**Tech Stack:**
Python 3.11+, Pydantic v2, FastMCP, pytest TDD（无新依赖）。

---

## P8 范围（来自 P7 reviewer + 仓库实际盘点）

| # | 项目 | 严重性 | 来源 |
|---|------|------|------|
| 1 | runner alert critical_types 集合缺 P6/P7 三个事件类型 | **真实 bug** | P8 实际盘点 |
| 2 | `_collect_sector_events` 单个 try/except 包两个 detector，前一个成功后一个失败会丢前一个的结果 | 健壮性 | P7 reviewer |
| 3 | runner 每 tick 调一次 `create_market_data_adapter()`，应缓存 | 性能 | P8 实际盘点 |
| 4 | `simulate_outcome` 接 `candidate_grade()` 真重算，弃用 P7 starter `_GRADE_LADDER` 启发 | 准确性 | P7 reviewer |
| 5 | P6 原 hypothesis 测试不断言 `hypothetical_grade`，现在 Task 4 之后能补 | 测试质量 | P7 reviewer |
| 6 | mock adapter `get_active_seats_today` 只返回 1 项，演示价值低 | 可观察性 | P8 实际盘点 |
| 7 | docs sync + 全量回归 | 标准收尾 |  |

任务总数：7 个 task。

## 强制约束（Subagent 实施时必须遵守）

1. **不允许真实交易、不允许写真实下单**。
2. **不能私改 LLM 模型名**。`anthropic/claude-opus-4-7` 与 `deepseek-v4-pro` 名字保持原样。
3. **TDD 严格执行**：每个改动先写失败测试，再改实现，再 commit。
4. **保留向后兼容**：公开 API（MCP tool / Protocol 方法 / 模型字段）不删字段不改类型。
5. **不要新增子系统**：本期纯修补 + Task 4 一处算法替换。
6. **不要重构**：例如不要拆 `runner.py`、不要重命名常量。只在原位改最小代码。
7. **不要碰 jvQuant placeholder**。它们由 `docs/superpowers/plans/2026-06-01-future-jvquant-real-integration-roadmap.md` 单独管理。
8. **不要校准 starter 阈值**。值不变，等以后有足够 review_outcomes 样本再说。
9. **所有 sub-agent worktree 必须 base 在 `main` 当前 HEAD**（仓库根 `.claude/settings.json` 已配 `worktree.baseRef = head`）。

## 文件结构（落盘前先看完）

### 修改

| Path | 修改内容 |
|------|---------|
| `src/aegis_alpha/runner.py` | (1) `critical_types` 集合加 3 项；(2) `_collect_sector_events` 拆 2 个 try/except；(3) adapter 缓存 |
| `src/aegis_alpha/feedback/hypothesis.py` | `simulate_outcome` 调 `candidate_grade()` 真重算（保留 starter 的整数 delta 接口供回退） |
| `src/aegis_alpha/adapters/mock_market_data.py` | `get_active_seats_today` 增加 2 个游资别名条目，让 SKILL 演示更真实 |
| `tests/test_runner.py` | 3 个新测试覆盖 alert 集合 + try/except 拆分 + adapter 缓存 |
| `tests/feedback/test_hypothesis.py` | 加严 P6 旧测试的 hypothetical_grade 断言；新增 candidate_grade 真重算测试 |
| `tests/extensions/test_dragon_tiger.py` | mock adapter 多游资测试 |
| `README.md` | P8 段落 |
| `.hermes/skills/second-board-radar/SKILL.md` | item 21 备注「板块事件现在会触发告警」 |

### 新增

| Path | 责任 |
|------|------|
| 无新文件 | 本期纯修补 |

---

## Task 1: 修复 runner alert critical_types 集合

**Files:**
- Modify: `src/aegis_alpha/runner.py:236-240`
- Test: `tests/test_runner.py`

**Background:**
P5 / P6 加了 3 个新 `MarketEventType` 值（`MARKET_BOTTOM_REVERSAL`, `THEME_LEADER_BREAK_BOARD`, `SECTOR_ROTATION`），但 `_maybe_alert_from_events` 的 `critical_types` 集合在 P3 时定下，从未更新。P7 把 `THEME_LEADER_BREAK_BOARD` / `SECTOR_ROTATION` 接进 `_collect_sector_events`，但事件被产出后还是不会触发 `notify_macos`。这是真实 bug。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_runner.py`：

```python
def test_maybe_alert_from_events_includes_p6_event_types(tmp_path, monkeypatch):
    """P6/P7 added 3 new MarketEventType values; runner alert pipeline must
    surface them. Otherwise THEME_LEADER_BREAK_BOARD / SECTOR_ROTATION /
    MARKET_BOTTOM_REVERSAL events are detected and silently dropped."""
    from unittest.mock import MagicMock

    from aegis_alpha.models import MarketEvent
    from aegis_alpha.runner import AegisAlphaRunner

    config_path = tmp_path / "runner.yaml"
    db_path = tmp_path / "runner.db"
    config_path.write_text(
        f"""
market: ab
loop_interval_seconds: 5
trading_sessions:
  - name: all_day
    start: "00:00"
    end: "23:59"
subscription:
  default_symbols: ["600000"]
  levels: ["lv1"]
storage:
  sqlite_path: "{db_path}"
  status_path: "{tmp_path / 'runner_status.json'}"
""".strip()
    )
    runner = AegisAlphaRunner(config_path=str(config_path), connect=False)

    triggered: list[str] = []

    def _capture(_alert):
        triggered.append(_alert.title)

    monkeypatch.setattr("aegis_alpha.runner.notify_macos", _capture, raising=False)
    # alerts.notifier.notify_macos is also imported lazily inside the method;
    # patch both lookup sites
    import aegis_alpha.alerts.notifier as notifier_mod
    monkeypatch.setattr(notifier_mod, "notify_macos", _capture, raising=False)

    events = [
        MarketEvent(
            event_id=f"e{i}",
            event_type=event_type,  # type: ignore[arg-type]
            symbol="600519", name="x", theme="AI",
            confidence="medium", score=70.0,
            evidence=["test"],
            provider_timestamp="2026-06-01T09:30:00+08:00",
            received_at="2026-06-01T09:30:00+08:00",
            freshness_status="fresh",
            suggested_agent_action=[],
            data={},
        )
        for i, event_type in enumerate(
            [
                "THEME_LEADER_BREAK_BOARD",
                "SECTOR_ROTATION",
                "MARKET_BOTTOM_REVERSAL",
            ]
        )
    ]
    runner._maybe_alert_from_events(events)
    assert len(triggered) == 3, (
        f"all 3 P6 event types should trigger notify_macos; got titles: {triggered}"
    )
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py::test_maybe_alert_from_events_includes_p6_event_types -v`
Expected: FAIL — only 0 alerts triggered (none of the 3 are in `critical_types` yet).

- [ ] **Step 3: 修 runner.py**

打开 `src/aegis_alpha/runner.py:236-240`。把 `critical_types` 集合扩成：

```python
        critical_types = {
            "SEAL_ORDER_DECAY",
            "BIG_ORDER_INFLOW_SPIKE",
            "THEME_DIVERGENCE",
            "THEME_LEADER_BREAK_BOARD",
            "SECTOR_ROTATION",
            "MARKET_BOTTOM_REVERSAL",
        }
```

并把 severity 选择拓宽（高 height 龙头炸板 + 板块底部反转判 critical，sector_rotation 判 warning）。把 `severity = ...` 那一行替换为：

```python
            critical_severity_types = {
                "SEAL_ORDER_DECAY",
                "THEME_LEADER_BREAK_BOARD",
                "MARKET_BOTTOM_REVERSAL",
            }
            severity = (
                "critical" if event.event_type in critical_severity_types else "warning"
            )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py -v`
Expected: 全部 PASS（既有 + 新加）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/runner.py tests/test_runner.py
git commit -m "Fix runner alert pipeline missing P6/P7 event types"
```

---

## Task 2: 拆分 _collect_sector_events 的 try/except

**Files:**
- Modify: `src/aegis_alpha/runner.py:200-225`
- Test: `tests/test_runner.py`

**Background:**
P7 reviewer minor：`_collect_sector_events` 用单个 `except Exception` 包了 leader 拉取 + 两个 detector。如果 `detect_sector_rotation` 抛错，前面 `detect_theme_leader_break_board` 已经累积的 events 会被一起丢掉（因为整个块 `return []`）。改成分块 try/except 后，前一个 detector 的结果即使后一个失败也能保留。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_runner.py`：

```python
def test_collect_sector_events_preserves_partial_results_when_one_detector_fails(
    tmp_path, monkeypatch
):
    """If detect_theme_leader_break_board succeeds but detect_sector_rotation
    raises, the break_board events should NOT be dropped."""
    from unittest.mock import MagicMock

    from aegis_alpha.models import MarketEvent, ThemeLeader
    from aegis_alpha.runner import AegisAlphaRunner

    config_path = tmp_path / "runner.yaml"
    db_path = tmp_path / "runner.db"
    config_path.write_text(
        f"""
market: ab
loop_interval_seconds: 5
trading_sessions:
  - name: all_day
    start: "00:00"
    end: "23:59"
subscription:
  default_symbols: ["600000"]
  levels: ["lv1"]
storage:
  sqlite_path: "{db_path}"
  status_path: "{tmp_path / 'runner_status.json'}"
""".strip()
    )
    runner = AegisAlphaRunner(config_path=str(config_path), connect=False)

    broken_leader = ThemeLeader(
        theme="AI", trading_day="2026-06-01",
        leader_symbol="600519", leader_name="L",
        leader_consecutive_boards=3,
        leader_first_limit_up_time="09:30:00",
        leader_seal_amount_cny=200_000_000.0,
        leader_status="broken",
        co_leader_symbols=[],
        member_count=4,
    )
    fake_adapter = MagicMock()
    fake_adapter.get_theme_leaders = MagicMock(return_value=[broken_leader])
    monkeypatch.setattr(
        "aegis_alpha.runner.create_market_data_adapter",
        lambda: fake_adapter,
        raising=False,
    )

    def _explode(*args, **kwargs):
        raise RuntimeError("rotation detector exploded")

    monkeypatch.setattr(
        "aegis_alpha.runner.detect_sector_rotation", _explode, raising=False,
    )

    events = runner._collect_sector_events()
    types = {e.event_type for e in events}
    # break_board still landed despite rotation failing
    assert "THEME_LEADER_BREAK_BOARD" in types
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py::test_collect_sector_events_preserves_partial_results_when_one_detector_fails -v`
Expected: FAIL — current single-block try/except returns `[]` when rotation detector throws.

- [ ] **Step 3: 重写 _collect_sector_events**

打开 `src/aegis_alpha/runner.py:200`。把整个 `_collect_sector_events` 替换为：

```python
    def _collect_sector_events(self) -> list[MarketEvent]:
        """Best-effort: fetch ThemeLeader snapshot and run sector-event detectors.

        Each step has its own try/except so partial results survive a failing
        detector. Failures are still swallowed — sector events are advisory and
        runner liveness must not depend on them.
        """
        from datetime import date as _date

        try:
            adapter = create_market_data_adapter()
            trading_day = _date.today().isoformat()
            leaders = adapter.get_theme_leaders(theme="", trading_day=trading_day)
        except Exception:
            return []
        if not leaders:
            return []

        events: list[MarketEvent] = []
        try:
            events.extend(
                detect_theme_leader_break_board(
                    LeaderBreakInputs(leaders=leaders, trading_day=trading_day)
                )
            )
        except Exception:
            pass
        try:
            events.extend(
                detect_sector_rotation(
                    SectorRotationInputs(leaders=leaders, trading_day=trading_day)
                )
            )
        except Exception:
            pass
        return events
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py -v`
Expected: 全部 PASS（含 P7 已有的 `test_persist_buffer_outputs_appends_sector_events_when_leader_breaks` 也应继续 PASS，因为它没强制要求 rotation detector 必须跑成功）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/runner.py tests/test_runner.py
git commit -m "Split _collect_sector_events try/except so partial results survive"
```

---

## Task 3: runner adapter 缓存

**Files:**
- Modify: `src/aegis_alpha/runner.py`
- Test: `tests/test_runner.py`

**Background:**
P7 给 runner 加了 `_collect_sector_events`，每个 tick 调一次 `create_market_data_adapter()`。`MockMarketDataAdapter` 构造便宜，但 `JvQuantMarketDataAdapter.from_env()` 会建立 query client + 一些缓存对象，频繁实例化是浪费。改成 lazy 缓存 instance，构造一次后复用。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_runner.py`：

```python
def test_collect_sector_events_caches_adapter_instance(tmp_path, monkeypatch):
    """create_market_data_adapter should be called at most once across multiple
    runner ticks, not once per tick."""
    from unittest.mock import MagicMock

    from aegis_alpha.models import ThemeLeader
    from aegis_alpha.runner import AegisAlphaRunner

    config_path = tmp_path / "runner.yaml"
    db_path = tmp_path / "runner.db"
    config_path.write_text(
        f"""
market: ab
loop_interval_seconds: 5
trading_sessions:
  - name: all_day
    start: "00:00"
    end: "23:59"
subscription:
  default_symbols: ["600000"]
  levels: ["lv1"]
storage:
  sqlite_path: "{db_path}"
  status_path: "{tmp_path / 'runner_status.json'}"
""".strip()
    )
    runner = AegisAlphaRunner(config_path=str(config_path), connect=False)

    fake_adapter = MagicMock()
    fake_adapter.get_theme_leaders = MagicMock(return_value=[
        ThemeLeader(
            theme="AI", trading_day="2026-06-01",
            leader_symbol="600519", leader_name="L",
            leader_consecutive_boards=2,
            leader_first_limit_up_time="09:30:00",
            leader_seal_amount_cny=100_000_000.0,
            leader_status="sealed",
            co_leader_symbols=[],
            member_count=2,
        )
    ])
    factory = MagicMock(return_value=fake_adapter)
    monkeypatch.setattr(
        "aegis_alpha.runner.create_market_data_adapter", factory, raising=False,
    )

    runner._collect_sector_events()
    runner._collect_sector_events()
    runner._collect_sector_events()

    assert factory.call_count == 1, (
        f"adapter factory should be called once across 3 ticks; got {factory.call_count}"
    )
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py::test_collect_sector_events_caches_adapter_instance -v`
Expected: FAIL — current code calls `create_market_data_adapter()` every tick, factory.call_count == 3.

- [ ] **Step 3: 加缓存属性**

打开 `src/aegis_alpha/runner.py:89-105` 的 `__init__`。在末尾追加一行：

```python
        self._sector_events_adapter = None  # lazy-built on first _collect_sector_events
```

然后在 `_collect_sector_events` 中（Task 2 已经重写过的版本），把 `adapter = create_market_data_adapter()` 这一行替换为：

```python
            if self._sector_events_adapter is None:
                self._sector_events_adapter = create_market_data_adapter()
            adapter = self._sector_events_adapter
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_runner.py -v`
Expected: 全部 PASS。

注意：Task 2 加的 `test_collect_sector_events_preserves_partial_results_when_one_detector_fails` 测试当中也用 monkeypatch 替换了 `create_market_data_adapter`。Task 3 后这个 monkeypatch 仍然有效（cache 是 instance attr，每个测试新建 runner 时为 None）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/runner.py tests/test_runner.py
git commit -m "Cache market data adapter in runner _collect_sector_events"
```

---

## Task 4: simulate_outcome 接 candidate_grade() 真重算

**Files:**
- Modify: `src/aegis_alpha/feedback/hypothesis.py`
- Test: `tests/feedback/test_hypothesis.py`

**Background:**
P7 给 `simulate_outcome` 加了 starter `_GRADE_LADDER + _grade_delta_from_crossing` 启发式：seal_amount 跨 5亿、speed 跨 5% 各 ±1 step。这是临时方案。本任务接 `aegis_alpha.adapters.jvquant.scoring.candidate_grade()` 真函数：

```python
candidate_grade(
    *,
    action: str,
    change_pct: float,
    five_min_speed_pct: float,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    theme_count: int,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> CandidateGrade
```

策略：从 `snapshot.payload_json` 抽出当前 9 个字段值，应用 `hypothesis` 覆盖，喂 `candidate_grade()`，得到真 hypothetical_grade。Snapshot 缺字段时用合理默认（让 candidate_grade 退化到 C/REJECT）。

starter `_GRADE_LADDER` 启发式不再用，但 module-level 常量保留供回退或调试参考。

- [ ] **Step 1: 写失败测试**

追加到 `tests/feedback/test_hypothesis.py`：

```python
def test_simulate_outcome_uses_real_candidate_grade_for_a_grade_inputs():
    """When all of seal/speed/inflow/orderbook/theme_count clear A thresholds,
    candidate_grade returns 'A' and simulate_outcome must reflect that."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    # Snapshot with mediocre numbers → originally C
    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="AI", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json=(
            '{"action": "active",'
            ' "change_pct": 5.0,'
            ' "five_min_speed_pct": 1.0,'
            ' "big_order_net_inflow_ratio": 0.05,'
            ' "orderbook_quality_score": 50.0,'
            ' "same_theme_rising_count": 1,'
            ' "first_limit_up_time": "09:32:00",'
            ' "seal_amount_cny": 100000000.0,'
            ' "seal_to_turnover_ratio": 0.5}'
        ),
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={
                "change_pct": 9.5,
                "five_min_speed_pct": 4.0,
                "big_order_net_inflow_ratio": 0.30,
                "orderbook_quality_score": 75.0,
                "same_theme_rising_count": 5,
                "seal_amount_cny": 800_000_000.0,
                "seal_to_turnover_ratio": 3.0,
            },
        )
    )
    assert out is not None
    assert out.original_grade == "C"
    # Real candidate_grade with these numbers should return "A"
    assert out.hypothetical_grade == "A"


def test_simulate_outcome_uses_real_candidate_grade_for_reject_when_action_avoid():
    """When action=avoid, candidate_grade always returns REJECT regardless of metrics."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="B",
        grade_reason="", theme="AI", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json=(
            '{"action": "active",'
            ' "change_pct": 9.0,'
            ' "five_min_speed_pct": 4.0,'
            ' "big_order_net_inflow_ratio": 0.20,'
            ' "orderbook_quality_score": 70.0,'
            ' "same_theme_rising_count": 4,'
            ' "first_limit_up_time": "09:32:00",'
            ' "seal_amount_cny": 300000000.0,'
            ' "seal_to_turnover_ratio": 2.0}'
        ),
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"action": "avoid"},
        )
    )
    assert out is not None
    assert out.original_grade == "B"
    assert out.hypothetical_grade == "REJECT"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -k "uses_real_candidate_grade" -v`
Expected: FAIL — current starter rules don't track action=avoid → REJECT, and don't promote to A on multi-field crossings.

- [ ] **Step 3: 重写 simulate_outcome**

打开 `src/aegis_alpha/feedback/hypothesis.py`。完整替换文件内容为：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.adapters.jvquant.scoring import candidate_grade
from aegis_alpha.grading import CandidateGradingConfig
from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


_GRADE_FALLBACK = "C"


@dataclass(frozen=True)
class HypothesisInputs:
    snapshot: HistoricalCandidateSnapshot
    hypothesis: dict[str, Any]


def _safe_float(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(payload: dict[str, Any], key: str, default: int = 0) -> int:
    value = payload.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _grade_via_candidate_grade(
    payload: dict[str, Any], *, config: CandidateGradingConfig
) -> str:
    """Apply candidate_grade() to a payload dict, returning the resulting grade.

    Missing fields default to neutral values that make candidate_grade typically
    return 'C'. Returns the fallback grade if candidate_grade raises (which it
    shouldn't for any well-formed input)."""
    try:
        return candidate_grade(
            action=str(payload.get("action") or "active"),
            change_pct=_safe_float(payload, "change_pct"),
            five_min_speed_pct=_safe_float(payload, "five_min_speed_pct"),
            big_order_net_inflow_ratio=_safe_float(
                payload, "big_order_net_inflow_ratio"
            ),
            orderbook_quality=_safe_float(payload, "orderbook_quality_score"),
            theme_count=_safe_int(payload, "same_theme_rising_count"),
            first_limit_up_time=str(payload.get("first_limit_up_time") or "unknown"),
            seal_amount_cny=_safe_float(payload, "seal_amount_cny"),
            seal_to_turnover_ratio=_safe_float(payload, "seal_to_turnover_ratio"),
            config=config,
        )
    except Exception:
        return _GRADE_FALLBACK


def simulate_outcome(inputs: HypothesisInputs) -> HypothesisOutcome | None:
    """Apply `hypothesis` (a dict of field overrides) to the snapshot's payload
    and return a structured comparison with re-graded hypothetical_grade.

    Returns None when the snapshot payload is not valid JSON.

    Re-grading uses the real `candidate_grade()` function (P8), replacing the
    P7 starter `_GRADE_LADDER` heuristic. Hypothesis can override any of the
    9 candidate_grade kwargs by key (e.g. "action", "seal_amount_cny", ...).
    """
    try:
        payload = json.loads(inputs.snapshot.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    config = CandidateGradingConfig()
    new_payload = dict(payload)
    new_payload.update(inputs.hypothesis)

    payload_diff: dict[str, Any] = {}
    for key, new_value in inputs.hypothesis.items():
        original_value = payload.get(key, None)
        if original_value != new_value:
            payload_diff[key] = {
                "original": original_value,
                "hypothetical": new_value,
            }

    original_grade = _grade_via_candidate_grade(payload, config=config)
    hypothetical_grade = _grade_via_candidate_grade(new_payload, config=config)

    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        # Use snapshot's stored grade_at_pick when known, else derived
        original_grade=inputs.snapshot.grade_at_pick or original_grade,
        hypothetical_grade=hypothetical_grade,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            "P8: re-graded via candidate_grade() with hypothesis-overridden payload"
        ],
    )
```

注意：`original_grade` 优先用 `snapshot.grade_at_pick`（这是历史快照保存时的真实评级），fallback 才用 `_grade_via_candidate_grade(payload)`。这保留了「这个快照当时拿了什么评级」的事实，同时提供 `hypothetical_grade` 给「如果当时数据是这样会拿什么评级」的回答。

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -v`
Expected: 6 PASS（P6 原 2 个 + P7 加的 2 个 + P8 加的 2 个）。

如果 P7 测试 `test_simulate_outcome_promotes_grade_when_seal_amount_doubles_above_threshold` 或 `test_simulate_outcome_keeps_grade_when_hypothesis_does_not_cross_threshold` 在新逻辑下行为不同（candidate_grade 真重算可能给出不同答案），需要逐个评估：

- 如果 candidate_grade 给的答案**更准确**且与 `original_grade=C` + 新 payload 一致，更新断言。
- 如果新答案明显错误，回到 `_grade_via_candidate_grade` 检查字段映射是否漏字段。

预期：P7 的两个测试快照只设了 seal_amount/speed_pct 两字段。candidate_grade 缺其它字段时（特别是 `orderbook_quality` 默认 0），会把 5亿 + 4% speed + 0 inflow 的快照判为 `C`（B 路径需要 orderbook_quality >= b_orderbook_quality 或 inflow > 0 或 seal_q >= b_seal_quality）。**很可能 P7 的 promotes_grade 测试在 P8 后变成「C → C」**。如果这样，更新这俩测试的断言反映真实重算结果，并在 commit message 注明。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/feedback/hypothesis.py tests/feedback/test_hypothesis.py
git commit -m "Replace simulate_outcome starter heuristic with real candidate_grade()"
```

---

## Task 5: 加严 P6 hypothesis 测试断言

**Files:**
- Modify: `tests/feedback/test_hypothesis.py:1-50`

**Background:**
P7 reviewer minor：`test_simulate_outcome_changes_grade_when_seal_amount_doubled` 这个测试（P6 时写的）注释说「grade stays 'B'」，但函数体从来没断言过 `hypothetical_grade`。Task 4 接了真重算之后，可以补上这个断言。

- [ ] **Step 1: 看现状**

打开 `tests/feedback/test_hypothesis.py:1-50`。第一个测试 `test_simulate_outcome_changes_grade_when_seal_amount_doubled` 大致是：

```python
def test_simulate_outcome_changes_grade_when_seal_amount_doubled(tmp_path):
    ...
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 200_000_000.0},
        )
    )
    assert out.original_grade == "B"
    assert out.applied_hypothesis == {"seal_amount_cny": 200_000_000.0}
    assert "seal_amount_cny" in out.payload_diff
    # ❌ never asserts on hypothetical_grade
```

snapshot payload 只有 `{"seal_amount_cny": 100000000.0, "five_min_speed_pct": 2.5}`。其他字段都缺，candidate_grade 走 fallback 路径。Task 4 的 `_grade_via_candidate_grade` 把缺失字段当 0 / "active" / "unknown"。结果：

- 5亿 seal + 2.5% speed + 0 inflow + 0 orderbook → C（无 A 路径，无 B 路径）

把 hypothesis `seal_amount_cny=200M` 应用后，依然 C。

- [ ] **Step 2: 加断言**

把测试改成：

```python
def test_simulate_outcome_changes_grade_when_seal_amount_doubled(tmp_path):
    """If we hypothesize the seal amount is 2x larger, the rule may upgrade grade.
    With the existing payload (only seal_amount + 5min speed, no inflow/orderbook),
    candidate_grade returns C for both original and hypothetical. We still verify
    the structured comparison output."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="600519", trading_day="2026-05-30", grade_at_pick="B",
        grade_reason="", theme="X", theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"seal_amount_cny": 100000000.0, "five_min_speed_pct": 2.5}',
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(
            snapshot=snap,
            hypothesis={"seal_amount_cny": 200_000_000.0},
        )
    )
    assert out.original_grade == "B"  # snapshot's stored grade_at_pick
    assert out.applied_hypothesis == {"seal_amount_cny": 200_000_000.0}
    assert "seal_amount_cny" in out.payload_diff
    # P8: verify hypothetical_grade is computed via candidate_grade. With
    # only seal+speed in payload (other inputs default to 0), the hypothetical
    # grade lands at C via the fallback path.
    assert out.hypothetical_grade == "C"
```

- [ ] **Step 3: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -v`
Expected: 6 PASS。

- [ ] **Step 4: 提交**

```bash
git add tests/feedback/test_hypothesis.py
git commit -m "Strengthen P6 hypothesis test with hypothetical_grade assertion"
```

---

## Task 6: mock get_active_seats_today 增加多个游资条目

**Files:**
- Modify: `src/aegis_alpha/adapters/mock_market_data.py:860-868`
- Test: `tests/extensions/test_dragon_tiger.py`

**Background:**
mock 模式 `get_active_seats_today` 当前只返回 1 项（章盟主 + 1 只票）。SKILL workflow item 21 鼓励 agent 用这个工具看「当天哪几位游资同时进入多只股」，但 mock 只有 1 项时 agent 没机会演示「板块共振」。补到 3 项 + 让其中 1 个游资覆盖多只票，演示价值更高。

- [ ] **Step 1: 写失败测试**

追加到 `tests/extensions/test_dragon_tiger.py`：

```python
def test_mock_active_seats_today_returns_multiple_aliases_for_demo():
    """Mock should expose at least 3 aliases and at least one alias covering
    multiple symbols, so SKILL workflow's "板块共振" demo has signal."""
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    rows = adapter.get_active_seats_today("2026-06-01")
    aliases = {r["hot_money_alias"] for r in rows}
    assert len(aliases) >= 3, f"expected >=3 aliases, got {aliases}"
    multi_symbol_rows = [r for r in rows if r.get("symbol_count", 0) >= 2]
    assert multi_symbol_rows, (
        "at least one alias should cover multiple symbols for resonance demo"
    )
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py::test_mock_active_seats_today_returns_multiple_aliases_for_demo -v`
Expected: FAIL — current mock only returns 1 alias.

- [ ] **Step 3: 扩 mock**

打开 `src/aegis_alpha/adapters/mock_market_data.py:860-868`。把 `get_active_seats_today` 替换为：

```python
    def get_active_seats_today(self, trading_day: str) -> list[dict]:
        return [
            {
                "hot_money_alias": "章盟主",
                "symbol_count": 2,
                "total_net_buy_cny": 25_000_000.0,
                "symbols": ["600519", "300750"],
            },
            {
                "hot_money_alias": "孙哥",
                "symbol_count": 1,
                "total_net_buy_cny": 8_000_000.0,
                "symbols": ["002230"],
            },
            {
                "hot_money_alias": "欢乐海岸",
                "symbol_count": 3,
                "total_net_buy_cny": 18_000_000.0,
                "symbols": ["600519", "002594", "300750"],
            },
        ]
```

注意：章盟主 + 欢乐海岸都进了 600519 和 300750 → SKILL agent 可以拿这个演示「两个游资同时锁定同一只票」的板块共振语境。

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py -v`
Expected: 全部 PASS（既有 mock_adapter_active_seats_today_non_empty 仍 PASS，因为只断言 `isinstance` + `hot_money_alias` 字段存在）。

如果之前的 P5/P6 测试断言了「`章盟主` 出现且只出现 1 次」，那个测试需要适应新 mock 数据 — 但事先看了一下，没有这种硬约束。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/adapters/mock_market_data.py tests/extensions/test_dragon_tiger.py
git commit -m "Expand mock get_active_seats_today to 3 aliases for SKILL demo value"
```

---

## Task 7: docs sync + 全量回归

**Files:**
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

**Background:**
Tasks 1-6 改了 4 处 agent-visible behavior：
- 板块事件现在会触发 macOS 告警
- `simulate_outcome` 返回真重算的 `hypothetical_grade`
- mock 龙虎榜聚合多了 2 个游资
- 启动后 adapter 缓存 1 次

README + SKILL 加段说明，全量回归收尾。

- [ ] **Step 1: README 加 P8 段落**

打开 `README.md`，找到 P7 段落的结尾（应该是「给 `get_new_stock_candidates` / `get_suspended_stocks` 补 adapter-错误路径回归测试。」这一行）。在这行之后追加：

```markdown
P8 runner alerts + hypothesis 真重算（自 2026-06 起完成）：

- `runner._maybe_alert_from_events` 的 critical_types 集合补齐 P5/P6 加的 3 个事件类型（`MARKET_BOTTOM_REVERSAL`、`THEME_LEADER_BREAK_BOARD`、`SECTOR_ROTATION`），它们之前被检测出来后会被 silent 丢弃。
- `_collect_sector_events` 拆成 3 段独立 try/except —— 一个 detector 失败不会再丢弃另一个 detector 已产出的事件。
- runner 缓存 `create_market_data_adapter()` 实例，每次启动只构造一次，跨 tick 复用。
- `simulate_outcome` 弃用 P7 starter `_GRADE_LADDER` 启发式，接 `aegis_alpha.adapters.jvquant.scoring.candidate_grade()` 真重算 9 字段评级。`hypothesis_json` 现在能覆盖任何 `candidate_grade` kwarg（例如 `{"action": "avoid"}` 立即看到对应的 REJECT 假设结论）。
- mock `get_active_seats_today` 扩到 3 个游资条目（章盟主 + 孙哥 + 欢乐海岸），其中欢乐海岸覆盖 3 只票，让 SKILL 「板块共振」工作流有真实演示信号。
```

- [ ] **Step 2: SKILL.md item 21 加备注**

打开 `.hermes/skills/second-board-radar/SKILL.md`，找到 workflow item 21。在末尾加 1 行：

```text
    - 板块事件 `THEME_LEADER_BREAK_BOARD` / `SECTOR_ROTATION` / `MARKET_BOTTOM_REVERSAL` 现在会触发 runner macOS 告警（P8 修复）；通过 `get_pending_alerts(limit)` 拉到的告警里会带这 3 类。
    - `simulate_outcome` 现在用真 `candidate_grade()` 重算（P8）：你可以传任意 `{"action": "avoid"}` / `{"orderbook_quality_score": 80.0}` 等覆盖来观察 hypothetical_grade 变化，不再受限于 P7 的 `seal_amount_cny` / `five_min_speed_pct` 两字段启发。
```

- [ ] **Step 3: 全量回归**

Run: `PYTHONPATH=src .venv/bin/pytest tests/ -q --no-header 2>&1 | tail -10`
Expected: 全部 PASS（P7 当前 319 + P8 新加约 6 个 = 325 上下）。

Run: `.venv/bin/python -m compileall src scripts tests -q`
Expected: 退出 0。

Run: `PYTHONPATH=src .venv/bin/python scripts/smoke_check.py`
Expected: 退出 0。

- [ ] **Step 4: 提交**

```bash
git add README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "Document P8 runner alerts and hypothesis real re-grade"
```

---

## Self-Review Checklist

| 项 | 状态 |
|----|------|
| runner critical_types 加 3 个 P6/P7 事件类型 | ✅ Task 1 |
| `_collect_sector_events` try/except 拆 3 段 | ✅ Task 2 |
| runner adapter 缓存 1 次 | ✅ Task 3 |
| `simulate_outcome` 接 `candidate_grade()` 真重算 | ✅ Task 4 |
| P6 hypothesis 测试加 `hypothetical_grade` 断言 | ✅ Task 5 |
| mock `get_active_seats_today` 多游资 | ✅ Task 6 |
| docs sync + 全量回归 | ✅ Task 7 |
| 不引入新依赖 / 不重构 / 不改 starter 阈值 | ✅ 全期 |
| 不改 LLM 模型名 | ✅ 全期 |
| 不接 jvQuant placeholder | ✅ 由 future-roadmap 单独管 |
| Worktree base = main HEAD | ✅（沿用） |

## 已知留底（不在 P8 scope）

- **starter 阈值校准**：P6 14 个 `# CALIBRATE` 标记的常量值不变，等以后有 ≥200 条 review_outcomes 样本再说。
- **jvQuant 真实接入**：6 个 placeholder 仍在 placeholder 状态，由 `2026-06-01-future-jvquant-real-integration-roadmap.md` 单独管理。
- **`_collect_sector_events` 调用频率**：本期改成每 tick 仍调一次（缓存 adapter，但仍调 `get_theme_leaders`）。如果 leaders 数据 1 分钟内不变，未来可加 30-60s TTL cache，但现在不做。

完成 P8 后，runner 的 alert pipeline 不再漏报，假设分析能给出真评级，仓库保持 0 已知 bug。

---

## Execution notes

- Tasks 1-3 都是 `runner.py` + `tests/test_runner.py`，紧耦合，**不要**并行 sub-agent dispatch。按 1 → 2 → 3 顺序串行。
- Task 4 是本期最大单点改动，预计 30 分钟（含 P7 测试断言迁移评估）。建议给 sonnet 模型而非 haiku。
- Tasks 5、6 互不相关，可以放心串行（不要并行避免 git 冲突）。
- Task 7 最后跑 + 提交。
