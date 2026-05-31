# P5 — 数据维度扩展 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把第二板候选契约从「价格 + 涨速 + 题材」扩展到「资金主体（龙虎榜）+ 反向情绪（跌停/ST）+ 上涨驱动（4 类原因）+ 形态识别（T 字 / 一字 / 烂板 / 平台突破 / 假突破）+ 资金分时切片」，让 Hermes 读到的候选画像更接近一线打板老手的判断维度。

**Architecture:**
新增 `src/aegis_alpha/extensions/` 包，承载 P5 5 个独立子系统。每个子系统是「一个 pure-function 模块（识别 / 分类 / 切片）+ 一个 storage 入口（如有持久化需求）+ 一个 adapter wiring 钩子（在 jvQuant 拉数后产出字段，在 mock 内置确定性数据）+ 0–N 个 MCP tool 暴露给 Hermes」。所有新字段加到 `SecondBoardCandidate`、`MarketEvent` 或新增独立模型，但保留向后兼容（默认 `unknown` / 空数据），让 P4 的 backfill / attribution / backtest 链路无须改动即可继续工作。

**Tech Stack:**
Python 3.11+, Pydantic v2, SQLite (versioned migration `m0005_data_extensions.py`), jvQuant semantic queries / 龙虎榜端点 / 分时回放（已在 P0/P2 接入，可复用），FastMCP server, pytest TDD.

---

## P5 范围对齐（来自 roadmap）

来自 `docs/superpowers/plans/2026-05-29-aegis-alpha-roadmap.md` 第 118-127 行：

- **A. 龙虎榜适配器** — 接 jvQuant 龙虎榜接口或外部源；落 `dragon_tiger_records` 表；`get_dragon_tiger(symbol, trading_day)` / `get_active_seats_today()` 工具；游资席位识别白名单（章盟主、孙哥、欢乐海岸、炒股养家等）。
- **B. 跌停池 / ST 板** — `get_limit_down_pool()` / `get_st_pool()`；`MARKET_BOTTOM_REVERSAL` 反向情绪事件（连续跌停股出现集体涨停 → 板块见底信号）。
- **C. 涨停原因细分** — 业绩 / 政策 / 题材 / 游资 4 类分类器；候选契约新增 `limitup_driver_type`。
- **D. 分时形态识别** — T 字板 / 一字板 / 烂板 / 平台突破 / 假突破；候选契约新增 `intraday_pattern`。
- **E. 资金流分时切片** — 首封前 5 分钟 / 开板后 1 分钟 / 尾盘 30 分钟的资金分流，存到 `capital_flow_slices`。

任务总数：22 个 task（21 个实现任务 + 1 个 docs 任务）。

## 强制约束（Subagent 实施时必须遵守）

读完每个任务再下笔。这些约束不可放弃：

1. **不允许真实交易、不允许写真实下单**。所有 P5 输出仅 read-only。
2. **不能私改 LLM 模型名**。`anthropic/claude-opus-4-7` 与 `deepseek-v4-pro` 名字保持原样（用户明确指示）。
3. **TDD 严格执行**：每个新函数 / 新方法 / 新 MCP 工具都要先写失败测试，再写实现。提交粒度 = 一次 RED → GREEN → COMMIT。
4. **保留向后兼容**：新增字段默认 `unknown` / `0.0` / `[]`，让 P0–P4 现有测试与候选构造逻辑无须修改即可继续通过。
5. **数据缺失时不要捏造**：jvQuant 没返回的字段，落 `unknown` / `placeholder`，并在 `data_quality` 里标 `confidence=placeholder` + `usable_for_grading=False`。
6. **席位 / 营业部白名单不要硬编码到代码**：放 `config/dragon_tiger_seats.yaml`，让用户后期能维护。
7. **跨子系统弱耦合**：A、B、C、D、E 必须能独立交付。一个子系统失败不能阻塞其他子系统。
8. **storage 调用 conn 时必须用 self._connect() context manager**：参考 `storage.py:930+` 的 P4 模式。
9. **MCP tool 调用 store 时必须用 `_call_store(lambda store: ...)`，调用 adapter 时必须用 `_call_tool(lambda adapter: ...)`**：参考 `mcp/server.py:557+`。
10. **新表的 `created_at` 在 upsert 时不要被覆盖**（P4 已踩过坑）：`ON CONFLICT DO UPDATE SET ...` 子句中不出现 `created_at`，让原值保留。
11. **任何 sub-agent worktree 必须 base 在 `main` 当前 HEAD**（仓库根 `.claude/settings.json` 已配 `worktree.baseRef = head`）。

## 文件结构（落盘前先看完）

### 新增

| Path | 责任 |
|------|------|
| `config/dragon_tiger_seats.yaml` | 游资席位白名单 + 营业部分类（个人游资 / 机构 / 知名游资），用户可维护。 |
| `src/aegis_alpha/extensions/__init__.py` | P5 子系统的命名空间。 |
| `src/aegis_alpha/extensions/dragon_tiger.py` | A. 解析 jvQuant 龙虎榜原始返回 → `DragonTigerRecord` + 席位匹配。 |
| `src/aegis_alpha/extensions/contrarian_pool.py` | B. 跌停池 / ST 池构造 + `MARKET_BOTTOM_REVERSAL` 事件触发器。 |
| `src/aegis_alpha/extensions/limitup_driver.py` | C. 涨停原因 4 分类纯函数（输入候选关键字段，输出 `LimitupDriverType`）。 |
| `src/aegis_alpha/extensions/intraday_pattern.py` | D. 形态识别纯函数（输入分钟回放 bars，输出 `IntradayPattern`）。 |
| `src/aegis_alpha/extensions/capital_flow_slices.py` | E. 资金分时切片纯函数 + storage helper。 |
| `src/aegis_alpha/db_migrations_files/m0005_data_extensions.py` | 新表迁移：`dragon_tiger_records`, `contrarian_pool_snapshots`, `capital_flow_slices`。 |
| `tests/extensions/test_dragon_tiger.py` | A 子系统纯函数单测。 |
| `tests/extensions/test_contrarian_pool.py` | B 子系统单测（含 `MARKET_BOTTOM_REVERSAL` 检测器）。 |
| `tests/extensions/test_limitup_driver.py` | C 子系统单测。 |
| `tests/extensions/test_intraday_pattern.py` | D 子系统单测。 |
| `tests/extensions/test_capital_flow_slices.py` | E 子系统单测（含 mock adapter 整合）。 |
| `tests/extensions/__init__.py` | 测试包标识空文件。 |
| `tests/test_p5_models.py` | 新模型 + Literal 校验单测。 |
| `tests/test_p5_storage.py` | 3 张新表 storage 方法单测。 |
| `tests/test_db_migrations_p5.py` | m0005 迁移成功 + index 存在断言。 |
| `tests/test_jvquant_candidates.py` | jvquant adapter 在 candidate 内接入 P5 字段的集成测试。 |
| `tests/test_mcp_p5_tools.py` | 5 个新 MCP tool 的 dict-shape 断言。 |

### 修改

| Path | 修改内容 |
|------|---------|
| `src/aegis_alpha/models.py` | 新增 7 个 Literal + 5 个 Pydantic 模型 + `SecondBoardCandidate` 增 2 个字段 + `MarketEventType` 增 1 个值。 |
| `src/aegis_alpha/protocols.py` | `MarketDataAdapter` 增 4 个新方法签名。 |
| `src/aegis_alpha/storage.py` | 增 7 个 storage 方法（save/get/list × 3 张新表）。 |
| `src/aegis_alpha/adapters/mock_market_data.py` | 增 4 个新方法 mock 实现 + 在候选构造里填 `limitup_driver_type` / `intraday_pattern`。 |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | 增 4 个新方法 jvQuant 实现（部分以 placeholder 起步）。 |
| `src/aegis_alpha/adapters/jvquant/candidates.py` | 在 `build_one_candidate` 注入 `limitup_driver_type` / `intraday_pattern` 计算。 |
| `src/aegis_alpha/mcp/server.py` | 注册 5 个新 MCP tool。 |
| `.hermes/config/aegis-alpha-mcp.yaml` | include 列表加 5 个新工具名。 |
| `README.md` | 「MCP Tools」章节追加 P5 工具与字段说明。 |
| `.hermes/skills/second-board-radar/SKILL.md` | Required Tools 加 5 个新工具，Workflow 注明何时使用。 |

---

## 子系统 A — 龙虎榜适配器（Tasks 1–5）

### Task 1: 数据模型与 Literal 类型

**Files:**
- Modify: `src/aegis_alpha/models.py`
- Test: `tests/test_p5_models.py`

- [ ] **Step 1: 写失败测试**

新增 `tests/test_p5_models.py` 中的测试函数（如果文件存在则追加；否则创建）：

```python
def test_dragon_tiger_record_minimal_construct():
    from aegis_alpha.models import DragonTigerRecord, DragonTigerSeat

    seat = DragonTigerSeat(
        seat_name="国泰君安证券深圳益田路荣超商务中心证券营业部",
        seat_type="hot_money_known",
        hot_money_alias="章盟主",
        buy_amount_cny=12_000_000.0,
        sell_amount_cny=2_000_000.0,
        net_amount_cny=10_000_000.0,
    )
    record = DragonTigerRecord(
        symbol="600519",
        name="贵州茅台",
        trading_day="2026-05-30",
        list_reason="日涨幅偏离值达 7%",
        total_buy_cny=50_000_000.0,
        total_sell_cny=20_000_000.0,
        net_amount_cny=30_000_000.0,
        seats=[seat],
        provider="mock",
        data_mode="mock",
        created_at="2026-05-30T15:30:00+08:00",
    )
    assert record.symbol == "600519"
    assert record.seats[0].hot_money_alias == "章盟主"
    assert record.seats[0].seat_type == "hot_money_known"
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py::test_dragon_tiger_record_minimal_construct -v`
Expected: FAIL with `ImportError: cannot import name 'DragonTigerRecord'`.

- [ ] **Step 3: 在 `models.py` Literal 区追加类型**

定位到现有 Literal 区（`models.py:8` 前后），插入：

```python
DragonTigerSeatType = Literal[
    "hot_money_known",
    "hot_money_unknown",
    "institution",
    "hk_connect",
    "retail_proxy",
    "unknown",
]
LimitupDriverType = Literal[
    "earnings",
    "policy",
    "theme",
    "hot_money",
    "unknown",
]
IntradayPattern = Literal[
    "one_word_board",
    "t_shape_board",
    "messy_board",
    "platform_breakout",
    "false_breakout",
    "normal",
    "unknown",
]
ContrarianPoolKind = Literal["limit_down", "st"]
CapitalFlowSliceWindow = Literal[
    "pre_first_seal_5m",
    "post_break_1m",
    "tail_30m",
]
```

- [ ] **Step 4: 在 `models.py` 末尾追加 Pydantic 模型**

