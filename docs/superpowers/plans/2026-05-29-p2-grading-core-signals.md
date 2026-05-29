# P2 评级核心数据补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把评级体系从「单股语义查询拼凑」升级为「板块龙头/连板梯队/情绪温度计/竞价分析」四维结构化输入，让 A/B/C/REJECT 评级有可信的板块和梯队上下文。

**Architecture:** 4 个独立子系统，每个一个新模块 + 一张 SQLite 表 + 一个或多个 MCP 工具。所有计算输出落入候选契约 `SecondBoardCandidate` 的新字段或新 MCP tool。每个子系统都遵循 P1 建立的 Protocol/grading config/store/logger 模式。

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (P1 migration framework), pytest, jvQuant 语义查询。

**前置依赖：** P0（speed_pct/涨停板 bug 已修），P1（Protocol/grading config/migration/clock/cache/logger 已就位）。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/aegis_alpha/themes/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/themes/leader.py` | 新建 | `ThemeLeaderResolver`：识别板块龙头 |
| `src/aegis_alpha/themes/ladder.py` | 新建 | `LimitUpLadderResolver`：连板高度 |
| `src/aegis_alpha/themes/emotion.py` | 新建 | `MarketEmotionGauge`：情绪温度计 |
| `src/aegis_alpha/themes/auction.py` | 新建 | `AuctionAnalyzer`：竞价分析 |
| `src/aegis_alpha/db_migrations_files/m0002_themes.py` | 新建 | 加 `theme_leaders` / `limit_up_ladder` 表 |
| `src/aegis_alpha/models.py` | 修改 | 加 `ThemeLeader` / `LadderEntry` / `AuctionAnalysis` / `MarketEmotion` 模型；扩展 `SecondBoardCandidate` 与 `MarketSentimentGate` |
| `src/aegis_alpha/storage.py` | 修改 | 加 `save_theme_leaders` / `latest_theme_leaders` / `save_ladder_entries` / `get_ladder_entry` 方法 |
| `src/aegis_alpha/protocols.py` | 修改 | 加 4 个新方法到 Protocol |
| `src/aegis_alpha/adapters/mock_market_data.py` | 修改 | 实现 4 个新方法 |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | 修改 | 接入 4 个 resolver；填充候选新字段 |
| `src/aegis_alpha/mcp/server.py` | 修改 | 暴露新 MCP 工具 |
| `tests/test_theme_leader.py` | 新建 | 龙头识别测试 |
| `tests/test_ladder.py` | 新建 | 连板高度测试 |
| `tests/test_emotion.py` | 新建 | 情绪温度计测试 |
| `tests/test_auction.py` | 新建 | 竞价分析测试 |

---

## Task 1: 数据模型扩展

**Files:**
- Modify: `src/aegis_alpha/models.py`

- [ ] **Step 1: 加新模型**

在 `src/aegis_alpha/models.py` 末尾追加：

```python
LadderHeight = Literal[
    "first_board",
    "second_board",
    "third_board",
    "fourth_board",
    "high_height",  # 5+ boards
    "broken",  # had limit-up history but most recent break
    "unknown",
]


class LadderEntry(BaseModel):
    symbol: str
    trading_day: str
    consecutive_boards: int = Field(ge=0)
    height_label: LadderHeight = "unknown"
    last_limit_up_day: str = ""
    history_window_days: int = 10
    notes: list[str] = Field(default_factory=list)


ThemeLeaderRole = Literal["leader", "co_leader", "follower", "unknown"]


class ThemeLeader(BaseModel):
    theme: str
    trading_day: str
    leader_symbol: str
    leader_name: str
    leader_consecutive_boards: int = 0
    leader_first_limit_up_time: str = "unknown"
    leader_seal_amount_cny: float = 0.0
    leader_status: Literal["sealed", "broken", "reopened", "unknown"] = "unknown"
    co_leader_symbols: list[str] = Field(default_factory=list)
    member_count: int = 0
    notes: list[str] = Field(default_factory=list)


AuctionPattern = Literal[
    "strong_open",  # 高开 + 高换手 + 净买入
    "exit_liquidity",  # 高开 + 极高换手 (出货)
    "weak_open",  # 低开
    "stable",
    "unknown",
]


