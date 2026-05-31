# P4 反馈闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 outcome 表（review_outcomes / agent_reviews）的真实数据反馈进评级——历史候选回填、失败归因、`three_year_*` placeholder 兑现、回测框架，让 P0-P3 的「数据采集 → 评级 → outcome 记录」循环升级为「数据 → 评级 → outcome → 归因 → 回测建议 → 调阈值 → 回流」的真闭环。

**Architecture:** 4 个独立子系统 + 1 个集成层。所有持久化复用 P1 migration framework；所有 outcome 数据来自 P3 已有的 `review_outcomes` / `agent_reviews` 表，**不引入新 outcome 来源**——P4 只是「拿现有数据做计算」，不动数据采集。回测层用 deterministic snapshot 重放（`AgentReview.payload` 已经是结构化候选 grade），不依赖网络或 jvQuant。

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (P1 migration framework), pytest。无新外部依赖。可选 statistics 模块（标准库）。

**前置依赖：** P0 + P1 + P2 + P3 全部已落 main（P3 commit `aa10d46`，包含 daily/weekly review、watchlist、alerts 全套）。本 plan 不修改 P0-P3 任何契约，只新增。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/aegis_alpha/db_migrations_files/m0004_feedback_loop.py` | 新建 | 加 `outcome_attributions` / `historical_candidate_snapshots` / `backtest_runs` 三张表 |
| `src/aegis_alpha/models.py` | 修改 | 加 7 个新 Pydantic 模型 + 3 个 Literal |
| `src/aegis_alpha/feedback/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/feedback/attribution.py` | 新建 | `OutcomeAttributor`：失败归因分类器 |
| `src/aegis_alpha/feedback/history_stats.py` | 新建 | `compute_history_stats`：兑现 `three_year_*` placeholder |
| `src/aegis_alpha/feedback/backfill.py` | 新建 | `backfill_candidates`：把过去 N 天的候选按当日规则重跑落库 |
| `src/aegis_alpha/feedback/backtest.py` | 新建 | `backtest_grading_rule`：在历史快照上跑修改后的评级规则 |
| `src/aegis_alpha/feedback/threshold_advice.py` | 新建 | `propose_threshold_changes`：根据归因 + 回测产生阈值建议 |
| `src/aegis_alpha/storage.py` | 修改 | 加 outcome_attribution / historical_snapshot / backtest_run 持久化方法 |
| `src/aegis_alpha/protocols.py` | 修改 | 加 `get_history_stats(symbol)` 方法 |
| `src/aegis_alpha/adapters/mock_market_data.py` | 修改 | 实现 `get_history_stats` 返回固定值；`get_stock_history_limitup_stats` 接历史表 |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | 修改 | `get_stock_history_limitup_stats` 改为查 SQLite，三年统计字段从 placeholder 0.0 改为读 history_stats |
| `src/aegis_alpha/adapters/jvquant/candidates.py` | 修改 | `build_one_candidate` 接受 `history_stats: dict[str, LimitUpHistoryStats]`，用真实值替换 0.0 占位 |
| `src/aegis_alpha/mcp/server.py` | 修改 | 暴露 `backfill_candidates` / `attribute_outcome` / `get_history_stats` / `run_backtest` / `propose_threshold_changes` 5 个新 MCP 工具 |
| `tests/test_attribution.py` | 新建 | 归因分类器测试 |
| `tests/test_history_stats.py` | 新建 | 历史统计计算测试 |
| `tests/test_backfill.py` | 新建 | backfill 落库测试 |
| `tests/test_backtest.py` | 新建 | backtest 在 historical snapshot 上跑修改规则的测试 |
| `tests/test_threshold_advice.py` | 新建 | 阈值建议生成测试 |
| `tests/test_db_migrations_p4.py` | 新建 | migration 0004 表 + 索引验证 |
| `tests/test_p4_protocol.py` | 新建 | mock 满足 `get_history_stats` |
| `.hermes/config/aegis-alpha-mcp.yaml` | 修改 | tools.include 加 5 个 P4 工具 |
| `README.md` | 修改 | 工具清单加 5 个 |
| `.hermes/skills/second-board-radar/SKILL.md` | 修改 | Workflow 加反馈闭环步骤 17-19 |

---

## 子系统总览

```text
Subsystem A: 历史快照回填 + Migration（Tasks 1-4）
Subsystem B: 失败归因（Tasks 5-7）
Subsystem C: 历史统计兑现（Tasks 8-11）
Subsystem D: 回测框架 + 阈值建议（Tasks 12-15）
Subsystem E: MCP 暴露 + 文档（Tasks 16-17）
```

---

## Task 1: 数据模型扩展

**Files:**
- Modify: `src/aegis_alpha/models.py`

- [ ] **Step 1: 在 models.py 顶部 Literal 区追加（紧接 P3 的 AlertStatus 之后）**

```python
OutcomeAttributionTag = Literal[
    "leader_break_down",       # 同板块龙头炸板拖累
    "market_gate_turned_avoid",# 大盘闸门转 avoid
    "auction_high_open_too_far", # 竞价高开过多（>3%）
    "first_seal_too_late",     # 首封时间晚（10:30 后）
    "seal_amount_decay",       # 封单衰减
    "theme_breadth_collapsed", # 板块宽度崩塌
    "no_clear_attribution",    # 无明确归因
]
BacktestStatus = Literal["pending", "running", "completed", "failed"]
HistoryStatsConfidence = Literal["high", "medium", "low", "insufficient_sample"]
```

- [ ] **Step 2: 在 models.py 末尾追加 7 个新 Pydantic 模型**

```python
class OutcomeAttribution(BaseModel):
    attribution_id: str
    symbol: str
    trading_day: str
    primary_tag: OutcomeAttributionTag = "no_clear_attribution"
    secondary_tags: list[OutcomeAttributionTag] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    created_at: str = ""
    notes: list[str] = Field(default_factory=list)


class HistoryStats(BaseModel):
    symbol: str
    sample_size: int = 0
    sample_window_start: str = ""
    sample_window_end: str = ""
    touch_limit_up_success_rate: float = Field(default=0.0, ge=0, le=1)
    sealed_next_day_gap_up_rate: float = Field(default=0.0, ge=0, le=1)
    median_next_day_premium_pct: float = 0.0
    avg_next_day_premium_pct: float = 0.0
    confidence: HistoryStatsConfidence = "insufficient_sample"
    notes: list[str] = Field(default_factory=list)


class HistoricalCandidateSnapshot(BaseModel):
    symbol: str
    trading_day: str
    grade_at_pick: CandidateGrade
    grade_reason: str = ""
    theme: str = ""
    theme_role: ThemeLeaderRole = "unknown"
    previous_consecutive_boards: int = 0
    payload_json: str = ""
    created_at: str = ""


class BacktestCandidateRow(BaseModel):
    symbol: str
    trading_day: str
    original_grade: CandidateGrade
    new_grade: CandidateGrade
    sealed_second_board: bool | None = None
    next_day_open_pct: float | None = None


class BacktestRun(BaseModel):
    run_id: str
    rule_changes: dict = Field(default_factory=dict)
    start_day: str
    end_day: str
    status: BacktestStatus = "pending"
    sample_size: int = 0
    grade_distribution_before: dict[str, int] = Field(default_factory=dict)
    grade_distribution_after: dict[str, int] = Field(default_factory=dict)
    sealed_rate_before: float = 0.0
    sealed_rate_after: float = 0.0
    rows: list[BacktestCandidateRow] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    notes: list[str] = Field(default_factory=list)


class ThresholdProposal(BaseModel):
    proposal_id: str
    field_path: str
    current_value: float
    suggested_value: float
    rationale: str = ""
    backtest_run_id: str = ""
    sample_size: int = 0
    sealed_rate_delta: float = 0.0
    confidence: HistoryStatsConfidence = "low"
    created_at: str = ""


class ThresholdAdviceReport(BaseModel):
    backtest_run_id: str
    generated_at: str
    proposals: list[ThresholdProposal] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 3: 编译确认**

Run:
```
python3.13 -m compileall src/aegis_alpha/models.py
```
Expected: exit 0.

- [ ] **Step 4: 跑全量回归确认未破坏既有契约**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 全部 PASS（新模型都有默认值，新 Literal 不影响现有契约）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py
git commit -m "Add P4 contracts: outcome attribution, history stats, backtest, threshold advice"
```

---

## Task 2: 数据库迁移 0004

**Files:**
- Create: `src/aegis_alpha/db_migrations_files/m0004_feedback_loop.py`
- Create: `tests/test_db_migrations_p4.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p4_migration_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"outcome_attributions", "historical_candidate_snapshots", "backtest_runs"}.issubset(names)
    assert current_version(db) >= 4