```python
class DragonTigerSeat(BaseModel):
    seat_name: str
    seat_type: DragonTigerSeatType = "unknown"
    hot_money_alias: str = ""
    buy_amount_cny: float = 0.0
    sell_amount_cny: float = 0.0
    net_amount_cny: float = 0.0


class DragonTigerRecord(BaseModel):
    symbol: str
    name: str
    trading_day: str
    list_reason: str = ""
    total_buy_cny: float = 0.0
    total_sell_cny: float = 0.0
    net_amount_cny: float = 0.0
    seats: list[DragonTigerSeat] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
    created_at: str = ""


class ContrarianPoolEntry(BaseModel):
    symbol: str
    name: str
    pool_kind: ContrarianPoolKind
    trading_day: str
    consecutive_days: int = 0
    change_pct: float = 0.0
    notes: list[str] = Field(default_factory=list)


class CapitalFlowSlice(BaseModel):
    symbol: str
    trading_day: str
    window: CapitalFlowSliceWindow
    big_order_net_inflow_cny: float = 0.0
    main_capital_net_inflow_cny: float = 0.0
    retail_capital_net_inflow_cny: float = 0.0
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
    created_at: str = ""


class IntradayPatternFeatures(BaseModel):
    """形态识别中间产物，调试用，不直接暴露 MCP。"""
    pattern: IntradayPattern = "unknown"
    open_to_first_seal_minutes: int = 0
    break_count: int = 0
    sealed_at_open: bool = False
    closing_at_limit: bool = False
    high_to_close_drawdown_pct: float = 0.0
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py::test_dragon_tiger_record_minimal_construct -v`
Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/models.py tests/test_p5_models.py
git commit -m "Add P5 Pydantic models and Literal types"
```

---

### Task 2: 数据库迁移 m0005_data_extensions

**Files:**
- Create: `src/aegis_alpha/db_migrations_files/m0005_data_extensions.py`
- Create: `tests/test_db_migrations_p5.py`

仓库约定每个 P 阶段一份迁移测试文件（参考 `tests/test_db_migrations_p4.py`）。

- [ ] **Step 1: 写失败测试**

写入 `tests/test_db_migrations_p5.py`：

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p5_migration_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {
        "dragon_tiger_records",
        "contrarian_pool_snapshots",
        "capital_flow_slices",
    }.issubset(names)
    assert current_version(db) >= 5


def test_p5_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_dragon_tiger_day" in names
    assert "idx_dragon_tiger_symbol_day" in names
    assert "idx_contrarian_pool_day_kind" in names
    assert "idx_capital_flow_symbol_day" in names
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_db_migrations_p5.py -v`
Expected: FAIL — 新表不存在。

- [ ] **Step 3: 创建迁移文件**