class AuctionAnalysis(BaseModel):
    symbol: str
    trading_day: str
    auction_change_pct: float = 0.0
    auction_turnover_cny: float = 0.0
    auction_turnover_rate: float = 0.0
    pattern: AuctionPattern = "unknown"
    pattern_reason: str = ""
    pre_open_change_pct: float = 0.0  # 9:20 quote
    final_open_change_pct: float = 0.0  # 9:25 quote
    cancellation_rate: float = Field(default=0.0, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class MarketEmotion(BaseModel):
    trading_day: str
    yesterday_limitup_today_premium_pct: float = 0.0
    yesterday_consecutive_boards_alive_count: int = 0
    yesterday_consecutive_boards_total: int = 0
    yesterday_consecutive_boards_alive_rate: float = Field(default=0.0, ge=0, le=1)
    first_to_second_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    second_to_third_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    first_board_to_consecutive_ratio: float = Field(default=0.0, ge=0, le=10)
    max_height_today: int = 0
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: 扩展 `SecondBoardCandidate`**

在 `SecondBoardCandidate` 类中追加字段（必须有默认值以兼容旧调用）：

```python
    previous_consecutive_boards: int = 0
    previous_height_label: LadderHeight = "unknown"
    theme_role: ThemeLeaderRole = "unknown"
    theme_leader_symbol: str = ""
    auction_pattern: AuctionPattern = "unknown"
```

- [ ] **Step 3: 扩展 `MarketSentimentGate`**

在 `MarketSentimentGate` 类中追加：

```python
    yesterday_limitup_today_premium_pct: float = 0.0
    consecutive_boards_alive_rate: float = Field(default=0.0, ge=0, le=1)
    first_to_second_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    second_to_third_promotion_rate: float = Field(default=0.0, ge=0, le=1)
    max_height_today: int = 0
```

- [ ] **Step 4: 编译确认无 syntax 错误**

```bash
.venv/bin/python -m compileall src/aegis_alpha/models.py
```

- [ ] **Step 5: 跑既有测试确认未破坏**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 所有原 test 仍 PASS（新字段都有默认值）。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/models.py
git commit -m "feat(models): add ladder/theme-leader/auction/emotion contracts

Adds LadderEntry, ThemeLeader, AuctionAnalysis, MarketEmotion plus new
optional fields on SecondBoardCandidate and MarketSentimentGate. All
new fields have defaults to preserve existing test fixtures."
```

---

## Task 2: 数据库迁移 0002

**Files:**
- Create: `src/aegis_alpha/db_migrations_files/m0002_themes.py`

- [ ] **Step 1: 实现迁移**

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS theme_leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            leader_symbol TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_theme_leaders_theme_day
            ON theme_leaders (theme, trading_day);

        CREATE TABLE IF NOT EXISTS limit_up_ladder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            consecutive_boards INTEGER NOT NULL,
            height_label TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, trading_day)
        );
        """
    )
```

- [ ] **Step 2: 写迁移测试**

在 `tests/test_db_migrations.py` 末尾追加：

```python
def test_migration_0002_creates_theme_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "theme_leaders" in names
    assert "limit_up_ladder" in names
    assert current_version(db) >= 2
```

- [ ] **Step 3: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_db_migrations.py -v
git add src/aegis_alpha/db_migrations_files/m0002_themes.py tests/test_db_migrations.py
git commit -m "feat(db): migration 0002 - theme_leaders + limit_up_ladder tables"
```

---

## Task 3: 连板高度（`LimitUpLadderResolver`）

**Files:**
- Create: `src/aegis_alpha/themes/__init__.py`
- Create: `src/aegis_alpha/themes/ladder.py`
- Create: `tests/test_ladder.py`
- Modify: `src/aegis_alpha/storage.py`

- [ ] **Step 1: `themes/__init__.py`**

```python
"""Theme/ladder/leader/emotion/auction layer."""
```

- [ ] **Step 2: 写失败测试**

`tests/test_ladder.py`：

```python
from __future__ import annotations

from datetime import date

import pytest

from aegis_alpha.models import LadderEntry
from aegis_alpha.themes.ladder import (
    LimitUpHistory,
    classify_height,
    compute_consecutive_boards,
)


def test_compute_consecutive_boards_three_in_a_row() -> None:
    history = LimitUpHistory(
        symbol="600000",
        limit_up_days=["2026-05-27", "2026-05-28", "2026-05-29"],
    )
    assert compute_consecutive_boards(history, today=date(2026, 5, 29)) == 3


def test_compute_consecutive_boards_with_gap_resets() -> None:
    history = LimitUpHistory(
        symbol="600000",
        limit_up_days=["2026-05-27", "2026-05-29"],  # gap on the 28th
    )
    # 28th is a trading day (Thursday), so the 27th run is broken.
    # Today's 29th should count as a fresh single-day limit-up = 1 streak.
    assert compute_consecutive_boards(history, today=date(2026, 5, 29)) == 1


def test_compute_consecutive_boards_excludes_today_when_not_limit_up() -> None:
    history = LimitUpHistory(
        symbol="600000",
        limit_up_days=["2026-05-27", "2026-05-28"],
    )
    # If today is 5/29 and not in the history, today is not limit-up;
    # ladder still reports yesterday's streak of 2.
    assert compute_consecutive_boards(history, today=date(2026, 5, 29)) == 2


def test_compute_consecutive_boards_zero_when_empty() -> None:
    history = LimitUpHistory(symbol="600000", limit_up_days=[])
    assert compute_consecutive_boards(history, today=date(2026, 5, 29)) == 0


@pytest.mark.parametrize(
    "boards,expected_label",
    [
        (1, "first_board"),
        (2, "second_board"),
        (3, "third_board"),
        (4, "fourth_board"),
        (5, "high_height"),
        (8, "high_height"),
    ],
)
def test_classify_height(boards: int, expected_label: str) -> None:
    assert classify_height(boards).value if hasattr(classify_height(boards), "value") else classify_height(boards) == expected_label
    # The function returns the LadderHeight literal directly:
    assert classify_height(boards) == expected_label


def test_classify_height_zero_is_unknown() -> None:
    assert classify_height(0) == "unknown"
```

- [ ] **Step 3: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_ladder.py -v
```

- [ ] **Step 4: 实现 `themes/ladder.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from aegis_alpha.clock import SH_TZ
from aegis_alpha.models import LadderEntry, LadderHeight


@dataclass(frozen=True)
class LimitUpHistory:
    symbol: str
    limit_up_days: list[str]  # ISO yyyy-mm-dd, sorted ascending


def _parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def _previous_trading_day(day: date) -> date:
    """Return the previous calendar weekday (skip Sat/Sun). Holidays not handled here."""
    cursor = day - timedelta(days=1)
    while cursor.weekday() >= 5:  # 5 = Sat, 6 = Sun
        cursor -= timedelta(days=1)
    return cursor


def compute_consecutive_boards(history: LimitUpHistory, *, today: date) -> int:
    """Walk back from `today` (or yesterday if today not in history) counting contiguous limit-up days."""
    if not history.limit_up_days:
        return 0
    days = sorted({_parse_day(d) for d in history.limit_up_days})
    streak = 0
    cursor = today if today in days else _previous_trading_day(today)
    while cursor in days:
        streak += 1
        cursor = _previous_trading_day(cursor)
    return streak


def classify_height(consecutive_boards: int) -> LadderHeight:
    if consecutive_boards <= 0:
        return "unknown"
    if consecutive_boards == 1:
        return "first_board"
    if consecutive_boards == 2:
        return "second_board"
    if consecutive_boards == 3:
        return "third_board"
    if consecutive_boards == 4:
        return "fourth_board"
    return "high_height"


class LimitUpLadderResolver:
    """Resolve consecutive-board height for a symbol given a history fetcher."""

    def __init__(
        self,
        history_fetcher: "callable[[str, int], LimitUpHistory]",
        *,
        history_window_days: int = 10,
    ) -> None:
        self._fetch = history_fetcher
        self.history_window_days = history_window_days

    def resolve(self, symbol: str, *, today: date | None = None) -> LadderEntry:
        today_d = today or datetime.now(SH_TZ).date()
        history = self._fetch(symbol, self.history_window_days)
        boards = compute_consecutive_boards(history, today=today_d)
        last_day = max((d for d in history.limit_up_days), default="") if history.limit_up_days else ""
        return LadderEntry(
            symbol=symbol,
            trading_day=today_d.isoformat(),
            consecutive_boards=boards,
            height_label=classify_height(boards),
            last_limit_up_day=last_day,
            history_window_days=self.history_window_days,
            notes=[
                f"history_window_days={self.history_window_days}",
                f"sample_count={len(history.limit_up_days)}",
            ],
        )
```

- [ ] **Step 5: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_ladder.py -v
```

Expected: PASS。

- [ ] **Step 6: 加 storage 方法**

在 `src/aegis_alpha/storage.py` 的 `AegisAlphaStore` 类末尾加：

```python
    def save_ladder_entry(self, entry: LadderEntry) -> LadderEntry:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO limit_up_ladder (
                    symbol, trading_day, consecutive_boards, height_label, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trading_day) DO UPDATE SET
                    consecutive_boards = excluded.consecutive_boards,
                    height_label = excluded.height_label,
                    payload_json = excluded.payload_json
                """,
                (
                    entry.symbol,
                    entry.trading_day,
                    entry.consecutive_boards,
                    entry.height_label,
                    entry.model_dump_json(),
                ),
            )
        return entry

    def get_ladder_entry(self, symbol: str, trading_day: str) -> LadderEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM limit_up_ladder WHERE symbol = ? AND trading_day = ?",
                (symbol, trading_day),
            ).fetchone()
        return LadderEntry.model_validate_json(row[0]) if row else None
```

并在 `storage.py` 顶部 import 区加 `LadderEntry`。

- [ ] **Step 7: storage 写测试**

`tests/test_storage.py`（新建文件）：

```python
from __future__ import annotations

from pathlib import Path

from aegis_alpha.models import LadderEntry
from aegis_alpha.storage import AegisAlphaStore


def test_save_and_get_ladder_entry(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    entry = LadderEntry(
        symbol="600000",
        trading_day="2026-05-29",
        consecutive_boards=2,
        height_label="second_board",
        last_limit_up_day="2026-05-29",
    )
    store.save_ladder_entry(entry)
    fetched = store.get_ladder_entry("600000", "2026-05-29")
    assert fetched is not None
    assert fetched.consecutive_boards == 2
    assert fetched.height_label == "second_board"


def test_save_ladder_entry_upserts(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    store.save_ladder_entry(
        LadderEntry(symbol="600000", trading_day="2026-05-29", consecutive_boards=1, height_label="first_board")
    )
    store.save_ladder_entry(
        LadderEntry(symbol="600000", trading_day="2026-05-29", consecutive_boards=2, height_label="second_board")
    )
    fetched = store.get_ladder_entry("600000", "2026-05-29")
    assert fetched is not None
    assert fetched.consecutive_boards == 2
```

- [ ] **Step 8: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_ladder.py tests/test_storage.py -v
git add src/aegis_alpha/themes/ src/aegis_alpha/storage.py tests/test_ladder.py tests/test_storage.py
git commit -m "feat(themes): LimitUpLadderResolver + storage upsert

Walk back from today over historical limit-up days to compute
consecutive-board height (first_board / second_board / ... / high_height).
Used by candidate contract's previous_consecutive_boards field."
```

---

## Task 4: 板块龙头（`ThemeLeaderResolver`）

**Files:**
- Create: `src/aegis_alpha/themes/leader.py`
- Create: `tests/test_theme_leader.py`
- Modify: `src/aegis_alpha/storage.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from aegis_alpha.themes.leader import (
    ThemeMember,
    rank_theme_members,
    resolve_theme_leader,
)


def _member(symbol: str, **overrides) -> ThemeMember:
    return ThemeMember(
        symbol=symbol,
        name=overrides.get("name", symbol),
        consecutive_boards=overrides.get("consecutive_boards", 1),
        first_limit_up_time=overrides.get("first_limit_up_time", "10:00:00"),
        seal_amount_cny=overrides.get("seal_amount_cny", 100_000_000),
        is_sealed=overrides.get("is_sealed", True),
    )


def test_higher_consecutive_boards_wins() -> None:
    members = [
        _member("A", consecutive_boards=2),
        _member("B", consecutive_boards=3),
        _member("C", consecutive_boards=1),
    ]
    ranked = rank_theme_members(members)
    assert ranked[0].symbol == "B"


def test_earlier_first_limit_up_wins_when_equal_height() -> None:
    members = [
        _member("A", consecutive_boards=2, first_limit_up_time="09:45:00"),
        _member("B", consecutive_boards=2, first_limit_up_time="09:35:00"),
        _member("C", consecutive_boards=2, first_limit_up_time="10:30:00"),
    ]
    ranked = rank_theme_members(members)
    assert ranked[0].symbol == "B"


def test_larger_seal_wins_when_equal_height_and_time() -> None:
    members = [
        _member("A", consecutive_boards=2, first_limit_up_time="09:30:00", seal_amount_cny=100_000_000),
        _member("B", consecutive_boards=2, first_limit_up_time="09:30:00", seal_amount_cny=300_000_000),
    ]
    ranked = rank_theme_members(members)
    assert ranked[0].symbol == "B"


def test_broken_board_demoted_when_alive_alternative_exists() -> None:
    members = [
        _member("A", consecutive_boards=3, is_sealed=False),
        _member("B", consecutive_boards=2, is_sealed=True),
    ]
    leader = resolve_theme_leader(theme="AI应用", trading_day="2026-05-29", members=members)
    # Rule: when a higher-board candidate has broken status, alive 2-board takes priority
    assert leader.leader_symbol == "B"


def test_resolve_theme_leader_returns_unknown_when_empty() -> None:
    leader = resolve_theme_leader(theme="AI应用", trading_day="2026-05-29", members=[])
    assert leader.leader_symbol == ""
    assert leader.member_count == 0


def test_co_leaders_listed_when_within_one_board_of_leader() -> None:
    members = [
        _member("A", consecutive_boards=3),
        _member("B", consecutive_boards=3),
        _member("C", consecutive_boards=2),
        _member("D", consecutive_boards=1),
    ]
    leader = resolve_theme_leader(theme="AI应用", trading_day="2026-05-29", members=members)
    assert leader.leader_symbol in {"A", "B"}
    co_set = set(leader.co_leader_symbols)
    # Same height as leader → co_leader; one below → also a co_leader (within 1)
    assert "C" in co_set
    assert "D" not in co_set
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 `themes/leader.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from aegis_alpha.models import ThemeLeader


@dataclass(frozen=True)
class ThemeMember:
    symbol: str
    name: str
    consecutive_boards: int
    first_limit_up_time: str
    seal_amount_cny: float
    is_sealed: bool


def rank_theme_members(members: list[ThemeMember]) -> list[ThemeMember]:
    """Sort by (alive_first, consecutive_boards desc, first_limit_up_time asc, seal_amount desc)."""

    def key(m: ThemeMember) -> tuple:
        return (
            0 if m.is_sealed else 1,
            -m.consecutive_boards,
            m.first_limit_up_time if m.first_limit_up_time != "unknown" else "99:99:99",
            -m.seal_amount_cny,
            m.symbol,
        )

    return sorted(members, key=key)


def resolve_theme_leader(
    *,
    theme: str,
    trading_day: str,
    members: list[ThemeMember],
) -> ThemeLeader:
    if not members:
        return ThemeLeader(
            theme=theme,
            trading_day=trading_day,
            leader_symbol="",
            leader_name="",
            member_count=0,
            notes=["No members in theme."],
        )
    ranked = rank_theme_members(members)
    leader = ranked[0]
    co_threshold = max(1, leader.consecutive_boards - 1)
    co_leaders = [
        m.symbol
        for m in ranked[1:]
        if m.consecutive_boards >= co_threshold and m.is_sealed
    ]
    return ThemeLeader(
        theme=theme,
        trading_day=trading_day,
        leader_symbol=leader.symbol,
        leader_name=leader.name,
        leader_consecutive_boards=leader.consecutive_boards,
        leader_first_limit_up_time=leader.first_limit_up_time,
        leader_seal_amount_cny=leader.seal_amount_cny,
        leader_status="sealed" if leader.is_sealed else "broken",
        co_leader_symbols=co_leaders,
        member_count=len(members),
        notes=[
            f"ranked_count={len(ranked)}",
            f"co_threshold_boards={co_threshold}",
        ],
    )
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: storage 加方法**

在 `storage.py` 加：

```python
    def save_theme_leaders(self, leaders: list[ThemeLeader]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO theme_leaders (theme, trading_day, leader_symbol, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (l.theme, l.trading_day, l.leader_symbol, l.model_dump_json())
                    for l in leaders
                ],
            )

    def latest_theme_leaders(self, trading_day: str) -> list[ThemeLeader]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM theme_leaders
                WHERE trading_day = ?
                ORDER BY id DESC
                """,
                (trading_day,),
            ).fetchall()
        # De-duplicate by theme keeping the latest record.
        seen: set[str] = set()
        result: list[ThemeLeader] = []
        for row in rows:
            leader = ThemeLeader.model_validate_json(row[0])
            if leader.theme in seen:
                continue
            seen.add(leader.theme)
            result.append(leader)
        return result