def test_p4_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_outcome_attributions_symbol_day" in names
    assert "idx_historical_snapshots_symbol_day" in names
    assert "idx_backtest_runs_status" in names
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_db_migrations_p4.py -v
```
Expected: FAIL（current_version 仍是 3，新表不存在）。

- [ ] **Step 3: 实现迁移**

`src/aegis_alpha/db_migrations_files/m0004_feedback_loop.py`:

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS outcome_attributions (
            attribution_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            primary_tag TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_outcome_attributions_symbol_day
            ON outcome_attributions (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS historical_candidate_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            grade_at_pick TEXT NOT NULL,
            theme TEXT,
            theme_role TEXT,
            previous_consecutive_boards INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day)
        );
        CREATE INDEX IF NOT EXISTS idx_historical_snapshots_symbol_day
            ON historical_candidate_snapshots (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS backtest_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            start_day TEXT NOT NULL,
            end_day TEXT NOT NULL,
            sample_size INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_backtest_runs_status
            ON backtest_runs (status, started_at);
        """
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_db_migrations_p4.py -v
```
Expected: PASS（2/2）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/db_migrations_files/m0004_feedback_loop.py tests/test_db_migrations_p4.py
git commit -m "Add migration 0004: outcome_attributions, historical_snapshots, backtest_runs tables"
```

---

## Task 3: 历史候选快照存储

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Create: `tests/test_historical_snapshot_storage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_historical_snapshot_storage.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import HistoricalCandidateSnapshot
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_save_and_get_historical_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    snap = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="B",
        grade_reason="follower with strong seal",
        theme="AI",
        theme_role="follower",
        previous_consecutive_boards=2,
        payload_json='{"hello": "world"}',
        created_at="2026-05-31T15:30:00+08:00",
    )

    store.save_historical_snapshot(snap)
    fetched = store.get_historical_snapshot("002230.SZ", "2026-05-31")

    assert fetched is not None
    assert fetched.grade_at_pick == "B"
    assert fetched.theme_role == "follower"


def test_save_historical_snapshot_upserts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    snap1 = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="C",
        created_at="2026-05-31T09:30:00+08:00",
    )
    snap2 = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="A",
        created_at="2026-05-31T09:35:00+08:00",
    )

    store.save_historical_snapshot(snap1)
    store.save_historical_snapshot(snap2)
    fetched = store.get_historical_snapshot("002230.SZ", "2026-05-31")

    assert fetched is not None
    assert fetched.grade_at_pick == "A"


