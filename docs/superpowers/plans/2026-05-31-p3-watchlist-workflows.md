# P3 持续工作流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Aegis Alpha MCP 工具集从「单次查询」升级为「跨时点连续工作流」——盯盘列表、分歧→一致追踪、复盘报告、告警、板块强度排行。让 Hermes 可以管理一个跨小时持续演变的候选池，而不是每次查询都从零开始。

**Architecture:** 5 个独立子系统，每个新增一张 SQLite 表 + 一个或多个领域模块 + 1-3 个 MCP 工具。所有持久化走 P1 建立的 migration framework；所有信号走 P2 建立的 ladder/leader/emotion 上下文。每个子系统**对外契约稳定**：盯盘列表用户名当作 owner，分歧→一致追踪以 candidate symbol 为索引，复盘按 trading_day 聚合，告警按 event_id 去重，板块排行复用 ThemeLeader。

**Tech Stack:** Python 3.11+, Pydantic v2, FastMCP, SQLite (P1 migration framework), pytest。无新外部依赖。macOS notification 是可选项，用 `subprocess.run(["osascript", ...])` 调原生 API。

**前置依赖：** P0 + P1 + P2 全部完成（已合到 main，commit 87683d6 及之前）。本 plan 不需要再改 P0/P1/P2 的核心模块。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/aegis_alpha/db_migrations_files/m0003_watchlist_workflows.py` | 新建 | 加 5 张表 |
| `src/aegis_alpha/models.py` | 修改 | 加 8 个新 Pydantic 模型 + 4 个 Literal |
| `src/aegis_alpha/watchlists/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/watchlists/manager.py` | 新建 | `WatchlistManager`：CRUD + diff |
| `src/aegis_alpha/seal_timeline/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/seal_timeline/tracker.py` | 新建 | `SealTimelineTracker`：intraday seal/break events |
| `src/aegis_alpha/seal_timeline/divergence.py` | 新建 | THEME_DIVERGENCE 事件检测器 |
| `src/aegis_alpha/reviews/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/reviews/daily.py` | 新建 | `generate_daily_review` |
| `src/aegis_alpha/reviews/weekly.py` | 新建 | `generate_weekly_pattern_report` |
| `src/aegis_alpha/alerts/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/alerts/store.py` | 新建 | alert 持久化与去重 |
| `src/aegis_alpha/alerts/notifier.py` | 新建 | macOS notification hook |
| `src/aegis_alpha/themes/ranking.py` | 新建 | top themes / theme rotation |
| `src/aegis_alpha/storage.py` | 修改 | 加 watchlist / seal_timeline / alerts 持久化方法 |
| `src/aegis_alpha/protocols.py` | 修改 | 加 7 个新方法（保持 mock + jvquant 同步）|
| `src/aegis_alpha/adapters/mock_market_data.py` | 修改 | 实现新 protocol 方法 |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | 修改 | 实现新 protocol 方法（用 store 中转）|
| `src/aegis_alpha/runner.py` | 修改 | 检测到关键 event 时写 alert |
| `src/aegis_alpha/mcp/server.py` | 修改 | 暴露新工具 |
| `src/aegis_alpha/mcp/dependencies.py` | 修改 | 增加 `get_watchlist_manager` / `get_seal_tracker` 等单例 |
| `tests/test_watchlists.py` | 新建 | watchlist CRUD + diff 测试 |
| `tests/test_seal_timeline.py` | 新建 | timeline 持久化与事件生成 |
| `tests/test_divergence.py` | 新建 | THEME_DIVERGENCE 触发测试 |
| `tests/test_reviews_daily.py` | 新建 | daily review 聚合测试 |
| `tests/test_reviews_weekly.py` | 新建 | weekly pattern 聚合测试 |
| `tests/test_alerts.py` | 新建 | 告警去重 + ack 测试 |
| `tests/test_theme_ranking.py` | 新建 | top themes / rotation 测试 |
| `tests/test_p3_protocol.py` | 新建 | mock 满足 P3 protocol 扩展 |

---

## 子系统总览

每个子系统是 plan 内一个 task 群。task 编号连续。

```text
Subsystem A: Watchlist 持久化（Tasks 1-4）
Subsystem B: Seal Timeline + Divergence 事件（Tasks 5-8）
Subsystem C: Review 报告（Tasks 9-11）
Subsystem D: Alerts（Tasks 12-14）
Subsystem E: Theme Ranking（Tasks 15-16）
Subsystem F: 收尾（Task 17）
```

---

## Task 1: 数据模型扩展

**Files:**
- Modify: `src/aegis_alpha/models.py`

- [ ] **Step 1: 在 models.py 顶部 Literal 区追加**

定位文件中所有 Literal 定义之后（约第 36 行 `MarketEventType` 末尾）追加：

```python
WatchlistStatus = Literal["active", "closed", "expired"]
WatchlistEntryAction = Literal["added", "promoted", "downgraded", "dropped", "noted"]
SealTimelineKind = Literal["first_seal", "break", "reseal", "final_break"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["pending", "acknowledged", "expired"]
```

并在 `MarketEventType` Literal 中追加 `"THEME_DIVERGENCE"` 一项：

```python
MarketEventType = Literal[
    "THEME_CLUSTER_RISING",
    "APPROACHING_LIMIT_UP",
    "SEAL_ORDER_DECAY",
    "BIG_ORDER_INFLOW_SPIKE",
    "SECOND_BOARD_CANDIDATE_REPRICE",
    "THEME_DIVERGENCE",
]
```

- [ ] **Step 2: 在 models.py 末尾追加 8 个新 Pydantic 模型**

```python
class WatchlistEntry(BaseModel):
    symbol: str
    added_at: str
    initial_grade: CandidateGrade = "C"
    last_grade: CandidateGrade = "C"
    last_action: WatchlistEntryAction = "added"
    last_action_at: str = ""
    notes: list[str] = Field(default_factory=list)


class Watchlist(BaseModel):
    watchlist_id: str
    owner: str
    label: str
    status: WatchlistStatus = "active"
    created_at: str
    expires_at: str = ""
    closed_at: str = ""
    entries: list[WatchlistEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WatchlistDiff(BaseModel):
    watchlist_id: str
    from_timestamp: str
    to_timestamp: str
    added_symbols: list[str] = Field(default_factory=list)
    dropped_symbols: list[str] = Field(default_factory=list)
    grade_changes: dict[str, dict[str, str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class SealTimelineEvent(BaseModel):
    symbol: str
    trading_day: str
    kind: SealTimelineKind
    occurred_at: str
    seal_amount_cny: float = 0.0
    notes: list[str] = Field(default_factory=list)


class SealTimeline(BaseModel):
    symbol: str
    trading_day: str
    events: list[SealTimelineEvent] = Field(default_factory=list)
    final_status: Literal["sealed", "broken", "reopened", "unknown"] = "unknown"
    break_count: int = 0
    reseal_count: int = 0


class DailyReviewItem(BaseModel):
    symbol: str
    grade_at_pick: CandidateGrade
    theme: str = ""
    theme_role: ThemeLeaderRole = "unknown"
    previous_consecutive_boards: int = 0
    touched_limit_up: bool | None = None
    sealed_second_board: bool | None = None
    next_day_open_pct: float | None = None
    notes: list[str] = Field(default_factory=list)


class DailyReview(BaseModel):
    trading_day: str
    generated_at: str
    candidate_count: int = 0
    grade_distribution: dict[str, int] = Field(default_factory=dict)
    sealed_count: int = 0
    items: list[DailyReviewItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WeeklyPatternReport(BaseModel):
    start_day: str
    end_day: str
    generated_at: str
    grade_outcome_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_themes: list[str] = Field(default_factory=list)
    sample_size: int = 0
    notes: list[str] = Field(default_factory=list)


class AgentAlert(BaseModel):
    alert_id: str
    event_id: str = ""
    symbol: str = ""
    theme: str = ""
    severity: AlertSeverity = "info"
    status: AlertStatus = "pending"
    title: str
    body: str = ""
    created_at: str
    acknowledged_at: str = ""
    notes: list[str] = Field(default_factory=list)


class ThemeRanking(BaseModel):
    theme: str
    trading_day: str
    rank: int
    member_count: int
    leader_symbol: str = ""
    leader_consecutive_boards: int = 0
    score: float = Field(ge=0, le=100)
    notes: list[str] = Field(default_factory=list)


class ThemeRotationEntry(BaseModel):
    trading_day: str
    top_themes: list[str] = Field(default_factory=list)
    new_themes: list[str] = Field(default_factory=list)
    fading_themes: list[str] = Field(default_factory=list)
```

- [ ] **Step 3: 编译确认**

```bash
python3 -m compileall src/aegis_alpha/models.py
```

Expected: exit 0.

- [ ] **Step 4: 跑既有测试确认不破坏**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
```

Expected: 所有原 test 仍 PASS（新模型都有默认值，`MarketEventType` 加成员是兼容扩展）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/models.py
git commit -m "Add P3 contracts: watchlist, seal timeline, review, alert, theme ranking"
```

---

## Task 2: 数据库迁移 0003

**Files:**
- Create: `src/aegis_alpha/db_migrations_files/m0003_watchlist_workflows.py`
- Create: `tests/test_db_migrations_p3.py`

- [ ] **Step 1: 写迁移 syntax 测试**

新文件 `tests/test_db_migrations_p3.py`：

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p3_migration_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"watchlists", "watchlist_entries", "seal_timeline_events", "agent_alerts", "theme_rankings"}.issubset(names)
    assert current_version(db) >= 3


def test_p3_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_watchlist_entries_watchlist" in names
    assert "idx_seal_timeline_symbol_day" in names
    assert "idx_alerts_status_created" in names
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_db_migrations_p3.py -v
```

Expected: FAIL（current_version 仍是 2）。

- [ ] **Step 3: 实现迁移**

`src/aegis_alpha/db_migrations_files/m0003_watchlist_workflows.py`:

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            closed_at TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_watchlists_owner_status
            ON watchlists (owner, status);

        CREATE TABLE IF NOT EXISTS watchlist_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watchlist_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            added_at TEXT NOT NULL,
            last_action TEXT NOT NULL,
            last_action_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(watchlist_id, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_watchlist_entries_watchlist
            ON watchlist_entries (watchlist_id);

        CREATE TABLE IF NOT EXISTS seal_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_seal_timeline_symbol_day
            ON seal_timeline_events (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS agent_alerts (
            alert_id TEXT PRIMARY KEY,
            event_id TEXT,
            symbol TEXT,
            theme TEXT,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_status_created
            ON agent_alerts (status, created_at);

        CREATE TABLE IF NOT EXISTS theme_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day TEXT NOT NULL,
            theme TEXT NOT NULL,
            rank INTEGER NOT NULL,
            score REAL NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(trading_day, theme)
        );
        CREATE INDEX IF NOT EXISTS idx_theme_rankings_day_rank
            ON theme_rankings (trading_day, rank);
        """
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_db_migrations_p3.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/db_migrations_files/m0003_watchlist_workflows.py tests/test_db_migrations_p3.py
git commit -m "Add migration 0003: watchlist, seal timeline, alerts, theme rankings tables"
```

---

## Task 3: WatchlistManager 实现

**Files:**
- Create: `src/aegis_alpha/watchlists/__init__.py`
- Create: `src/aegis_alpha/watchlists/manager.py`
- Create: `tests/test_watchlists.py`

- [ ] **Step 1: 空 init**

`src/aegis_alpha/watchlists/__init__.py`:

```python
"""Watchlist persistence layer."""
```

- [ ] **Step 2: 写失败测试**

`tests/test_watchlists.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from aegis_alpha.storage import AegisAlphaStore
from aegis_alpha.watchlists.manager import WatchlistManager


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_create_watchlist_assigns_id_and_persists(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))

    wl = manager.create(owner="user", label="2026-05-31 morning radar", symbols=["002230.SZ", "300024.SZ"])

    assert wl.watchlist_id
    assert wl.owner == "user"
    assert wl.status == "active"
    assert {entry.symbol for entry in wl.entries} == {"002230.SZ", "300024.SZ"}

    fetched = manager.get(wl.watchlist_id)
    assert fetched is not None
    assert {entry.symbol for entry in fetched.entries} == {"002230.SZ", "300024.SZ"}


def test_update_state_records_grade_change(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl = manager.create(owner="user", label="x", symbols=["002230.SZ"])

    manager.update_state(wl.watchlist_id, "002230.SZ", new_grade="A", action="promoted", note="seal stable")

    fetched = manager.get(wl.watchlist_id)
    assert fetched is not None
    entry = next(e for e in fetched.entries if e.symbol == "002230.SZ")
    assert entry.last_grade == "A"
    assert entry.last_action == "promoted"
    assert any("seal stable" in note for note in entry.notes)


def test_diff_against_prior_snapshot_lists_added_dropped_grade_changes(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl = manager.create(owner="user", label="x", symbols=["A", "B"])
    snap_before = manager.snapshot(wl.watchlist_id)
    manager.update_state(wl.watchlist_id, "A", new_grade="A", action="promoted")
    manager.add_symbols(wl.watchlist_id, ["C"])
    manager.drop_symbols(wl.watchlist_id, ["B"])
    snap_after = manager.snapshot(wl.watchlist_id)

    diff = manager.diff(snap_before, snap_after)

    assert diff.added_symbols == ["C"]
    assert diff.dropped_symbols == ["B"]
    assert diff.grade_changes["A"] == {"from": "C", "to": "A"}


def test_close_watchlist_sets_status(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl = manager.create(owner="user", label="x", symbols=["A"])

    closed = manager.close(wl.watchlist_id, note="end of day")

    assert closed.status == "closed"
    assert closed.closed_at
    assert any("end of day" in note for note in closed.notes)


def test_list_active_for_owner(tmp_path: Path) -> None:
    manager = WatchlistManager(_store(tmp_path))
    wl_a = manager.create(owner="alice", label="a", symbols=["X"])
    wl_b = manager.create(owner="alice", label="b", symbols=["Y"])
    manager.create(owner="bob", label="c", symbols=["Z"])
    manager.close(wl_b.watchlist_id)

    active = manager.list_active(owner="alice")

    assert {item.watchlist_id for item in active} == {wl_a.watchlist_id}
```

- [ ] **Step 3: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_watchlists.py -v
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 4: 实现 manager**

`src/aegis_alpha/watchlists/manager.py`:

```python
from __future__ import annotations

import uuid
from typing import Iterable

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    CandidateGrade,
    Watchlist,
    WatchlistDiff,
    WatchlistEntry,
    WatchlistEntryAction,
)
from aegis_alpha.storage import AegisAlphaStore


class WatchlistManager:
    def __init__(self, store: AegisAlphaStore) -> None:
        self.store = store

    def create(
        self,
        *,
        owner: str,
        label: str,
        symbols: Iterable[str],
        expires_at: str = "",
    ) -> Watchlist:
        timestamp = now_iso()
        watchlist = Watchlist(
            watchlist_id=str(uuid.uuid4()),
            owner=owner.strip(),
            label=label.strip(),
            status="active",
            created_at=timestamp,
            expires_at=expires_at.strip(),
            entries=[
                WatchlistEntry(
                    symbol=symbol.strip(),
                    added_at=timestamp,
                    initial_grade="C",
                    last_grade="C",
                    last_action="added",
                    last_action_at=timestamp,
                )
                for symbol in symbols
                if symbol.strip()
            ],
        )
        self.store.save_watchlist(watchlist)
        return watchlist

    def get(self, watchlist_id: str) -> Watchlist | None:
        return self.store.get_watchlist(watchlist_id)

    def list_active(self, *, owner: str = "") -> list[Watchlist]:
        return self.store.list_watchlists(owner=owner, status="active")

    def add_symbols(self, watchlist_id: str, symbols: Iterable[str]) -> Watchlist:
        watchlist = self._require(watchlist_id)
        timestamp = now_iso()
        existing = {entry.symbol for entry in watchlist.entries}
        new_entries = [
            WatchlistEntry(
                symbol=symbol.strip(),
                added_at=timestamp,
                initial_grade="C",
                last_grade="C",
                last_action="added",
                last_action_at=timestamp,
            )
            for symbol in symbols
            if symbol.strip() and symbol.strip() not in existing
        ]
        if not new_entries:
            return watchlist
        watchlist = watchlist.model_copy(update={"entries": [*watchlist.entries, *new_entries]})
        self.store.save_watchlist(watchlist)
        return watchlist

    def drop_symbols(self, watchlist_id: str, symbols: Iterable[str]) -> Watchlist:
        watchlist = self._require(watchlist_id)
        targets = {symbol.strip() for symbol in symbols if symbol.strip()}
        kept = [entry for entry in watchlist.entries if entry.symbol not in targets]
        if len(kept) == len(watchlist.entries):
            return watchlist
        watchlist = watchlist.model_copy(update={"entries": kept})
        self.store.save_watchlist(watchlist)
        return watchlist

    def update_state(
        self,
        watchlist_id: str,
        symbol: str,
        *,
        new_grade: CandidateGrade,
        action: WatchlistEntryAction,
        note: str = "",
    ) -> Watchlist:
        watchlist = self._require(watchlist_id)
        timestamp = now_iso()
        updated_entries: list[WatchlistEntry] = []
        for entry in watchlist.entries:
            if entry.symbol != symbol.strip():
                updated_entries.append(entry)
                continue
            notes = list(entry.notes)
            if note.strip():
                notes.append(f"{timestamp} {note.strip()}")
            updated_entries.append(
                entry.model_copy(
                    update={
                        "last_grade": new_grade,
                        "last_action": action,
                        "last_action_at": timestamp,
                        "notes": notes,
                    }
                )
            )
        watchlist = watchlist.model_copy(update={"entries": updated_entries})
        self.store.save_watchlist(watchlist)
        return watchlist

    def close(self, watchlist_id: str, *, note: str = "") -> Watchlist:
        watchlist = self._require(watchlist_id)
        timestamp = now_iso()
        notes = list(watchlist.notes)
        if note.strip():
            notes.append(f"{timestamp} {note.strip()}")
        watchlist = watchlist.model_copy(
            update={"status": "closed", "closed_at": timestamp, "notes": notes}
        )
        self.store.save_watchlist(watchlist)
        return watchlist

    def snapshot(self, watchlist_id: str) -> Watchlist:
        watchlist = self._require(watchlist_id)
        return watchlist.model_copy()

    def diff(self, before: Watchlist, after: Watchlist) -> WatchlistDiff:
        before_map = {entry.symbol: entry for entry in before.entries}
        after_map = {entry.symbol: entry for entry in after.entries}
        added = sorted(after_map.keys() - before_map.keys())
        dropped = sorted(before_map.keys() - after_map.keys())
        grade_changes: dict[str, dict[str, str]] = {}
        for symbol in before_map.keys() & after_map.keys():
            old = before_map[symbol].last_grade
            new = after_map[symbol].last_grade
            if old != new:
                grade_changes[symbol] = {"from": old, "to": new}
        return WatchlistDiff(
            watchlist_id=after.watchlist_id,
            from_timestamp=before.created_at,
            to_timestamp=now_iso(),
            added_symbols=added,
            dropped_symbols=dropped,
            grade_changes=grade_changes,
        )

    def _require(self, watchlist_id: str) -> Watchlist:
        watchlist = self.store.get_watchlist(watchlist_id)
        if watchlist is None:
            raise KeyError(f"watchlist not found: {watchlist_id}")
        return watchlist
```

- [ ] **Step 5: Commit**（实现先 commit，store 方法下个 task 加）

```bash
git add src/aegis_alpha/watchlists/__init__.py src/aegis_alpha/watchlists/manager.py tests/test_watchlists.py
git commit -m "Add WatchlistManager CRUD and diff (storage methods follow)"
```

---

## Task 4: storage 加 watchlist 方法 + 跑测试

**Files:**
- Modify: `src/aegis_alpha/storage.py`

- [ ] **Step 1: 在 storage.py 顶部 imports 追加**

```python
from aegis_alpha.models import (
    ...,  # existing
    Watchlist,
    WatchlistEntry,
)
```

- [ ] **Step 2: 在 `AegisAlphaStore` 类末尾追加方法**

```python
    def save_watchlist(self, watchlist: Watchlist) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlists (
                    watchlist_id, owner, label, status, created_at,
                    expires_at, closed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(watchlist_id) DO UPDATE SET
                    status = excluded.status,
                    closed_at = excluded.closed_at,
                    payload_json = excluded.payload_json
                """,
                (
                    watchlist.watchlist_id,
                    watchlist.owner,
                    watchlist.label,
                    watchlist.status,
                    watchlist.created_at,
                    watchlist.expires_at,
                    watchlist.closed_at,
                    watchlist.model_dump_json(),
                ),
            )
            conn.execute("DELETE FROM watchlist_entries WHERE watchlist_id = ?", (watchlist.watchlist_id,))
            conn.executemany(
                """
                INSERT INTO watchlist_entries (
                    watchlist_id, symbol, added_at, last_action, last_action_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        watchlist.watchlist_id,
                        entry.symbol,
                        entry.added_at,
                        entry.last_action,
                        entry.last_action_at,
                        entry.model_dump_json(),
                    )
                    for entry in watchlist.entries
                ],
            )

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM watchlists WHERE watchlist_id = ?",
                (watchlist_id,),
            ).fetchone()
        return Watchlist.model_validate_json(row[0]) if row else None

    def list_watchlists(self, *, owner: str = "", status: str = "") -> list[Watchlist]:
        clauses = []
        params: list[object] = []
        if owner:
            clauses.append("owner = ?")
            params.append(owner)
        if status:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT payload_json FROM watchlists"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Watchlist.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 3: 跑 watchlist 测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_watchlists.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: 全量回归**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
```

Expected: 全 PASS（无破坏既有测试）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/storage.py
git commit -m "Add watchlist storage methods to AegisAlphaStore"
```

---

## Task 5: SealTimelineTracker

**Files:**
- Create: `src/aegis_alpha/seal_timeline/__init__.py`
- Create: `src/aegis_alpha/seal_timeline/tracker.py`
- Create: `tests/test_seal_timeline.py`
- Modify: `src/aegis_alpha/storage.py`

- [ ] **Step 1: 空 init**

`src/aegis_alpha/seal_timeline/__init__.py`:

```python
"""Intraday seal/break timeline tracker."""
```

- [ ] **Step 2: 写失败测试**

`tests/test_seal_timeline.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import SealTimelineEvent
from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_record_first_seal_then_break_then_reseal(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))

    tracker.record(SealTimelineEvent(symbol="002230.SZ", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00", seal_amount_cny=120_000_000))
    tracker.record(SealTimelineEvent(symbol="002230.SZ", trading_day="2026-05-31", kind="break", occurred_at="2026-05-31T10:15:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="002230.SZ", trading_day="2026-05-31", kind="reseal", occurred_at="2026-05-31T10:42:00+08:00", seal_amount_cny=80_000_000))

    timeline = tracker.get_timeline("002230.SZ", "2026-05-31")

    assert [event.kind for event in timeline.events] == ["first_seal", "break", "reseal"]
    assert timeline.break_count == 1
    assert timeline.reseal_count == 1
    assert timeline.final_status == "reopened"


def test_final_break_marks_status_broken(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))
    tracker.record(SealTimelineEvent(symbol="X", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="X", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T14:55:00+08:00"))

    timeline = tracker.get_timeline("X", "2026-05-31")

    assert timeline.final_status == "broken"


def test_no_break_means_sealed(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))
    tracker.record(SealTimelineEvent(symbol="X", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))

    timeline = tracker.get_timeline("X", "2026-05-31")

    assert timeline.final_status == "sealed"
    assert timeline.break_count == 0


def test_empty_timeline_status_unknown(tmp_path: Path) -> None:
    tracker = SealTimelineTracker(_store(tmp_path))

    timeline = tracker.get_timeline("X", "2026-05-31")

    assert timeline.final_status == "unknown"
    assert not timeline.events
```

- [ ] **Step 3: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_seal_timeline.py -v
```

Expected: FAIL（模块不存在）。

- [ ] **Step 4: 实现 tracker**

`src/aegis_alpha/seal_timeline/tracker.py`:

```python
from __future__ import annotations

from typing import Literal

from aegis_alpha.models import SealTimeline, SealTimelineEvent
from aegis_alpha.storage import AegisAlphaStore


class SealTimelineTracker:
    def __init__(self, store: AegisAlphaStore) -> None:
        self.store = store

    def record(self, event: SealTimelineEvent) -> SealTimelineEvent:
        self.store.save_seal_timeline_event(event)
        return event

    def get_timeline(self, symbol: str, trading_day: str) -> SealTimeline:
        events = self.store.list_seal_timeline_events(symbol, trading_day)
        events_sorted = sorted(events, key=lambda item: item.occurred_at)
        break_count = sum(1 for event in events_sorted if event.kind in {"break", "final_break"})
        reseal_count = sum(1 for event in events_sorted if event.kind == "reseal")
        final_status = self._derive_final_status(events_sorted)
        return SealTimeline(
            symbol=symbol,
            trading_day=trading_day,
            events=events_sorted,
            final_status=final_status,
            break_count=break_count,
            reseal_count=reseal_count,
        )

    @staticmethod
    def _derive_final_status(events: list[SealTimelineEvent]) -> Literal["sealed", "broken", "reopened", "unknown"]:
        if not events:
            return "unknown"
        last = events[-1]
        if last.kind == "first_seal":
            return "sealed"
        if last.kind == "final_break":
            return "broken"
        if last.kind == "break":
            return "broken"
        if last.kind == "reseal":
            return "reopened"
        return "unknown"
```

- [ ] **Step 5: storage.py 加方法**

在 `storage.py` import 区追加 `SealTimelineEvent`，在 `AegisAlphaStore` 末尾加：

```python
    def save_seal_timeline_event(self, event: SealTimelineEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO seal_timeline_events (
                    symbol, trading_day, kind, occurred_at, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.symbol,
                    event.trading_day,
                    event.kind,
                    event.occurred_at,
                    event.model_dump_json(),
                ),
            )

    def list_seal_timeline_events(self, symbol: str, trading_day: str) -> list[SealTimelineEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM seal_timeline_events
                WHERE symbol = ? AND trading_day = ?
                ORDER BY occurred_at ASC
                """,
                (symbol, trading_day),
            ).fetchall()
        return [SealTimelineEvent.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 6: 跑测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_seal_timeline.py -v
```

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add src/aegis_alpha/seal_timeline/ src/aegis_alpha/storage.py tests/test_seal_timeline.py
git commit -m "Add SealTimelineTracker for intraday seal/break events"
```

---

## Task 6: THEME_DIVERGENCE 事件检测器

**Files:**
- Create: `src/aegis_alpha/seal_timeline/divergence.py`
- Create: `tests/test_divergence.py`

- [ ] **Step 1: 写失败测试**

`tests/test_divergence.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import SealTimelineEvent, ThemeLeader
from aegis_alpha.seal_timeline.divergence import detect_theme_divergence
from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_leader_break_with_followers_alive_emits_divergence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tracker = SealTimelineTracker(store)
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T13:30:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="F1", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T10:00:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="F2", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T10:30:00+08:00"))
    leader = ThemeLeader(theme="AI", trading_day="2026-05-31", leader_symbol="LDR", leader_name="LDR", co_leader_symbols=["F1", "F2"], member_count=3)

    events = detect_theme_divergence([leader], tracker, trading_day="2026-05-31")

    assert len(events) == 1
    assert events[0].event_type == "THEME_DIVERGENCE"
    assert events[0].theme == "AI"
    assert "LDR" in events[0].evidence[0]


def test_leader_alive_no_divergence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tracker = SealTimelineTracker(store)
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    leader = ThemeLeader(theme="AI", trading_day="2026-05-31", leader_symbol="LDR", leader_name="LDR", member_count=3)

    events = detect_theme_divergence([leader], tracker, trading_day="2026-05-31")

    assert events == []


def test_leader_break_with_no_alive_followers_no_divergence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tracker = SealTimelineTracker(store)
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T09:35:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="LDR", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T13:30:00+08:00"))
    leader = ThemeLeader(theme="AI", trading_day="2026-05-31", leader_symbol="LDR", leader_name="LDR", co_leader_symbols=["F1"], member_count=2)
    tracker.record(SealTimelineEvent(symbol="F1", trading_day="2026-05-31", kind="first_seal", occurred_at="2026-05-31T10:00:00+08:00"))
    tracker.record(SealTimelineEvent(symbol="F1", trading_day="2026-05-31", kind="final_break", occurred_at="2026-05-31T13:50:00+08:00"))

    events = detect_theme_divergence([leader], tracker, trading_day="2026-05-31")

    assert events == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_divergence.py -v
```

Expected: FAIL。

- [ ] **Step 3: 实现 divergence.py**

`src/aegis_alpha/seal_timeline/divergence.py`:

```python
from __future__ import annotations

import hashlib

from aegis_alpha.clock import now_iso
from aegis_alpha.models import MarketEvent, ThemeLeader
from aegis_alpha.seal_timeline.tracker import SealTimelineTracker


def detect_theme_divergence(
    leaders: list[ThemeLeader],
    tracker: SealTimelineTracker,
    *,
    trading_day: str,
) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    received_at = now_iso()
    for leader in leaders:
        leader_timeline = tracker.get_timeline(leader.leader_symbol, trading_day)
        if leader_timeline.final_status not in {"broken"}:
            continue
        alive_followers = []
        for follower in leader.co_leader_symbols:
            follower_timeline = tracker.get_timeline(follower, trading_day)
            if follower_timeline.final_status in {"sealed", "reopened"}:
                alive_followers.append(follower)
        if not alive_followers:
            continue
        evidence = [
            f"Leader {leader.leader_symbol} broken in theme {leader.theme}; alive followers: {','.join(alive_followers)}.",
        ]
        seed = f"THEME_DIVERGENCE|{leader.theme}|{leader.leader_symbol}|{trading_day}"
        event_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        events.append(
            MarketEvent(
                event_id=event_id,
                event_type="THEME_DIVERGENCE",
                symbol=leader.leader_symbol,
                name=leader.leader_name,
                theme=leader.theme,
                confidence="medium",
                score=70.0,
                evidence=evidence,
                provider_timestamp=received_at,
                received_at=received_at,
                freshness_status="fresh",
                suggested_agent_action=[
                    "warn_orderbook_risk",
                    "rescore_second_board_candidates",
                ],
                data={
                    "leader_symbol": leader.leader_symbol,
                    "alive_followers": alive_followers,
                    "trading_day": trading_day,
                },
            )
        )
    return events
```

- [ ] **Step 4: 跑测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_divergence.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/seal_timeline/divergence.py tests/test_divergence.py
git commit -m "Detect THEME_DIVERGENCE when leader breaks while followers stay alive"
```

---

## Task 7: 接 SealTimeline 进 jvquant + mock

**Files:**
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`

注意：jvquant 现阶段没有真实 intraday seal/break 监控来源（要 lv2 才有）。本 task 只实现「读 timeline」（从 store 拿）和「附加 divergence event 到 get_recent_market_events」。**不实现自动写入** intraday seal events——那是 P5 lv2 落地的事。Mock 写一个固定 timeline 让 contract test 跑通。

- [ ] **Step 1: 在 protocols.py 中追加方法**

```python
    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline: ...

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent: ...
```

并 import `SealTimeline, SealTimelineEvent`。

- [ ] **Step 2: mock 实现**

在 `mock_market_data.py` 的 `MockMarketDataAdapter` 末尾加：

```python
    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline:
        from aegis_alpha.models import SealTimelineEvent
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        normalized = symbol.strip().upper()
        if normalized.startswith("002230"):
            return SealTimeline(
                symbol=normalized,
                trading_day=day,
                events=[
                    SealTimelineEvent(symbol=normalized, trading_day=day, kind="first_seal", occurred_at=f"{day}T09:56:12+08:00", seal_amount_cny=128_000_000),
                ],
                final_status="sealed",
                break_count=0,
                reseal_count=0,
            )
        return SealTimeline(symbol=normalized, trading_day=day, events=[], final_status="unknown")

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent:
        # Mock adapter does not persist; return as-is for contract.
        return event
```

并在 mock 的 `import` 区追加 `SealTimeline`。

- [ ] **Step 3: jvquant adapter 实现**

在 `src/aegis_alpha/adapters/jvquant/adapter.py` 加：

```python
    def get_seal_timeline(self, symbol: str, trading_day: str = "") -> SealTimeline:
        from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
        from aegis_alpha.symbols import normalize_symbol
        normalized = normalize_symbol(symbol)
        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        return SealTimelineTracker(AegisAlphaStore()).get_timeline(normalized, day)

    def record_seal_timeline_event(self, event: SealTimelineEvent) -> SealTimelineEvent:
        from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
        return SealTimelineTracker(AegisAlphaStore()).record(event)
```

并在 import 区追加 `SealTimeline, SealTimelineEvent`。

- [ ] **Step 4: 在 `get_recent_market_events` 中追加 divergence 检测**

定位 `get_recent_market_events` 方法。在现有事件检测之后追加：

```python
        from aegis_alpha.seal_timeline.divergence import detect_theme_divergence
        from aegis_alpha.seal_timeline.tracker import SealTimelineTracker
        store = AegisAlphaStore()
        tracker = SealTimelineTracker(store)
        trading_day = datetime.now(SH_TZ).date().isoformat()
        leaders = self.get_theme_leaders(trading_day=trading_day)
        divergence_events = detect_theme_divergence(leaders, tracker, trading_day=trading_day)
        for event in divergence_events:
            store.save_market_event(event)
        events.extend(divergence_events)
```

注意：如果原方法已经把 events 落库，divergence 也要落库（防止重复 event_id 由 `INSERT OR REPLACE` 保护）。如果原方法没有 `save_market_event(single)` 方法只有 `save_market_events(iterable)`，改为 `store.save_market_events(divergence_events)`。

如果 `event_type` filter 在调用栈上面（例如 `get_recent_market_events(event_type="THEME_DIVERGENCE")`），让 divergence event 也通过该 filter——这个由现有 filter 逻辑统一处理，不需要额外代码。

- [ ] **Step 5: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
```

Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/protocols.py src/aegis_alpha/adapters/mock_market_data.py src/aegis_alpha/adapters/jvquant/adapter.py
git commit -m "Wire SealTimeline and THEME_DIVERGENCE into adapters"
```

---

## Task 8: P3 protocol 与 mock contract test

**Files:**
- Create: `tests/test_p3_protocol.py`

- [ ] **Step 1: 写测试**

`tests/test_p3_protocol.py`:

```python
from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.models import SealTimelineEvent
from aegis_alpha.protocols import MarketDataAdapter


def test_mock_adapter_satisfies_p3_protocol_extensions() -> None:
    adapter: MarketDataAdapter = MockMarketDataAdapter()
    timeline = adapter.get_seal_timeline("002230.SZ")
    assert timeline.final_status == "sealed"
    assert timeline.events
    recorded = adapter.record_seal_timeline_event(
        SealTimelineEvent(
            symbol="X",
            trading_day="2026-05-31",
            kind="first_seal",
            occurred_at="2026-05-31T09:35:00+08:00",
        )
    )
    assert recorded.symbol == "X"


def test_mock_adapter_unknown_symbol_returns_empty_timeline() -> None:
    adapter = MockMarketDataAdapter()
    timeline = adapter.get_seal_timeline("XXXXXX")
    assert timeline.final_status == "unknown"
    assert not timeline.events
```

- [ ] **Step 2: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_p3_protocol.py -v
git add tests/test_p3_protocol.py
git commit -m "Add P3 protocol contract test for mock adapter"
```

---

## Task 9: DailyReview 生成器

**Files:**
- Create: `src/aegis_alpha/reviews/__init__.py`
- Create: `src/aegis_alpha/reviews/daily.py`
- Create: `tests/test_reviews_daily.py`

- [ ] **Step 1: 空 init**

`src/aegis_alpha/reviews/__init__.py`:

```python
"""Review report generators."""
```

- [ ] **Step 2: 写失败测试**

`tests/test_reviews_daily.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.models import CandidateOutcomeReview
from aegis_alpha.reviews.daily import generate_daily_review
from aegis_alpha.storage import AegisAlphaStore


def test_daily_review_aggregates_grades_and_outcomes(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="002230.SZ",
            trading_day="2026-05-31",
            touched_limit_up=True,
            sealed_second_board=True,
            next_day_open_pct=2.4,
        )
    )
    store.save_review_outcome(
        CandidateOutcomeReview(
            symbol="300024.SZ",
            trading_day="2026-05-31",
            touched_limit_up=False,
            sealed_second_board=False,
        )
    )
    adapter = MockMarketDataAdapter()

    review = generate_daily_review(adapter, store, trading_day="2026-05-31")

    assert review.trading_day == "2026-05-31"
    assert review.candidate_count == 2
    assert review.grade_distribution
    assert review.sealed_count == 1
    assert {item.symbol for item in review.items} == {"002230.SZ", "300024.SZ"}


def test_daily_review_with_no_outcomes_has_zero_sealed(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    adapter = MockMarketDataAdapter()

    review = generate_daily_review(adapter, store, trading_day="2026-05-31")

    assert review.sealed_count == 0
    for item in review.items:
        assert item.touched_limit_up is None
```

- [ ] **Step 3: 跑测试确认失败**

- [ ] **Step 4: 实现 daily.py**

```python
from __future__ import annotations

from collections import Counter

from aegis_alpha.clock import now_iso
from aegis_alpha.models import DailyReview, DailyReviewItem
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


def generate_daily_review(
    adapter: MarketDataAdapter,
    store: AegisAlphaStore,
    *,
    trading_day: str,
) -> DailyReview:
    candidates = adapter.get_second_board_candidates()
    items: list[DailyReviewItem] = []
    grade_counter: Counter[str] = Counter()
    sealed_count = 0
    for candidate in candidates:
        outcome = store.get_review_outcome(candidate.symbol, trading_day)
        sealed = outcome.sealed_second_board if outcome else None
        if sealed:
            sealed_count += 1
        grade_counter[candidate.grade] += 1
        items.append(
            DailyReviewItem(
                symbol=candidate.symbol,
                grade_at_pick=candidate.grade,
                theme=candidate.theme,
                theme_role=candidate.theme_role,
                previous_consecutive_boards=candidate.previous_consecutive_boards,
                touched_limit_up=outcome.touched_limit_up if outcome else None,
                sealed_second_board=sealed,
                next_day_open_pct=outcome.next_day_open_pct if outcome else None,
            )
        )
    return DailyReview(
        trading_day=trading_day,
        generated_at=now_iso(),
        candidate_count=len(items),
        grade_distribution=dict(grade_counter),
        sealed_count=sealed_count,
        items=items,
        notes=[
            "Daily review aggregates today's candidate pool and stored outcomes.",
            "Outcomes that have not been recorded show null for touched_limit_up / sealed_second_board.",
        ],
    )
```

注意：`store.get_review_outcome` 当前签名是 `(symbol, trading_day) -> CandidateOutcomeReview`（永远返回对象，找不到就返回 placeholder）。检查 storage.py 实际签名。如果它返回带 `notes=["No stored review outcome yet."]` 的占位对象而非 None，调整逻辑：

```python
        if outcome and outcome.touched_limit_up is not None:
            sealed = outcome.sealed_second_board
        else:
            sealed = None
```

- [ ] **Step 5: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_reviews_daily.py -v
git add src/aegis_alpha/reviews/__init__.py src/aegis_alpha/reviews/daily.py tests/test_reviews_daily.py
git commit -m "Add generate_daily_review aggregating today's candidates and outcomes"
```

---

## Task 10: WeeklyPatternReport 生成器

**Files:**
- Create: `src/aegis_alpha/reviews/weekly.py`
- Create: `tests/test_reviews_weekly.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import AgentReview, CandidateOutcomeReview
from aegis_alpha.reviews.weekly import generate_weekly_pattern_report
from aegis_alpha.storage import AegisAlphaStore


def test_weekly_report_builds_grade_outcome_matrix(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    # Persist a few candidate-day outcomes; reuse review_outcomes table.
    store.save_review_outcome(CandidateOutcomeReview(symbol="A", trading_day="2026-05-25", sealed_second_board=True))
    store.save_review_outcome(CandidateOutcomeReview(symbol="B", trading_day="2026-05-26", sealed_second_board=False))
    store.save_review_outcome(CandidateOutcomeReview(symbol="C", trading_day="2026-05-27", sealed_second_board=True))

    # Weekly is grade × outcome — we need agent_reviews carrying grade.
    review = AgentReview(run_type="historical_eval", target_time="2026-05-25T10:00:00+08:00", symbols=["A"], grades=["A"])
    store.save_agent_review(review)
    review = AgentReview(run_type="historical_eval", target_time="2026-05-26T10:00:00+08:00", symbols=["B"], grades=["B"])
    store.save_agent_review(review)
    review = AgentReview(run_type="historical_eval", target_time="2026-05-27T10:00:00+08:00", symbols=["C"], grades=["A"])
    store.save_agent_review(review)

    report = generate_weekly_pattern_report(store, start_day="2026-05-25", end_day="2026-05-29")

    assert report.sample_size == 3
    assert "A" in report.grade_outcome_matrix
    assert report.grade_outcome_matrix["A"]["sealed"] == 2
    assert report.grade_outcome_matrix["B"]["broken"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 `weekly.py`**

```python
from __future__ import annotations

from collections import defaultdict

from aegis_alpha.clock import now_iso
from aegis_alpha.models import WeeklyPatternReport
from aegis_alpha.storage import AegisAlphaStore


def generate_weekly_pattern_report(
    store: AegisAlphaStore,
    *,
    start_day: str,
    end_day: str,
) -> WeeklyPatternReport:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    samples = 0
    reviews = store.list_agent_reviews_between(start_day, end_day)
    for review in reviews:
        for symbol, grade in zip(review.symbols, review.grades):
            target_day = review.target_time[:10] if review.target_time else ""
            outcome = store.get_review_outcome(symbol, target_day)
            sealed = outcome.sealed_second_board
            if sealed is None:
                continue
            label = "sealed" if sealed else "broken"
            matrix[grade][label] += 1
            samples += 1
    return WeeklyPatternReport(
        start_day=start_day,
        end_day=end_day,
        generated_at=now_iso(),
        grade_outcome_matrix={key: dict(value) for key, value in matrix.items()},
        sample_size=samples,
        notes=[
            f"Sampled {samples} grade/outcome pairs from agent_reviews between {start_day} and {end_day}.",
        ],
    )
```

需要 storage 加 `list_agent_reviews_between`：

```python
    def list_agent_reviews_between(self, start_day: str, end_day: str) -> list[AgentReview]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM agent_reviews
                ORDER BY id DESC
                """,
            ).fetchall()
        results: list[AgentReview] = []
        for row in rows:
            review = AgentReview.model_validate_json(row[0])
            target_day = review.target_time[:10] if review.target_time else ""
            if start_day <= target_day <= end_day:
                results.append(review)
        return results
```

import `AgentReview` 在 storage.py（应该已经在）。

- [ ] **Step 4: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_reviews_weekly.py -v
git add src/aegis_alpha/reviews/weekly.py src/aegis_alpha/storage.py tests/test_reviews_weekly.py
git commit -m "Add generate_weekly_pattern_report grade-outcome matrix"
```

---

## Task 11: MCP 暴露 review 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `src/aegis_alpha/mcp/dependencies.py`

- [ ] **Step 1: dependencies 加 store helper（已有则跳过）**

`mcp/dependencies.py` 已有 `get_store()`。无需改动。

- [ ] **Step 2: server.py 追加 2 个工具**

```python
@mcp.tool
def generate_daily_review(trading_day: str) -> dict:
    """Generate today's review aggregating candidates and outcomes."""
    from aegis_alpha.reviews.daily import generate_daily_review as _gen
    safe_day = trading_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}

    def _build(adapter):
        deps_store = get_default_dependencies().store
        return _gen(adapter, deps_store, trading_day=safe_day).model_dump()

    return _call_tool(_build)


@mcp.tool
def generate_weekly_pattern_report(start_day: str, end_day: str) -> dict:
    """Generate grade × outcome report between start_day and end_day (inclusive)."""
    from aegis_alpha.reviews.weekly import generate_weekly_pattern_report as _gen
    safe_start = start_day.strip()
    safe_end = end_day.strip()
    if not (safe_start and safe_end):
        return {"data_mode": "unavailable", "error": "start_day and end_day are required"}
    return _call_store(lambda store: _gen(store, start_day=safe_start, end_day=safe_end).model_dump())
```

确保 `get_default_dependencies` / `_call_tool` / `_call_store` 已 import（看现有文件顶部即可）。

- [ ] **Step 3: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
```

Expected: 全 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/aegis_alpha/mcp/server.py
git commit -m "Expose generate_daily_review and generate_weekly_pattern_report MCP tools"
```

---

## Task 12: AlertStore + 去重

**Files:**
- Create: `src/aegis_alpha/alerts/__init__.py`
- Create: `src/aegis_alpha/alerts/store.py`
- Create: `tests/test_alerts.py`
- Modify: `src/aegis_alpha/storage.py`

- [ ] **Step 1: 空 init**

```python
"""Alert persistence and notification."""
```

- [ ] **Step 2: 写失败测试**

`tests/test_alerts.py`:

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.alerts.store import AlertStore
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_create_alert_assigns_id_and_persists(tmp_path: Path) -> None:
    store = AlertStore(_store(tmp_path))

    alert = store.create(
        title="Theme leader broken",
        body="LDR theme=AI broken at 13:30",
        severity="warning",
        event_id="evt_1",
        symbol="LDR",
        theme="AI",
    )

    assert alert.alert_id
    assert alert.status == "pending"
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].alert_id == alert.alert_id


def test_create_dedupes_on_event_id(tmp_path: Path) -> None:
    store = AlertStore(_store(tmp_path))
    store.create(title="A", severity="info", event_id="evt_1")
    store.create(title="A again", severity="info", event_id="evt_1")

    pending = store.list_pending()
    assert len(pending) == 1


def test_acknowledge_marks_status(tmp_path: Path) -> None:
    store = AlertStore(_store(tmp_path))
    alert = store.create(title="A", severity="info")

    acked = store.acknowledge(alert.alert_id, note="seen")

    assert acked.status == "acknowledged"
    assert acked.acknowledged_at
    assert any("seen" in note for note in acked.notes)
    assert store.list_pending() == []
```

- [ ] **Step 3: 跑测试确认失败**

- [ ] **Step 4: 实现 AlertStore**

`src/aegis_alpha/alerts/store.py`:

```python
from __future__ import annotations

import uuid

from aegis_alpha.clock import now_iso
from aegis_alpha.models import AgentAlert, AlertSeverity
from aegis_alpha.storage import AegisAlphaStore


class AlertStore:
    def __init__(self, store: AegisAlphaStore) -> None:
        self.store = store

    def create(
        self,
        *,
        title: str,
        severity: AlertSeverity = "info",
        body: str = "",
        event_id: str = "",
        symbol: str = "",
        theme: str = "",
    ) -> AgentAlert:
        if event_id:
            existing = self.store.get_alert_by_event(event_id)
            if existing is not None:
                return existing
        alert = AgentAlert(
            alert_id=str(uuid.uuid4()),
            event_id=event_id,
            symbol=symbol,
            theme=theme,
            severity=severity,
            status="pending",
            title=title.strip(),
            body=body.strip(),
            created_at=now_iso(),
        )
        self.store.save_alert(alert)
        return alert

    def acknowledge(self, alert_id: str, *, note: str = "") -> AgentAlert:
        alert = self.store.get_alert(alert_id)
        if alert is None:
            raise KeyError(f"alert not found: {alert_id}")
        timestamp = now_iso()
        notes = list(alert.notes)
        if note.strip():
            notes.append(f"{timestamp} {note.strip()}")
        updated = alert.model_copy(
            update={"status": "acknowledged", "acknowledged_at": timestamp, "notes": notes}
        )
        self.store.save_alert(updated)
        return updated

    def list_pending(self, *, limit: int = 50) -> list[AgentAlert]:
        return self.store.list_alerts(status="pending", limit=limit)

    def list_recent(self, *, limit: int = 50) -> list[AgentAlert]:
        return self.store.list_alerts(status="", limit=limit)
```

- [ ] **Step 5: storage.py 加方法**

```python
    def save_alert(self, alert: AgentAlert) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_alerts (
                    alert_id, event_id, symbol, theme, severity, status,
                    created_at, acknowledged_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alert_id) DO UPDATE SET
                    status = excluded.status,
                    acknowledged_at = excluded.acknowledged_at,
                    payload_json = excluded.payload_json
                """,
                (
                    alert.alert_id,
                    alert.event_id,
                    alert.symbol,
                    alert.theme,
                    alert.severity,
                    alert.status,
                    alert.created_at,
                    alert.acknowledged_at,
                    alert.model_dump_json(),
                ),
            )

    def get_alert(self, alert_id: str) -> AgentAlert | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        return AgentAlert.model_validate_json(row[0]) if row else None

    def get_alert_by_event(self, event_id: str) -> AgentAlert | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM agent_alerts WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
        return AgentAlert.model_validate_json(row[0]) if row else None

    def list_alerts(self, *, status: str = "", limit: int = 50) -> list[AgentAlert]:
        safe_limit = max(1, min(int(limit or 50), 200))
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT payload_json FROM agent_alerts"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AgentAlert.model_validate_json(row[0]) for row in rows]
```

import `AgentAlert` 在 storage.py。

- [ ] **Step 6: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_alerts.py -v
git add src/aegis_alpha/alerts/__init__.py src/aegis_alpha/alerts/store.py src/aegis_alpha/storage.py tests/test_alerts.py
git commit -m "Add AlertStore with event-id dedup and acknowledge flow"
```

---

## Task 13: macOS Notifier（可选 sidecar）

**Files:**
- Create: `src/aegis_alpha/alerts/notifier.py`

注意：notifier 是**可选 sidecar**，单元测试不强制启用 macOS API。配置开关是 `AEGIS_ALPHA_ENABLE_DESKTOP_NOTIFICATIONS`。

- [ ] **Step 1: 写实现**

`src/aegis_alpha/alerts/notifier.py`:

```python
from __future__ import annotations

import os
import shlex
import subprocess
import sys

from aegis_alpha.logging_setup import get_logger
from aegis_alpha.models import AgentAlert


_LOGGER = get_logger(__name__)


def _enabled() -> bool:
    raw = os.environ.get("AEGIS_ALPHA_ENABLE_DESKTOP_NOTIFICATIONS", "false").strip().lower()
    return raw in {"1", "true", "yes", "y"}


def notify_macos(alert: AgentAlert) -> bool:
    if not _enabled():
        return False
    if sys.platform != "darwin":
        _LOGGER.debug("event=desktop_notify_skip platform=%s", sys.platform)
        return False
    title = alert.title.replace("\"", "'")[:120]
    body = alert.body.replace("\"", "'")[:240] or alert.title
    script = f'display notification "{body}" with title "Aegis Alpha" subtitle "{title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=3,
            capture_output=True,
        )
        return True
    except Exception as exc:
        _LOGGER.warning("event=desktop_notify_failed error=%s", type(exc).__name__)
        return False
```

- [ ] **Step 2: Commit**（不写测试——这是 OS 集成，单元测试只能 mock，价值不大；环境变量默认关）

```bash
git add src/aegis_alpha/alerts/notifier.py
git commit -m "Add optional macOS desktop notifier behind env flag"
```

---

## Task 14: runner 检测 event 时写 alert + MCP 暴露 alert 工具

**Files:**
- Modify: `src/aegis_alpha/runner.py`
- Modify: `src/aegis_alpha/mcp/server.py`

- [ ] **Step 1: runner.py 在 persist_buffer_outputs 之后写 alerts**

定位 `persist_buffer_outputs` 方法，找到 `if events: self.store.save_market_events(events)` 的下一行追加：

```python
        if events:
            self._maybe_alert_from_events(events)
```

并加新方法：

```python
    def _maybe_alert_from_events(self, events: list[MarketEvent]) -> None:
        try:
            from aegis_alpha.alerts.store import AlertStore
            from aegis_alpha.alerts.notifier import notify_macos
        except Exception:
            return
        alert_store = AlertStore(self.store)
        critical_types = {
            "SEAL_ORDER_DECAY",
            "BIG_ORDER_INFLOW_SPIKE",
            "THEME_DIVERGENCE",
        }
        for event in events:
            if event.event_type not in critical_types:
                continue
            severity = "critical" if event.event_type == "SEAL_ORDER_DECAY" else "warning"
            alert = alert_store.create(
                title=f"{event.event_type} {event.symbol}",
                body="; ".join(event.evidence)[:512],
                severity=severity,
                event_id=event.event_id,
                symbol=event.symbol,
                theme=event.theme,
            )
            notify_macos(alert)
```

import `MarketEvent` 在 runner.py（应该已经在）。

- [ ] **Step 2: server.py 追加 3 个 alert 工具**

```python
@mcp.tool
def get_pending_alerts(limit: int = 20) -> list[dict] | dict:
    """Return pending alerts that have not been acknowledged."""
    from aegis_alpha.alerts.store import AlertStore
    safe_limit = max(1, min(int(limit or 20), 100))
    return _call_store(lambda store: [a.model_dump() for a in AlertStore(store).list_pending(limit=safe_limit)])


@mcp.tool
def acknowledge_alert(alert_id: str, note: str = "") -> dict:
    """Acknowledge a pending alert."""
    from aegis_alpha.alerts.store import AlertStore
    safe_id = alert_id.strip()
    if not safe_id:
        return {"data_mode": "unavailable", "error": "alert_id is required"}
    return _call_store(lambda store: AlertStore(store).acknowledge(safe_id, note=note.strip()).model_dump())


@mcp.tool
def get_seal_timeline(symbol: str, trading_day: str = "") -> dict:
    """Return the intraday seal/break timeline for one stock."""
    return _call_tool(lambda adapter: adapter.get_seal_timeline(symbol, trading_day.strip()).model_dump())
```

- [ ] **Step 3: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
```

Expected: 全 PASS。

- [ ] **Step 4: Commit**

```bash
git add src/aegis_alpha/runner.py src/aegis_alpha/mcp/server.py
git commit -m "Wire critical events to alerts and expose alert MCP tools"
```

---

## Task 15: ThemeRanking 模块

**Files:**
- Create: `src/aegis_alpha/themes/ranking.py`
- Create: `tests/test_theme_ranking.py`

- [ ] **Step 1: 写失败测试**

`tests/test_theme_ranking.py`:

```python
from __future__ import annotations

from aegis_alpha.models import LimitUpStock, ThemeLeader
from aegis_alpha.themes.ranking import compute_top_themes, theme_rotation_diff


def test_compute_top_themes_ranks_by_member_then_leader_height() -> None:
    leaders = [
        ThemeLeader(theme="A", trading_day="2026-05-31", leader_symbol="x", leader_name="x", leader_consecutive_boards=1, member_count=3),
        ThemeLeader(theme="B", trading_day="2026-05-31", leader_symbol="y", leader_name="y", leader_consecutive_boards=4, member_count=2),
        ThemeLeader(theme="C", trading_day="2026-05-31", leader_symbol="z", leader_name="z", leader_consecutive_boards=2, member_count=5),
    ]
    rankings = compute_top_themes(leaders, trading_day="2026-05-31", limit=3)
    assert [r.theme for r in rankings] == ["C", "A", "B"]  # member_count first
    assert rankings[0].rank == 1


def test_compute_top_themes_filters_zero_members() -> None:
    leaders = [
        ThemeLeader(theme="empty", trading_day="2026-05-31", leader_symbol="", leader_name="", member_count=0),
    ]
    rankings = compute_top_themes(leaders, trading_day="2026-05-31", limit=5)
    assert rankings == []


def test_theme_rotation_diff_finds_new_and_fading() -> None:
    today = ["A", "B", "C"]
    yesterday = ["B", "D"]
    rotation = theme_rotation_diff(today_themes=today, yesterday_themes=yesterday, trading_day="2026-05-31")
    assert rotation.new_themes == ["A", "C"]
    assert rotation.fading_themes == ["D"]
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 `themes/ranking.py`**

```python
from __future__ import annotations

from aegis_alpha.models import ThemeLeader, ThemeRanking, ThemeRotationEntry


def compute_top_themes(
    leaders: list[ThemeLeader],
    *,
    trading_day: str,
    limit: int = 10,
) -> list[ThemeRanking]:
    valid = [leader for leader in leaders if leader.member_count > 0]
    valid.sort(
        key=lambda leader: (
            leader.member_count,
            leader.leader_consecutive_boards,
            leader.leader_seal_amount_cny,
        ),
        reverse=True,
    )
    safe_limit = max(1, min(int(limit or 10), 50))
    rankings: list[ThemeRanking] = []
    for index, leader in enumerate(valid[:safe_limit]):
        score = min(
            100.0,
            leader.member_count * 10.0
            + leader.leader_consecutive_boards * 8.0,
        )
        rankings.append(
            ThemeRanking(
                theme=leader.theme,
                trading_day=trading_day,
                rank=index + 1,
                member_count=leader.member_count,
                leader_symbol=leader.leader_symbol,
                leader_consecutive_boards=leader.leader_consecutive_boards,
                score=round(score, 2),
            )
        )
    return rankings


def theme_rotation_diff(
    *,
    today_themes: list[str],
    yesterday_themes: list[str],
    trading_day: str,
) -> ThemeRotationEntry:
    today_set = set(today_themes)
    yesterday_set = set(yesterday_themes)
    return ThemeRotationEntry(
        trading_day=trading_day,
        top_themes=today_themes,
        new_themes=sorted(today_set - yesterday_set),
        fading_themes=sorted(yesterday_set - today_set),
    )
```

- [ ] **Step 4: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_theme_ranking.py -v
git add src/aegis_alpha/themes/ranking.py tests/test_theme_ranking.py
git commit -m "Add theme ranking and rotation diff helpers"
```

---

## Task 16: MCP 暴露 watchlist + theme ranking 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`

- [ ] **Step 1: 追加工具**

```python
@mcp.tool
def create_watchlist(owner: str, label: str, symbols: str = "", expires_at: str = "") -> dict:
    """Create a new watchlist for `owner` with optional pipe-separated `symbols`."""
    from aegis_alpha.watchlists.manager import WatchlistManager
    safe_symbols = [item.strip() for item in symbols.split("|") if item.strip()]

    def _build(store):
        return WatchlistManager(store).create(
            owner=owner.strip(),
            label=label.strip(),
            symbols=safe_symbols,
            expires_at=expires_at.strip(),
        ).model_dump()

    return _call_store(_build)


@mcp.tool
def update_watchlist_state(
    watchlist_id: str,
    symbol: str,
    new_grade: str,
    action: str,
    note: str = "",
) -> dict:
    """Update one entry's grade and action history in a watchlist."""
    from aegis_alpha.watchlists.manager import WatchlistManager

    def _build(store):
        return WatchlistManager(store).update_state(
            watchlist_id.strip(),
            symbol.strip(),
            new_grade=new_grade.strip().upper(),
            action=action.strip().lower(),
            note=note.strip(),
        ).model_dump()

    return _call_store(_build)


@mcp.tool
def close_watchlist(watchlist_id: str, note: str = "") -> dict:
    """Close an active watchlist."""
    from aegis_alpha.watchlists.manager import WatchlistManager
    return _call_store(lambda store: WatchlistManager(store).close(watchlist_id.strip(), note=note.strip()).model_dump())


@mcp.tool
def list_active_watchlists(owner: str = "") -> list[dict] | dict:
    """List active watchlists for an owner (or all owners if blank)."""
    from aegis_alpha.watchlists.manager import WatchlistManager
    return _call_store(
        lambda store: [item.model_dump() for item in WatchlistManager(store).list_active(owner=owner.strip())]
    )


@mcp.tool
def get_top_themes_today(trading_day: str = "", limit: int = 10) -> list[dict]:
    """Return today's top themes ranked by member count and leader height."""
    from aegis_alpha.themes.ranking import compute_top_themes
    safe_day = trading_day.strip()
    safe_limit = max(1, min(int(limit or 10), 50))

    def _build(adapter):
        leaders = adapter.get_theme_leaders(trading_day=safe_day)
        return [r.model_dump() for r in compute_top_themes(leaders, trading_day=safe_day or "", limit=safe_limit)]

    return _call_tool(_build)
```

- [ ] **Step 2: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
```

Expected: 全 PASS。

- [ ] **Step 3: Commit**

```bash
git add src/aegis_alpha/mcp/server.py
git commit -m "Expose watchlist CRUD and top themes MCP tools"
```

---

## Task 17: 收尾 — MCP yaml + README + SKILL 文档

**Files:**
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: yaml 加新工具名**

在 `tools.include` 列表中追加（紧跟现有 P2 工具之后）：

```yaml
        - generate_daily_review
        - generate_weekly_pattern_report
        - get_pending_alerts
        - acknowledge_alert
        - get_seal_timeline
        - create_watchlist
        - update_watchlist_state
        - close_watchlist
        - list_active_watchlists
        - get_top_themes_today
```

- [ ] **Step 2: README 加新工具到两个工具列表**

在 jvquant 段（约 README:122-141 行的 list）和完整工具列表段（约 README:312-345 行的 list）都追加上面 10 个工具名（带签名注释更佳）。

- [ ] **Step 3: SKILL.md 更新 Required MCP Tools 段**

在「Core tools」末尾追加（按工作流顺序）：

```markdown
- `get_top_themes_today`
- `get_seal_timeline`
- `get_pending_alerts`
- `acknowledge_alert`
- `create_watchlist`
- `update_watchlist_state`
- `close_watchlist`
- `list_active_watchlists`
- `generate_daily_review`
- `generate_weekly_pattern_report`
```

并在 SKILL.md 的「Standard Workflow」末尾加新 step 13-15：

```markdown
13. For multi-hour monitoring, create a watchlist with `create_watchlist(owner=user, label=YYYY-MM-DD label, symbols=A|B|C)` early in the session. Use `update_watchlist_state` whenever a candidate's grade changes. Use `close_watchlist` at session end to seal the audit trail.
14. Read `get_pending_alerts` whenever the user starts a new chat to surface anything the runner detected while away. After acting on an alert call `acknowledge_alert(alert_id, note=...)`.
15. After 15:10, run `generate_daily_review(trading_day=today)` to produce the structured review item used by Phase 3 review-and-correction. For weekly pattern audits use `generate_weekly_pattern_report(start_day, end_day)` (max 14-day window recommended).
```

- [ ] **Step 4: 全量测试 + smoke**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ --tb=short -q
PYTHONPATH=src .venv/bin/python scripts/smoke_check.py
```

Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add .hermes/config/aegis-alpha-mcp.yaml README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "Document P3 MCP tools in MCP yaml, README, and SKILL"
```

---

## Self-Review

- [x] **Subsystem coverage** —
  - A 盯盘列表 → Tasks 1-4 + 16
  - B Seal Timeline + 分歧→一致 → Tasks 5-8 + 14（critical event → alert）
  - C 复盘报告 → Tasks 9-11
  - D 告警 → Tasks 12-14
  - E 板块强度排行 → Tasks 15-16
  - F 文档收尾 → Task 17

- [x] **No placeholders** — 所有 step 都给具体代码、具体测试、具体命令。Task 9 Step 4 提到 store 签名兼容时给了完整调整方案。

- [x] **Type consistency** —
  - `WatchlistEntryAction` Literal 在 model 中定义，manager 和 test 中使用一致（`"added"` / `"promoted"` / `"downgraded"` / `"dropped"` / `"noted"`）。
  - `SealTimelineKind` Literal 在 model 中定义，tracker 状态推导使用一致（`"first_seal"` / `"break"` / `"reseal"` / `"final_break"`）。
  - `AlertSeverity` 在 model 中定义，runner 写时和 store create 一致。
  - `MarketEventType` 加 `"THEME_DIVERGENCE"` 后与 events.py 现有 detector 兼容（detector 用 try/lookup config rule，新事件类型不进 `_detect_single` 分支因此不破坏现有事件链）。
  - `Watchlist.entries` 在 manager `model_copy` 时保持 List 类型一致；`WatchlistDiff.grade_changes` 是 dict[str, dict[str, str]]，diff 函数和 test 断言一致。

- [x] **TDD 全程** — 每个新模块都先写失败测试再实现。

- [x] **依赖关系顺序正确** — Task 1 (models) → Task 2 (migration) → Task 3-4 (watchlist) → Task 5-8 (seal timeline + divergence + adapter wiring) → Task 9-11 (reviews) → Task 12-14 (alerts + runner) → Task 15-16 (theme ranking + MCP) → Task 17 (docs)。每一步要么 self-contained 要么前一步刚铺好底。

- [x] **No commit-message-only files** — 每个 commit 都改了至少 1 个 src 或 tests 文件，没有「只改 commit message」的空提交。