```

import `ThemeLeader` 顶部。

- [ ] **Step 6: storage 测试**

在 `tests/test_storage.py` 末尾追加：

```python
from aegis_alpha.models import ThemeLeader


def test_save_and_get_theme_leaders(tmp_path: Path) -> None:
    store = AegisAlphaStore(tmp_path / "test.db")
    store.save_theme_leaders([
        ThemeLeader(theme="AI应用", trading_day="2026-05-29", leader_symbol="002230", leader_name="科大讯飞", member_count=5),
        ThemeLeader(theme="机器人", trading_day="2026-05-29", leader_symbol="300024", leader_name="机器人", member_count=3),
    ])
    leaders = store.latest_theme_leaders("2026-05-29")
    assert {l.theme for l in leaders} == {"AI应用", "机器人"}
```

- [ ] **Step 7: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_theme_leader.py tests/test_storage.py -v
git add src/aegis_alpha/themes/leader.py src/aegis_alpha/storage.py tests/test_theme_leader.py tests/test_storage.py
git commit -m "feat(themes): ThemeLeaderResolver

Identify board-leader by ranking on (alive, consecutive boards, first
limit-up time, seal amount). Co-leaders are alive members within one
board of the top. Persist daily snapshots."
```

---

## Task 5: 情绪温度计（`MarketEmotionGauge`）