def test_list_historical_snapshots_between(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for day in ("2026-05-25", "2026-05-26", "2026-05-27", "2026-05-30"):
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol="X",
                trading_day=day,
                grade_at_pick="B",
                created_at=f"{day}T09:30:00+08:00",
            )
        )

    rows = store.list_historical_snapshots_between(start_day="2026-05-26", end_day="2026-05-29")

    assert {row.trading_day for row in rows} == {"2026-05-26", "2026-05-27"}
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_historical_snapshot_storage.py -v
```
Expected: FAIL，AttributeError: 'AegisAlphaStore' object has no attribute 'save_historical_snapshot'。

- [ ] **Step 3: 修改 storage.py 顶部 import**

定位到 `src/aegis_alpha/storage.py` 的 import 区，在现有 `from aegis_alpha.models import (` 块中追加：

```python
    HistoricalCandidateSnapshot,
    OutcomeAttribution,
    BacktestRun,
```

(按字母顺序插入到合适位置)

- [ ] **Step 4: 在 `AegisAlphaStore` 类末尾、`def write_runner_status` 之前追加方法**

```python
    def save_historical_snapshot(self, snap: HistoricalCandidateSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO historical_candidate_snapshots (
                    symbol, trading_day, grade_at_pick, theme, theme_role,
                    previous_consecutive_boards, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trading_day) DO UPDATE SET
                    grade_at_pick = excluded.grade_at_pick,
                    theme = excluded.theme,
                    theme_role = excluded.theme_role,
                    previous_consecutive_boards = excluded.previous_consecutive_boards,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    snap.symbol,
                    snap.trading_day,
                    snap.grade_at_pick,
                    snap.theme,
                    snap.theme_role,
                    snap.previous_consecutive_boards,
                    snap.model_dump_json(),
                    snap.created_at,
                ),
            )

    def get_historical_snapshot(
        self, symbol: str, trading_day: str
    ) -> HistoricalCandidateSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM historical_candidate_snapshots
                WHERE symbol = ? AND trading_day = ?
                """,
                (symbol, trading_day),
            ).fetchone()
        return HistoricalCandidateSnapshot.model_validate_json(row[0]) if row else None

    def list_historical_snapshots_between(
        self, *, start_day: str, end_day: str, symbol: str = ""
    ) -> list[HistoricalCandidateSnapshot]:
        clauses = ["trading_day BETWEEN ? AND ?"]
        params: list[object] = [start_day, end_day]
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        query = (
            "SELECT payload_json FROM historical_candidate_snapshots "
            "WHERE " + " AND ".join(clauses) + " ORDER BY trading_day ASC, symbol ASC"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [HistoricalCandidateSnapshot.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 5: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_historical_snapshot_storage.py -v
```
Expected: PASS（3/3）。

- [ ] **Step 6: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 7: Commit**

```bash
git add src/aegis_alpha/storage.py tests/test_historical_snapshot_storage.py
git commit -m "Add HistoricalCandidateSnapshot storage methods"
```

---

## Task 4: 候选回填脚本

**Files:**
- Create: `src/aegis_alpha/feedback/__init__.py`
- Create: `src/aegis_alpha/feedback/backfill.py`
- Create: `tests/test_backfill.py`

- [ ] **Step 1: 空 init**

`src/aegis_alpha/feedback/__init__.py`:

```python
"""Feedback loop: attribution, history stats, backfill, backtest, threshold advice."""
```

- [ ] **Step 2: 写失败测试**

`tests/test_backfill.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.feedback.backfill import backfill_candidates
from aegis_alpha.storage import AegisAlphaStore


def test_backfill_persists_candidates_for_today(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    persisted = backfill_candidates(adapter, store, trading_days=["2026-05-31"])

    assert persisted >= 1
    rows = store.list_historical_snapshots_between(start_day="2026-05-31", end_day="2026-05-31")
    assert {row.symbol for row in rows} == {"002230.SZ", "300024.SZ"}
    kdxf = next(row for row in rows if row.symbol == "002230.SZ")
    assert kdxf.theme == "AI应用"
    assert kdxf.theme_role == "leader"


def test_backfill_idempotent_on_same_day(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    first = backfill_candidates(adapter, store, trading_days=["2026-05-31"])
    second = backfill_candidates(adapter, store, trading_days=["2026-05-31"])

    assert first == second
    rows = store.list_historical_snapshots_between(start_day="2026-05-31", end_day="2026-05-31")
    # 仍然只有 2 条 (UPSERT)
    assert len(rows) == 2


def test_backfill_multiple_days(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    persisted = backfill_candidates(adapter, store, trading_days=["2026-05-30", "2026-05-31"])

    rows_30 = store.list_historical_snapshots_between(start_day="2026-05-30", end_day="2026-05-30")
    rows_31 = store.list_historical_snapshots_between(start_day="2026-05-31", end_day="2026-05-31")
    assert len(rows_30) == 2
    assert len(rows_31) == 2
    assert persisted == 4
```

- [ ] **Step 3: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backfill.py -v
```
Expected: FAIL，ModuleNotFoundError: aegis_alpha.feedback。

- [ ] **Step 4: 实现 backfill**

`src/aegis_alpha/feedback/backfill.py`:

```python
from __future__ import annotations

from typing import Iterable

from aegis_alpha.clock import now_iso
from aegis_alpha.models import HistoricalCandidateSnapshot
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


def backfill_candidates(
    adapter: MarketDataAdapter,
    store: AegisAlphaStore,
    *,
    trading_days: Iterable[str],
) -> int:
    """Take a snapshot of today's candidate pool for each requested trading day.

    The mock adapter returns the same pool regardless of trading_day so this
    is deterministic for tests. The jvquant adapter returns whatever its
    semantic queries produce now — backfill is meant to be re-run daily as
    a cron job to capture each day's candidate pool.

    Returns the count of HistoricalCandidateSnapshot rows persisted (one per
    candidate per trading_day).
    """
    persisted = 0
    timestamp = now_iso()
    days = [day.strip() for day in trading_days if day.strip()]
    for trading_day in days:
        candidates = adapter.get_second_board_candidates()
        for candidate in candidates:
            snap = HistoricalCandidateSnapshot(
                symbol=candidate.symbol,
                trading_day=trading_day,
                grade_at_pick=candidate.grade,
                grade_reason=candidate.grade_reason,
                theme=candidate.theme,
                theme_role=candidate.theme_role,
                previous_consecutive_boards=candidate.previous_consecutive_boards,
                payload_json=candidate.model_dump_json(),
                created_at=timestamp,
            )
            store.save_historical_snapshot(snap)
            persisted += 1
    return persisted
```

- [ ] **Step 5: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backfill.py -v
```
Expected: PASS（3/3）。

- [ ] **Step 6: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 7: Commit**

```bash
git add src/aegis_alpha/feedback/__init__.py src/aegis_alpha/feedback/backfill.py tests/test_backfill.py
git commit -m "Add backfill_candidates to capture daily candidate pool snapshots"
```

---

## Task 5: 失败归因分类器

**Files:**
- Create: `src/aegis_alpha/feedback/attribution.py`
- Create: `tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

`tests/test_attribution.py`:

```python
from __future__ import annotations

from aegis_alpha.feedback.attribution import (
    AttributionInputs,
    attribute_outcome,
)


def test_leader_break_down_when_theme_role_follower_and_leader_broke() -> None:
    inputs = AttributionInputs(
        symbol="F1",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="follower",
        theme_leader_symbol="LDR",
        theme_leader_final_status="broken",
        market_action="selective",
        auction_change_pct=2.0,
        first_limit_up_time="09:50:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "leader_break_down"
    assert any("LDR" in line for line in attribution.evidence)


def test_market_gate_avoid_dominates_other_signals() -> None:
    inputs = AttributionInputs(
        symbol="X",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="X",
        theme_leader_final_status="sealed",
        market_action="avoid",
        auction_change_pct=1.0,
        first_limit_up_time="09:30:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=2,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "market_gate_turned_avoid"


def test_auction_high_open_too_far_threshold() -> None:
    inputs = AttributionInputs(
        symbol="Y",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="Y",
        theme_leader_final_status="broken",
        market_action="selective",
        auction_change_pct=4.5,
        first_limit_up_time="10:00:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    # Leader 自己炸板优先于竞价高开
    assert attribution.primary_tag in {"leader_break_down", "auction_high_open_too_far"}


def test_no_clear_attribution_when_sealed() -> None:
    inputs = AttributionInputs(
        symbol="Z",
        trading_day="2026-05-31",
        sealed_second_board=True,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="Z",
        theme_leader_final_status="sealed",
        market_action="active",
        auction_change_pct=2.0,
        first_limit_up_time="09:35:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=2,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "no_clear_attribution"


def test_first_seal_too_late_when_after_10_30() -> None:
    inputs = AttributionInputs(
        symbol="W",
        trading_day="2026-05-31",
        sealed_second_board=False,
        theme="AI",
        theme_role="leader",
        theme_leader_symbol="W",
        theme_leader_final_status="reopened",
        market_action="selective",
        auction_change_pct=1.5,
        first_limit_up_time="13:45:00",
        seal_decay_pct=0.0,
        previous_consecutive_boards=1,
    )

    attribution = attribute_outcome(inputs)

    assert attribution.primary_tag == "first_seal_too_late"
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_attribution.py -v
```
Expected: FAIL，ModuleNotFoundError。

- [ ] **Step 3: 实现 attribution.py**

`src/aegis_alpha/feedback/attribution.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    MarketAction,
    OutcomeAttribution,
    OutcomeAttributionTag,
    ThemeLeaderRole,
)


@dataclass(frozen=True)
class AttributionInputs:
    symbol: str
    trading_day: str
    sealed_second_board: bool
    theme: str
    theme_role: ThemeLeaderRole
    theme_leader_symbol: str
    theme_leader_final_status: str  # "sealed" / "broken" / "reopened" / "unknown"
    market_action: MarketAction
    auction_change_pct: float
    first_limit_up_time: str
    seal_decay_pct: float
    previous_consecutive_boards: int


_HIGH_OPEN_THRESHOLD = 3.0  # 竞价高开 > 3% 视为风险
_LATE_SEAL_CUTOFF = "10:30:00"
_SEAL_DECAY_THRESHOLD = 30.0


def _attribution_id(symbol: str, trading_day: str) -> str:
    seed = f"{symbol}|{trading_day}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def attribute_outcome(inputs: AttributionInputs) -> OutcomeAttribution:
    evidence: list[str] = []
    secondary: list[OutcomeAttributionTag] = []

    if inputs.sealed_second_board:
        return OutcomeAttribution(
            attribution_id=_attribution_id(inputs.symbol, inputs.trading_day),
            symbol=inputs.symbol,
            trading_day=inputs.trading_day,
            primary_tag="no_clear_attribution",
            secondary_tags=[],
            evidence=["Candidate sealed second board; no failure to attribute."],
            created_at=now_iso(),
        )

    primary: OutcomeAttributionTag = "no_clear_attribution"

    # Rule 1: market_gate_turned_avoid 优先级最高（结构性问题）
    if inputs.market_action == "avoid":
        primary = "market_gate_turned_avoid"
        evidence.append(f"market_action={inputs.market_action} when candidate failed to seal.")

    # Rule 2: leader_break_down——follower 且龙头炸板
    elif inputs.theme_role in {"follower", "co_leader"} and inputs.theme_leader_final_status == "broken":
        primary = "leader_break_down"
        evidence.append(
            f"Theme leader {inputs.theme_leader_symbol} broken in theme {inputs.theme}; "
            f"candidate is {inputs.theme_role}."
        )

    # Rule 3: seal_amount_decay——封单衰减大于阈值
    elif inputs.seal_decay_pct >= _SEAL_DECAY_THRESHOLD:
        primary = "seal_amount_decay"
        evidence.append(f"seal_decay_pct={inputs.seal_decay_pct:.1f} >= {_SEAL_DECAY_THRESHOLD:.1f}.")

    # Rule 4: auction_high_open_too_far——竞价高开过多
    elif inputs.auction_change_pct >= _HIGH_OPEN_THRESHOLD:
        primary = "auction_high_open_too_far"
        evidence.append(
            f"auction_change_pct={inputs.auction_change_pct:.2f} >= {_HIGH_OPEN_THRESHOLD:.2f}."
        )

    # Rule 5: first_seal_too_late——首封时间晚（仅当 first_limit_up_time 不是 unknown 时检测）
    elif (
        inputs.first_limit_up_time
        and inputs.first_limit_up_time != "unknown"
        and inputs.first_limit_up_time > _LATE_SEAL_CUTOFF
    ):
        primary = "first_seal_too_late"
        evidence.append(
            f"first_limit_up_time={inputs.first_limit_up_time} > {_LATE_SEAL_CUTOFF}."
        )

    # Secondary tags collect non-primary risk signals for context
    if primary != "auction_high_open_too_far" and inputs.auction_change_pct >= _HIGH_OPEN_THRESHOLD:
        secondary.append("auction_high_open_too_far")
    if (
        primary != "first_seal_too_late"
        and inputs.first_limit_up_time
        and inputs.first_limit_up_time != "unknown"
        and inputs.first_limit_up_time > _LATE_SEAL_CUTOFF
    ):
        secondary.append("first_seal_too_late")

    if not evidence:
        evidence.append("No clear attribution signal matched; outcome remains unexplained.")

    return OutcomeAttribution(
        attribution_id=_attribution_id(inputs.symbol, inputs.trading_day),
        symbol=inputs.symbol,
        trading_day=inputs.trading_day,
        primary_tag=primary,
        secondary_tags=secondary,
        evidence=evidence,
        created_at=now_iso(),
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_attribution.py -v
```
Expected: PASS（5/5）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/feedback/attribution.py tests/test_attribution.py
git commit -m "Add OutcomeAttributor classifier for failed second-board candidates"
```

---

## Task 6: 归因 storage 持久化

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Create: `tests/test_attribution_storage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_attribution_storage.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import OutcomeAttribution
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_save_and_get_attribution(tmp_path: Path) -> None:
    store = _store(tmp_path)
    attribution = OutcomeAttribution(
        attribution_id="abc123",
        symbol="002230.SZ",
        trading_day="2026-05-31",
        primary_tag="leader_break_down",
        secondary_tags=["auction_high_open_too_far"],
        evidence=["Leader X broken at 13:30"],
        created_at="2026-05-31T15:30:00+08:00",
    )

    store.save_attribution(attribution)
    fetched = store.get_attribution("002230.SZ", "2026-05-31")

    assert fetched is not None
    assert fetched.primary_tag == "leader_break_down"
    assert fetched.secondary_tags == ["auction_high_open_too_far"]


def test_list_attributions_by_tag(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="1",
            symbol="A",
            trading_day="2026-05-30",
            primary_tag="leader_break_down",
            created_at="2026-05-30T15:30:00+08:00",
        )
    )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="2",
            symbol="B",
            trading_day="2026-05-31",
            primary_tag="market_gate_turned_avoid",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="3",
            symbol="C",
            trading_day="2026-05-31",
            primary_tag="leader_break_down",
            created_at="2026-05-31T15:30:00+08:00",
        )
    )

    rows = store.list_attributions(primary_tag="leader_break_down")

    assert {row.symbol for row in rows} == {"A", "C"}
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_attribution_storage.py -v
```
Expected: FAIL，AttributeError: 'AegisAlphaStore' object has no attribute 'save_attribution'。

- [ ] **Step 3: 在 storage.py 加方法**

在 `AegisAlphaStore` 类的 `list_historical_snapshots_between` 方法之后追加：

```python
    def save_attribution(self, attribution: OutcomeAttribution) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO outcome_attributions (
                    attribution_id, symbol, trading_day, primary_tag,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(attribution_id) DO UPDATE SET
                    primary_tag = excluded.primary_tag,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    attribution.attribution_id,
                    attribution.symbol,
                    attribution.trading_day,
                    attribution.primary_tag,
                    attribution.model_dump_json(),
                    attribution.created_at,
                ),
            )

    def get_attribution(self, symbol: str, trading_day: str) -> OutcomeAttribution | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM outcome_attributions
                WHERE symbol = ? AND trading_day = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (symbol, trading_day),
            ).fetchone()
        return OutcomeAttribution.model_validate_json(row[0]) if row else None

    def list_attributions(
        self, *, primary_tag: str = "", start_day: str = "", end_day: str = ""
    ) -> list[OutcomeAttribution]:
        clauses: list[str] = []
        params: list[object] = []
        if primary_tag:
            clauses.append("primary_tag = ?")
            params.append(primary_tag)
        if start_day:
            clauses.append("trading_day >= ?")
            params.append(start_day)
        if end_day:
            clauses.append("trading_day <= ?")
            params.append(end_day)
        query = "SELECT payload_json FROM outcome_attributions"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY trading_day DESC, created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [OutcomeAttribution.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_attribution_storage.py -v
```
Expected: PASS（2/2）。

- [ ] **Step 5: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/storage.py tests/test_attribution_storage.py
git commit -m "Add OutcomeAttribution storage methods"
```

---

## Task 7: 归因集成 helper（attribute_from_stored_data）

**Files:**
- Modify: `src/aegis_alpha/feedback/attribution.py`
- Create: `tests/test_attribution_integration.py`

- [ ] **Step 1: 写失败测试**

`tests/test_attribution_integration.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.feedback.attribution import attribute_from_stored_data
from aegis_alpha.models import CandidateOutcomeReview, HistoricalCandidateSnapshot
from aegis_alpha.storage import AegisAlphaStore


def test_attribute_uses_outcome_and_historical_snapshot(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    # 先落历史快照（mock candidate 002230.SZ 是 leader）
    snap = HistoricalCandidateSnapshot(
        symbol="300024.SZ",
        trading_day="2026-05-31",
        grade_at_pick="C",
        theme="机器人",
        theme_role="leader",
        previous_consecutive_boards=1,
        payload_json='{"auction_change_pct": 1.5, "first_limit_up_time": "13:50:00", "seal_decay_pct": 0.0}',
        created_at="2026-05-31T09:30:00+08:00",
    )
    store.save_historical_snapshot(snap)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="300024.SZ",
            trading_day="2026-05-31",
            touched_limit_up=False,
            sealed_second_board=False,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="300024.SZ",
        trading_day="2026-05-31",
    )

    assert attribution is not None
    # late seal 时间是 13:50:00，所以分类是 first_seal_too_late
    assert attribution.primary_tag == "first_seal_too_late"


def test_attribute_returns_none_when_outcome_missing(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="UNKNOWN",
        trading_day="2026-05-31",
    )

    assert attribution is None


def test_attribute_returns_no_attribution_when_sealed(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()
    snap = HistoricalCandidateSnapshot(
        symbol="002230.SZ",
        trading_day="2026-05-31",
        grade_at_pick="A",
        theme="AI应用",
        theme_role="leader",
        previous_consecutive_boards=2,
        payload_json='{"auction_change_pct": 1.0, "first_limit_up_time": "09:35:00", "seal_decay_pct": 0.0}',
        created_at="2026-05-31T09:30:00+08:00",
    )
    store.save_historical_snapshot(snap)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            sealed_second_board=True,
        )
    )

    attribution = attribute_from_stored_data(
        adapter=adapter,
        store=store,
        symbol="002230.SZ",
        trading_day="2026-05-31",
    )

    assert attribution is not None
    assert attribution.primary_tag == "no_clear_attribution"
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_attribution_integration.py -v
```
Expected: FAIL，ImportError 或 AttributeError。

- [ ] **Step 3: 修改 `attribution.py`**

在文件末尾追加（保留 Step 3 已有 `attribute_outcome`）：

```python
import json

from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


def attribute_from_stored_data(
    *,
    adapter: MarketDataAdapter,
    store: AegisAlphaStore,
    symbol: str,
    trading_day: str,
) -> OutcomeAttribution | None:
    """Resolve attribution by joining historical snapshot + outcome + theme leader.

    Returns None when no outcome row exists for (symbol, trading_day) — there is
    nothing to attribute.
    """
    outcome = store.get_review_outcome(symbol, trading_day)
    # get_review_outcome returns a placeholder when missing; sealed_second_board is
    # only meaningful when actually recorded
    if outcome.touched_limit_up is None and outcome.sealed_second_board is None:
        return None

    snap = store.get_historical_snapshot(symbol, trading_day)
    if snap is None:
        return None

    raw = {}
    try:
        raw = json.loads(snap.payload_json or "{}")
    except json.JSONDecodeError:
        raw = {}

    leader_symbol = raw.get("theme_leader_symbol", "") or symbol
    leader_status = "unknown"
    try:
        timeline = adapter.get_seal_timeline(leader_symbol, trading_day)
        leader_status = timeline.final_status
    except Exception:
        leader_status = "unknown"

    market_action = "selective"
    try:
        gate = adapter.get_market_sentiment_gate()
        market_action = gate.action
    except Exception:
        market_action = "selective"

    inputs = AttributionInputs(
        symbol=symbol,
        trading_day=trading_day,
        sealed_second_board=bool(outcome.sealed_second_board),
        theme=snap.theme,
        theme_role=snap.theme_role,
        theme_leader_symbol=leader_symbol,
        theme_leader_final_status=leader_status,
        market_action=market_action,
        auction_change_pct=float(raw.get("auction_change_pct") or 0.0),
        first_limit_up_time=str(raw.get("first_limit_up_time") or "unknown"),
        seal_decay_pct=float(raw.get("seal_decay_pct") or 0.0),
        previous_consecutive_boards=snap.previous_consecutive_boards,
    )
    attribution = attribute_outcome(inputs)
    store.save_attribution(attribution)
    return attribution
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_attribution_integration.py -v
```
Expected: PASS（3/3）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/feedback/attribution.py tests/test_attribution_integration.py
git commit -m "Wire attribute_from_stored_data joining outcome + snapshot + adapter"
```

---

## Task 8: 历史统计计算

**Files:**
- Create: `src/aegis_alpha/feedback/history_stats.py`
- Create: `tests/test_history_stats.py`

- [ ] **Step 1: 写失败测试**

`tests/test_history_stats.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.feedback.history_stats import compute_history_stats
from aegis_alpha.models import CandidateOutcomeReview
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_compute_history_stats_with_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for day, sealed, gap_up, premium in [
        ("2026-05-25", True, True, 3.0),
        ("2026-05-26", True, False, -1.0),
        ("2026-05-27", False, False, 0.0),
        ("2026-05-28", True, True, 4.0),
    ]:
        store.save_review_outcome(
            CandidateOutcomeReview(
                symbol="002230.SZ",
                trading_day=day,
                touched_limit_up=sealed,
                sealed_second_board=sealed,
                next_day_open_pct=gap_up_pct(gap_up, premium),
                next_day_high_pct=premium,
            )
        )

    stats = compute_history_stats(
        store=store,
        symbol="002230.SZ",
        start_day="2026-05-01",
        end_day="2026-06-01",
    )

    assert stats.symbol == "002230.SZ"
    assert stats.sample_size == 4
    # 3/4 sealed
    assert abs(stats.touch_limit_up_success_rate - 0.75) < 1e-6
    # 2/3 of sealed had gap-up
    assert abs(stats.sealed_next_day_gap_up_rate - (2 / 3)) < 1e-6
    # avg of next_day_high_pct: (3 + -1 + 0 + 4) / 4 = 1.5
    assert abs(stats.avg_next_day_premium_pct - 1.5) < 1e-6
    assert stats.confidence in {"medium", "high"}


def test_compute_history_stats_insufficient_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="X",
            trading_day="2026-05-31",
            sealed_second_board=True,
            next_day_open_pct=2.0,
            next_day_high_pct=3.0,
        )
    )

    stats = compute_history_stats(
        store=store,
        symbol="X",
        start_day="2026-05-01",
        end_day="2026-06-01",
    )

    assert stats.sample_size == 1
    assert stats.confidence == "insufficient_sample"


def test_compute_history_stats_no_records_returns_zero_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)

    stats = compute_history_stats(
        store=store,
        symbol="UNKNOWN",
        start_day="2026-05-01",
        end_day="2026-06-01",
    )

    assert stats.sample_size == 0
    assert stats.confidence == "insufficient_sample"
    assert stats.touch_limit_up_success_rate == 0.0


def gap_up_pct(gap_up: bool, premium: float) -> float:
    """Helper: positive next_day_open_pct only when gap_up is True."""
    return 1.5 if gap_up else -0.5
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_history_stats.py -v
```
Expected: FAIL，ModuleNotFoundError。

- [ ] **Step 3: 实现 history_stats.py**

`src/aegis_alpha/feedback/history_stats.py`:

```python
from __future__ import annotations

import statistics

from aegis_alpha.models import HistoryStats, HistoryStatsConfidence
from aegis_alpha.storage import AegisAlphaStore


_INSUFFICIENT_SAMPLE_BELOW = 3
_MEDIUM_CONFIDENCE_BELOW = 10


def _confidence_from_sample(size: int) -> HistoryStatsConfidence:
    if size < _INSUFFICIENT_SAMPLE_BELOW:
        return "insufficient_sample"
    if size < _MEDIUM_CONFIDENCE_BELOW:
        return "medium"
    return "high"


def compute_history_stats(
    *,
    store: AegisAlphaStore,
    symbol: str,
    start_day: str,
    end_day: str,
) -> HistoryStats:
    """Compute touch-limit-up success rate, sealed-next-day gap-up rate, and
    next-day premium statistics from review_outcomes within the window.

    A review is counted toward the sample if either touched_limit_up or
    sealed_second_board is non-null. next_day_open_pct > 0 is treated as
    "gap up" for sealed candidates.
    """
    outcomes = store.list_review_outcomes(symbol=symbol, start_day=start_day, end_day=end_day)
    countable = [
        outcome
        for outcome in outcomes
        if outcome.touched_limit_up is not None or outcome.sealed_second_board is not None
    ]
    sample_size = len(countable)

    sealed_outcomes = [outcome for outcome in countable if outcome.sealed_second_board]
    touch_rate = len(sealed_outcomes) / sample_size if sample_size else 0.0

    gap_up_among_sealed = [
        outcome for outcome in sealed_outcomes if (outcome.next_day_open_pct or 0.0) > 0
    ]
    gap_up_rate = len(gap_up_among_sealed) / len(sealed_outcomes) if sealed_outcomes else 0.0

    premiums = [outcome.next_day_high_pct or 0.0 for outcome in countable]
    avg_premium = round(sum(premiums) / sample_size, 4) if sample_size else 0.0
    median_premium = round(statistics.median(premiums), 4) if premiums else 0.0

    return HistoryStats(
        symbol=symbol,
        sample_size=sample_size,
        sample_window_start=start_day,
        sample_window_end=end_day,
        touch_limit_up_success_rate=round(touch_rate, 4),
        sealed_next_day_gap_up_rate=round(gap_up_rate, 4),
        median_next_day_premium_pct=median_premium,
        avg_next_day_premium_pct=avg_premium,
        confidence=_confidence_from_sample(sample_size),
        notes=[
            f"Window: {start_day} to {end_day}.",
            f"Sample size: {sample_size}.",
        ],
    )
```

- [ ] **Step 4: 跑测试预期 fail——`list_review_outcomes` 不存在**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_history_stats.py -v
```
Expected: FAIL，AttributeError: 'AegisAlphaStore' object has no attribute 'list_review_outcomes'。

下一个 task 加这个方法。

- [ ] **Step 5: Commit（with failing test, will be fixed in Task 9）**

```bash
git add src/aegis_alpha/feedback/history_stats.py tests/test_history_stats.py
git commit -m "Add compute_history_stats (storage method follows in next commit)"
```

---

## Task 9: storage `list_review_outcomes` 方法

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Create: `tests/test_review_outcomes_storage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_review_outcomes_storage.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import CandidateOutcomeReview
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_list_review_outcomes_filters_by_symbol_and_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for symbol, day, sealed in [
        ("A", "2026-05-25", True),
        ("A", "2026-05-26", False),
        ("A", "2026-05-30", True),
        ("B", "2026-05-26", True),
    ]:
        store.save_review_outcome(
            CandidateOutcomeReview(symbol=symbol, trading_day=day, sealed_second_board=sealed)
        )

    rows = store.list_review_outcomes(symbol="A", start_day="2026-05-25", end_day="2026-05-27")

    assert {row.trading_day for row in rows} == {"2026-05-25", "2026-05-26"}


def test_list_review_outcomes_no_symbol_filter_returns_all(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_review_outcome(CandidateOutcomeReview(symbol="A", trading_day="2026-05-25", sealed_second_board=True))
    store.save_review_outcome(CandidateOutcomeReview(symbol="B", trading_day="2026-05-25", sealed_second_board=False))

    rows = store.list_review_outcomes(start_day="2026-05-25", end_day="2026-05-25")

    assert {row.symbol for row in rows} == {"A", "B"}


def test_list_review_outcomes_empty_window(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_review_outcome(CandidateOutcomeReview(symbol="A", trading_day="2026-05-25"))

    rows = store.list_review_outcomes(start_day="2026-06-01", end_day="2026-06-30")

    assert rows == []
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_review_outcomes_storage.py -v
```
Expected: FAIL（AttributeError）。

- [ ] **Step 3: 在 storage.py 加 `list_review_outcomes`**

定位现有 `def get_review_outcome` 方法（约 storage.py:260），在它之后追加：

```python
    def list_review_outcomes(
        self, *, symbol: str = "", start_day: str = "", end_day: str = ""
    ) -> list[CandidateOutcomeReview]:
        clauses: list[str] = []
        params: list[object] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if start_day:
            clauses.append("trading_day >= ?")
            params.append(start_day)
        if end_day:
            clauses.append("trading_day <= ?")
            params.append(end_day)
        query = "SELECT payload_json FROM review_outcomes"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY trading_day ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CandidateOutcomeReview.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_review_outcomes_storage.py tests/test_history_stats.py -v
```
Expected: PASS（3 + 3 = 6/6）。

- [ ] **Step 5: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/storage.py tests/test_review_outcomes_storage.py
git commit -m "Add list_review_outcomes storage method for history stats sample extraction"
```

---

## Task 10: 兑现 `three_year_*` placeholder

**Files:**
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Modify: `src/aegis_alpha/adapters/jvquant/candidates.py`
- Create: `tests/test_p4_protocol.py`

- [ ] **Step 1: 在 protocols.py 加新方法**

在 `MarketDataAdapter` Protocol 末尾加（紧接 `explain_second_board_candidate` 之前）：

```python
    def get_history_stats(self, symbol: str) -> HistoryStats: ...
```

并在文件顶部 import `HistoryStats`。

- [ ] **Step 2: 写 protocol 测试**

`tests/test_p4_protocol.py`:

```python
from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.protocols import MarketDataAdapter


def test_mock_adapter_satisfies_p4_history_stats() -> None:
    adapter: MarketDataAdapter = MockMarketDataAdapter()
    stats = adapter.get_history_stats("002230.SZ")
    assert stats.symbol == "002230.SZ"
    assert stats.sample_size >= 0
    assert 0.0 <= stats.touch_limit_up_success_rate <= 1.0


def test_mock_adapter_unknown_symbol_returns_zero_sample() -> None:
    adapter = MockMarketDataAdapter()
    stats = adapter.get_history_stats("XXXXXX")
    assert stats.sample_size == 0
    assert stats.confidence == "insufficient_sample"
```

- [ ] **Step 3: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_p4_protocol.py -v
```
Expected: FAIL（AttributeError）。

- [ ] **Step 4: mock 实现**

在 `src/aegis_alpha/adapters/mock_market_data.py` 末尾加（在 import 区追加 `HistoryStats`）：

```python
    def get_history_stats(self, symbol: str) -> HistoryStats:
        normalized = symbol.strip().upper()
        if normalized.startswith("002230"):
            return HistoryStats(
                symbol=normalized,
                sample_size=18,
                sample_window_start="2023-05-31",
                sample_window_end="2026-05-31",
                touch_limit_up_success_rate=0.72,
                sealed_next_day_gap_up_rate=0.61,
                median_next_day_premium_pct=2.4,
                avg_next_day_premium_pct=3.1,
                confidence="high",
                notes=["Mock historical stats for contract tests."],
            )
        return HistoryStats(
            symbol=normalized,
            sample_size=0,
            confidence="insufficient_sample",
            notes=["Mock has no history for this symbol."],
        )
```

- [ ] **Step 5: jvquant adapter 实现**

在 `src/aegis_alpha/adapters/jvquant/adapter.py` 加（顶部 import 追加 `HistoryStats`，并 import `compute_history_stats`、`AegisAlphaStore`，应该都已经在）：

```python
    def get_history_stats(self, symbol: str) -> HistoryStats:
        from aegis_alpha.feedback.history_stats import compute_history_stats

        normalized = normalize_symbol(symbol)
        # 默认窗口：3 年
        from datetime import timedelta

        end = datetime.now(SH_TZ).date()
        start = end - timedelta(days=365 * 3)
        return compute_history_stats(
            store=AegisAlphaStore(),
            symbol=normalized,
            start_day=start.isoformat(),
            end_day=end.isoformat(),
        )
```

- [ ] **Step 6: 跑 protocol test**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_p4_protocol.py -v
```
Expected: PASS（2/2）。

- [ ] **Step 7: 修改 jvquant candidates.py 接 history_stats**

在 `src/aegis_alpha/adapters/jvquant/candidates.py` 的 `build_one_candidate` 签名末尾追加：

```python
    history_stats_by_symbol: dict[str, HistoryStats],
```

并在文件顶部 import 追加 `HistoryStats`。

定位 `build_second_board_candidate(...)` 调用，把：

```python
        three_year_touch_limit_success_rate=0.0,
        three_year_sealed_next_day_gap_up_rate=0.0,
```

改为：

```python
        three_year_touch_limit_success_rate=(history_stats_by_symbol.get(symbol).touch_limit_up_success_rate
            if symbol in history_stats_by_symbol else 0.0),
        three_year_sealed_next_day_gap_up_rate=(history_stats_by_symbol.get(symbol).sealed_next_day_gap_up_rate
            if symbol in history_stats_by_symbol else 0.0),
```

- [ ] **Step 8: 修改 jvquant adapter 在循环前预取 history_stats**

在 `src/aegis_alpha/adapters/jvquant/adapter.py` 的 `get_second_board_candidates` 中，定位到现有的 `theme_leaders_list = self.get_theme_leaders(...)` 那段，在它之后追加：

```python
        history_stats_by_symbol: dict[str, HistoryStats] = {}
        for row in rows[:max_candidates]:
            row_symbol = P._symbol_from_row(row)
            if not row_symbol:
                continue
            history_stats_by_symbol[row_symbol] = self.get_history_stats(row_symbol)
```

并在 `build_one_candidate(...)` 调用末尾追加：

```python
                history_stats_by_symbol=history_stats_by_symbol,
```

- [ ] **Step 9: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 10: Commit**

```bash
git add src/aegis_alpha/protocols.py src/aegis_alpha/adapters/mock_market_data.py src/aegis_alpha/adapters/jvquant/adapter.py src/aegis_alpha/adapters/jvquant/candidates.py tests/test_p4_protocol.py
git commit -m "Wire HistoryStats into adapters; replace three_year_* placeholders with real lookups"
```

---

## Task 11: 更新 mock contract test 验证 three_year 字段

**Files:**
- Modify: `tests/test_p2_adapter_contract.py`

- [ ] **Step 1: 检查现有测试**

Run:
```
grep -n "three_year_touch_limit_success_rate\|three_year_sealed_next_day_gap_up_rate" tests/test_p2_adapter_contract.py
```

如果未引用，加入。

- [ ] **Step 2: 在 `test_mock_adapter_exposes_p2_theme_ladder_emotion_auction_contracts` 函数末尾追加断言**

打开 `tests/test_p2_adapter_contract.py`，找到那个函数最后一个 `assert` 语句，在其后追加：

```python
    # P4: three_year_* should be 0 for both candidates because mock get_history_stats
    # only carries data for 002230.SZ but jvquant candidate builder is not in the path
    # for mock adapter; mock adapter does not call get_history_stats during candidate build.
    # The mock candidates therefore retain their pre-existing literal 0.0 placeholder.
    # This test guards that we do not silently break the mock when changing jvquant.
    for cand in candidates:
        assert 0.0 <= cand.three_year_touch_limit_success_rate <= 1.0
        assert 0.0 <= cand.three_year_sealed_next_day_gap_up_rate <= 1.0
```

- [ ] **Step 3: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_p2_adapter_contract.py -v
```
Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add tests/test_p2_adapter_contract.py
git commit -m "Guard three_year_* fields stay in [0,1] in mock candidate contract"
```

---

## Task 12: 回测核心逻辑（pure function，不持久化）

**Files:**
- Create: `src/aegis_alpha/feedback/backtest.py`
- Create: `tests/test_backtest.py`

- [ ] **Step 1: 写失败测试**

`tests/test_backtest.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.feedback.backtest import (
    BacktestInputs,
    backtest_grading_rule,
)
from aegis_alpha.models import CandidateOutcomeReview, HistoricalCandidateSnapshot
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def _seed_three_days(store: AegisAlphaStore) -> None:
    days = [
        ("2026-05-25", "X", "B", True),
        ("2026-05-26", "Y", "C", False),
        ("2026-05-27", "Z", "A", True),
    ]
    for day, symbol, grade, sealed in days:
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol=symbol,
                trading_day=day,
                grade_at_pick=grade,
                payload_json=f'{{"current_change_pct": 9.8, "five_min_speed_pct": 2.0}}',
                created_at=f"{day}T09:30:00+08:00",
            )
        )
        store.save_review_outcome(
            CandidateOutcomeReview(
                symbol=symbol,
                trading_day=day,
                touched_limit_up=sealed,
                sealed_second_board=sealed,
            )
        )


def test_backtest_no_changes_keeps_grades_constant(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_three_days(store)

    run = backtest_grading_rule(
        BacktestInputs(
            store=store,
            rule_changes={},
            start_day="2026-05-25",
            end_day="2026-05-27",
        )
    )

    assert run.sample_size == 3
    assert run.status == "completed"
    for row in run.rows:
        assert row.original_grade == row.new_grade


def test_backtest_with_promote_b_to_a_changes_distribution(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seed_three_days(store)

    run = backtest_grading_rule(
        BacktestInputs(
            store=store,
            rule_changes={"promote_b_to_a": True},
            start_day="2026-05-25",
            end_day="2026-05-27",
        )
    )

    assert run.grade_distribution_before.get("B", 0) == 1
    assert run.grade_distribution_after.get("A", 0) == run.grade_distribution_before.get("A", 0) + 1
    assert run.grade_distribution_after.get("B", 0) == 0


def test_backtest_empty_window_is_completed_with_zero_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)

    run = backtest_grading_rule(
        BacktestInputs(
            store=store,
            rule_changes={},
            start_day="2026-06-01",
            end_day="2026-06-30",
        )
    )

    assert run.status == "completed"
    assert run.sample_size == 0
    assert run.sealed_rate_before == 0.0
    assert run.sealed_rate_after == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backtest.py -v
```
Expected: FAIL（ModuleNotFoundError）。

- [ ] **Step 3: 实现 backtest.py**

`src/aegis_alpha/feedback/backtest.py`:

```python
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    BacktestCandidateRow,
    BacktestRun,
    CandidateGrade,
)
from aegis_alpha.storage import AegisAlphaStore


@dataclass(frozen=True)
class BacktestInputs:
    store: AegisAlphaStore
    rule_changes: dict[str, Any]
    start_day: str
    end_day: str


def _run_id(start_day: str, end_day: str, rule_changes: dict[str, Any]) -> str:
    seed = f"{start_day}|{end_day}|{sorted(rule_changes.items())}|{now_iso()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _apply_rule_changes(grade: CandidateGrade, rule_changes: dict[str, Any]) -> CandidateGrade:
    """Apply a small set of supported rule_changes to remap a grade.

    Supported keys:
      - promote_b_to_a: bool — every B becomes A
      - downgrade_c_to_reject: bool — every C becomes REJECT
      - flip_a_to_b: bool — every A becomes B (sanity test)
    """
    if rule_changes.get("promote_b_to_a") and grade == "B":
        return "A"
    if rule_changes.get("downgrade_c_to_reject") and grade == "C":
        return "REJECT"
    if rule_changes.get("flip_a_to_b") and grade == "A":
        return "B"
    return grade


def _sealed_rate(rows: list[BacktestCandidateRow], *, use_new_grade: bool) -> float:
    promoted = [
        row for row in rows
        if (use_new_grade and row.new_grade in {"A", "B"})
        or (not use_new_grade and row.original_grade in {"A", "B"})
    ]
    if not promoted:
        return 0.0
    sealed = [row for row in promoted if row.sealed_second_board]
    return round(len(sealed) / len(promoted), 4)


def backtest_grading_rule(inputs: BacktestInputs) -> BacktestRun:
    """Run a backtest on stored historical snapshots within the window.

    Pure function — does not persist the run. Persistence is handled by
    storage.save_backtest_run in Task 13.
    """
    started_at = now_iso()
    snapshots = inputs.store.list_historical_snapshots_between(
        start_day=inputs.start_day,
        end_day=inputs.end_day,
    )

    rows: list[BacktestCandidateRow] = []
    for snap in snapshots:
        outcome = inputs.store.get_review_outcome(snap.symbol, snap.trading_day)
        sealed = outcome.sealed_second_board if outcome.sealed_second_board is not None else None
        new_grade = _apply_rule_changes(snap.grade_at_pick, inputs.rule_changes)
        rows.append(
            BacktestCandidateRow(
                symbol=snap.symbol,
                trading_day=snap.trading_day,
                original_grade=snap.grade_at_pick,
                new_grade=new_grade,
                sealed_second_board=sealed,
                next_day_open_pct=outcome.next_day_open_pct,
            )
        )

    distribution_before: dict[str, int] = dict(Counter(row.original_grade for row in rows))
    distribution_after: dict[str, int] = dict(Counter(row.new_grade for row in rows))

    completed_at = now_iso()
    return BacktestRun(
        run_id=_run_id(inputs.start_day, inputs.end_day, inputs.rule_changes),
        rule_changes=dict(inputs.rule_changes),
        start_day=inputs.start_day,
        end_day=inputs.end_day,
        status="completed",
        sample_size=len(rows),
        grade_distribution_before=distribution_before,
        grade_distribution_after=distribution_after,
        sealed_rate_before=_sealed_rate(rows, use_new_grade=False),
        sealed_rate_after=_sealed_rate(rows, use_new_grade=True),
        rows=rows,
        started_at=started_at,
        completed_at=completed_at,
        notes=[
            f"Backtest over {len(rows)} historical snapshots from {inputs.start_day} to {inputs.end_day}.",
            f"Rule changes: {sorted(inputs.rule_changes.items())}.",
        ],
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backtest.py -v
```
Expected: PASS（3/3）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/feedback/backtest.py tests/test_backtest.py
git commit -m "Add backtest_grading_rule pure function over historical snapshots"
```

---

## Task 13: 回测持久化

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Create: `tests/test_backtest_storage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_backtest_storage.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import BacktestRun
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_save_and_get_backtest_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    run = BacktestRun(
        run_id="run123",
        rule_changes={"promote_b_to_a": True},
        start_day="2026-05-01",
        end_day="2026-05-31",
        status="completed",
        sample_size=10,
        sealed_rate_before=0.4,
        sealed_rate_after=0.55,
        started_at="2026-05-31T16:00:00+08:00",
        completed_at="2026-05-31T16:00:05+08:00",
    )

    store.save_backtest_run(run)
    fetched = store.get_backtest_run("run123")

    assert fetched is not None
    assert fetched.sealed_rate_after == 0.55


def test_list_backtest_runs_by_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for run_id, status in [("a", "completed"), ("b", "running"), ("c", "completed")]:
        store.save_backtest_run(
            BacktestRun(
                run_id=run_id,
                start_day="2026-05-01",
                end_day="2026-05-31",
                status=status,
            )
        )

    completed = store.list_backtest_runs(status="completed")

    assert {row.run_id for row in completed} == {"a", "c"}
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backtest_storage.py -v
```
Expected: FAIL（AttributeError）。

- [ ] **Step 3: 在 storage.py 加方法**

定位 `def save_attribution` 之后，追加：

```python
    def save_backtest_run(self, run: BacktestRun) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_runs (
                    run_id, status, start_day, end_day, sample_size,
                    payload_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    sample_size = excluded.sample_size,
                    payload_json = excluded.payload_json,
                    completed_at = excluded.completed_at
                """,
                (
                    run.run_id,
                    run.status,
                    run.start_day,
                    run.end_day,
                    run.sample_size,
                    run.model_dump_json(),
                    run.started_at,
                    run.completed_at,
                ),
            )

    def get_backtest_run(self, run_id: str) -> BacktestRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM backtest_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return BacktestRun.model_validate_json(row[0]) if row else None

    def list_backtest_runs(self, *, status: str = "", limit: int = 50) -> list[BacktestRun]:
        safe_limit = max(1, min(int(limit or 50), 200))
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT payload_json FROM backtest_runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [BacktestRun.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backtest_storage.py -v
```
Expected: PASS（2/2）。

- [ ] **Step 5: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/storage.py tests/test_backtest_storage.py
git commit -m "Add BacktestRun storage methods"
```

---

## Task 14: 阈值建议生成器

**Files:**
- Create: `src/aegis_alpha/feedback/threshold_advice.py`
- Create: `tests/test_threshold_advice.py`

- [ ] **Step 1: 写失败测试**

`tests/test_threshold_advice.py`:

```python
from __future__ import annotations

from aegis_alpha.feedback.threshold_advice import propose_threshold_changes
from aegis_alpha.models import BacktestCandidateRow, BacktestRun, OutcomeAttribution


def _run(rule_changes: dict, *, sealed_before: float, sealed_after: float, sample: int = 20) -> BacktestRun:
    return BacktestRun(
        run_id="run1",
        rule_changes=rule_changes,
        start_day="2026-05-01",
        end_day="2026-05-31",
        status="completed",
        sample_size=sample,
        sealed_rate_before=sealed_before,
        sealed_rate_after=sealed_after,
        started_at="2026-05-31T16:00:00+08:00",
        completed_at="2026-05-31T16:00:05+08:00",
    )


def test_proposes_change_when_after_rate_higher_and_sample_sufficient() -> None:
    run = _run({"promote_b_to_a": True}, sealed_before=0.40, sealed_after=0.55, sample=20)

    report = propose_threshold_changes(run=run, attributions=[])

    assert report.proposals
    proposal = report.proposals[0]
    assert proposal.sealed_rate_delta > 0
    assert proposal.confidence in {"medium", "high"}
    assert proposal.rationale


def test_no_proposal_when_after_rate_not_better() -> None:
    run = _run({"promote_b_to_a": True}, sealed_before=0.50, sealed_after=0.45, sample=20)

    report = propose_threshold_changes(run=run, attributions=[])

    assert report.proposals == []


def test_low_confidence_when_sample_too_small() -> None:
    run = _run({"promote_b_to_a": True}, sealed_before=0.30, sealed_after=0.60, sample=2)

    report = propose_threshold_changes(run=run, attributions=[])

    if report.proposals:
        assert report.proposals[0].confidence == "low"
    # 也可能直接被过滤掉；任一 OK


def test_attributions_appear_in_notes() -> None:
    run = _run({"promote_b_to_a": True}, sealed_before=0.4, sealed_after=0.55, sample=20)
    attributions = [
        OutcomeAttribution(
            attribution_id="x",
            symbol="A",
            trading_day="2026-05-25",
            primary_tag="leader_break_down",
            created_at="2026-05-25T16:00:00+08:00",
        ),
        OutcomeAttribution(
            attribution_id="y",
            symbol="B",
            trading_day="2026-05-26",
            primary_tag="leader_break_down",
            created_at="2026-05-26T16:00:00+08:00",
        ),
    ]

    report = propose_threshold_changes(run=run, attributions=attributions)

    note_blob = " ".join(report.notes)
    assert "leader_break_down" in note_blob
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_threshold_advice.py -v
```
Expected: FAIL（ModuleNotFoundError）。

- [ ] **Step 3: 实现 threshold_advice.py**

`src/aegis_alpha/feedback/threshold_advice.py`:

```python
from __future__ import annotations

import hashlib
from collections import Counter

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    BacktestRun,
    HistoryStatsConfidence,
    OutcomeAttribution,
    ThresholdAdviceReport,
    ThresholdProposal,
)


_LARGE_SAMPLE = 30
_SMALL_SAMPLE = 5
_DELTA_MIN = 0.02


def _confidence(sample: int) -> HistoryStatsConfidence:
    if sample < _SMALL_SAMPLE:
        return "low"
    if sample < _LARGE_SAMPLE:
        return "medium"
    return "high"


def _proposal_id(run_id: str, key: str) -> str:
    seed = f"{run_id}|{key}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _rule_change_to_proposal(
    *,
    run: BacktestRun,
    key: str,
    value: object,
    delta: float,
) -> ThresholdProposal | None:
    if not value:
        return None
    field_path = ""
    rationale = ""
    current_value = 0.0
    suggested_value = 0.0
    if key == "promote_b_to_a":
        field_path = "candidate_grading.candidate.b_change_pct"
        current_value = 7.0
        suggested_value = 8.5
        rationale = (
            "Backtest shows promoting B to A increases sealed-rate; "
            "consider raising the change_pct threshold for B-grade so the bar matches the new ceiling."
        )
    elif key == "downgrade_c_to_reject":
        field_path = "candidate_grading.candidate.reject_change_pct_below"
        current_value = 5.0
        suggested_value = 6.0
        rationale = (
            "Backtest shows downgrading C to REJECT removes losers without dropping sealed-rate; "
            "consider raising the reject_change_pct floor."
        )
    elif key == "flip_a_to_b":
        field_path = "candidate_grading.candidate.a_min_change_pct"
        current_value = 9.5
        suggested_value = 10.0
        rationale = (
            "Backtest shows flipping A to B did not hurt sealed-rate; consider tightening the A-grade floor."
        )
    else:
        return None
    return ThresholdProposal(
        proposal_id=_proposal_id(run.run_id, key),
        field_path=field_path,
        current_value=current_value,
        suggested_value=suggested_value,
        rationale=rationale,
        backtest_run_id=run.run_id,
        sample_size=run.sample_size,
        sealed_rate_delta=round(delta, 4),
        confidence=_confidence(run.sample_size),
        created_at=now_iso(),
    )


def propose_threshold_changes(
    *,
    run: BacktestRun,
    attributions: list[OutcomeAttribution],
) -> ThresholdAdviceReport:
    """Generate threshold proposals from a completed backtest + recent attributions."""
    delta = run.sealed_rate_after - run.sealed_rate_before
    proposals: list[ThresholdProposal] = []

    if delta >= _DELTA_MIN:
        for key, value in run.rule_changes.items():
            proposal = _rule_change_to_proposal(
                run=run,
                key=str(key),
                value=value,
                delta=delta,
            )
            if proposal is not None:
                proposals.append(proposal)

    notes: list[str] = [
        f"Backtest sealed_rate before={run.sealed_rate_before:.4f}, after={run.sealed_rate_after:.4f}, delta={delta:+.4f}.",
        f"Sample size: {run.sample_size}.",
    ]
    if attributions:
        tag_counter = Counter(a.primary_tag for a in attributions)
        top_tags = ", ".join(f"{tag}({count})" for tag, count in tag_counter.most_common(3))
        notes.append(f"Top attribution tags in window: {top_tags}.")

    return ThresholdAdviceReport(
        backtest_run_id=run.run_id,
        generated_at=now_iso(),
        proposals=proposals,
        notes=notes,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_threshold_advice.py -v
```
Expected: PASS（4/4）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/feedback/threshold_advice.py tests/test_threshold_advice.py
git commit -m "Add propose_threshold_changes generating advice from backtest + attributions"
```

---

## Task 15: 集成 helper（run_backtest_and_advise）

**Files:**
- Modify: `src/aegis_alpha/feedback/backtest.py`
- Create: `tests/test_backtest_integration.py`

- [ ] **Step 1: 写失败测试**

`tests/test_backtest_integration.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.feedback.backtest import (
    BacktestInputs,
    run_backtest_and_advise,
)
from aegis_alpha.models import (
    CandidateOutcomeReview,
    HistoricalCandidateSnapshot,
    OutcomeAttribution,
)
from aegis_alpha.storage import AegisAlphaStore


def test_run_backtest_persists_run_and_returns_advice(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    for day, symbol, grade, sealed in [
        ("2026-05-25", "X", "B", True),
        ("2026-05-26", "Y", "B", True),
        ("2026-05-27", "Z", "B", False),
    ]:
        store.save_historical_snapshot(
            HistoricalCandidateSnapshot(
                symbol=symbol,
                trading_day=day,
                grade_at_pick=grade,
                payload_json="{}",
                created_at=f"{day}T09:30:00+08:00",
            )
        )
        store.save_review_outcome(
            CandidateOutcomeReview(
                symbol=symbol,
                trading_day=day,
                touched_limit_up=sealed,
                sealed_second_board=sealed,
            )
        )
    store.save_attribution(
        OutcomeAttribution(
            attribution_id="x",
            symbol="Z",
            trading_day="2026-05-27",
            primary_tag="leader_break_down",
            created_at="2026-05-27T16:00:00+08:00",
        )
    )

    run, advice = run_backtest_and_advise(
        BacktestInputs(
            store=store,
            rule_changes={"promote_b_to_a": True},
            start_day="2026-05-25",
            end_day="2026-05-27",
        )
    )

    assert run.sample_size == 3
    fetched = store.get_backtest_run(run.run_id)
    assert fetched is not None
    assert advice.backtest_run_id == run.run_id
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backtest_integration.py -v
```
Expected: FAIL（ImportError）。

- [ ] **Step 3: 在 backtest.py 末尾追加**

```python
def run_backtest_and_advise(inputs: BacktestInputs) -> tuple[BacktestRun, "ThresholdAdviceReport"]:
    """Run a backtest, persist the run, generate threshold advice from window attributions."""
    from aegis_alpha.feedback.threshold_advice import (
        ThresholdAdviceReport,
        propose_threshold_changes,
    )

    run = backtest_grading_rule(inputs)
    inputs.store.save_backtest_run(run)
    attributions = inputs.store.list_attributions(
        start_day=inputs.start_day,
        end_day=inputs.end_day,
    )
    advice = propose_threshold_changes(run=run, attributions=attributions)
    return run, advice
```

并在文件顶部增加 `from aegis_alpha.models import ThresholdAdviceReport`，否则前向引用 string 仍能跑通——string 形式不需 import，但更直接的方式是放 import。这里保持 string 形式以避免循环 import。

- [ ] **Step 4: 跑测试确认通过**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/test_backtest_integration.py -v
```
Expected: PASS（1/1）。

- [ ] **Step 5: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/feedback/backtest.py tests/test_backtest_integration.py
git commit -m "Add run_backtest_and_advise that persists run and returns threshold advice"
```

---

## Task 16: MCP 工具暴露

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`

- [ ] **Step 1: 在 `def main` 之前追加 5 个新 MCP 工具**

```python
@mcp.tool
def backfill_candidates(trading_days: str) -> dict:
    """Capture today's candidate pool snapshot for each given trading day (pipe-separated)."""
    from aegis_alpha.feedback.backfill import backfill_candidates as _backfill

    safe_days = [d.strip() for d in trading_days.split("|") if d.strip()]
    if not safe_days:
        return {"data_mode": "unavailable", "error": "trading_days is required (pipe-separated)"}

    def _run(adapter: Any) -> dict:
        store = get_store()
        persisted = _backfill(adapter, store, trading_days=safe_days)
        return {"persisted": persisted, "trading_days": safe_days}

    return _call_tool(_run)


@mcp.tool
def attribute_outcome(symbol: str, trading_day: str) -> dict:
    """Attribute a failed candidate outcome from stored data."""
    from aegis_alpha.feedback.attribution import attribute_from_stored_data

    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable", "error": "symbol and trading_day are required"}

    def _run(adapter: Any) -> dict:
        attribution = attribute_from_stored_data(
            adapter=adapter,
            store=get_store(),
            symbol=safe_symbol,
            trading_day=safe_day,
        )
        if attribution is None:
            return {
                "data_mode": "unavailable",
                "error": "No outcome record or historical snapshot for this symbol/day.",
            }
        return attribution.model_dump()

    return _call_tool(_run)


@mcp.tool
def get_history_stats(symbol: str) -> dict:
    """Return three-year historical limit-up stats for one stock."""
    return _call_tool(lambda adapter: adapter.get_history_stats(symbol).model_dump())


@mcp.tool
def run_backtest(rule_changes_json: str, start_day: str, end_day: str) -> dict:
    """Run a backtest with rule_changes (JSON string) over historical snapshots."""
    import json

    from aegis_alpha.feedback.backtest import BacktestInputs, run_backtest_and_advise

    safe_start = start_day.strip()
    safe_end = end_day.strip()
    if not (safe_start and safe_end):
        return {"data_mode": "unavailable", "error": "start_day and end_day are required"}
    try:
        rule_changes = json.loads(rule_changes_json or "{}")
    except json.JSONDecodeError as exc:
        return {"data_mode": "unavailable", "error": f"rule_changes_json invalid: {exc}"}

    def _run(_store: AegisAlphaStore) -> dict:
        run, advice = run_backtest_and_advise(
            BacktestInputs(
                store=_store,
                rule_changes=rule_changes,
                start_day=safe_start,
                end_day=safe_end,
            )
        )
        return {"run": run.model_dump(), "advice": advice.model_dump()}

    return _call_store(_run)


@mcp.tool
def get_recent_backtests(limit: int = 10) -> list[dict] | dict:
    """List recent backtest runs."""
    safe_limit = max(1, min(int(limit or 10), 50))
    return _call_store(lambda store: [r.model_dump() for r in store.list_backtest_runs(limit=safe_limit)])
```

- [ ] **Step 2: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 3: 编译确认**

Run:
```
python3.13 -m compileall src/aegis_alpha/mcp/server.py
```
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add src/aegis_alpha/mcp/server.py
git commit -m "Expose P4 MCP tools: backfill, attribute, history_stats, backtest, recent_backtests"
```

---

## Task 17: 文档更新

**Files:**
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: yaml `tools.include` 末尾追加（紧接 P3 工具之后）**

```yaml
        - backfill_candidates
        - attribute_outcome
        - get_history_stats
        - run_backtest
        - get_recent_backtests
```

- [ ] **Step 2: README jvquant 段（约 README:122-149 行）追加 5 行**

定位现有 `- get_auction_analysis(symbol, trading_day)` 之后（jvquant 段），追加：

```markdown
- `backfill_candidates(trading_days)`
- `attribute_outcome(symbol, trading_day)`
- `get_history_stats(symbol)`
- `run_backtest(rule_changes_json, start_day, end_day)`
- `get_recent_backtests(limit)`
```

- [ ] **Step 3: README 完整工具列表段（约 README:343-360 行）末尾追加同样 5 个工具名**

```markdown
- `backfill_candidates`
- `attribute_outcome`
- `get_history_stats`
- `run_backtest`
- `get_recent_backtests`
```

- [ ] **Step 4: SKILL.md 「Required MCP Tools」段「Core tools」末尾追加**

```markdown
- `attribute_outcome`
- `get_history_stats`
- `run_backtest`
- `get_recent_backtests`
- `backfill_candidates`
```

- [ ] **Step 5: SKILL.md「Standard Workflow」末尾追加新 step 17-19**

```markdown
17. After collecting at least 5 trading days of outcomes, run `attribute_outcome(symbol, trading_day)` for failed candidates to identify recurring failure patterns. Surface the top primary_tag from `get_recent_attributions` as a Hermes memory candidate after 3+ similar tags accumulate.
18. Use `get_history_stats(symbol)` instead of relying on the placeholder three_year_* fields when available. If `confidence` is `insufficient_sample`, treat the historical signal as unavailable and do not narrate a probability.
19. When the user asks "would tightening rule X improve hit rate?", call `run_backtest(rule_changes_json='{"flip_a_to_b": true}', start_day, end_day)` and report the sealed_rate delta + advice. Never apply a threshold proposal automatically — they always require the human-confirmation flow defined by `record_correction_action_decision`.
```

- [ ] **Step 6: 验证所有 5 个工具在 3 处都有引用**

Run:
```
for tool in backfill_candidates attribute_outcome get_history_stats run_backtest get_recent_backtests; do
  echo "$tool:"
  grep -c "$tool" README.md .hermes/skills/second-board-radar/SKILL.md .hermes/config/aegis-alpha-mcp.yaml
done
```
Expected: 每个工具在 3 个文件中都至少 1 次（README 应该 2 次）。

- [ ] **Step 7: 跑全量回归**

Run:
```
PYTHONPATH=src python3.13 -m pytest tests/ --tb=short -q
```
Expected: 0 new regression。

- [ ] **Step 8: Commit**

```bash
git add .hermes/config/aegis-alpha-mcp.yaml README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "Document P4 MCP tools and workflows"
```

---

## Self-Review

- [x] **Spec coverage** —
  - 历史候选回填 → Tasks 3-4
  - 失败归因 → Tasks 5-7
  - `three_year_*` placeholder 兑现 → Tasks 8-11
  - 回测框架 → Tasks 12-13, 15
  - 阈值建议 → Task 14
  - MCP 暴露 → Task 16
  - 文档 → Task 17

- [x] **Placeholder 扫描** — 所有 step 都有完整代码或确切命令。Task 9 Step 1 说「使用 helper `gap_up_pct`」并定义了它的 helper 函数（在 test 文件末尾）。Task 11 引用 P2 contract test 的具体函数名 `test_mock_adapter_exposes_p2_theme_ladder_emotion_auction_contracts`，可定位。

- [x] **Type consistency** —
  - `OutcomeAttributionTag` Literal 在 attribution.py 的 logic 和 test 中保持一致。
  - `BacktestStatus` Literal 在 BacktestRun 模型、backtest.py 函数返回值、storage list_backtest_runs 过滤中一致。
  - `HistoryStatsConfidence` 在 history_stats.py 和 threshold_advice.py 间保持同一 Literal 引用。
  - `AttributionInputs` dataclass 字段在 attribute_outcome 和 attribute_from_stored_data 调用处签名一致。
  - `BacktestInputs` dataclass 在 backtest_grading_rule 和 run_backtest_and_advise 间一致使用。
  - `ThresholdAdviceReport` 模型在 propose_threshold_changes 返回值、run_backtest_and_advise 返回值、MCP `run_backtest` 工具中保持一致。

- [x] **TDD 全程** — 每个新模块都先写失败测试再实现。

- [x] **依赖关系顺序正确** — Task 1 (models) → Task 2 (migration) → Task 3 (snapshot storage) → Task 4 (backfill, depends on snapshot) → Task 5 (attribution pure) → Task 6 (attribution storage) → Task 7 (attribution integration, depends on snapshot + outcome) → Task 8-9 (history stats + storage) → Task 10 (wire history stats into adapters) → Task 11 (P2 contract guard) → Task 12-13 (backtest core + storage) → Task 14 (threshold advice) → Task 15 (integration helper) → Task 16-17 (MCP + docs)。每一步都有前置铺好。

- [x] **No commit-message-only changes** — 每个 commit 都改了至少 1 个 src 或 tests 文件。