写入 `src/aegis_alpha/db_migrations_files/m0005_data_extensions.py`：

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dragon_tiger_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            list_reason TEXT NOT NULL DEFAULT '',
            total_buy_cny REAL NOT NULL DEFAULT 0,
            total_sell_cny REAL NOT NULL DEFAULT 0,
            net_amount_cny REAL NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day)
        );
        CREATE INDEX IF NOT EXISTS idx_dragon_tiger_day
            ON dragon_tiger_records (trading_day);
        CREATE INDEX IF NOT EXISTS idx_dragon_tiger_symbol_day
            ON dragon_tiger_records (symbol, trading_day);

        CREATE TABLE IF NOT EXISTS contrarian_pool_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trading_day TEXT NOT NULL,
            pool_kind TEXT NOT NULL,
            symbol TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(trading_day, pool_kind, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_contrarian_pool_day_kind
            ON contrarian_pool_snapshots (trading_day, pool_kind);

        CREATE TABLE IF NOT EXISTS capital_flow_slices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            window TEXT NOT NULL,
            big_order_net_inflow_cny REAL NOT NULL DEFAULT 0,
            main_capital_net_inflow_cny REAL NOT NULL DEFAULT 0,
            retail_capital_net_inflow_cny REAL NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, trading_day, window)
        );
        CREATE INDEX IF NOT EXISTS idx_capital_flow_symbol_day
            ON capital_flow_slices (symbol, trading_day);
        """
    )
```

- [ ] **Step 4: 不需要手动注册迁移**

迁移由 `src/aegis_alpha/db_migrations.py` 通过 `pkgutil.iter_modules` 自动从 `db_migrations_files/` 包发现（命名模式 `m\d{4}_*.py`）。新增 `m0005_data_extensions.py` 后下次 `init_db` 会自动应用，无需修改 `__init__.py`。该步骤是空操作。

- [ ] **Step 5: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_db_migrations_p5.py -v`
Expected: PASS（2 个测试）。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/db_migrations_files/m0005_data_extensions.py \
    tests/test_db_migrations_p5.py
git commit -m "Add migration m0005: dragon_tiger / contrarian_pool / capital_flow_slices tables"
```

---

### Task 3: 龙虎榜席位白名单加载器

**Files:**
- Create: `config/dragon_tiger_seats.yaml`
- Create: `src/aegis_alpha/extensions/__init__.py`
- Create: `src/aegis_alpha/extensions/dragon_tiger.py`
- Create: `tests/extensions/__init__.py`
- Create: `tests/extensions/test_dragon_tiger.py`

- [ ] **Step 1: 写席位白名单 YAML**

写入 `config/dragon_tiger_seats.yaml`（仅起步白名单，用户后期补充）：

```yaml
version: 1
hot_money_known:
  - alias: 章盟主
    seat_match:
      - 国泰君安证券深圳益田路荣超商务中心证券营业部
      - 国泰君安证券股份有限公司深圳益田路荣超商务中心证券营业部
  - alias: 孙哥
    seat_match:
      - 财通证券股份有限公司绍兴营业部
      - 财通证券绍兴营业部
  - alias: 欢乐海岸
    seat_match:
      - 中信证券股份有限公司北京呼家楼证券营业部
      - 华泰证券股份有限公司北京中关村大街证券营业部
  - alias: 炒股养家
    seat_match:
      - 中投证券股份有限公司温州第一桥证券营业部
      - 中国中投证券有限责任公司温州第一桥证券营业部
institution_keywords:
  - 机构专用
  - 沪股通专用
  - 深股通专用
hk_connect_keywords:
  - 沪股通
  - 深股通
```

- [ ] **Step 2: 写失败测试**

写入 `tests/extensions/__init__.py`（空文件）。然后写入 `tests/extensions/test_dragon_tiger.py`：

```python
import pathlib

from aegis_alpha.extensions.dragon_tiger import (
    classify_seat,
    load_seat_whitelist,
    parse_dragon_tiger_payload,
)


CONFIG_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "dragon_tiger_seats.yaml"


def test_load_whitelist_known_alias():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    classification = classify_seat(
        "国泰君安证券深圳益田路荣超商务中心证券营业部",
        whitelist,
    )
    assert classification == ("hot_money_known", "章盟主")


def test_classify_institution_seat():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("机构专用", whitelist)
    assert seat_type == "institution"
    assert alias == ""


def test_classify_unknown_seat_falls_back_to_hot_money_unknown():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("某营业部", whitelist)
    assert seat_type == "hot_money_unknown"
    assert alias == ""


def test_parse_dragon_tiger_payload_extracts_top_seats():
    raw = {
        "symbol": "600519",
        "name": "贵州茅台",
        "trading_day": "2026-05-30",
        "list_reason": "日涨幅偏离值达 7%",
        "buy_seats": [
            {"seat_name": "国泰君安证券深圳益田路荣超商务中心证券营业部", "amount": 12000000},
            {"seat_name": "机构专用", "amount": 8000000},
        ],
        "sell_seats": [
            {"seat_name": "某营业部", "amount": 5000000},
        ],
    }
    record = parse_dragon_tiger_payload(
        raw, whitelist=load_seat_whitelist(str(CONFIG_PATH)), provider="mock"
    )
    assert record.symbol == "600519"
    assert record.total_buy_cny == 20_000_000.0
    assert record.total_sell_cny == 5_000_000.0
    assert record.net_amount_cny == 15_000_000.0
    assert {s.seat_type for s in record.seats} == {
        "hot_money_known",
        "institution",
        "hot_money_unknown",
    }
    aliases = {s.hot_money_alias for s in record.seats if s.hot_money_alias}
    assert "章盟主" in aliases
```

- [ ] **Step 3: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py -v`
Expected: FAIL — `ImportError: No module named 'aegis_alpha.extensions'`.

- [ ] **Step 4: 写实现**

写入 `src/aegis_alpha/extensions/__init__.py`（一行 docstring）：

```python
"""P5 data extensions: dragon-tiger, contrarian pool, drivers, patterns, capital flow."""
```

写入 `src/aegis_alpha/extensions/dragon_tiger.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    DragonTigerRecord,
    DragonTigerSeat,
    DragonTigerSeatType,
)


@dataclass(frozen=True)
class HotMoneyEntry:
    alias: str
    seat_match: tuple[str, ...]


@dataclass(frozen=True)
class SeatWhitelist:
    hot_money: tuple[HotMoneyEntry, ...]
    institution_keywords: tuple[str, ...]
    hk_connect_keywords: tuple[str, ...]


def load_seat_whitelist(config_path: str) -> SeatWhitelist:
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    hot_money_raw = raw.get("hot_money_known") or []
    hot_money = tuple(
        HotMoneyEntry(
            alias=str(item.get("alias", "")).strip(),
            seat_match=tuple(str(s).strip() for s in (item.get("seat_match") or [])),
        )
        for item in hot_money_raw
        if item.get("alias")
    )
    institution_keywords = tuple(
        str(k).strip() for k in (raw.get("institution_keywords") or []) if str(k).strip()
    )
    hk_connect_keywords = tuple(
        str(k).strip() for k in (raw.get("hk_connect_keywords") or []) if str(k).strip()
    )
    return SeatWhitelist(
        hot_money=hot_money,
        institution_keywords=institution_keywords,
        hk_connect_keywords=hk_connect_keywords,
    )


def classify_seat(
    seat_name: str, whitelist: SeatWhitelist
) -> tuple[DragonTigerSeatType, str]:
    name = (seat_name or "").strip()
    if not name:
        return "unknown", ""
    for entry in whitelist.hot_money:
        for match in entry.seat_match:
            if match and match in name:
                return "hot_money_known", entry.alias
    for keyword in whitelist.hk_connect_keywords:
        if keyword and keyword in name:
            return "hk_connect", ""
    for keyword in whitelist.institution_keywords:
        if keyword and keyword in name:
            return "institution", ""
    return "hot_money_unknown", ""


def _safe_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_dragon_tiger_payload(
    raw: dict[str, Any],
    *,
    whitelist: SeatWhitelist,
    provider: str = "mock",
    data_mode: str = "mock",
) -> DragonTigerRecord:
    symbol = str(raw.get("symbol", "")).strip()
    name = str(raw.get("name", "")).strip()
    trading_day = str(raw.get("trading_day", "")).strip()
    list_reason = str(raw.get("list_reason", "")).strip()

    buy_rows = raw.get("buy_seats") or []
    sell_rows = raw.get("sell_seats") or []

    seats: list[DragonTigerSeat] = []
    total_buy = 0.0
    total_sell = 0.0
    for row in buy_rows:
        amount = _safe_float(row.get("amount"))
        seat_type, alias = classify_seat(str(row.get("seat_name", "")), whitelist)
        seats.append(
            DragonTigerSeat(
                seat_name=str(row.get("seat_name", "")),
                seat_type=seat_type,
                hot_money_alias=alias,
                buy_amount_cny=amount,
                sell_amount_cny=0.0,
                net_amount_cny=amount,
            )
        )
        total_buy += amount
    for row in sell_rows:
        amount = _safe_float(row.get("amount"))
        seat_type, alias = classify_seat(str(row.get("seat_name", "")), whitelist)
        seats.append(
            DragonTigerSeat(
                seat_name=str(row.get("seat_name", "")),
                seat_type=seat_type,
                hot_money_alias=alias,
                buy_amount_cny=0.0,
                sell_amount_cny=amount,
                net_amount_cny=-amount,
            )
        )
        total_sell += amount

    return DragonTigerRecord(
        symbol=symbol,
        name=name,
        trading_day=trading_day,
        list_reason=list_reason,
        total_buy_cny=total_buy,
        total_sell_cny=total_sell,
        net_amount_cny=total_buy - total_sell,
        seats=seats,
        provider=provider,
        data_mode=data_mode,
        created_at=now_iso(),
    )
```

- [ ] **Step 5: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py -v`
Expected: PASS（4 个测试）。

- [ ] **Step 6: 提交**

```bash
git add config/dragon_tiger_seats.yaml \
    src/aegis_alpha/extensions/__init__.py \
    src/aegis_alpha/extensions/dragon_tiger.py \
    tests/extensions/__init__.py \
    tests/extensions/test_dragon_tiger.py
git commit -m "Add dragon-tiger seat whitelist + parse_dragon_tiger_payload"
```

---

### Task 4: 龙虎榜 storage 与 adapter 接入

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Test: `tests/test_p5_storage.py`, `tests/extensions/test_dragon_tiger.py`

- [ ] **Step 1: 写失败测试 — storage**

追加到 `tests/test_p5_storage.py`：

```python
def test_save_and_get_dragon_tiger_record(tmp_path):
    from aegis_alpha.models import DragonTigerRecord, DragonTigerSeat
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "dt.db"))
    store.init_db()

    record = DragonTigerRecord(
        symbol="600519",
        name="贵州茅台",
        trading_day="2026-05-30",
        list_reason="日涨幅偏离 7%",
        total_buy_cny=20_000_000.0,
        total_sell_cny=5_000_000.0,
        net_amount_cny=15_000_000.0,
        seats=[
            DragonTigerSeat(
                seat_name="国泰君安证券深圳益田路荣超商务中心证券营业部",
                seat_type="hot_money_known",
                hot_money_alias="章盟主",
                buy_amount_cny=12_000_000.0,
                sell_amount_cny=0.0,
                net_amount_cny=12_000_000.0,
            )
        ],
        provider="jvquant",
        data_mode="real",
        created_at="2026-05-30T15:30:00+08:00",
    )
    store.save_dragon_tiger(record)
    fetched = store.get_dragon_tiger("600519", "2026-05-30")
    assert fetched is not None
    assert fetched.net_amount_cny == 15_000_000.0
    assert fetched.seats[0].hot_money_alias == "章盟主"


def test_list_active_seats_today_aggregates_known_aliases(tmp_path):
    from aegis_alpha.models import DragonTigerRecord, DragonTigerSeat
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "dt2.db"))
    store.init_db()

    seat_a = DragonTigerSeat(
        seat_name="A", seat_type="hot_money_known", hot_money_alias="章盟主",
        buy_amount_cny=10_000_000.0, sell_amount_cny=0.0, net_amount_cny=10_000_000.0,
    )
    seat_b = DragonTigerSeat(
        seat_name="B", seat_type="hot_money_known", hot_money_alias="章盟主",
        buy_amount_cny=5_000_000.0, sell_amount_cny=0.0, net_amount_cny=5_000_000.0,
    )
    store.save_dragon_tiger(
        DragonTigerRecord(
            symbol="600519", name="贵州茅台", trading_day="2026-05-30",
            total_buy_cny=10_000_000.0, total_sell_cny=0.0, net_amount_cny=10_000_000.0,
            seats=[seat_a], provider="mock", data_mode="mock", created_at="t",
        )
    )
    store.save_dragon_tiger(
        DragonTigerRecord(
            symbol="000001", name="平安银行", trading_day="2026-05-30",
            total_buy_cny=5_000_000.0, total_sell_cny=0.0, net_amount_cny=5_000_000.0,
            seats=[seat_b], provider="mock", data_mode="mock", created_at="t",
        )
    )
    rows = store.list_active_seats_today("2026-05-30")
    aliases = {row["hot_money_alias"]: row for row in rows}
    assert "章盟主" in aliases
    assert aliases["章盟主"]["symbol_count"] == 2
    assert aliases["章盟主"]["total_net_buy_cny"] == 15_000_000.0
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_storage.py -k dragon_tiger -v`
Expected: FAIL — 方法不存在。

- [ ] **Step 3: 实现 storage 方法**

打开 `src/aegis_alpha/storage.py`，先在文件顶端 import 区追加：

```python
from aegis_alpha.models import (
    DragonTigerRecord,
    # ... existing imports ...
)
```

在 `save_backtest_run` 前后追加方法（保持 alpha 顺序非强制，按 P4 邻近原则即可）：

```python
def save_dragon_tiger(self, record: DragonTigerRecord) -> None:
    with self._connect() as conn:
        conn.execute(
            """
            INSERT INTO dragon_tiger_records (
                symbol, trading_day, list_reason,
                total_buy_cny, total_sell_cny, net_amount_cny,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, trading_day) DO UPDATE SET
                list_reason = excluded.list_reason,
                total_buy_cny = excluded.total_buy_cny,
                total_sell_cny = excluded.total_sell_cny,
                net_amount_cny = excluded.net_amount_cny,
                payload_json = excluded.payload_json
            """,
            (
                record.symbol,
                record.trading_day,
                record.list_reason,
                record.total_buy_cny,
                record.total_sell_cny,
                record.net_amount_cny,
                record.model_dump_json(),
                record.created_at,
            ),
        )

def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord | None:
    with self._connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM dragon_tiger_records "
            "WHERE symbol = ? AND trading_day = ?",
            (symbol, trading_day),
        ).fetchone()
    return DragonTigerRecord.model_validate_json(row[0]) if row else None

def list_active_seats_today(self, trading_day: str) -> list[dict]:
    """Aggregate net buy by hot_money_alias for one trading day."""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM dragon_tiger_records WHERE trading_day = ?",
            (trading_day,),
        ).fetchall()

    aggregated: dict[str, dict] = {}
    for row in rows:
        record = DragonTigerRecord.model_validate_json(row[0])
        for seat in record.seats:
            if seat.seat_type != "hot_money_known" or not seat.hot_money_alias:
                continue
            entry = aggregated.setdefault(
                seat.hot_money_alias,
                {
                    "hot_money_alias": seat.hot_money_alias,
                    "symbol_count": 0,
                    "total_net_buy_cny": 0.0,
                    "symbols": [],
                },
            )
            if record.symbol not in entry["symbols"]:
                entry["symbols"].append(record.symbol)
                entry["symbol_count"] += 1
            entry["total_net_buy_cny"] += seat.net_amount_cny
    return sorted(
        aggregated.values(),
        key=lambda x: x["total_net_buy_cny"],
        reverse=True,
    )
```

- [ ] **Step 4: 跑 storage 测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_storage.py -k dragon_tiger -v`
Expected: PASS。

- [ ] **Step 5: 写 protocol + adapter 测试（先 RED）**

追加到 `tests/extensions/test_dragon_tiger.py`：

```python
def test_mock_adapter_returns_deterministic_dragon_tiger():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    record = adapter.get_dragon_tiger("600519", "2026-05-30")
    assert record.symbol == "600519"
    assert record.trading_day == "2026-05-30"
    assert record.data_mode == "mock"
    assert len(record.seats) >= 1


def test_mock_adapter_active_seats_today_non_empty():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    rows = adapter.get_active_seats_today("2026-05-30")
    assert isinstance(rows, list)
    assert all("hot_money_alias" in r for r in rows)
```

- [ ] **Step 6: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py -k mock_adapter -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_dragon_tiger'`。

- [ ] **Step 7: 在 `protocols.py` 新增方法签名**

在 `MarketDataAdapter` Protocol 类内（`get_history_stats` 之后）添加：

```python
def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord: ...

def get_active_seats_today(self, trading_day: str) -> list[dict[str, Any]]: ...
```

并在文件顶 import 添加：

```python
from aegis_alpha.models import (
    # ... existing ...
    DragonTigerRecord,
    # ... existing ...
)
```

- [ ] **Step 8: 实现 mock adapter**

在 `src/aegis_alpha/adapters/mock_market_data.py` 末尾追加：

```python
def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord:
    seat = DragonTigerSeat(
        seat_name="国泰君安证券深圳益田路荣超商务中心证券营业部",
        seat_type="hot_money_known",
        hot_money_alias="章盟主",
        buy_amount_cny=12_000_000.0,
        sell_amount_cny=2_000_000.0,
        net_amount_cny=10_000_000.0,
    )
    return DragonTigerRecord(
        symbol=symbol,
        name=f"mock-{symbol}",
        trading_day=trading_day,
        list_reason="日涨幅偏离值达 7%",
        total_buy_cny=12_000_000.0,
        total_sell_cny=2_000_000.0,
        net_amount_cny=10_000_000.0,
        seats=[seat],
        provider="mock",
        data_mode="mock",
        created_at="2026-05-30T15:30:00+08:00",
    )

def get_active_seats_today(self, trading_day: str) -> list[dict]:
    return [
        {
            "hot_money_alias": "章盟主",
            "symbol_count": 1,
            "total_net_buy_cny": 10_000_000.0,
            "symbols": ["600519"],
        }
    ]
```

并把所需 import 加到 `mock_market_data.py` 顶部：

```python
from aegis_alpha.models import (
    # ... existing ...
    DragonTigerRecord,
    DragonTigerSeat,
)
```

- [ ] **Step 9: 实现 jvquant adapter（暂用 placeholder）**

打开 `src/aegis_alpha/adapters/jvquant/adapter.py`，类内追加：

```python
def get_dragon_tiger(self, symbol: str, trading_day: str) -> DragonTigerRecord:
    # P5 starter: jvQuant 龙虎榜端点尚未对齐契约，先返回 placeholder 记录。
    # 真实接入在 P5 Wave 2 单独 issue 内完成（参考 docs/JVQUANT_OFFICIAL_INDEX.md）。
    return DragonTigerRecord(
        symbol=symbol,
        name="",
        trading_day=trading_day,
        list_reason="placeholder: jvQuant dragon-tiger endpoint not wired",
        total_buy_cny=0.0,
        total_sell_cny=0.0,
        net_amount_cny=0.0,
        seats=[],
        provider="jvquant",
        data_mode="placeholder",
        created_at=now_iso(),
    )

def get_active_seats_today(self, trading_day: str) -> list[dict]:
    return []
```

并在文件顶 import 添加：`from aegis_alpha.models import DragonTigerRecord` 与 `from aegis_alpha.clock import now_iso`（若尚未导入）。

- [ ] **Step 10: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_dragon_tiger.py -v`
Expected: PASS（前 4 个 + 新加的 2 个 = 6 个测试）。

- [ ] **Step 11: 提交**

```bash
git add src/aegis_alpha/storage.py src/aegis_alpha/protocols.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py \
    tests/test_p5_storage.py tests/extensions/test_dragon_tiger.py
git commit -m "Wire dragon-tiger storage + adapter methods (mock complete, jvquant placeholder)"
```

---

### Task 5: 龙虎榜 MCP 工具 + skill

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p5_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p5_tools.py`：

```python
def test_get_dragon_tiger_tool_returns_dict():
    from aegis_alpha.mcp.server import get_dragon_tiger

    result = get_dragon_tiger("600519", "2026-05-30")
    assert isinstance(result, dict)
    assert result.get("symbol") == "600519"
    assert "seats" in result


def test_get_active_seats_today_tool_returns_list():
    from aegis_alpha.mcp.server import get_active_seats_today

    result = get_active_seats_today("2026-05-30")
    assert isinstance(result, list)
    if result:
        assert "hot_money_alias" in result[0]
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k dragon_tiger -v`
Expected: FAIL — `ImportError: cannot import name 'get_dragon_tiger'`。

- [ ] **Step 3: 实现 MCP tool**

打开 `src/aegis_alpha/mcp/server.py`，在 `get_recent_backtests` 之前追加：

```python
@mcp.tool
def get_dragon_tiger(symbol: str, trading_day: str) -> dict:
    """Return one symbol's dragon-tiger record for the given day (mock or jvquant placeholder)."""
    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable", "error": "symbol and trading_day are required"}
    return _call_tool(lambda adapter: adapter.get_dragon_tiger(safe_symbol, safe_day).model_dump())


@mcp.tool
def get_active_seats_today(trading_day: str) -> list[dict] | dict:
    """Aggregate hot-money seats by alias for a single trading day."""
    safe_day = trading_day.strip()
    if not safe_day:
        return {"data_mode": "unavailable", "error": "trading_day is required"}
    return _call_tool(lambda adapter: adapter.get_active_seats_today(safe_day))
```

- [ ] **Step 4: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k dragon_tiger -v`
Expected: PASS。

- [ ] **Step 5: 把工具名加到 MCP config include 列表**

修改 `.hermes/config/aegis-alpha-mcp.yaml`，在 `include:` 列表中增加（合适位置即可）：