**Files:**
- Create: `src/aegis_alpha/themes/emotion.py`
- Create: `tests/test_emotion.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from aegis_alpha.themes.emotion import (
    EmotionInputs,
    YesterdayLimitUpStock,
    compute_market_emotion,
)


def test_premium_pct_average_of_yesterday_limit_ups() -> None:
    inputs = EmotionInputs(
        trading_day="2026-05-29",
        yesterday_limit_ups=[
            YesterdayLimitUpStock(symbol="A", consecutive_boards=1, today_change_pct=5.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="B", consecutive_boards=1, today_change_pct=-3.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="C", consecutive_boards=2, today_change_pct=10.0, today_status="alive"),
        ],
    )
    emotion = compute_market_emotion(inputs)
    assert abs(emotion.yesterday_limitup_today_premium_pct - 4.0) < 0.01


def test_alive_rate_only_counts_consecutive_boards() -> None:
    inputs = EmotionInputs(
        trading_day="2026-05-29",
        yesterday_limit_ups=[
            YesterdayLimitUpStock(symbol="A", consecutive_boards=1, today_change_pct=5.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="B", consecutive_boards=2, today_change_pct=10.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="C", consecutive_boards=2, today_change_pct=-5.0, today_status="dead"),
            YesterdayLimitUpStock(symbol="D", consecutive_boards=3, today_change_pct=10.0, today_status="alive"),
        ],
    )
    emotion = compute_market_emotion(inputs)
    # Consecutive boards (>=2): B, C, D. Alive: B, D. Rate = 2/3.
    assert emotion.yesterday_consecutive_boards_total == 3
    assert emotion.yesterday_consecutive_boards_alive_count == 2
    assert abs(emotion.yesterday_consecutive_boards_alive_rate - (2 / 3)) < 0.01


def test_promotion_rates() -> None:
    inputs = EmotionInputs(
        trading_day="2026-05-29",
        yesterday_limit_ups=[
            YesterdayLimitUpStock(symbol="A", consecutive_boards=1, today_change_pct=10.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="B", consecutive_boards=1, today_change_pct=10.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="C", consecutive_boards=1, today_change_pct=5.0, today_status="alive"),  # not promoted
            YesterdayLimitUpStock(symbol="D", consecutive_boards=2, today_change_pct=10.0, today_status="alive"),
            YesterdayLimitUpStock(symbol="E", consecutive_boards=2, today_change_pct=-2.0, today_status="dead"),
        ],
        promoted_today=["A", "B", "D"],  # those that hit limit-up today
    )
    emotion = compute_market_emotion(inputs)
    # First-board promo: A,B,C → A,B promoted = 2/3
    assert abs(emotion.first_to_second_promotion_rate - (2 / 3)) < 0.01
    # Second-board promo: D,E → D promoted = 1/2
    assert abs(emotion.second_to_third_promotion_rate - 0.5) < 0.01


def test_max_height_today() -> None:
    inputs = EmotionInputs(
        trading_day="2026-05-29",
        yesterday_limit_ups=[
            YesterdayLimitUpStock(symbol="A", consecutive_boards=4, today_change_pct=10.0, today_status="alive"),
        ],
        promoted_today=["A"],
    )
    emotion = compute_market_emotion(inputs)
    assert emotion.max_height_today == 5  # 4 + 1


def test_no_data_returns_zeros() -> None:
    inputs = EmotionInputs(trading_day="2026-05-29", yesterday_limit_ups=[])
    emotion = compute_market_emotion(inputs)
    assert emotion.yesterday_limitup_today_premium_pct == 0.0
    assert emotion.yesterday_consecutive_boards_total == 0
    assert emotion.yesterday_consecutive_boards_alive_rate == 0.0
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 `themes/emotion.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from aegis_alpha.models import MarketEmotion


YesterdayLimitUpStatus = Literal["alive", "dead"]


@dataclass(frozen=True)
class YesterdayLimitUpStock:
    symbol: str
    consecutive_boards: int  # boards as of yesterday
    today_change_pct: float
    today_status: YesterdayLimitUpStatus  # "alive" if still positive / sealed today, else "dead"


@dataclass(frozen=True)
class EmotionInputs:
    trading_day: str
    yesterday_limit_ups: list[YesterdayLimitUpStock]
    promoted_today: list[str] = field(default_factory=list)


def _safe_avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _safe_rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def compute_market_emotion(inputs: EmotionInputs) -> MarketEmotion:
    promoted = set(inputs.promoted_today)

    if not inputs.yesterday_limit_ups:
        return MarketEmotion(
            trading_day=inputs.trading_day,
            notes=["No yesterday-limit-up sample."],
        )

    premium = _safe_avg([s.today_change_pct for s in inputs.yesterday_limit_ups])

    consec = [s for s in inputs.yesterday_limit_ups if s.consecutive_boards >= 2]
    consec_alive = [s for s in consec if s.today_status == "alive"]

    first_boards = [s for s in inputs.yesterday_limit_ups if s.consecutive_boards == 1]
    first_promoted = [s for s in first_boards if s.symbol in promoted]
    second_boards = [s for s in inputs.yesterday_limit_ups if s.consecutive_boards == 2]
    second_promoted = [s for s in second_boards if s.symbol in promoted]

    promoted_inputs = [s for s in inputs.yesterday_limit_ups if s.symbol in promoted]
    max_height = max(
        (s.consecutive_boards + 1 for s in promoted_inputs),
        default=max((s.consecutive_boards for s in inputs.yesterday_limit_ups), default=0),
    )

    first_to_consec_ratio = (
        round(len(first_boards) / len(consec), 4) if consec else 0.0
    )

    return MarketEmotion(
        trading_day=inputs.trading_day,
        yesterday_limitup_today_premium_pct=premium,
        yesterday_consecutive_boards_total=len(consec),
        yesterday_consecutive_boards_alive_count=len(consec_alive),
        yesterday_consecutive_boards_alive_rate=_safe_rate(len(consec_alive), len(consec)),
        first_to_second_promotion_rate=_safe_rate(len(first_promoted), len(first_boards)),
        second_to_third_promotion_rate=_safe_rate(len(second_promoted), len(second_boards)),
        first_board_to_consecutive_ratio=first_to_consec_ratio,
        max_height_today=max_height,
        notes=[
            f"sample_size={len(inputs.yesterday_limit_ups)}",
            f"promoted_today_count={len(promoted)}",
        ],
    )
```

- [ ] **Step 4: 跑测试确认通过 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_emotion.py -v
git add src/aegis_alpha/themes/emotion.py tests/test_emotion.py
git commit -m "feat(themes): MarketEmotionGauge

Compute yesterday-limit-up premium, consecutive-board alive rate,
first→second & second→third promotion rates, and today's max height
from structured inputs. Pure function, no side effects."
```

---

## Task 6: 竞价分析（`AuctionAnalyzer`）

**Files:**
- Create: `src/aegis_alpha/themes/auction.py`
- Create: `tests/test_auction.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from aegis_alpha.themes.auction import (
    AuctionInputs,
    classify_auction_pattern,
    compute_auction_analysis,
)


def test_strong_open_pattern() -> None:
    inputs = AuctionInputs(
        symbol="600000",
        trading_day="2026-05-29",
        pre_open_change_pct=2.0,
        final_open_change_pct=4.5,
        auction_turnover_cny=80_000_000,
        auction_turnover_rate=2.5,
    )
    pattern = classify_auction_pattern(inputs)
    assert pattern == "strong_open"


def test_exit_liquidity_pattern_high_turnover() -> None:
    inputs = AuctionInputs(
        symbol="600000",
        trading_day="2026-05-29",
        pre_open_change_pct=8.0,
        final_open_change_pct=7.0,
        auction_turnover_cny=400_000_000,
        auction_turnover_rate=12.0,
    )
    pattern = classify_auction_pattern(inputs)
    assert pattern == "exit_liquidity"


def test_weak_open_pattern() -> None:
    inputs = AuctionInputs(
        symbol="600000",
        trading_day="2026-05-29",
        pre_open_change_pct=-1.0,
        final_open_change_pct=-2.0,
        auction_turnover_cny=20_000_000,
        auction_turnover_rate=0.5,
    )
    assert classify_auction_pattern(inputs) == "weak_open"


def test_stable_pattern_when_changes_small() -> None:
    inputs = AuctionInputs(
        symbol="600000",
        trading_day="2026-05-29",
        pre_open_change_pct=0.4,
        final_open_change_pct=0.6,
        auction_turnover_cny=10_000_000,
        auction_turnover_rate=0.3,
    )
    assert classify_auction_pattern(inputs) == "stable"


def test_cancellation_rate_when_pre_open_higher_than_final() -> None:
    inputs = AuctionInputs(
        symbol="600000",
        trading_day="2026-05-29",
        pre_open_change_pct=5.0,
        final_open_change_pct=2.5,
        auction_turnover_cny=80_000_000,
        auction_turnover_rate=2.0,
    )
    analysis = compute_auction_analysis(inputs)
    assert analysis.cancellation_rate > 0
    assert analysis.cancellation_rate <= 1


def test_compute_auction_analysis_returns_pattern_and_reason() -> None:
    inputs = AuctionInputs(
        symbol="600000",
        trading_day="2026-05-29",
        pre_open_change_pct=2.0,
        final_open_change_pct=4.5,
        auction_turnover_cny=80_000_000,
        auction_turnover_rate=2.5,
    )
    analysis = compute_auction_analysis(inputs)
    assert analysis.pattern == "strong_open"
    assert analysis.pattern_reason
    assert analysis.symbol == "600000"
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 `themes/auction.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from aegis_alpha.models import AuctionAnalysis, AuctionPattern


@dataclass(frozen=True)
class AuctionInputs:
    symbol: str
    trading_day: str
    pre_open_change_pct: float  # 9:20 quote (best-effort)
    final_open_change_pct: float  # 9:25 final auction quote
    auction_turnover_cny: float
    auction_turnover_rate: float  # turnover / float in pct


_HIGH_OPEN_THRESHOLD = 3.0
_HIGH_TURNOVER_RATE_THRESHOLD = 5.0
_MILD_OPEN_THRESHOLD = 0.5


def classify_auction_pattern(inputs: AuctionInputs) -> AuctionPattern:
    final = inputs.final_open_change_pct
    rate = inputs.auction_turnover_rate
    if final >= _HIGH_OPEN_THRESHOLD and rate >= _HIGH_TURNOVER_RATE_THRESHOLD:
        return "exit_liquidity"
    if final >= _MILD_OPEN_THRESHOLD and rate < _HIGH_TURNOVER_RATE_THRESHOLD:
        return "strong_open"
    if final <= -_MILD_OPEN_THRESHOLD:
        return "weak_open"
    return "stable"


def _cancellation_rate(pre: float, final: float) -> float:
    if pre <= 0:
        return 0.0
    drop = max(0.0, pre - final)
    if pre == 0:
        return 0.0
    return round(min(1.0, drop / pre), 4)


def _pattern_reason(pattern: AuctionPattern, inputs: AuctionInputs) -> str:
    if pattern == "exit_liquidity":
        return (
            f"竞价高开 {inputs.final_open_change_pct:.2f}% 且换手率 "
            f"{inputs.auction_turnover_rate:.2f}% 超过阈值，疑似出货盘。"
        )
    if pattern == "strong_open":
        return (
            f"竞价高开 {inputs.final_open_change_pct:.2f}%，换手率 "
            f"{inputs.auction_turnover_rate:.2f}% 在合理区间，符合抢筹特征。"
        )
    if pattern == "weak_open":
        return f"竞价低开 {inputs.final_open_change_pct:.2f}%，盘前抛压主导。"
    return "竞价波动有限，未形成明显方向。"