```yaml
        - get_dragon_tiger
        - get_active_seats_today
```

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p5_tools.py
git commit -m "Expose dragon-tiger MCP tools: get_dragon_tiger, get_active_seats_today"
```

---

## 子系统 B — 跌停池 / ST 池 + 反向情绪事件（Tasks 6–9）

### Task 6: 反向池模型与 storage

**Files:**
- Modify: `src/aegis_alpha/models.py`（已在 Task 1 加 `ContrarianPoolEntry` / `ContrarianPoolKind`）
- Modify: `src/aegis_alpha/storage.py`
- Test: `tests/test_p5_storage.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_p5_storage.py`：

```python
def test_save_and_list_contrarian_pool(tmp_path):
    from aegis_alpha.models import ContrarianPoolEntry
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "cp.db"))
    store.init_db()

    entry_a = ContrarianPoolEntry(
        symbol="000001", name="A", pool_kind="limit_down", trading_day="2026-05-30",
        consecutive_days=2, change_pct=-9.95, notes=["跌停"],
    )
    entry_b = ContrarianPoolEntry(
        symbol="000002", name="B", pool_kind="st", trading_day="2026-05-30",
        consecutive_days=0, change_pct=4.95, notes=["ST 涨停"],
    )
    store.save_contrarian_pool_entry(entry_a, created_at="t1")
    store.save_contrarian_pool_entry(entry_b, created_at="t2")

    limit_down = store.list_contrarian_pool("2026-05-30", pool_kind="limit_down")
    assert len(limit_down) == 1
    assert limit_down[0].symbol == "000001"

    everything = store.list_contrarian_pool("2026-05-30")
    assert {e.symbol for e in everything} == {"000001", "000002"}
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_storage.py -k contrarian -v`
Expected: FAIL.

- [ ] **Step 3: 实现 storage**

打开 `storage.py`，import 区追加：

```python
from aegis_alpha.models import (
    # ... existing ...
    ContrarianPoolEntry,
)
```

类内追加：

```python
def save_contrarian_pool_entry(
    self, entry: ContrarianPoolEntry, *, created_at: str
) -> None:
    with self._connect() as conn:
        conn.execute(
            """
            INSERT INTO contrarian_pool_snapshots (
                trading_day, pool_kind, symbol, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(trading_day, pool_kind, symbol) DO UPDATE SET
                payload_json = excluded.payload_json
            """,
            (
                entry.trading_day,
                entry.pool_kind,
                entry.symbol,
                entry.model_dump_json(),
                created_at,
            ),
        )