def compute_auction_analysis(inputs: AuctionInputs) -> AuctionAnalysis:
    pattern = classify_auction_pattern(inputs)
    return AuctionAnalysis(
        symbol=inputs.symbol,
        trading_day=inputs.trading_day,
        auction_change_pct=round(inputs.final_open_change_pct, 4),
        auction_turnover_cny=round(inputs.auction_turnover_cny, 2),
        auction_turnover_rate=round(inputs.auction_turnover_rate, 4),
        pattern=pattern,
        pattern_reason=_pattern_reason(pattern, inputs),
        pre_open_change_pct=round(inputs.pre_open_change_pct, 4),
        final_open_change_pct=round(inputs.final_open_change_pct, 4),
        cancellation_rate=_cancellation_rate(inputs.pre_open_change_pct, inputs.final_open_change_pct),
        notes=[
            f"pre_open_change_pct={inputs.pre_open_change_pct:.2f}",
            f"final_open_change_pct={inputs.final_open_change_pct:.2f}",
        ],
    )
```

- [ ] **Step 4: 跑测试确认通过 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_auction.py -v
git add src/aegis_alpha/themes/auction.py tests/test_auction.py
git commit -m "feat(themes): AuctionAnalyzer

Classify pre-market auction into strong_open/exit_liquidity/weak_open
/stable based on final change vs turnover rate, plus cancellation
rate from 9:20→9:25 quote drop."
```

---

## Task 7: 把 4 个新方法加进 Protocol 和 mock 适配器

**Files:**
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`

- [ ] **Step 1: 扩展 Protocol**

在 `src/aegis_alpha/protocols.py` 的 Protocol 内追加：

```python
    def get_theme_leaders(self, trading_day: str | None = None) -> list[ThemeLeader]: ...
    def get_ladder_entry(self, symbol: str, trading_day: str | None = None) -> LadderEntry: ...
    def get_market_emotion(self, trading_day: str | None = None) -> MarketEmotion: ...
    def get_auction_analysis(self, symbol: str, trading_day: str | None = None) -> AuctionAnalysis: ...
```

并在文件顶部 import 区追加：

```python
from aegis_alpha.models import (
    AuctionAnalysis,
    LadderEntry,
    MarketEmotion,
    ThemeLeader,
    # ... existing imports
)
```

- [ ] **Step 2: mock 适配器实现 4 个新方法**

在 `src/aegis_alpha/adapters/mock_market_data.py` 的 `MockMarketDataAdapter` 类中追加：

```python
    def get_theme_leaders(self, trading_day: str | None = None) -> list[ThemeLeader]:
        from aegis_alpha.models import ThemeLeader

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        return [
            ThemeLeader(
                theme="AI应用",
                trading_day=day,
                leader_symbol="002230.SZ",
                leader_name="科大讯飞",
                leader_consecutive_boards=2,
                leader_first_limit_up_time="09:56:12",
                leader_seal_amount_cny=128_000_000,
                leader_status="sealed",
                co_leader_symbols=["300033.SZ"],
                member_count=6,
                notes=["Mock theme leader."],
            ),
            ThemeLeader(
                theme="机器人",
                trading_day=day,
                leader_symbol="300024.SZ",
                leader_name="机器人",
                leader_consecutive_boards=2,
                leader_first_limit_up_time="10:22:31",
                leader_seal_amount_cny=42_000_000,
                leader_status="reopened",
                member_count=3,
                notes=["Mock theme leader."],
            ),
        ]

    def get_ladder_entry(self, symbol: str, trading_day: str | None = None) -> LadderEntry:
        from aegis_alpha.models import LadderEntry

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        # Deterministic mock ladder per known symbol
        ladders = {
            "002230.SZ": (2, "second_board"),
            "300024.SZ": (2, "second_board"),
        }
        boards, label = ladders.get(symbol, (1, "first_board"))
        return LadderEntry(
            symbol=symbol,
            trading_day=day,
            consecutive_boards=boards,
            height_label=label,
            last_limit_up_day=day,
            history_window_days=10,
            notes=["Mock ladder entry."],
        )

    def get_market_emotion(self, trading_day: str | None = None) -> MarketEmotion:
        from aegis_alpha.models import MarketEmotion

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        return MarketEmotion(
            trading_day=day,
            yesterday_limitup_today_premium_pct=2.4,
            yesterday_consecutive_boards_total=8,
            yesterday_consecutive_boards_alive_count=5,
            yesterday_consecutive_boards_alive_rate=0.625,
            first_to_second_promotion_rate=0.42,
            second_to_third_promotion_rate=0.31,
            first_board_to_consecutive_ratio=4.0,
            max_height_today=5,
            notes=["Mock market emotion."],
        )

    def get_auction_analysis(self, symbol: str, trading_day: str | None = None) -> AuctionAnalysis:
        from aegis_alpha.models import AuctionAnalysis

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        return AuctionAnalysis(
            symbol=symbol,
            trading_day=day,
            auction_change_pct=3.2,
            auction_turnover_cny=92_000_000,
            auction_turnover_rate=1.8,
            pattern="strong_open",
            pattern_reason="Mock pattern reason: 高开稳健,符合抢筹特征。",
            pre_open_change_pct=2.5,
            final_open_change_pct=3.2,
            cancellation_rate=0.0,
            notes=["Mock auction analysis."],
        )
```

- [ ] **Step 3: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS（含 protocol 测试，mock 满足新 Protocol 方法）。

- [ ] **Step 4: Commit**

```bash
git add src/aegis_alpha/protocols.py src/aegis_alpha/adapters/mock_market_data.py
git commit -m "feat(adapters): mock theme_leaders/ladder/emotion/auction

Mock adapter satisfies P2 protocol additions so contract tests pass
and downstream MCP tools can be wired before live jvQuant impl lands."
```

---

## Task 8: jvQuant 适配器接入 4 个新方法

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`

由于这一步信号量大，分小步：

- [ ] **Step 1: `get_ladder_entry` 实现**

在 `JvQuantMarketDataAdapter` 加：