def list_contrarian_pool(
    self, trading_day: str, *, pool_kind: str = ""
) -> list[ContrarianPoolEntry]:
    clauses = ["trading_day = ?"]
    params: list[object] = [trading_day]
    if pool_kind:
        clauses.append("pool_kind = ?")
        params.append(pool_kind)
    query = (
        "SELECT payload_json FROM contrarian_pool_snapshots WHERE "
        + " AND ".join(clauses)
        + " ORDER BY symbol ASC"
    )
    with self._connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [ContrarianPoolEntry.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_storage.py -k contrarian -v`
Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/storage.py tests/test_p5_storage.py
git commit -m "Add contrarian_pool_snapshots storage methods"
```

---

### Task 7: 反向池 adapter wiring（mock + jvquant placeholder）

**Files:**
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Test: `tests/extensions/test_contrarian_pool.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/extensions/test_contrarian_pool.py`：

```python
def test_mock_adapter_get_limit_down_pool_returns_entries():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    pool = adapter.get_limit_down_pool("2026-05-30")
    assert isinstance(pool, list)
    assert all(entry.pool_kind == "limit_down" for entry in pool)
    assert all(entry.change_pct < 0 for entry in pool)


def test_mock_adapter_get_st_pool_returns_entries():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    pool = adapter.get_st_pool("2026-05-30")
    assert all(entry.pool_kind == "st" for entry in pool)


def test_jvquant_adapter_returns_empty_pool_when_unwired():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    # 不调真实构造器，避免依赖 jvQuant token；只验证两方法存在并返回 []。
    assert adapter.get_limit_down_pool("2026-05-30") == []
    assert adapter.get_st_pool("2026-05-30") == []
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_contrarian_pool.py -v`
Expected: FAIL.

- [ ] **Step 3: 在 `protocols.py` 增 2 个方法**

类内追加：

```python
def get_limit_down_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]: ...

def get_st_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]: ...
```

import 增 `ContrarianPoolEntry`。

- [ ] **Step 4: 实现 mock adapter**

在 `mock_market_data.py` 顶部 import 增 `ContrarianPoolEntry`，类末追加：

```python
def get_limit_down_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
    day = trading_day or "2026-05-30"
    return [
        ContrarianPoolEntry(
            symbol="000099", name="mock-跌停-1", pool_kind="limit_down",
            trading_day=day, consecutive_days=2, change_pct=-9.95,
            notes=["mock 数据"],
        ),
        ContrarianPoolEntry(
            symbol="000100", name="mock-跌停-2", pool_kind="limit_down",
            trading_day=day, consecutive_days=1, change_pct=-9.97,
            notes=["mock 数据"],
        ),
    ]

def get_st_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
    day = trading_day or "2026-05-30"
    return [
        ContrarianPoolEntry(
            symbol="900998", name="mock-ST-1", pool_kind="st",
            trading_day=day, consecutive_days=0, change_pct=4.92,
            notes=["mock ST"],
        ),
    ]
```

- [ ] **Step 5: 实现 jvquant adapter（placeholder）**

`adapters/jvquant/adapter.py` 类内追加：

```python
def get_limit_down_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
    # P5 starter: 跌停池 semantic query 尚未确定字段映射，先返回空列表。
    return []

def get_st_pool(self, trading_day: str = "") -> list[ContrarianPoolEntry]:
    # P5 starter: ST 池接入待 jvQuant 字段确认。
    return []
```

并在 import 增 `ContrarianPoolEntry`。

- [ ] **Step 6: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_contrarian_pool.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add src/aegis_alpha/protocols.py src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py tests/extensions/test_contrarian_pool.py
git commit -m "Wire limit_down / st pool adapter methods (mock complete, jvquant placeholder)"
```

---

### Task 8: MARKET_BOTTOM_REVERSAL 事件检测器

**Files:**
- Modify: `src/aegis_alpha/models.py`（`MarketEventType` Literal 加值）
- Create: `src/aegis_alpha/extensions/contrarian_pool.py`
- Test: `tests/extensions/test_contrarian_pool.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/extensions/test_contrarian_pool.py`：

```python
def test_market_bottom_reversal_event_triggered_on_3plus_recovers():
    from aegis_alpha.models import ContrarianPoolEntry
    from aegis_alpha.extensions.contrarian_pool import detect_bottom_reversal

    today = [
        ContrarianPoolEntry(symbol=f"00010{i}", name=f"r{i}",
                            pool_kind="limit_down", trading_day="2026-05-30",
                            consecutive_days=2, change_pct=9.95)
        for i in range(3)
    ]
    yesterday_pool_symbols = {f"00010{i}" for i in range(5)}
    event = detect_bottom_reversal(
        today_recovered_symbols=[e.symbol for e in today],
        yesterday_limit_down_symbols=yesterday_pool_symbols,
        trading_day="2026-05-30",
    )
    assert event is not None
    assert event.event_type == "MARKET_BOTTOM_REVERSAL"
    assert event.score >= 60
    assert "recovered_count=3" in " ".join(event.evidence)


def test_market_bottom_reversal_event_skipped_below_threshold():
    from aegis_alpha.extensions.contrarian_pool import detect_bottom_reversal

    event = detect_bottom_reversal(
        today_recovered_symbols=["000101"],
        yesterday_limit_down_symbols={"000101", "000102"},
        trading_day="2026-05-30",
    )
    assert event is None
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_contrarian_pool.py -k bottom_reversal -v`
Expected: FAIL — module not found.

- [ ] **Step 3: 把 `MARKET_BOTTOM_REVERSAL` 加到 `MarketEventType` Literal**

修改 `models.py:30-37` 现有的 `MarketEventType`：

```python
MarketEventType = Literal[
    "THEME_CLUSTER_RISING",
    "APPROACHING_LIMIT_UP",
    "SEAL_ORDER_DECAY",
    "BIG_ORDER_INFLOW_SPIKE",
    "SECOND_BOARD_CANDIDATE_REPRICE",
    "THEME_DIVERGENCE",
    "MARKET_BOTTOM_REVERSAL",
]
```

- [ ] **Step 4: 实现检测器**

写入 `src/aegis_alpha/extensions/contrarian_pool.py`：

```python
from __future__ import annotations

import hashlib
from typing import Iterable

from aegis_alpha.clock import now_iso
from aegis_alpha.models import MarketEvent


_RECOVERY_THRESHOLD = 3  # 至少 3 只昨日跌停股今日 reverse 涨停才触发反向情绪事件
_MAX_SCORE = 100.0


def _event_id(trading_day: str, symbols: Iterable[str]) -> str:
    seed = "MARKET_BOTTOM_REVERSAL|" + trading_day + "|" + ",".join(sorted(symbols))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def detect_bottom_reversal(
    *,
    today_recovered_symbols: list[str],
    yesterday_limit_down_symbols: set[str],
    trading_day: str,
) -> MarketEvent | None:
    """When N>=_RECOVERY_THRESHOLD yesterday-limit-down stocks limit-up today,
    publish a MARKET_BOTTOM_REVERSAL event."""
    matched = [s for s in today_recovered_symbols if s in yesterday_limit_down_symbols]
    if len(matched) < _RECOVERY_THRESHOLD:
        return None
    score = min(_MAX_SCORE, 50.0 + 10.0 * len(matched))
    timestamp = now_iso()
    return MarketEvent(
        event_id=_event_id(trading_day, matched),
        event_type="MARKET_BOTTOM_REVERSAL",
        symbol="",
        name="",
        theme="contrarian",
        confidence="medium",
        score=score,
        evidence=[
            f"recovered_count={len(matched)}",
            f"sample_symbols={','.join(matched[:5])}",
        ],
        provider_timestamp=timestamp,
        received_at=timestamp,
        freshness_status="fresh",
        suggested_agent_action=[
            "explain context only; do not chase boards on reversal day",
            "treat as defensive market-wide signal, not single-stock trigger",
        ],
        data={"trading_day": trading_day, "recovered_symbols": matched},
    )
```

- [ ] **Step 5: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_contrarian_pool.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/models.py src/aegis_alpha/extensions/contrarian_pool.py \
    tests/extensions/test_contrarian_pool.py
git commit -m "Add MARKET_BOTTOM_REVERSAL detector + event type"
```

---

### Task 9: 反向池 MCP 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p5_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p5_tools.py`：

```python
def test_get_limit_down_pool_returns_list():
    from aegis_alpha.mcp.server import get_limit_down_pool

    rows = get_limit_down_pool("2026-05-30")
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["pool_kind"] == "limit_down"


def test_get_st_pool_returns_list():
    from aegis_alpha.mcp.server import get_st_pool

    rows = get_st_pool("2026-05-30")
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["pool_kind"] == "st"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k "limit_down_pool or st_pool" -v`
Expected: FAIL。

- [ ] **Step 3: 实现 MCP tool**

在 `mcp/server.py` `get_active_seats_today` 之后追加：

```python
@mcp.tool
def get_limit_down_pool(trading_day: str = "") -> list[dict]:
    """Return today's limit-down stocks (contrarian pool)."""
    safe_day = trading_day.strip()
    return _call_tool(
        lambda adapter: [e.model_dump() for e in adapter.get_limit_down_pool(safe_day)]
    )


@mcp.tool
def get_st_pool(trading_day: str = "") -> list[dict]:
    """Return today's ST stocks active today."""
    safe_day = trading_day.strip()
    return _call_tool(
        lambda adapter: [e.model_dump() for e in adapter.get_st_pool(safe_day)]
    )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k "limit_down_pool or st_pool" -v`
Expected: PASS。

- [ ] **Step 5: 把工具名加到 MCP config include 列表**

在 `.hermes/config/aegis-alpha-mcp.yaml` 的 `include:` 列表追加：

```yaml
        - get_limit_down_pool
        - get_st_pool
```

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p5_tools.py
git commit -m "Expose contrarian pool MCP tools: get_limit_down_pool, get_st_pool"
```

---

## 子系统 C — 涨停原因细分（Tasks 10–12）

### Task 10: 涨停原因 4 分类纯函数

**Files:**
- Create: `src/aegis_alpha/extensions/limitup_driver.py`
- Test: `tests/extensions/test_limitup_driver.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/extensions/test_limitup_driver.py`：

```python
from aegis_alpha.extensions.limitup_driver import classify_limitup_driver, LimitupDriverInputs


def _inputs(**overrides):
    base = dict(
        symbol="600519",
        concept_tags=[],
        topic_tags=[],
        list_reason="",
        net_amount_cny=0.0,
        previous_consecutive_boards=0,
        recent_earnings_surprise=False,
        recent_policy_keywords=[],
    )
    base.update(overrides)
    return LimitupDriverInputs(**base)


def test_earnings_driver_when_recent_surprise():
    out = classify_limitup_driver(_inputs(recent_earnings_surprise=True))
    assert out == "earnings"


def test_policy_driver_when_topic_matches_policy_keyword():
    out = classify_limitup_driver(_inputs(topic_tags=["国务院发布", "新基建"]))
    assert out == "policy"


def test_hot_money_driver_when_dragon_tiger_net_buy_and_no_policy():
    out = classify_limitup_driver(
        _inputs(
            net_amount_cny=15_000_000.0,
            previous_consecutive_boards=2,
        )
    )
    assert out == "hot_money"


def test_theme_driver_default_when_concept_tags_present():
    out = classify_limitup_driver(_inputs(concept_tags=["AI", "机器人"]))
    assert out == "theme"


def test_unknown_driver_when_nothing_matches():
    out = classify_limitup_driver(_inputs())
    assert out == "unknown"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_limitup_driver.py -v`
Expected: FAIL.

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/extensions/limitup_driver.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field

from aegis_alpha.models import LimitupDriverType


_POLICY_KEYWORDS: tuple[str, ...] = (
    "国务院",
    "国务院发布",
    "中央",
    "国家发改委",
    "工信部",
    "财政部",
    "证监会",
    "新基建",
    "十四五",
    "十五五",
    "政策",
    "补贴",
    "顶层设计",
)
_HOT_MONEY_NET_BUY_THRESHOLD = 10_000_000.0


@dataclass(frozen=True)
class LimitupDriverInputs:
    symbol: str
    concept_tags: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    list_reason: str = ""
    net_amount_cny: float = 0.0
    previous_consecutive_boards: int = 0
    recent_earnings_surprise: bool = False
    recent_policy_keywords: list[str] = field(default_factory=list)


def _hits_any(items: list[str], keywords: tuple[str, ...]) -> bool:
    if not items:
        return False
    bag = " ".join(str(s) for s in items if s)
    return any(kw and kw in bag for kw in keywords)


def classify_limitup_driver(inputs: LimitupDriverInputs) -> LimitupDriverType:
    """Classify the driver of a limit-up event into 4 buckets:
    earnings / policy / theme / hot_money. Returns 'unknown' when no rule matches."""
    if inputs.recent_earnings_surprise:
        return "earnings"
    if (
        _hits_any(inputs.topic_tags, _POLICY_KEYWORDS)
        or _hits_any(inputs.concept_tags, _POLICY_KEYWORDS)
        or any(kw in inputs.list_reason for kw in _POLICY_KEYWORDS)
        or inputs.recent_policy_keywords
    ):
        return "policy"
    if (
        inputs.net_amount_cny >= _HOT_MONEY_NET_BUY_THRESHOLD
        and inputs.previous_consecutive_boards >= 1
    ):
        return "hot_money"
    if inputs.concept_tags or inputs.topic_tags:
        return "theme"
    return "unknown"
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_limitup_driver.py -v`
Expected: PASS（5 个测试）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/extensions/limitup_driver.py tests/extensions/test_limitup_driver.py
git commit -m "Add limit-up driver 4-class classifier"
```

---

### Task 11: 候选契约接入 limitup_driver_type

**Files:**
- Modify: `src/aegis_alpha/models.py`（`SecondBoardCandidate` 加字段）
- Modify: `src/aegis_alpha/adapters/jvquant/candidates.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Test: `tests/test_jvquant_candidates.py`, `tests/test_mock_adapter.py`

- [ ] **Step 1: 写失败测试 — mock contract**

追加到 `tests/test_mock_adapter.py`（已存在）：

```python
def test_mock_second_board_candidate_includes_limitup_driver_type():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    assert candidates, "mock should return at least one candidate"
    for cand in candidates:
        assert hasattr(cand, "limitup_driver_type")
        assert cand.limitup_driver_type in {"earnings", "policy", "theme", "hot_money", "unknown"}
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k limitup_driver -v`
Expected: FAIL（字段不存在）。

- [ ] **Step 3: 在 `SecondBoardCandidate` 模型加字段**

打开 `models.py`，在 `SecondBoardCandidate` 类内（`grade_reason` 之前）新增：

```python
limitup_driver_type: LimitupDriverType = "unknown"
intraday_pattern: IntradayPattern = "unknown"
```

- [ ] **Step 4: 跑测试确认仍 RED（字段已加但 mock 没填）**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k limitup_driver -v`
Expected: 现在通过（因为默认值 unknown 满足断言）。

但我们要测真正的 driver 推断，所以扩展测试：

```python
def test_mock_candidate_driver_inferred_from_concept_tags():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    drivers = {c.limitup_driver_type for c in candidates}
    # mock 至少给出一个非 unknown 的样本，便于 Hermes 演示该字段
    assert drivers - {"unknown"}, f"mock should include at least one non-unknown driver, got: {drivers}"
```

跑 RED（mock 没接入推断逻辑前会失败）。

- [ ] **Step 5: 在 mock adapter 中接 driver 推断**

打开 `src/aegis_alpha/adapters/mock_market_data.py:442` 的 `get_second_board_candidates` 方法。当前 mock 直接用 `SecondBoardCandidate(symbol=..., name=..., theme=..., ...)` 字面量构造若干候选并 return list。

最小改动策略：在每个 `SecondBoardCandidate(...)` 字面量末尾追加两个字段，给至少一个候选填具体的非 unknown 值，其余可保持默认。例：

```python
SecondBoardCandidate(
    symbol="000001",
    name="平安银行",
    theme="银行",
    # ... 其他已有字段保持原样 ...
    limitup_driver_type="policy",   # ← 新增（让测试看到非 unknown）
    intraday_pattern="unknown",     # ← 新增（Task 14 会接入真实推断）
    grade="B",
    grade_reason="...",
    notes=[],
),
SecondBoardCandidate(
    symbol="600519",
    # ... 其他字段保持原样 ...
    limitup_driver_type="theme",
    intraday_pattern="unknown",
    grade="C",
    grade_reason="...",
    notes=[],
),
```

不需要 import `classify_limitup_driver`（mock 内手写常量值即可，简化测试）。如果 mock 字面量已经使用 dict 解包构造（少见），则在 dict 里加这两个键。

- [ ] **Step 6: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k limitup_driver -v`
Expected: PASS。

- [ ] **Step 7: 写 jvquant adapter 集成测试（先 RED）**

`tests/test_jvquant_candidates.py` 不存在；新建一个文件，复用 `tests/test_jvquant_resolver_wiring.py` 已经有的 `JvQuantMarketDataAdapter(token="fake")` + `FakeJvQuantClient()` 模式。写入：

```python
from __future__ import annotations

from unittest.mock import patch

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
from aegis_alpha.models import LadderEntry

from tests.test_jvquant_resolver_wiring import FakeJvQuantClient  # 复用现有 fake client


def _build_candidates_with_minimal_patches(theme_leaders=None):
    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(
            symbol=symbol, trading_day=trading_day or "2026-05-30",
            consecutive_boards=1, height_label="first_board",
        )

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=theme_leaders or []):
        return adapter.get_second_board_candidates()


def test_jvquant_candidate_has_limitup_driver_type_in_allowed_set():
    candidates = _build_candidates_with_minimal_patches()
    allowed = {"earnings", "policy", "theme", "hot_money", "unknown"}
    assert candidates, "fake client should produce at least one candidate"
    for cand in candidates:
        assert cand.limitup_driver_type in allowed
```

如 `FakeJvQuantClient` 不在 resolver_wiring 测试里 export，subagent 把它复制到本文件即可。Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k limitup_driver -v` — 期望 RED（字段未接入）。

- [ ] **Step 8: 在 `jvquant/candidates.py:build_one_candidate` 集成**

打开 `src/aegis_alpha/adapters/jvquant/candidates.py`。已有的局部变量：
- `concept_tags` (`candidates.py:148`)
- `topic_tags` (`candidates.py:149`)
- `previous_consecutive` (注意：不是 `previous_consecutive_boards`，见 `candidates.py:164`)

在最终 `return SecondBoardCandidate(...)` 之前（约 candidates.py:270 前）插入：

```python
from aegis_alpha.extensions.limitup_driver import (
    classify_limitup_driver,
    LimitupDriverInputs,
)

# list_reason_text 留作 P5 后续接 jvQuant 龙虎榜时补充
limitup_driver_type = classify_limitup_driver(
    LimitupDriverInputs(
        symbol=symbol,
        concept_tags=list(concept_tags),
        topic_tags=list(topic_tags),
        list_reason="",
        net_amount_cny=0.0,  # 待龙虎榜接入后填净买额
        previous_consecutive_boards=int(previous_consecutive or 0),
    )
)
```

并在最终 `SecondBoardCandidate(...)` 字面量中追加（紧挨着 `grade_reason=...` 之前）：

```python
limitup_driver_type=limitup_driver_type,
intraday_pattern="unknown",  # Task 14 会接入真实推断
```

- [ ] **Step 9: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k limitup_driver -v && PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k limitup_driver -v`
Expected: PASS。

- [ ] **Step 10: 提交**

```bash
git add src/aegis_alpha/models.py src/aegis_alpha/adapters/jvquant/candidates.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    tests/test_jvquant_candidates.py tests/test_mock_adapter.py
git commit -m "Wire limitup_driver_type into SecondBoardCandidate (mock + jvquant)"
```

---

### Task 12: 在 candidate 的 grade_reason / data_quality 中暴露 driver

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/scoring.py`
- Modify: `src/aegis_alpha/adapters/jvquant/data_quality.py`
- Test: `tests/test_jvquant_candidates.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_jvquant_candidates.py`（复用 Task 11 加的 helper）：

```python
def test_grade_reason_mentions_driver_when_classified():
    """When candidate has a non-unknown limitup_driver_type, grade_reason should hint it."""
    candidates = _build_candidates_with_minimal_patches()
    classified = [c for c in candidates if c.limitup_driver_type != "unknown"]
    assert classified, "fake client should yield at least one classified driver"
    for cand in classified:
        assert cand.limitup_driver_type in cand.grade_reason or f"driver={cand.limitup_driver_type}" in cand.grade_reason
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k grade_reason_mentions_driver -v`
Expected: FAIL — `grade_reason` 不包含 driver 字串。

- [ ] **Step 3: 在 `scoring.py:candidate_grade_reason` 把 driver 拼进短语**

打开 `src/aegis_alpha/adapters/jvquant/scoring.py`，找到 `candidate_grade_reason`。先打开文件确认 inputs 形态（该函数接收一个 dataclass-like inputs 还是直接 kwargs）。最小改法步骤：

1. 在 inputs dataclass（如 `_ScoringInputs`）末尾加可选字段：

   ```python
   limitup_driver_type: str = "unknown"
   ```

2. 在函数体最终 `return ", ".join(parts)` 之前追加：

   ```python
   driver = getattr(inputs, "limitup_driver_type", "unknown")
   if driver != "unknown":
       parts.append(f"driver={driver}")
   ```

3. 在 `candidates.py:build_one_candidate` 调用 `candidate_grade_reason(...)` 处把 `limitup_driver_type=limitup_driver_type` 传进去（Task 11 已经计算好 `limitup_driver_type` 局部变量）。

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k grade_reason_mentions_driver -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/adapters/jvquant/scoring.py src/aegis_alpha/adapters/jvquant/candidates.py \
    tests/test_jvquant_candidates.py
git commit -m "Surface limitup_driver_type in grade_reason"
```

---

## 子系统 D — 分时形态识别（Tasks 13–16）

### Task 13: 形态识别纯函数

**Files:**
- Create: `src/aegis_alpha/extensions/intraday_pattern.py`
- Test: `tests/extensions/test_intraday_pattern.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/extensions/test_intraday_pattern.py`：

```python
from aegis_alpha.extensions.intraday_pattern import (
    PatternInputs,
    classify_intraday_pattern,
)


def _bars(values):
    """values is a list of (minutes_since_open, change_pct_at_close, is_at_limit)."""
    return [
        {"minute": m, "change_pct": pct, "at_limit": at_limit}
        for m, pct, at_limit in values
    ]


def test_one_word_board_when_open_at_limit_and_no_break():
    bars = _bars([
        (1, 9.95, True), (5, 9.95, True), (60, 9.95, True),
        (120, 9.95, True), (240, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=0, reseal_count=0,
            first_seal_minute=1, sealed_at_open=True, closed_at_limit=True,
        )
    )
    assert out.pattern == "one_word_board"


def test_t_shape_board_when_open_limit_break_then_reseal():
    bars = _bars([
        (1, 9.95, True), (30, 5.0, False), (90, 9.95, True), (240, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=1, reseal_count=1,
            first_seal_minute=1, sealed_at_open=True, closed_at_limit=True,
        )
    )
    assert out.pattern == "t_shape_board"


def test_messy_board_when_break_count_high():
    bars = _bars([
        (60, 7.0, False), (120, 9.95, True), (150, 5.0, False),
        (200, 9.95, True), (220, 4.0, False), (240, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=3, reseal_count=2,
            first_seal_minute=120, sealed_at_open=False, closed_at_limit=True,
        )
    )
    assert out.pattern == "messy_board"


def test_platform_breakout_when_long_consolidation_then_strong_move():
    bars = _bars([
        (5, 1.0, False), (60, 1.5, False), (120, 1.8, False),
        (180, 5.0, False), (220, 9.95, True),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=0, reseal_count=0,
            first_seal_minute=220, sealed_at_open=False, closed_at_limit=True,
        )
    )
    assert out.pattern == "platform_breakout"


def test_false_breakout_when_touch_limit_then_close_below():
    bars = _bars([
        (60, 9.5, False), (120, 9.95, True), (130, 9.95, True),
        (180, 5.0, False), (240, 1.0, False),
    ])
    out = classify_intraday_pattern(
        PatternInputs(
            bars=bars, daily_limit_pct=10.0, break_count=2, reseal_count=0,
            first_seal_minute=120, sealed_at_open=False, closed_at_limit=False,
        )
    )
    assert out.pattern == "false_breakout"


def test_normal_when_no_special_signal():
    out = classify_intraday_pattern(
        PatternInputs(
            bars=[], daily_limit_pct=10.0, break_count=0, reseal_count=0,
            first_seal_minute=0, sealed_at_open=False, closed_at_limit=True,
        )
    )
    assert out.pattern in {"normal", "unknown"}
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_intraday_pattern.py -v`
Expected: FAIL — module not found。

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/extensions/intraday_pattern.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis_alpha.models import IntradayPattern, IntradayPatternFeatures


_MESSY_BREAK_THRESHOLD = 3
_PLATFORM_CONSOLIDATION_MAX_PCT = 3.0  # 平台震荡幅度
_PLATFORM_CONSOLIDATION_MIN_MINUTES = 60  # 平台至少 60 分钟才算平台
_FALSE_BREAKOUT_RETRACE_PCT = 5.0  # 触板后回落 >5% 视为假突破


@dataclass(frozen=True)
class PatternInputs:
    bars: list[dict[str, Any]] = field(default_factory=list)
    daily_limit_pct: float = 10.0
    break_count: int = 0
    reseal_count: int = 0
    first_seal_minute: int = 0
    sealed_at_open: bool = False
    closed_at_limit: bool = False


def _high_pct(bars: list[dict[str, Any]]) -> float:
    if not bars:
        return 0.0
    return max(float(b.get("change_pct", 0.0)) for b in bars)


def _last_pct(bars: list[dict[str, Any]]) -> float:
    if not bars:
        return 0.0
    return float(bars[-1].get("change_pct", 0.0))


def classify_intraday_pattern(inputs: PatternInputs) -> IntradayPatternFeatures:
    if not inputs.bars and not inputs.first_seal_minute:
        return IntradayPatternFeatures(pattern="unknown")

    high = _high_pct(inputs.bars)
    last = _last_pct(inputs.bars)
    drawdown = max(0.0, high - last)

    if (
        inputs.sealed_at_open
        and inputs.break_count == 0
        and inputs.closed_at_limit
    ):
        return IntradayPatternFeatures(
            pattern="one_word_board",
            sealed_at_open=True, closing_at_limit=True,
            break_count=0, open_to_first_seal_minutes=inputs.first_seal_minute,
        )

    if (
        inputs.sealed_at_open
        and inputs.break_count >= 1
        and inputs.reseal_count >= 1
        and inputs.closed_at_limit
    ):
        return IntradayPatternFeatures(
            pattern="t_shape_board",
            sealed_at_open=True, closing_at_limit=True,
            break_count=inputs.break_count,
            open_to_first_seal_minutes=inputs.first_seal_minute,
        )

    if inputs.break_count >= _MESSY_BREAK_THRESHOLD:
        return IntradayPatternFeatures(
            pattern="messy_board",
            break_count=inputs.break_count,
            closing_at_limit=inputs.closed_at_limit,
            open_to_first_seal_minutes=inputs.first_seal_minute,
        )

    # 平台突破：至少 _PLATFORM_CONSOLIDATION_MIN_MINUTES 分钟震荡幅度小于阈值，然后冲板
    early_bars = [b for b in inputs.bars if int(b.get("minute", 0)) <= _PLATFORM_CONSOLIDATION_MIN_MINUTES * 2]
    if early_bars:
        early_max = max(float(b.get("change_pct", 0.0)) for b in early_bars)
        early_min = min(float(b.get("change_pct", 0.0)) for b in early_bars)
        consolidation_range = early_max - early_min
        if (
            consolidation_range <= _PLATFORM_CONSOLIDATION_MAX_PCT
            and inputs.first_seal_minute >= _PLATFORM_CONSOLIDATION_MIN_MINUTES
            and inputs.closed_at_limit
        ):
            return IntradayPatternFeatures(
                pattern="platform_breakout",
                closing_at_limit=True,
                open_to_first_seal_minutes=inputs.first_seal_minute,
            )

    # 假突破：盘中触板（high 接近涨停），收盘明显回落
    near_limit = high >= inputs.daily_limit_pct - 0.2
    if near_limit and not inputs.closed_at_limit and drawdown >= _FALSE_BREAKOUT_RETRACE_PCT:
        return IntradayPatternFeatures(
            pattern="false_breakout",
            high_to_close_drawdown_pct=drawdown,
            break_count=inputs.break_count,
        )

    return IntradayPatternFeatures(
        pattern="normal",
        closing_at_limit=inputs.closed_at_limit,
        break_count=inputs.break_count,
    )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_intraday_pattern.py -v`
Expected: 6 个测试全 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/extensions/intraday_pattern.py tests/extensions/test_intraday_pattern.py
git commit -m "Add intraday pattern classifier (one_word/t_shape/messy/platform/false)"
```

---

### Task 14: 候选契约接入 intraday_pattern

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/candidates.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Test: `tests/test_jvquant_candidates.py`, `tests/test_mock_adapter.py`

- [ ] **Step 1: 写失败测试 — mock**

追加到 `tests/test_mock_adapter.py`：

```python
def test_mock_candidate_intraday_pattern_in_allowed_set():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    allowed = {"one_word_board", "t_shape_board", "messy_board",
               "platform_breakout", "false_breakout", "normal", "unknown"}
    for cand in candidates:
        assert cand.intraday_pattern in allowed
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k intraday_pattern -v`
Expected: 通过（默认 unknown）。把测试加严：

```python
def test_mock_candidate_at_least_one_non_unknown_intraday_pattern():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    patterns = {c.intraday_pattern for c in candidates}
    assert patterns - {"unknown"}, f"mock should expose at least one real pattern, got: {patterns}"
```

跑 RED。

- [ ] **Step 3: 在 mock 中给至少一个候选填具体 pattern**

修改 `mock_market_data.py:442` 之后的候选字面量列表，把第一只候选 `intraday_pattern="t_shape_board"`，第二只 `intraday_pattern="one_word_board"`，其余保持 `"unknown"`。

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k intraday_pattern -v`
Expected: PASS。

- [ ] **Step 5: 在 jvquant adapter 中接入**

`MinuteReplayBar` 现有字段是 `time` / `last_price` / `average_price` / `volume`（见 `models.py:234`）。需要从 `time + last_price + previous_close + daily_limit_pct(symbol)` 推导出 pattern 输入需要的 `minute / change_pct / at_limit`。打开 `src/aegis_alpha/adapters/jvquant/candidates.py:build_one_candidate`，在已构造完 `break_board_count` / `reseal_count` / `change_pct` / `first_limit_up_time` 之后、`return SecondBoardCandidate(...)` 之前，插入：

```python
from aegis_alpha.extensions.intraday_pattern import (
    PatternInputs,
    classify_intraday_pattern,
)

intraday_pattern_value = "unknown"
if minute_replay_used and minute_replay.previous_close > 0:
    daily_limit_value = daily_limit_pct(symbol)
    limit_price_threshold = minute_replay.previous_close * (1.0 + daily_limit_value / 100.0)
    pattern_bars: list[dict] = []
    for bar in minute_replay.bars:
        try:
            hh, mm, *_ = bar.time.split(":")
            minute_offset = max(0, (int(hh) - 9) * 60 + int(mm) - 30)
        except Exception:
            continue
        if minute_replay.previous_close > 0:
            change_pct_local = (bar.last_price - minute_replay.previous_close) / minute_replay.previous_close * 100.0
        else:
            change_pct_local = 0.0
        at_limit = bar.last_price >= limit_price_threshold - 0.005  # 含 1 分价位容差
        pattern_bars.append({
            "minute": minute_offset,
            "change_pct": float(change_pct_local),
            "at_limit": bool(at_limit),
        })

    first_seal_minute = 0
    if first_limit_up_time and first_limit_up_time != "unknown":
        try:
            hh, mm = first_limit_up_time.split(":")[:2]
            first_seal_minute = max(0, (int(hh) - 9) * 60 + int(mm) - 30)
        except Exception:
            first_seal_minute = 0
    sealed_at_open = first_seal_minute <= 1
    closed_at_limit = abs(float(change_pct) - daily_limit_value) < 0.05
    features = classify_intraday_pattern(
        PatternInputs(
            bars=pattern_bars,
            daily_limit_pct=daily_limit_value,
            break_count=int(break_board_count or 0),
            reseal_count=int(reseal_count or 0),
            first_seal_minute=first_seal_minute,
            sealed_at_open=sealed_at_open,
            closed_at_limit=closed_at_limit,
        )
    )
    intraday_pattern_value = features.pattern
```

然后把 `SecondBoardCandidate(..., intraday_pattern="unknown", ...)` 字面量改成 `intraday_pattern=intraday_pattern_value`。

注意：本步骤完全使用 `MinuteReplayBar` 已有字段（`time`, `last_price`），不引入新模型字段。如未来要更精确（例如从 lv2 推一根 bar 的最高点），再在 P6 扩展 `MinuteReplayBar`。

- [ ] **Step 6: 跑测试**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py tests/extensions -v`
Expected: PASS（如失败请打开实际字段名校对）。

- [ ] **Step 7: 提交**

```bash
git add src/aegis_alpha/adapters/jvquant/candidates.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    tests/test_jvquant_candidates.py tests/test_mock_adapter.py
git commit -m "Wire intraday_pattern into SecondBoardCandidate via minute replay"
```

---

### Task 15: 形态展示在 compact MCP 输出中

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Test: `tests/test_mcp_p5_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p5_tools.py`：

```python
def test_compact_candidate_includes_limitup_driver_and_pattern():
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "limitup_driver_type" in item
        assert "intraday_pattern" in item
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k compact_candidate_includes_limitup -v`
Expected: FAIL。

- [ ] **Step 3: 在 compact 输出中加两个字段**

打开 `src/aegis_alpha/mcp/server.py:326+`（`get_second_board_candidates_compact`）。在 dict 字面量中追加：

```python
"limitup_driver_type": candidate.limitup_driver_type,
"intraday_pattern": candidate.intraday_pattern,
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k compact_candidate -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/mcp/server.py tests/test_mcp_p5_tools.py
git commit -m "Surface limitup_driver_type and intraday_pattern in compact MCP output"
```

---

### Task 16: 形态在 grade_reason 中给一句话备注

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/scoring.py`
- Test: `tests/test_jvquant_candidates.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_jvquant_candidates.py`（复用 Task 11 helper）：

```python
def test_grade_reason_mentions_pattern_when_classified():
    """When intraday_pattern is non-trivial (not unknown/normal), grade_reason should hint it."""
    candidates = _build_candidates_with_minimal_patches()
    interesting = [
        c for c in candidates
        if c.intraday_pattern not in {"unknown", "normal"}
    ]
    if not interesting:
        # fake client may not produce a non-trivial pattern; in that case test is vacuously true
        # but we still verify the field exists.
        for c in candidates:
            assert hasattr(c, "intraday_pattern")
        return
    for cand in interesting:
        assert cand.intraday_pattern in cand.grade_reason or f"pattern={cand.intraday_pattern}" in cand.grade_reason
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k grade_reason_mentions_pattern -v`
Expected: FAIL（如果 fake client 触发 pattern 分类）或 PASS（vacuous）。如果是 vacuous PASS，subagent 应在 `FakeJvQuantClient` 内增加触发 messy_board 的 break_count 数据使该分支可达；详见 fake client 在 resolver_wiring 测试中的字段设置。

- [ ] **Step 3: 在 `candidate_grade_reason` 末尾追加形态备注**

打开 `src/aegis_alpha/adapters/jvquant/scoring.py`，在 `parts` 拼装末尾、return 之前：

```python
pattern = getattr(inputs, "intraday_pattern", "unknown")
if pattern not in {"unknown", "normal"}:
    parts.append(f"pattern={pattern}")
```

把 `intraday_pattern: str = "unknown"` 加到 inputs dataclass，并在 `build_one_candidate` 调用时传入 `intraday_pattern=intraday_pattern_value`（Task 14 计算好的局部变量）。

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k grade_reason_mentions_pattern -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/adapters/jvquant/scoring.py \
    src/aegis_alpha/adapters/jvquant/candidates.py \
    tests/test_jvquant_candidates.py
git commit -m "Surface intraday_pattern hint in grade_reason"
```

---

## 子系统 E — 资金流分时切片（Tasks 17–20）

### Task 17: 资金切片 storage

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Test: `tests/test_p5_storage.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_p5_storage.py`：

```python
def test_save_and_get_capital_flow_slices(tmp_path):
    from aegis_alpha.models import CapitalFlowSlice
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "cf.db"))
    store.init_db()

    slice_a = CapitalFlowSlice(
        symbol="600519", trading_day="2026-05-30", window="pre_first_seal_5m",
        big_order_net_inflow_cny=12_000_000.0,
        main_capital_net_inflow_cny=15_000_000.0,
        retail_capital_net_inflow_cny=-3_000_000.0,
        provider="mock", data_mode="mock",
        created_at="2026-05-30T09:35:00+08:00",
    )
    slice_b = CapitalFlowSlice(
        symbol="600519", trading_day="2026-05-30", window="tail_30m",
        big_order_net_inflow_cny=-5_000_000.0,
        main_capital_net_inflow_cny=-7_000_000.0,
        retail_capital_net_inflow_cny=2_000_000.0,
        provider="mock", data_mode="mock",
        created_at="2026-05-30T15:00:00+08:00",
    )
    store.save_capital_flow_slice(slice_a)
    store.save_capital_flow_slice(slice_b)

    slices = store.list_capital_flow_slices("600519", "2026-05-30")
    windows = {s.window for s in slices}
    assert windows == {"pre_first_seal_5m", "tail_30m"}
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_storage.py -k capital_flow -v`
Expected: FAIL。

- [ ] **Step 3: 实现 storage**

打开 `storage.py`，import 区追加 `CapitalFlowSlice`。类内追加：

```python
def save_capital_flow_slice(self, slice_: CapitalFlowSlice) -> None:
    with self._connect() as conn:
        conn.execute(
            """
            INSERT INTO capital_flow_slices (
                symbol, trading_day, window,
                big_order_net_inflow_cny, main_capital_net_inflow_cny,
                retail_capital_net_inflow_cny, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, trading_day, window) DO UPDATE SET
                big_order_net_inflow_cny = excluded.big_order_net_inflow_cny,
                main_capital_net_inflow_cny = excluded.main_capital_net_inflow_cny,
                retail_capital_net_inflow_cny = excluded.retail_capital_net_inflow_cny,
                payload_json = excluded.payload_json
            """,
            (
                slice_.symbol,
                slice_.trading_day,
                slice_.window,
                slice_.big_order_net_inflow_cny,
                slice_.main_capital_net_inflow_cny,
                slice_.retail_capital_net_inflow_cny,
                slice_.model_dump_json(),
                slice_.created_at,
            ),
        )

def list_capital_flow_slices(
    self, symbol: str, trading_day: str
) -> list[CapitalFlowSlice]:
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM capital_flow_slices "
            "WHERE symbol = ? AND trading_day = ? ORDER BY window ASC",
            (symbol, trading_day),
        ).fetchall()
    return [CapitalFlowSlice.model_validate_json(row[0]) for row in rows]
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_storage.py -k capital_flow -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/storage.py tests/test_p5_storage.py
git commit -m "Add capital_flow_slices storage methods"
```

---

### Task 18: 资金切片纯函数（输入分钟回放 → 输出 3 个切片）

**Files:**
- Create: `src/aegis_alpha/extensions/capital_flow_slices.py`
- Test: `tests/extensions/test_capital_flow_slices.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/extensions/test_capital_flow_slices.py`：

```python
from aegis_alpha.extensions.capital_flow_slices import (
    CapitalFlowSliceInputs,
    compute_capital_flow_slices,
)


def test_compute_pre_first_seal_5m_uses_5_bars_before_first_seal():
    bars = [
        {"minute": m, "big_order_net_inflow_cny": 1_000_000.0,
         "main_capital_net_inflow_cny": 2_000_000.0,
         "retail_capital_net_inflow_cny": -500_000.0}
        for m in range(0, 30)
    ]
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(
            symbol="600519", trading_day="2026-05-30",
            bars=bars, first_seal_minute=20,
        )
    )
    pre = next(s for s in out if s.window == "pre_first_seal_5m")
    # 5 bars (minute 15-19): each big=1M → sum 5M
    assert pre.big_order_net_inflow_cny == 5_000_000.0
    assert pre.main_capital_net_inflow_cny == 10_000_000.0
    assert pre.retail_capital_net_inflow_cny == -2_500_000.0


def test_post_break_1m_when_break_minute_present():
    bars = [
        {"minute": m, "big_order_net_inflow_cny": -3_000_000.0,
         "main_capital_net_inflow_cny": -2_000_000.0,
         "retail_capital_net_inflow_cny": 1_000_000.0}
        for m in range(60, 65)
    ]
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(
            symbol="600519", trading_day="2026-05-30",
            bars=bars, first_seal_minute=50, first_break_minute=60,
        )
    )
    post = next(s for s in out if s.window == "post_break_1m")
    assert post.big_order_net_inflow_cny == -3_000_000.0


def test_tail_30m_aggregates_last_30_bars():
    bars = [
        {"minute": m, "big_order_net_inflow_cny": 100_000.0,
         "main_capital_net_inflow_cny": 200_000.0,
         "retail_capital_net_inflow_cny": -50_000.0}
        for m in range(210, 240)  # 14:30-15:00 (30 分钟)
    ]
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(
            symbol="600519", trading_day="2026-05-30",
            bars=bars, first_seal_minute=10,
        )
    )
    tail = next(s for s in out if s.window == "tail_30m")
    assert tail.big_order_net_inflow_cny == 30 * 100_000.0


def test_no_slices_when_inputs_empty():
    out = compute_capital_flow_slices(
        CapitalFlowSliceInputs(symbol="X", trading_day="2026-05-30", bars=[])
    )
    assert out == []
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_capital_flow_slices.py -v`
Expected: FAIL。

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/extensions/capital_flow_slices.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis_alpha.clock import now_iso
from aegis_alpha.models import CapitalFlowSlice


@dataclass(frozen=True)
class CapitalFlowSliceInputs:
    symbol: str
    trading_day: str
    bars: list[dict[str, Any]] = field(default_factory=list)
    first_seal_minute: int = 0
    first_break_minute: int = 0
    provider: str = "mock"
    data_mode: str = "mock"


def _aggregate(window_bars: list[dict[str, Any]]) -> tuple[float, float, float]:
    big = sum(float(b.get("big_order_net_inflow_cny", 0.0)) for b in window_bars)
    main = sum(float(b.get("main_capital_net_inflow_cny", 0.0)) for b in window_bars)
    retail = sum(float(b.get("retail_capital_net_inflow_cny", 0.0)) for b in window_bars)
    return big, main, retail


def compute_capital_flow_slices(
    inputs: CapitalFlowSliceInputs,
) -> list[CapitalFlowSlice]:
    if not inputs.bars:
        return []
    timestamp = now_iso()
    output: list[CapitalFlowSlice] = []
    by_minute = {int(b.get("minute", -1)): b for b in inputs.bars if int(b.get("minute", -1)) >= 0}

    # 切片 1: pre_first_seal_5m —— 首封前 5 根 bar
    if inputs.first_seal_minute > 0:
        start = max(0, inputs.first_seal_minute - 5)
        window_bars = [by_minute[m] for m in range(start, inputs.first_seal_minute) if m in by_minute]
        if window_bars:
            big, main, retail = _aggregate(window_bars)
            output.append(
                CapitalFlowSlice(
                    symbol=inputs.symbol, trading_day=inputs.trading_day,
                    window="pre_first_seal_5m",
                    big_order_net_inflow_cny=big,
                    main_capital_net_inflow_cny=main,
                    retail_capital_net_inflow_cny=retail,
                    provider=inputs.provider, data_mode=inputs.data_mode,
                    created_at=timestamp,
                )
            )

    # 切片 2: post_break_1m —— 首次炸板后 1 根 bar
    if inputs.first_break_minute > 0:
        m = inputs.first_break_minute
        if m in by_minute:
            big, main, retail = _aggregate([by_minute[m]])
            output.append(
                CapitalFlowSlice(
                    symbol=inputs.symbol, trading_day=inputs.trading_day,
                    window="post_break_1m",
                    big_order_net_inflow_cny=big,
                    main_capital_net_inflow_cny=main,
                    retail_capital_net_inflow_cny=retail,
                    provider=inputs.provider, data_mode=inputs.data_mode,
                    created_at=timestamp,
                )
            )

    # 切片 3: tail_30m —— 收盘前最后 30 分钟
    minutes_present = sorted(by_minute.keys())
    if minutes_present:
        max_minute = minutes_present[-1]
        tail_bars = [by_minute[m] for m in minutes_present if m > max_minute - 30]
        if tail_bars:
            big, main, retail = _aggregate(tail_bars)
            output.append(
                CapitalFlowSlice(
                    symbol=inputs.symbol, trading_day=inputs.trading_day,
                    window="tail_30m",
                    big_order_net_inflow_cny=big,
                    main_capital_net_inflow_cny=main,
                    retail_capital_net_inflow_cny=retail,
                    provider=inputs.provider, data_mode=inputs.data_mode,
                    created_at=timestamp,
                )
            )
    return output
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_capital_flow_slices.py -v`
Expected: 4 个测试 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/extensions/capital_flow_slices.py \
    tests/extensions/test_capital_flow_slices.py
git commit -m "Add capital flow slice computation (pre_first_seal / post_break / tail_30m)"
```

---

### Task 19: adapter wiring 资金切片（mock + jvquant placeholder）

**Files:**
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Test: `tests/extensions/test_capital_flow_slices.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/extensions/test_capital_flow_slices.py`：

```python
def test_mock_adapter_get_capital_flow_slices_returns_three_windows():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    slices = adapter.get_capital_flow_slices("600519", "2026-05-30")
    windows = {s.window for s in slices}
    assert windows == {"pre_first_seal_5m", "post_break_1m", "tail_30m"}
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_capital_flow_slices.py -k mock_adapter -v`
Expected: FAIL.

- [ ] **Step 3: 在 protocols 增方法**

```python
def get_capital_flow_slices(
    self, symbol: str, trading_day: str
) -> list[CapitalFlowSlice]: ...
```

import 增 `CapitalFlowSlice`。

- [ ] **Step 4: mock 实现**

`mock_market_data.py` 类末追加：

```python
def get_capital_flow_slices(
    self, symbol: str, trading_day: str
) -> list[CapitalFlowSlice]:
    timestamp = "2026-05-30T15:00:00+08:00"
    return [
        CapitalFlowSlice(
            symbol=symbol, trading_day=trading_day, window="pre_first_seal_5m",
            big_order_net_inflow_cny=8_000_000.0,
            main_capital_net_inflow_cny=12_000_000.0,
            retail_capital_net_inflow_cny=-3_000_000.0,
            provider="mock", data_mode="mock",
            created_at=timestamp,
        ),
        CapitalFlowSlice(
            symbol=symbol, trading_day=trading_day, window="post_break_1m",
            big_order_net_inflow_cny=-2_000_000.0,
            main_capital_net_inflow_cny=-1_500_000.0,
            retail_capital_net_inflow_cny=500_000.0,
            provider="mock", data_mode="mock",
            created_at=timestamp,
        ),
        CapitalFlowSlice(
            symbol=symbol, trading_day=trading_day, window="tail_30m",
            big_order_net_inflow_cny=3_000_000.0,
            main_capital_net_inflow_cny=4_500_000.0,
            retail_capital_net_inflow_cny=-1_000_000.0,
            provider="mock", data_mode="mock",
            created_at=timestamp,
        ),
    ]
```

import 增 `CapitalFlowSlice`。

- [ ] **Step 5: jvquant placeholder 实现**

`adapters/jvquant/adapter.py` 类末追加：

```python
def get_capital_flow_slices(
    self, symbol: str, trading_day: str
) -> list[CapitalFlowSlice]:
    # P5 starter: minute-level capital flow detail not yet exposed by jvQuant
    # semantic queries; return [] until dedicated probe lands.
    return []
```

import 增 `CapitalFlowSlice`。

- [ ] **Step 6: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_capital_flow_slices.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add src/aegis_alpha/protocols.py src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py \
    tests/extensions/test_capital_flow_slices.py
git commit -m "Wire get_capital_flow_slices adapter method (mock complete, jvquant placeholder)"
```

---

### Task 20: 资金切片 MCP 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p5_tools.py`

- [ ] **Step 1: 写失败测试**

```python
def test_get_capital_flow_slices_returns_three_dicts():
    from aegis_alpha.mcp.server import get_capital_flow_slices

    rows = get_capital_flow_slices("600519", "2026-05-30")
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert {r["window"] for r in rows} == {
        "pre_first_seal_5m", "post_break_1m", "tail_30m"
    }
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k capital_flow_slices -v`
Expected: FAIL。

- [ ] **Step 3: 实现工具**

在 `mcp/server.py` 末尾（`get_recent_backtests` 之后）追加：

```python
@mcp.tool
def get_capital_flow_slices(symbol: str, trading_day: str) -> list[dict] | dict:
    """Return per-symbol per-day capital flow slices: pre_first_seal_5m / post_break_1m / tail_30m."""
    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable", "error": "symbol and trading_day are required"}
    return _call_tool(
        lambda adapter: [
            s.model_dump() for s in adapter.get_capital_flow_slices(safe_symbol, safe_day)
        ]
    )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py -k capital_flow_slices -v`
Expected: PASS。

- [ ] **Step 5: 加到 MCP config include**

```yaml
        - get_capital_flow_slices
```

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p5_tools.py
git commit -m "Expose get_capital_flow_slices MCP tool"
```

---

## 子系统 F — 集成与文档（Tasks 21–22）

### Task 21: README 与 SKILL 同步 P5 工具

**Files:**
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: README 加 P5 工具与字段段落**

打开 `README.md`，在「MCP Tools」列表中补上：

```markdown
- `get_dragon_tiger(symbol, trading_day)`
- `get_active_seats_today(trading_day)`
- `get_limit_down_pool(trading_day)`
- `get_st_pool(trading_day)`
- `get_capital_flow_slices(symbol, trading_day)`
```

并在 jvQuant 工具列表里补上同 5 个工具名。

在「The second-board candidate pool is currently derived ...」段落后追加一段：

```markdown
P5 数据扩展（自 2026-05 起）增加了 4 个外部数据维度：

- 龙虎榜适配器 — `get_dragon_tiger` / `get_active_seats_today` 暴露知名游资席位（章盟主、孙哥、欢乐海岸、炒股养家等，白名单可在 `config/dragon_tiger_seats.yaml` 维护）；jvQuant 端尚未对齐契约，目前以 placeholder 起步，mock 端给出确定性样本。
- 跌停池 / ST 池 — `get_limit_down_pool` / `get_st_pool` 给出今日跌停股与 ST 板成员；连续多只昨日跌停股今日反弹涨停时触发 `MARKET_BOTTOM_REVERSAL` 反向情绪事件。
- 涨停原因细分 — 候选契约新增 `limitup_driver_type ∈ {earnings, policy, theme, hot_money, unknown}`。
- 分时形态识别 — 候选契约新增 `intraday_pattern ∈ {one_word_board, t_shape_board, messy_board, platform_breakout, false_breakout, normal, unknown}`。
- 资金分时切片 — `get_capital_flow_slices` 返回 `pre_first_seal_5m` / `post_break_1m` / `tail_30m` 三个窗口的大单 / 主力 / 散户净流入。

P5 字段在 jvQuant 真实端尚未完全接入时会以 placeholder 模式返回；agent 应在 SKILL 工作流中检查 `data_mode == "placeholder"` 并据此降级置信。
```

- [ ] **Step 2: SKILL.md 加规则**

打开 `.hermes/skills/second-board-radar/SKILL.md`，在「Required MCP Tools」列表加：

```text
- `get_dragon_tiger`
- `get_active_seats_today`
- `get_limit_down_pool`
- `get_st_pool`
- `get_capital_flow_slices`
```

并在 Standard Workflow 末尾追加一条：

```text
20. P5 数据维度可选用：
    - `get_dragon_tiger(symbol, trading_day)` 在收盘后查看候选股的龙虎榜结构；如席位含 `hot_money_known` 且 `hot_money_alias` 为白名单游资（章盟主、孙哥等），在评级原因里点出资金主体。
    - `get_active_seats_today(trading_day)` 看当天哪几位游资同时进入多只股，用作板块共振辅助证据。
    - `get_limit_down_pool(trading_day)` / `get_st_pool(trading_day)` 在判断市场情绪时观察反向池规模；如 `MARKET_BOTTOM_REVERSAL` 事件出现，将其当作板块见底的辅助语境，不要由它直接推荐买点。
    - 候选契约里 `limitup_driver_type` 与 `intraday_pattern` 在 evidence 里给一句中文备注；`policy` / `earnings` 驱动通常比 `theme` 更稳，`one_word_board` / `platform_breakout` 比 `messy_board` / `false_breakout` 风险更低。
    - `get_capital_flow_slices(symbol, trading_day)` 在复盘失败案例时使用：`tail_30m` 主力净流出说明尾盘机构离场。
```

- [ ] **Step 3: 提交**

```bash
git add README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "Document P5 MCP tools and workflow guidance"
```

---

### Task 22: 全量回归与 smoke

**Files:**
- 无新文件

- [ ] **Step 1: 跑全量单测**

Run: `PYTHONPATH=src .venv/bin/pytest tests/ -q`
Expected: 全部 PASS。如有失败，回到对应 Task 修复，且新写一行 commit 不要 amend 之前的 commit。

- [ ] **Step 2: 跑 compileall**

Run: `python -m compileall src scripts tests -q`
Expected: 无 SyntaxError。

- [ ] **Step 3: smoke check**

Run: `PYTHONPATH=src .venv/bin/python scripts/smoke_check.py`
Expected: 退出码 0。

- [ ] **Step 4: 简单触发一次 MCP server import**

Run: `PYTHONPATH=src .venv/bin/python -c "from aegis_alpha.mcp.server import get_dragon_tiger, get_active_seats_today, get_limit_down_pool, get_st_pool, get_capital_flow_slices; print('ok')"`
Expected: 输出 `ok`。

- [ ] **Step 5: 不需要新提交**（只验证）

无变更产生时不要 commit；如发现 bug 修复后单独 commit。

---

## Self-Review Checklist

| 项 | 状态 |
|----|------|
| 龙虎榜：`DragonTigerRecord/Seat` + 席位白名单 + storage + 2 MCP tools | ✅ Tasks 1, 3, 4, 5 |
| 跌停池 / ST 池 + `MARKET_BOTTOM_REVERSAL` 事件 + 2 MCP tools | ✅ Tasks 1, 6, 7, 8, 9 |
| 涨停原因 4 分类 + 候选契约 `limitup_driver_type` + grade_reason | ✅ Tasks 1, 10, 11, 12 |
| 形态识别 5 类（+ normal/unknown）+ 候选契约 `intraday_pattern` + grade_reason | ✅ Tasks 1, 13, 14, 15, 16 |
| 资金分时 3 窗口 + storage + adapter + MCP tool | ✅ Tasks 1, 2, 17, 18, 19, 20 |
| 数据库迁移 m0005 + 表结构 | ✅ Task 2 |
| `MarketEventType` Literal 加 `MARKET_BOTTOM_REVERSAL` | ✅ Task 8 |
| README + SKILL 同步 | ✅ Task 21 |
| 全量回归通过 | ✅ Task 22 |
| 任意 sub-agent 失败不阻塞其余子系统（A/B/C/D/E 弱耦合） | ✅ 子系统目录隔离 |
| `created_at` 不会被 upsert 覆盖 | ✅ 所有 ON CONFLICT 子句不含 `created_at` |
| 所有 Bash 命令使用 `PYTHONPATH=src .venv/bin/...`（已在 `.claude/settings.json` allowlist） | ✅ |
| Worktree base = main HEAD（`.claude/settings.json: worktree.baseRef = head`） | ✅ |
| 不修改 LLM 模型名 (`claude-opus-4-7`, `deepseek-v4-pro`) | ✅ 本计划无 LLM 模型变更 |

## 已知限制（写明留给 P6 / future issue）

- **jvQuant 龙虎榜端点**：当前 placeholder。等 jvQuant 官方文档明确字段后再补真实 query。Hermes 看到 `data_mode=placeholder` 应理解为「未接入」，不要据此排板。
- **jvQuant 跌停池 / ST 池 semantic query**：尚未确定字段映射，placeholder 模式。
- **资金流分钟切片**：jvQuant 单次大单流入字段在 minute 级是否齐全未验证；mock 端给出确定性样本，jvQuant 端 placeholder。
- **policy 关键词列表**：起步白名单偏小（`国务院` 等 14 个），用户可在 `extensions/limitup_driver.py:_POLICY_KEYWORDS` 里加，未来可改为 yaml。
- **`intraday_pattern` 阈值参数**：现写在常量里（`_MESSY_BREAK_THRESHOLD=3` 等）。如果回测发现需调，迁到 `config/candidate_grading.yaml` 是 P6 的事。
- **`grade_reason` 中文化**：当前在 reason 里加的是英文 `driver=policy` / `pattern=messy_board`。若用户希望全中文，下一轮 P6 时再做映射表（不强求 P5 完成）。

完成 P5 后，Hermes 在解释二板候选时会有 5 个新维度可点名（席位 / 反向池 / 上涨驱动 / 分时形态 / 资金切片），完整闭环到 P4 的 attribution + backtest 框架。