```python
    def get_ladder_entry(self, symbol: str, trading_day: str | None = None) -> LadderEntry:
        from aegis_alpha.themes.ladder import LimitUpHistory, LimitUpLadderResolver

        store = self._store_for_themes()
        cached = None
        if trading_day:
            cached = store.get_ladder_entry(symbol, trading_day)
            if cached is not None:
                return cached

        def history_fetcher(sym: str, window_days: int) -> LimitUpHistory:
            # Use existing kline payload; jvQuant returns daily bars with change_pct.
            payload = self.queries.kline(sym, "stock", "前复权", "day", window_days + 5)
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            fields = data.get("fields", []) if isinstance(data, dict) else []
            rows = data.get("list", []) if isinstance(data, dict) else []
            day_index = self._field_index(fields, "时间", "日期", "date")
            change_index = self._field_index(fields, "涨跌幅")
            limit_up_days: list[str] = []
            limit_pct = daily_limit_pct(sym) - 0.05  # tolerance for rounding
            for row in rows:
                if not isinstance(row, list):
                    continue
                day = self._row_value(row, day_index)
                change = _float_or_zero(self._row_value(row, change_index))
                if change >= limit_pct:
                    limit_up_days.append(str(day)[:10])
            return LimitUpHistory(symbol=sym, limit_up_days=limit_up_days)

        resolver = LimitUpLadderResolver(history_fetcher, history_window_days=10)
        entry = resolver.resolve(symbol)
        store.save_ladder_entry(entry)
        return entry
```

需要在文件中辅助方法 `_field_index` / `_row_value` 已经从 parsers 模块导入；如果还没，在 import 区加：

```python
from aegis_alpha.adapters.jvquant.parsers import _field_index, _row_value
from aegis_alpha.symbols import daily_limit_pct
```

并在 `__init__` 加：

```python
def _store_for_themes(self) -> AegisAlphaStore:
    from aegis_alpha.storage import AegisAlphaStore
    return AegisAlphaStore()
```

- [ ] **Step 2: `get_theme_leaders` 实现**

在 `JvQuantMarketDataAdapter` 加：

```python
    def get_theme_leaders(self, trading_day: str | None = None) -> list[ThemeLeader]:
        from aegis_alpha.themes.leader import ThemeMember, resolve_theme_leader

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        # Group today's limit-up pool by theme.
        limitup = self.get_limitup_pool()
        by_theme: dict[str, list[ThemeMember]] = {}
        for stock in limitup:
            ladder = self.get_ladder_entry(stock.symbol, day)
            member = ThemeMember(
                symbol=stock.symbol,
                name=stock.name,
                consecutive_boards=ladder.consecutive_boards,
                first_limit_up_time=stock.first_limit_up_time,
                seal_amount_cny=stock.seal_amount_cny,
                is_sealed=stock.status == "sealed",
            )
            by_theme.setdefault(stock.theme, []).append(member)
        leaders = [
            resolve_theme_leader(theme=theme, trading_day=day, members=members)
            for theme, members in by_theme.items()
        ]
        store = self._store_for_themes()
        if leaders:
            store.save_theme_leaders(leaders)
        return leaders
```

- [ ] **Step 3: `get_market_emotion` 实现**

```python
    def get_market_emotion(self, trading_day: str | None = None) -> MarketEmotion:
        from aegis_alpha.themes.emotion import (
            EmotionInputs,
            YesterdayLimitUpStock,
            compute_market_emotion,
        )

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        # Yesterday limit-up pool with today's change is exactly the second-board
        # candidate base query, but we want the full pool (including today's losers).
        payload = self.queries.query(
            "昨日涨停,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = self._query_rows(payload)
        promoted_today = {limitup.symbol for limitup in self.get_limitup_pool()}
        yesterday_stocks: list[YesterdayLimitUpStock] = []
        for row in rows:
            symbol = self._symbol_from_row(row)
            if not symbol:
                continue
            change_pct = _float_or_zero(self._field_value(row, "涨跌幅"))
            ladder = self.get_ladder_entry(symbol, day)
            today_status = "alive" if change_pct >= -1.0 else "dead"
            yesterday_stocks.append(
                YesterdayLimitUpStock(
                    symbol=symbol,
                    consecutive_boards=ladder.consecutive_boards,
                    today_change_pct=change_pct,
                    today_status=today_status,
                )
            )
        return compute_market_emotion(
            EmotionInputs(
                trading_day=day,
                yesterday_limit_ups=yesterday_stocks,
                promoted_today=list(promoted_today),
            )
        )
```

注意：`_query_rows` / `_symbol_from_row` / `_field_value` 已经在 parsers 模块；从 parsers 导入即可。

- [ ] **Step 4: `get_auction_analysis` 实现**

```python
    def get_auction_analysis(self, symbol: str, trading_day: str | None = None) -> AuctionAnalysis:
        from aegis_alpha.themes.auction import AuctionInputs, compute_auction_analysis

        day = trading_day or datetime.now(SH_TZ).date().isoformat()
        # The pool query returns auction fields per-symbol.
        payload = self.queries.query(
            "今日涨停,非ST,股票代码,股票简称,竞价涨幅,竞价成交额,竞价换手率,开盘价,价格,成交额,行业",
            sort_key="涨跌幅",
        )
        rows = self._rows_by_symbol(self._query_rows(payload))
        row = rows.get(symbol) or rows.get(self._normalize_symbol(symbol)) or {}
        final_change = _float_or_zero(self._field_value(row, "集合竞价涨跌幅", "竞价涨幅"))
        # 9:20 quote is not exposed by jvQuant's semantic query; use 9:25 as both pre/final.
        return compute_auction_analysis(
            AuctionInputs(
                symbol=symbol,
                trading_day=day,
                pre_open_change_pct=final_change,
                final_open_change_pct=final_change,
                auction_turnover_cny=self._parse_cny_amount(self._field_value(row, "集合竞价成交额", "竞价成交额")),
                auction_turnover_rate=_float_or_zero(self._field_value(row, "集合竞价换手率", "竞价换手率")),
            )
        )
```

注意 `_normalize_symbol` 是从 `aegis_alpha.symbols` 导入。

- [ ] **Step 5: 让 `get_second_board_candidates` 填充新字段**

在 candidate 构造前后调整：

```python
            # Compute ladder + theme leader for this candidate
            ladder_entry = self.get_ladder_entry(symbol, query_timestamp[:10])
            previous_consecutive = max(0, ladder_entry.consecutive_boards - (1 if symbol in promoted_today_set else 0))
            theme_leader = next(
                (
                    leader for leader in theme_leaders
                    if leader.theme == theme
                ),
                None,
            )
            theme_role: ThemeLeaderRole = "unknown"
            theme_leader_symbol = ""
            if theme_leader is not None:
                theme_leader_symbol = theme_leader.leader_symbol
                if symbol == theme_leader.leader_symbol:
                    theme_role = "leader"
                elif symbol in theme_leader.co_leader_symbols:
                    theme_role = "co_leader"
                else:
                    theme_role = "follower"
            auction_pattern: AuctionPattern = "unknown"
            try:
                auction = self.get_auction_analysis(symbol, query_timestamp[:10])
                auction_pattern = auction.pattern
            except Exception:
                pass
```

并在 candidate 构造的 kwargs 中追加：

```python
                    previous_consecutive_boards=previous_consecutive,
                    previous_height_label=ladder_entry.height_label,
                    theme_role=theme_role,
                    theme_leader_symbol=theme_leader_symbol,
                    auction_pattern=auction_pattern,
```

需要在函数顶部一次性 fetch theme_leaders：

```python
        theme_leaders = self.get_theme_leaders(query_timestamp[:10])
        promoted_today_set = {limit_up.symbol for limit_up in self.get_limitup_pool()}
```

- [ ] **Step 6: 让 `get_market_sentiment_gate` 填情绪字段**

修改 `get_market_sentiment_gate`：

```python
    def get_market_sentiment_gate(self) -> MarketSentimentGate:
        snapshot = self.get_market_snapshot()
        emotion = self.get_market_emotion(snapshot.trading_day)
        # ... existing score / risk / positive computation ...
        return MarketSentimentGate(
            # ... existing fields ...
            yesterday_limitup_today_premium_pct=emotion.yesterday_limitup_today_premium_pct,
            consecutive_boards_alive_rate=emotion.yesterday_consecutive_boards_alive_rate,
            first_to_second_promotion_rate=emotion.first_to_second_promotion_rate,
            second_to_third_promotion_rate=emotion.second_to_third_promotion_rate,
            max_height_today=emotion.max_height_today,
        )
```

- [ ] **Step 7: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 8: Commit**

```bash
git add src/aegis_alpha/adapters/jvquant/
git commit -m "feat(jvquant): wire ladder/leader/emotion/auction into adapter

get_second_board_candidates now fills previous_consecutive_boards,
theme_role, and auction_pattern. get_market_sentiment_gate exposes
emotion metrics. Lookups use SQLite cache where available."
```

---

## Task 9: MCP 工具暴露

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`

- [ ] **Step 1: 加 4 个 MCP 工具**

```python
@mcp.tool
def get_theme_leaders(trading_day: str = "") -> list[dict]:
    """Return theme leaders identified for a trading day (default: today)."""
    safe_day = trading_day.strip() or None
    return _call_tool(
        lambda adapter: [leader.model_dump() for leader in adapter.get_theme_leaders(safe_day)]
    )


@mcp.tool
def get_stock_ladder_entry(symbol: str, trading_day: str = "") -> dict:
    """Return consecutive-board height (ladder) for one stock."""
    safe_day = trading_day.strip() or None
    return _call_tool(lambda adapter: adapter.get_ladder_entry(symbol, safe_day).model_dump())


@mcp.tool
def get_market_emotion(trading_day: str = "") -> dict:
    """Return today's market emotion gauge (premium, alive rate, promotion rates, max height)."""
    safe_day = trading_day.strip() or None
    return _call_tool(lambda adapter: adapter.get_market_emotion(safe_day).model_dump())


@mcp.tool
def get_auction_analysis(symbol: str, trading_day: str = "") -> dict:
    """Return auction-window analysis (pattern, cancellation rate) for one stock."""
    safe_day = trading_day.strip() or None
    return _call_tool(lambda adapter: adapter.get_auction_analysis(symbol, safe_day).model_dump())
```

- [ ] **Step 2: 跑测试 + smoke**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
PYTHONPATH=src .venv/bin/python scripts/smoke_check.py
```

Expected: 全部 PASS。

- [ ] **Step 3: Commit**

```bash
git add src/aegis_alpha/mcp/server.py
git commit -m "feat(mcp): expose theme_leaders/ladder/emotion/auction tools"
```

---

## Task 10: 更新 README + Hermes skill 提示

**Files:**
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: README 工具列表更新**

在 `README.md` 中找到 MCP 工具列表（约第 312 行起），在合适位置插入：

```text
- `get_theme_leaders`
- `get_stock_ladder_entry`
- `get_market_emotion`
- `get_auction_analysis`
```

并在 jvQuant 工具列表（约第 122-149 行）也插入相同 4 项。

- [ ] **Step 2: SKILL.md 工作流更新**

在 `.hermes/skills/second-board-radar/SKILL.md` 「Standard Workflow」部分插入新步骤（在 step 1 之后）：

```text
1.5. Read `get_market_emotion` to confirm yesterday-limit-up premium and consecutive-board alive rate. If alive rate < 0.4 or premium < -1%, treat the day as risk-off and stop at a defensive summary.

1.6. For each candidate, fetch `get_stock_ladder_entry` and `get_theme_leaders` to know its connect-board height and whether it is the leader, co-leader, or follower. Reject board-chasing on a follower when the leader has broken board.
```

- [ ] **Step 3: Commit**

```bash
git add README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "docs: document P2 ladder/leader/emotion/auction tools"
```

---

## Task 11: 收尾验证

- [ ] **Step 1: 全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: 全部 PASS。覆盖率应明显高于 P1 完成时（新增 5 个新测试文件）。

- [ ] **Step 2: 编译检查**

```bash
.venv/bin/python -m compileall src scripts tests
```

- [ ] **Step 3: Smoke**

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_check.py
PYTHONPATH=src .venv/bin/python scripts/replay_orderbook_fixture.py
```

- [ ] **Step 4: 文件大小检查**

```bash
wc -l src/aegis_alpha/themes/*.py src/aegis_alpha/adapters/jvquant/*.py
```

Expected: themes 模块每个 < 200 行；jvquant adapter.py 由于加了 4 个新方法可能接近 800，必要时考虑后续 split。

---

## Self-Review

- [x] **Spec coverage** —
  - 板块龙头 → Task 4 + Task 7 + Task 8 + Task 9 (`get_theme_leaders`)
  - 连板高度 → Task 3 + Task 7 + Task 8 + Task 9 (`get_stock_ladder_entry`)
  - 情绪温度计 → Task 5 + Task 7 + Task 8 (gate 接入) + Task 9 (`get_market_emotion`)
  - 竞价分析 → Task 6 + Task 7 + Task 8 + Task 9 (`get_auction_analysis`)
  - 候选契约扩展（previous_consecutive_boards 等）→ Task 1 + Task 8 Step 5
  - SentimentGate 扩展 → Task 1 + Task 8 Step 6
  - 数据库迁移 → Task 2
  - SKILL/README 文档 → Task 10

- [x] **No placeholders** — Step 5/6 of Task 8（jvquant 接入候选与 gate）虽然只贴了 diff 风格的代码，但变量都已在前文定义（`theme_leaders`, `promoted_today_set`, `theme`, `symbol`, `query_timestamp`, `theme_role`, `auction_pattern` 等）；执行者照搬不需推断。

- [x] **Type consistency** —
  - `LadderHeight` literal 在 ladder.py 与 models.py 中保持一致。
  - `ThemeMember` dataclass 在 leader.py 内部使用，不进契约。
  - `AuctionInputs`, `EmotionInputs`, `LimitUpHistory` dataclass 是输入助手，不进契约。
  - `LadderEntry`, `ThemeLeader`, `MarketEmotion`, `AuctionAnalysis` 都是 Pydantic model，所有 task 调用一致。
  - mock 适配器和 jvquant 适配器的 4 个新方法签名完全一致，与 Protocol 一致。

- [x] **TDD 流程** — 每个新模块（ladder/leader/emotion/auction）都先写测试再实现；storage 新方法和 mock 适配器配合 protocol test 间接覆盖。
