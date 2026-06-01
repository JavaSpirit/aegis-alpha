# P6 — 进阶事件与生态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 P0–P5 已经搭好的「单股 / 板块 / 历史 / 反馈」骨架升级到「板块事件 + 跨周期校验 + 相似形态匹配 + 次新 / 停牌支持 + Parquet 历史层 + 假设分析」，让 Hermes 能用更结构化的语言解释为什么某个候选要回避或上调评级。

**Architecture:**
本期沿用 P5 的「pure-function 模块 + storage 入口 + adapter wiring + MCP tool」分层。新增 7 个子系统：A. `extensions/sector_events.py` 扩展 `MarketEventType`，B. `extensions/weekly_position.py` 接周线视角，C. `extensions/similar_setups.py` 用 5 维向量在 P4 历史快照上做余弦匹配，D. `extensions/new_stocks.py` 给次新股专用通道，E. `extensions/suspended_stocks.py` + 新表 `suspended_stocks`，F. 新包 `aegis_alpha/history_store/` 用 pyarrow 写 Parquet + DuckDB 查询，G. `feedback/hypothesis.py` 在 P4 backtest 之上加单股假设分析。Parquet 是唯一引入新依赖的模块，作为 `[project.optional-dependencies] history-store` 暴露，缺失时 MCP 工具优雅降级。

**Tech Stack:**
Python 3.11+, Pydantic v2, SQLite (versioned migration `m0006_p6_extensions.py`), 可选 `pyarrow>=15` + `duckdb>=0.10` (history-store 组), FastMCP server, pytest TDD。复用现有 `seal_timeline/`、`themes/`、`feedback/`、`extensions/` 模块。

---

## P6 范围对齐（来自 roadmap）

来自 `docs/superpowers/plans/2026-05-29-aegis-alpha-roadmap.md` 第 132-141 行：

- **A. 板块事件** — `THEME_LEADER_BREAK_BOARD` / `SECTOR_ROTATION`（`THEME_DIVERGENCE` 已经在 P3 落地）。
- **B. 跨周期校验** — 周线视角；`get_weekly_position(symbol)`；候选契约新增 `weekly_health_score`。
- **C. 相似形态搜索** — `find_similar_setups(symbol, lookback_days, similarity_threshold)`；用结构化指标（连板高度 / 板块 / 封单 / 情绪 / 涨速）做向量匹配。
- **D. 次新股专用通道** — `get_new_stock_candidates()`；按上市天数 + 流通市值分层。
- **E. 停牌 / 复牌处理** — `suspended_stocks` 表；候选拉取链路忽略停牌股。
- **F. Parquet 历史层** — pyarrow 写 minute bars；DuckDB 查询入口。
- **G. 假设分析** — `simulate_outcome(symbol, hypothesis)`：单股假设回测。

任务总数：23 个 task（22 个实现任务 + 1 个 docs 任务）。

## 强制约束（Subagent 实施时必须遵守）

读完每个任务再下笔。这些约束不可放弃：

1. **不允许真实交易、不允许写真实下单**。所有 P6 输出仅 read-only。
2. **不能私改 LLM 模型名**。`anthropic/claude-opus-4-7` 与 `deepseek-v4-pro` 名字保持原样（用户明确指示）。
3. **TDD 严格执行**：每个新函数 / 新方法 / 新 MCP 工具都要先写失败测试，再写实现。提交粒度 = 一次 RED → GREEN → COMMIT。
4. **保留向后兼容**：新增字段默认 `unknown` / `0.0` / `[]` / `0`，让 P0–P5 现有测试与候选构造逻辑无须修改即可继续通过。
5. **不要重复实现已有的 THEME_DIVERGENCE**：`src/aegis_alpha/seal_timeline/divergence.py:detect_theme_divergence` 已经存在。本计划只新增 `THEME_LEADER_BREAK_BOARD` 和 `SECTOR_ROTATION`。
6. **数据缺失时不要捏造**：jvQuant 没返回的字段，落 `unknown` / `placeholder`，并在 `data_quality` 里标 `confidence=placeholder` + `usable_for_grading=False`。
7. **Parquet 是可选依赖**：`pyarrow` / `duckdb` 必须放 `[project.optional-dependencies] history-store`。`history_store/` 模块 import 必须 try/except 包住，缺失时所有 history-store 入口返回 `{"data_mode": "unavailable", "error": "history-store extras not installed"}`。绝不让缺依赖时整个 MCP server 崩。
8. **storage 调用 conn 时必须用 self._connect() context manager**：参考 `storage.py:1080+` 的 P4 / P5 模式。
9. **MCP tool 调用 store 时必须用 `_call_store(lambda store: ...)`，调用 adapter 时必须用 `_call_tool(lambda adapter: ...)`**。
10. **新表的 `created_at` 在 upsert 时不要被覆盖**：`ON CONFLICT DO UPDATE SET ...` 子句中不出现 `created_at`。
11. **跨子系统弱耦合**：A、B、C、D、E、F、G 必须能独立交付。一个子系统失败不能阻塞其他子系统。

## 文件结构（落盘前先看完）

### 新增

| Path | 责任 |
|------|------|
| `src/aegis_alpha/extensions/sector_events.py` | A. `detect_theme_leader_break_board` + `detect_sector_rotation` 纯函数 |
| `src/aegis_alpha/extensions/weekly_position.py` | B. `compute_weekly_health_score` 纯函数 |
| `src/aegis_alpha/extensions/similar_setups.py` | C. `vectorize_setup`, `cosine_similarity`, `find_similar_setups` |
| `src/aegis_alpha/extensions/new_stocks.py` | D. `build_new_stock_candidate` 纯函数 |
| `src/aegis_alpha/extensions/suspended_stocks.py` | E. `is_symbol_suspended` helper |
| `src/aegis_alpha/feedback/hypothesis.py` | G. `simulate_outcome` 纯函数（基于 P4 backtest 单条扩展） |
| `src/aegis_alpha/history_store/__init__.py` | F. 命名空间 + `is_history_store_available()` |
| `src/aegis_alpha/history_store/parquet_writer.py` | F. `MinuteBarWriter` |
| `src/aegis_alpha/history_store/parquet_reader.py` | F. `MinuteBarReader` (DuckDB 查询) |
| `src/aegis_alpha/db_migrations_files/m0006_p6_extensions.py` | E. `suspended_stocks` 表迁移 |
| `tests/extensions/test_sector_events.py` | A 子系统单测 |
| `tests/extensions/test_weekly_position.py` | B 子系统单测 |
| `tests/extensions/test_similar_setups.py` | C 子系统单测 |
| `tests/extensions/test_new_stocks.py` | D 子系统单测 |
| `tests/extensions/test_suspended_stocks.py` | E 子系统单测 |
| `tests/feedback/test_hypothesis.py` | G 子系统单测 |
| `tests/history_store/__init__.py` | F 测试包标识 |
| `tests/history_store/test_parquet_writer.py` | F 子系统单测（pyarrow 缺失时 skip） |
| `tests/history_store/test_parquet_reader.py` | F 子系统单测（pyarrow 缺失时 skip） |
| `tests/test_db_migrations_p6.py` | E 子系统迁移测试 |
| `tests/test_p6_storage.py` | E + C 跨子系统 storage 测试 |
| `tests/test_mcp_p6_tools.py` | 全部 P6 MCP 工具的 dict-shape 测试 |

### 修改

| Path | 修改内容 |
|------|---------|
| `pyproject.toml` | 增 `[project.optional-dependencies] history-store` 组（pyarrow + duckdb） |
| `src/aegis_alpha/models.py` | 新增 4 个 Literal + 6 个 Pydantic 模型 + `SecondBoardCandidate` 增 1 个字段 + `MarketEventType` 增 2 个值 |
| `src/aegis_alpha/protocols.py` | `MarketDataAdapter` 增 4 个新方法签名 |
| `src/aegis_alpha/storage.py` | 增 4 个 storage 方法（save/get/list × suspended_stocks 表 + similar_setups index） |
| `src/aegis_alpha/adapters/mock_market_data.py` | 增 4 个 mock 实现 + 候选构造里填 `weekly_health_score` |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | 增 4 个 jvQuant 实现（多数 placeholder 起步） |
| `src/aegis_alpha/adapters/jvquant/candidates.py` | 在 `build_one_candidate` 注入 `weekly_health_score` |
| `src/aegis_alpha/mcp/server.py` | 注册 7 个新 MCP tool |
| `.hermes/config/aegis-alpha-mcp.yaml` | include 列表加 7 个新工具名 |
| `README.md` | 「MCP Tools」章节追加 P6 工具与字段说明 |
| `.hermes/skills/second-board-radar/SKILL.md` | Required Tools 加 7 个新工具，Workflow 注明何时使用 |

---

## 子系统 A — 板块事件（Tasks 1–3）

### Task 1: 扩展 MarketEventType + 板块事件模型

**Files:**
- Modify: `src/aegis_alpha/models.py`
- Test: `tests/test_p5_models.py` (复用 P5 已建文件)

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_p5_models.py`：

```python
def test_p6_market_event_types_extended():
    from aegis_alpha.models import MarketEventType
    from typing import get_args

    types = set(get_args(MarketEventType))
    assert "THEME_LEADER_BREAK_BOARD" in types
    assert "SECTOR_ROTATION" in types
    # 旧值不动
    assert "THEME_DIVERGENCE" in types
    assert "MARKET_BOTTOM_REVERSAL" in types


def test_sector_rotation_evidence_model_construct():
    from aegis_alpha.models import SectorRotationEvidence

    ev = SectorRotationEvidence(
        weakening_theme="军工",
        weakening_leader_status="broken",
        strengthening_theme="AI",
        strengthening_leader_status="sealed",
        weakening_alive_count=0,
        strengthening_alive_count=4,
    )
    assert ev.weakening_theme == "军工"
    assert ev.strengthening_alive_count == 4
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py -k "p6_market_event_types_extended or sector_rotation_evidence_model_construct" -v`
Expected: FAIL（新值与新模型未定义）。

- [ ] **Step 3: 在 `MarketEventType` Literal 末尾加 2 个值**

修改 `src/aegis_alpha/models.py:30-38` 的 `MarketEventType`：

```python
MarketEventType = Literal[
    "THEME_CLUSTER_RISING",
    "APPROACHING_LIMIT_UP",
    "SEAL_ORDER_DECAY",
    "BIG_ORDER_INFLOW_SPIKE",
    "SECOND_BOARD_CANDIDATE_REPRICE",
    "THEME_DIVERGENCE",
    "MARKET_BOTTOM_REVERSAL",
    "THEME_LEADER_BREAK_BOARD",
    "SECTOR_ROTATION",
]
```

- [ ] **Step 4: 在 `models.py` 末尾追加调试用模型**

```python
class SectorRotationEvidence(BaseModel):
    """SECTOR_ROTATION 事件的结构化证据。"""

    weakening_theme: str
    weakening_leader_status: str = "unknown"
    strengthening_theme: str
    strengthening_leader_status: str = "unknown"
    weakening_alive_count: int = 0
    strengthening_alive_count: int = 0
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py -k "p6_market_event_types_extended or sector_rotation_evidence_model_construct" -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/models.py tests/test_p5_models.py
git commit -m "Extend MarketEventType for P6 + add SectorRotationEvidence"
```

---

### Task 2: detect_theme_leader_break_board 检测器

**Files:**
- Create: `src/aegis_alpha/extensions/sector_events.py`
- Create: `tests/extensions/test_sector_events.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/extensions/test_sector_events.py`：

```python
from aegis_alpha.models import ThemeLeader
from aegis_alpha.extensions.sector_events import (
    LeaderBreakInputs,
    detect_theme_leader_break_board,
)


def _leader(symbol="600519", theme="AI", consecutive=3, status="sealed", co=None):
    return ThemeLeader(
        theme=theme,
        trading_day="2026-06-01",
        leader_symbol=symbol,
        leader_name=f"L-{symbol}",
        leader_consecutive_boards=consecutive,
        leader_first_limit_up_time="09:32:00",
        leader_seal_amount_cny=300_000_000.0,
        leader_status=status,
        co_leader_symbols=co or [],
        member_count=4,
    )


def test_break_board_event_when_high_height_leader_breaks():
    leader = _leader(consecutive=3, status="broken")
    inputs = LeaderBreakInputs(
        leaders=[leader],
        trading_day="2026-06-01",
        min_consecutive_boards=2,
    )
    events = detect_theme_leader_break_board(inputs)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "THEME_LEADER_BREAK_BOARD"
    assert ev.symbol == "600519"
    assert ev.theme == "AI"
    assert ev.score >= 60
    assert any("consecutive=3" in e for e in ev.evidence)


def test_break_board_event_skipped_when_below_height_threshold():
    leader = _leader(consecutive=1, status="broken")
    inputs = LeaderBreakInputs(
        leaders=[leader],
        trading_day="2026-06-01",
        min_consecutive_boards=2,
    )
    events = detect_theme_leader_break_board(inputs)
    assert events == []


def test_break_board_event_skipped_when_leader_still_sealed():
    leader = _leader(consecutive=4, status="sealed")
    inputs = LeaderBreakInputs(
        leaders=[leader],
        trading_day="2026-06-01",
        min_consecutive_boards=2,
    )
    events = detect_theme_leader_break_board(inputs)
    assert events == []
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_sector_events.py -k break_board -v`
Expected: FAIL（模块未创建）。

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/extensions/sector_events.py`：

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from aegis_alpha.clock import now_iso
from aegis_alpha.models import (
    MarketEvent,
    SectorRotationEvidence,
    ThemeLeader,
)


_BREAK_BOARD_BASE_SCORE = 60.0
_BREAK_BOARD_HEIGHT_BONUS = 5.0  # 每多一个连板 +5 分
_ROTATION_BASE_SCORE = 65.0
_ROTATION_FOLLOWER_BONUS = 3.0  # 每一个 strengthening alive follower +3 分


@dataclass(frozen=True)
class LeaderBreakInputs:
    leaders: list[ThemeLeader]
    trading_day: str
    min_consecutive_boards: int = 2


@dataclass(frozen=True)
class SectorRotationInputs:
    leaders: list[ThemeLeader]
    trading_day: str
    min_strengthening_alive: int = 3


def _event_id(prefix: str, parts: list[str]) -> str:
    seed = prefix + "|" + "|".join(parts)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def detect_theme_leader_break_board(
    inputs: LeaderBreakInputs,
) -> list[MarketEvent]:
    """When a high-height (>= min_consecutive_boards) leader breaks, emit
    THEME_LEADER_BREAK_BOARD events for the theme."""
    events: list[MarketEvent] = []
    timestamp = now_iso()
    for leader in inputs.leaders:
        if leader.leader_status != "broken":
            continue
        if leader.leader_consecutive_boards < inputs.min_consecutive_boards:
            continue
        score = min(
            100.0,
            _BREAK_BOARD_BASE_SCORE
            + _BREAK_BOARD_HEIGHT_BONUS * float(leader.leader_consecutive_boards),
        )
        events.append(
            MarketEvent(
                event_id=_event_id(
                    "THEME_LEADER_BREAK_BOARD",
                    [leader.theme, leader.leader_symbol, inputs.trading_day],
                ),
                event_type="THEME_LEADER_BREAK_BOARD",
                symbol=leader.leader_symbol,
                name=leader.leader_name,
                theme=leader.theme,
                confidence="medium",
                score=score,
                evidence=[
                    f"theme={leader.theme}",
                    f"leader={leader.leader_symbol}",
                    f"consecutive={leader.leader_consecutive_boards}",
                    f"final_status={leader.leader_status}",
                ],
                provider_timestamp=timestamp,
                received_at=timestamp,
                freshness_status="fresh",
                suggested_agent_action=[
                    "downgrade_followers_in_same_theme",
                    "explain_break_board_risk_to_user",
                ],
                data={
                    "trading_day": inputs.trading_day,
                    "theme": leader.theme,
                    "leader_symbol": leader.leader_symbol,
                    "consecutive_boards": leader.leader_consecutive_boards,
                    "co_leader_symbols": list(leader.co_leader_symbols),
                },
            )
        )
    return events


def detect_sector_rotation(
    inputs: SectorRotationInputs,
) -> list[MarketEvent]:
    """When one theme's leader is broken AND another theme's leader is sealed
    with N>= alive followers, emit a SECTOR_ROTATION event linking the two."""
    events: list[MarketEvent] = []
    timestamp = now_iso()
    weak: list[ThemeLeader] = []
    strong: list[ThemeLeader] = []
    for leader in inputs.leaders:
        if leader.leader_status == "broken":
            weak.append(leader)
        elif leader.leader_status in {"sealed", "reopened"}:
            if leader.member_count >= inputs.min_strengthening_alive:
                strong.append(leader)
    if not weak or not strong:
        return events
    for w in weak:
        for s in strong:
            if w.theme == s.theme:
                continue
            evidence_model = SectorRotationEvidence(
                weakening_theme=w.theme,
                weakening_leader_status=w.leader_status,
                strengthening_theme=s.theme,
                strengthening_leader_status=s.leader_status,
                weakening_alive_count=0,
                strengthening_alive_count=s.member_count,
            )
            score = min(
                100.0,
                _ROTATION_BASE_SCORE
                + _ROTATION_FOLLOWER_BONUS * float(s.member_count),
            )
            events.append(
                MarketEvent(
                    event_id=_event_id(
                        "SECTOR_ROTATION",
                        [w.theme, s.theme, inputs.trading_day],
                    ),
                    event_type="SECTOR_ROTATION",
                    symbol="",
                    name="",
                    theme=s.theme,
                    confidence="medium",
                    score=score,
                    evidence=[
                        f"weakening_theme={w.theme}",
                        f"strengthening_theme={s.theme}",
                        f"strengthening_alive={s.member_count}",
                    ],
                    provider_timestamp=timestamp,
                    received_at=timestamp,
                    freshness_status="fresh",
                    suggested_agent_action=[
                        "rerank_themes",
                        "watch_strengthening_theme_followers",
                    ],
                    data=evidence_model.model_dump(),
                )
            )
    return events
```

- [ ] **Step 4: 跑测试确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_sector_events.py -k break_board -v`
Expected: 3 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/extensions/sector_events.py tests/extensions/test_sector_events.py
git commit -m "Add detect_theme_leader_break_board"
```

---

### Task 3: detect_sector_rotation 检测器

**Files:**
- Modify: `tests/extensions/test_sector_events.py` (Task 2 中已有 detect_sector_rotation 实现，仅补测试)

- [ ] **Step 1: 写失败测试**

追加到 `tests/extensions/test_sector_events.py`：

```python
from aegis_alpha.extensions.sector_events import (
    SectorRotationInputs,
    detect_sector_rotation,
)


def _strong_leader(theme="AI", member_count=5):
    return ThemeLeader(
        theme=theme,
        trading_day="2026-06-01",
        leader_symbol=f"L-{theme}",
        leader_name=theme,
        leader_consecutive_boards=2,
        leader_first_limit_up_time="09:31:00",
        leader_seal_amount_cny=200_000_000.0,
        leader_status="sealed",
        co_leader_symbols=[],
        member_count=member_count,
    )


def _weak_leader(theme="军工"):
    return ThemeLeader(
        theme=theme,
        trading_day="2026-06-01",
        leader_symbol=f"L-{theme}",
        leader_name=theme,
        leader_consecutive_boards=3,
        leader_first_limit_up_time="09:30:30",
        leader_seal_amount_cny=120_000_000.0,
        leader_status="broken",
        co_leader_symbols=[],
        member_count=2,
    )


def test_sector_rotation_event_when_one_breaks_and_other_strengthens():
    inputs = SectorRotationInputs(
        leaders=[_weak_leader("军工"), _strong_leader("AI", member_count=5)],
        trading_day="2026-06-01",
        min_strengthening_alive=3,
    )
    events = detect_sector_rotation(inputs)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "SECTOR_ROTATION"
    assert ev.theme == "AI"
    assert ev.data["weakening_theme"] == "军工"
    assert ev.data["strengthening_theme"] == "AI"
    assert ev.score >= 65


def test_sector_rotation_event_skipped_when_no_strong_leader():
    inputs = SectorRotationInputs(
        leaders=[_weak_leader("军工"), _strong_leader("AI", member_count=2)],
        trading_day="2026-06-01",
        min_strengthening_alive=3,
    )
    events = detect_sector_rotation(inputs)
    assert events == []


def test_sector_rotation_event_skipped_when_no_weak_leader():
    inputs = SectorRotationInputs(
        leaders=[_strong_leader("AI", member_count=5)],
        trading_day="2026-06-01",
        min_strengthening_alive=3,
    )
    events = detect_sector_rotation(inputs)
    assert events == []
```

- [ ] **Step 2: 跑确认 GREEN**（Task 2 实现已就绪，本步直接 GREEN）

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_sector_events.py -v`
Expected: 6 PASS（Task 2 的 3 + Task 3 的 3）。

如有失败说明 Task 2 实现有 bug，须修复 Task 2 的 sector_events.py 后再合并。

- [ ] **Step 3: 提交**

```bash
git add tests/extensions/test_sector_events.py
git commit -m "Add detect_sector_rotation test coverage"
```

---

## 子系统 B — 跨周期校验（Tasks 4–6）

### Task 4: WeeklyPosition 模型 + 候选契约新字段

**Files:**
- Modify: `src/aegis_alpha/models.py`
- Test: `tests/test_p5_models.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_p5_models.py`：

```python
def test_weekly_position_model_construct():
    from aegis_alpha.models import WeeklyPosition

    pos = WeeklyPosition(
        symbol="600519",
        trading_day="2026-06-01",
        weekly_high=2100.0,
        weekly_low=1820.0,
        weekly_close=1995.0,
        position_pct=0.625,  # (1995-1820)/(2100-1820) ≈ 0.625
        weeks_in_uptrend=3,
        ma20_above_ma60=True,
    )
    assert pos.symbol == "600519"
    assert 0.0 <= pos.position_pct <= 1.0
    assert pos.weeks_in_uptrend == 3


def test_second_board_candidate_has_weekly_health_score_default():
    from aegis_alpha.models import SecondBoardCandidate

    fields = set(SecondBoardCandidate.model_fields.keys())
    assert "weekly_health_score" in fields
    # default should be 50.0 (neutral)
    default = SecondBoardCandidate.model_fields["weekly_health_score"].default
    assert abs(default - 50.0) < 1e-6
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py -k "weekly_position or weekly_health_score" -v`
Expected: FAIL。

- [ ] **Step 3: 在 `models.py` 加 `WeeklyPosition` 模型**

在文件末尾追加：

```python
class WeeklyPosition(BaseModel):
    """从周线视角衡量个股位置健康度。"""

    symbol: str
    trading_day: str
    weekly_high: float = 0.0
    weekly_low: float = 0.0
    weekly_close: float = 0.0
    position_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    weeks_in_uptrend: int = 0
    ma20_above_ma60: bool = False
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
```

- [ ] **Step 4: 在 `SecondBoardCandidate` 加 `weekly_health_score` 字段**

在 `SecondBoardCandidate` 类内、紧挨着 P5 加的 `intraday_pattern` 字段之后，插入：

```python
    weekly_health_score: float = Field(default=50.0, ge=0.0, le=100.0)
```

- [ ] **Step 5: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py -k "weekly_position or weekly_health_score" -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/models.py tests/test_p5_models.py
git commit -m "Add WeeklyPosition model + weekly_health_score field"
```

---

### Task 5: get_weekly_position adapter 接入

**Files:**
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Create: `src/aegis_alpha/extensions/weekly_position.py`
- Create: `tests/extensions/test_weekly_position.py`

- [ ] **Step 1: 写失败测试 — pure function**

写入 `tests/extensions/test_weekly_position.py`：

```python
from aegis_alpha.models import WeeklyPosition
from aegis_alpha.extensions.weekly_position import (
    compute_weekly_health_score,
)


def _pos(position_pct=0.5, weeks_uptrend=2, ma_above=True):
    return WeeklyPosition(
        symbol="X",
        trading_day="2026-06-01",
        weekly_high=110.0,
        weekly_low=90.0,
        weekly_close=100.0,
        position_pct=position_pct,
        weeks_in_uptrend=weeks_uptrend,
        ma20_above_ma60=ma_above,
    )


def test_weekly_health_score_high_when_strong_position_and_uptrend():
    score = compute_weekly_health_score(_pos(0.85, weeks_uptrend=4, ma_above=True))
    assert score >= 75.0


def test_weekly_health_score_low_when_weak_position_no_uptrend_ma_below():
    score = compute_weekly_health_score(_pos(0.05, weeks_uptrend=0, ma_above=False))
    assert score <= 25.0


def test_weekly_health_score_neutral_when_mid():
    score = compute_weekly_health_score(_pos(0.5, weeks_uptrend=1, ma_above=True))
    assert 40.0 <= score <= 60.0


def test_weekly_health_score_clamped_to_0_100():
    extreme = WeeklyPosition(
        symbol="X", trading_day="2026-06-01",
        weekly_high=200.0, weekly_low=50.0, weekly_close=200.0,
        position_pct=1.0, weeks_in_uptrend=20, ma20_above_ma60=True,
    )
    score = compute_weekly_health_score(extreme)
    assert 0.0 <= score <= 100.0


def test_mock_adapter_returns_weekly_position():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    pos = adapter.get_weekly_position("600519")
    assert isinstance(pos, WeeklyPosition)
    assert pos.symbol == "600519"
    assert pos.data_mode == "mock"
    assert 0.0 <= pos.position_pct <= 1.0


def test_jvquant_adapter_get_weekly_position_returns_placeholder():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    pos = adapter.get_weekly_position("600519")
    assert pos.symbol == "600519"
    assert pos.data_mode == "placeholder"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_weekly_position.py -v`
Expected: FAIL（模块/方法未实现）。

- [ ] **Step 3: 写 pure function 实现**

写入 `src/aegis_alpha/extensions/weekly_position.py`：

```python
from __future__ import annotations

from aegis_alpha.models import WeeklyPosition


def compute_weekly_health_score(pos: WeeklyPosition) -> float:
    """Combine position_pct (40%) + weeks_in_uptrend (40%) + ma_above (20%).

    Returns a 0-100 score where 50 is neutral. The weights are starter values;
    P6 follow-up issue may calibrate against historical limit-up outcomes.
    """
    position_component = max(0.0, min(1.0, pos.position_pct)) * 100.0
    uptrend_normalized = max(0.0, min(1.0, pos.weeks_in_uptrend / 8.0)) * 100.0
    ma_component = 100.0 if pos.ma20_above_ma60 else 0.0
    weighted = (
        0.4 * position_component
        + 0.4 * uptrend_normalized
        + 0.2 * ma_component
    )
    return max(0.0, min(100.0, weighted))
```

- [ ] **Step 4: 在 `protocols.py` 增方法签名**

在 `MarketDataAdapter` Protocol 类内（`get_capital_flow_slices` 之后）追加：

```python
def get_weekly_position(self, symbol: str) -> WeeklyPosition: ...
```

并把 `WeeklyPosition` 加到现有 import。

- [ ] **Step 5: 实现 mock adapter**

在 `mock_market_data.py` 顶部 import 增 `WeeklyPosition`，类末追加：

```python
def get_weekly_position(self, symbol: str) -> WeeklyPosition:
    return WeeklyPosition(
        symbol=symbol,
        trading_day="2026-06-01",
        weekly_high=110.0,
        weekly_low=90.0,
        weekly_close=102.0,
        position_pct=0.6,
        weeks_in_uptrend=2,
        ma20_above_ma60=True,
        notes=["mock weekly position"],
        provider="mock",
        data_mode="mock",
    )
```

- [ ] **Step 6: 实现 jvquant adapter（placeholder）**

在 `adapters/jvquant/adapter.py` 顶部 import 增 `WeeklyPosition`，类末追加：

```python
def get_weekly_position(self, symbol: str) -> WeeklyPosition:
    # P6 starter: jvQuant 周线接口尚未对齐契约，placeholder 起步。
    return WeeklyPosition(
        symbol=symbol,
        trading_day="",
        weekly_high=0.0,
        weekly_low=0.0,
        weekly_close=0.0,
        position_pct=0.0,
        weeks_in_uptrend=0,
        ma20_above_ma60=False,
        notes=["placeholder: jvQuant weekly endpoint not wired"],
        provider="jvquant",
        data_mode="placeholder",
    )
```

- [ ] **Step 7: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_weekly_position.py -v`
Expected: 6 PASS。

- [ ] **Step 8: 提交**

```bash
git add src/aegis_alpha/protocols.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py \
    src/aegis_alpha/extensions/weekly_position.py \
    tests/extensions/test_weekly_position.py
git commit -m "Wire get_weekly_position adapter + weekly health score"
```

---

### Task 6: 候选契约接入 weekly_health_score

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant/candidates.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/mcp/server.py` (compact 输出加字段)
- Test: `tests/test_jvquant_candidates.py`, `tests/test_mock_adapter.py`, `tests/test_mcp_p5_tools.py`

- [ ] **Step 1: 写失败测试 — mock**

追加到 `tests/test_mock_adapter.py`：

```python
def test_mock_candidate_includes_weekly_health_score():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    candidates = adapter.get_second_board_candidates()
    assert candidates
    for cand in candidates:
        assert hasattr(cand, "weekly_health_score")
        assert 0.0 <= cand.weekly_health_score <= 100.0
    # 至少一只非默认 50 分
    scores = {c.weekly_health_score for c in candidates}
    assert scores - {50.0}, "mock should expose at least one calibrated weekly_health_score"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k weekly_health -v`
Expected: FAIL（mock 没填）。

- [ ] **Step 3: mock 给至少一个候选填非默认分**

在 `mock_market_data.py:get_second_board_candidates` 中，给第一只候选追加 `weekly_health_score=78.0`，第二只 `weekly_health_score=42.0`，其他保持默认即可。

- [ ] **Step 4: 跑确认 mock GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mock_adapter.py -k weekly_health -v`
Expected: PASS。

- [ ] **Step 5: 写 jvquant 测试**

追加到 `tests/test_jvquant_candidates.py`：

```python
def test_jvquant_candidate_has_weekly_health_score_in_range():
    from unittest.mock import patch

    candidates = _build_candidates_with_minimal_patches()
    for cand in candidates:
        assert 0.0 <= cand.weekly_health_score <= 100.0
```

跑确认 RED（`weekly_health_score` 应该是默认 50.0，但因为模型已加默认值，测试可能直接 PASS）。如果默认 PASS，加严：

```python
def test_jvquant_candidate_weekly_health_score_uses_adapter_call():
    from unittest.mock import patch

    from aegis_alpha.models import WeeklyPosition

    fixed_pos = WeeklyPosition(
        symbol="STUB", trading_day="2026-06-01",
        weekly_high=120.0, weekly_low=100.0, weekly_close=118.0,
        position_pct=0.9, weeks_in_uptrend=4, ma20_above_ma60=True,
    )

    candidates = _build_candidates_with_minimal_patches()
    if not candidates:
        return

    # 重新构造一次：patch 掉 get_weekly_position 让它返回固定 high-score 的 WeeklyPosition
    from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
    from aegis_alpha.models import LadderEntry

    adapter = JvQuantMarketDataAdapter(token="fake")
    adapter._client = FakeJvQuantClient()  # type: ignore[attr-defined]

    def fake_ladder(symbol: str, trading_day: str = "") -> LadderEntry:
        return LadderEntry(symbol=symbol, trading_day="2026-06-01",
                           consecutive_boards=1, height_label="first_board")

    with patch.object(adapter, "get_limit_up_ladder", side_effect=fake_ladder), \
         patch.object(adapter, "get_theme_leaders", return_value=[]), \
         patch.object(adapter, "get_weekly_position", return_value=fixed_pos):
        out = adapter.get_second_board_candidates()
    assert all(c.weekly_health_score >= 75.0 for c in out)
```

- [ ] **Step 6: 跑 jvquant RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py -k weekly_health -v`
Expected: FAIL（jvquant build_one_candidate 还没接入 weekly_position）。

- [ ] **Step 7: 在 `jvquant/candidates.py:build_one_candidate` 接入**

在文件 import 区追加：

```python
from aegis_alpha.extensions.weekly_position import compute_weekly_health_score
```

注意 `build_one_candidate` 没有 `self`，目前是 module-level function。它接收的 fixture / 上下文里如果还没有 weekly_position，就让 `build_second_board_candidate` 接收一个新参数 `weekly_health_score: float = 50.0`，由调用方（`get_second_board_candidates`）注入。

具体修改：在 `JvQuantMarketDataAdapter.get_second_board_candidates`（或 `build_one_candidate` 调用处）调用 `self.get_weekly_position(symbol)`，把结果通过 `compute_weekly_health_score` 转成 float，然后传给 build_one_candidate 的新 kwarg。

最小改动是：
1. `build_one_candidate` 签名末尾加 `weekly_health_score: float = 50.0`
2. 在 `SecondBoardCandidate(...)` 字面量里加 `weekly_health_score=weekly_health_score`
3. 在 `JvQuantMarketDataAdapter.get_second_board_candidates` 循环里：

   ```python
   try:
       weekly_pos = self.get_weekly_position(symbol)
       weekly_score = compute_weekly_health_score(weekly_pos)
   except Exception:
       weekly_score = 50.0
   candidate = build_one_candidate(
       ...,
       weekly_health_score=weekly_score,
   )
   ```

如果 jvquant adapter 直接调用 `build_second_board_candidate` 而不是 `build_one_candidate`，按同样逻辑改 wrapper。

- [ ] **Step 8: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_jvquant_candidates.py tests/test_mock_adapter.py -k weekly_health -v`
Expected: PASS。

- [ ] **Step 9: compact MCP 输出加字段**

修改 `src/aegis_alpha/mcp/server.py:get_second_board_candidates_compact` 中的 dict 字面量，追加：

```python
"weekly_health_score": candidate.weekly_health_score,
```

并加测试到 `tests/test_mcp_p5_tools.py`：

```python
def test_compact_candidate_includes_weekly_health_score():
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "weekly_health_score" in item
        assert 0.0 <= item["weekly_health_score"] <= 100.0
```

- [ ] **Step 10: 全量跑 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p5_tools.py tests/test_jvquant_candidates.py tests/test_mock_adapter.py -v`
Expected: 全部 PASS。

- [ ] **Step 11: 提交**

```bash
git add src/aegis_alpha/adapters/jvquant/candidates.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/mcp/server.py \
    tests/test_jvquant_candidates.py tests/test_mock_adapter.py \
    tests/test_mcp_p5_tools.py
git commit -m "Wire weekly_health_score into SecondBoardCandidate + compact output"
```

---

## 子系统 C — 相似形态搜索（Tasks 7–10）

### Task 7: SimilarSetupResult 模型

**Files:**
- Modify: `src/aegis_alpha/models.py`
- Test: `tests/test_p5_models.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_p5_models.py`：

```python
def test_similar_setup_result_model_construct():
    from aegis_alpha.models import SimilarSetupResult

    res = SimilarSetupResult(
        query_symbol="600519",
        match_symbol="000858",
        match_trading_day="2025-11-12",
        similarity=0.83,
        match_grade_at_pick="A",
        match_outcome_summary="sealed_second_board=True",
        notes=["同板块 + 同高度"],
    )
    assert res.similarity == 0.83
    assert res.match_grade_at_pick == "A"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py -k similar_setup -v`
Expected: FAIL。

- [ ] **Step 3: 在 `models.py` 末尾追加模型**

```python
class SimilarSetupResult(BaseModel):
    """find_similar_setups 的单条返回。"""

    query_symbol: str
    match_symbol: str
    match_trading_day: str
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    match_grade_at_pick: str = "C"
    match_outcome_summary: str = ""
    feature_diffs: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p5_models.py -k similar_setup -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/models.py tests/test_p5_models.py
git commit -m "Add SimilarSetupResult model"
```

---

### Task 8: vectorize_setup + cosine_similarity 纯函数

**Files:**
- Create: `src/aegis_alpha/extensions/similar_setups.py`
- Create: `tests/extensions/test_similar_setups.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/extensions/test_similar_setups.py`：

```python
from aegis_alpha.extensions.similar_setups import (
    SetupVector,
    cosine_similarity,
    vectorize_setup,
)


def test_vectorize_setup_produces_5_dim_vector():
    payload = {
        "previous_consecutive_boards": 2,
        "same_theme_rising_count": 5,
        "seal_amount_cny": 200_000_000.0,
        "five_min_speed_pct": 3.5,
        "auction_change_pct": 1.2,
    }
    vec = vectorize_setup(payload)
    assert isinstance(vec, SetupVector)
    assert len(vec.values) == 5
    assert all(isinstance(v, float) for v in vec.values)


def test_cosine_similarity_identical_returns_one():
    payload = {
        "previous_consecutive_boards": 2,
        "same_theme_rising_count": 5,
        "seal_amount_cny": 200_000_000.0,
        "five_min_speed_pct": 3.5,
        "auction_change_pct": 1.2,
    }
    a = vectorize_setup(payload)
    b = vectorize_setup(payload)
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_returns_zero():
    a = SetupVector(values=[1.0, 0.0, 0.0, 0.0, 0.0])
    b = SetupVector(values=[0.0, 1.0, 0.0, 0.0, 0.0])
    assert abs(cosine_similarity(a, b) - 0.0) < 1e-9


def test_cosine_similarity_zero_vector_returns_zero():
    a = SetupVector(values=[0.0, 0.0, 0.0, 0.0, 0.0])
    b = SetupVector(values=[1.0, 1.0, 1.0, 1.0, 1.0])
    assert cosine_similarity(a, b) == 0.0


def test_vectorize_setup_handles_missing_fields_with_zeros():
    vec = vectorize_setup({})
    assert vec.values == [0.0, 0.0, 0.0, 0.0, 0.0]
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_similar_setups.py -v`
Expected: FAIL（模块未创建）。

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/extensions/similar_setups.py`：

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


_VECTOR_DIM = 5
# Per-axis normalization scale — chosen to keep typical values in [0, 1]
_AXIS_SCALES = (
    5.0,             # previous_consecutive_boards: 5+ 板封顶
    30.0,            # same_theme_rising_count: 30+ 封顶（板块极端火爆）
    500_000_000.0,   # seal_amount_cny: 5 亿封顶（折成 0~1）
    10.0,            # five_min_speed_pct: 10% 算极强涨速
    5.0,             # auction_change_pct: 5% 算极端高开
)


@dataclass(frozen=True)
class SetupVector:
    values: list[float]


def _safe_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def vectorize_setup(payload: dict[str, Any]) -> SetupVector:
    """Convert a candidate snapshot payload (dict) into a 5-dim normalized vector.

    Missing fields default to 0. Returned values are clipped to [0, 1] per axis.
    """
    raw = (
        _safe_float(payload.get("previous_consecutive_boards")),
        _safe_float(payload.get("same_theme_rising_count")),
        _safe_float(payload.get("seal_amount_cny")),
        _safe_float(payload.get("five_min_speed_pct")),
        _safe_float(payload.get("auction_change_pct")),
    )
    normalized = [
        max(0.0, min(1.0, raw[i] / _AXIS_SCALES[i])) for i in range(_VECTOR_DIM)
    ]
    return SetupVector(values=normalized)


def cosine_similarity(a: SetupVector, b: SetupVector) -> float:
    if len(a.values) != len(b.values):
        return 0.0
    dot = sum(x * y for x, y in zip(a.values, b.values))
    norm_a = math.sqrt(sum(x * x for x in a.values))
    norm_b = math.sqrt(sum(y * y for y in b.values))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_similar_setups.py -v`
Expected: 5 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/extensions/similar_setups.py tests/extensions/test_similar_setups.py
git commit -m "Add SetupVector + cosine_similarity for similar-setup search"
```

---

### Task 9: find_similar_setups 在历史快照上查找

**Files:**
- Modify: `src/aegis_alpha/extensions/similar_setups.py` (扩展)
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Test: `tests/extensions/test_similar_setups.py`, `tests/test_p6_storage.py`

- [ ] **Step 1: 写失败测试 — pure search 函数**

追加到 `tests/extensions/test_similar_setups.py`：

```python
def test_find_similar_setups_filters_by_threshold(tmp_path):
    """find_similar_setups builds vectors over a list of historical snapshots
    and returns those above a similarity threshold, sorted desc."""
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.extensions.similar_setups import (
        find_similar_setups_in_snapshots,
        SetupVector,
        vectorize_setup,
    )

    query = vectorize_setup(
        {
            "previous_consecutive_boards": 2,
            "same_theme_rising_count": 6,
            "seal_amount_cny": 200_000_000.0,
            "five_min_speed_pct": 4.0,
            "auction_change_pct": 1.0,
        }
    )

    snaps = [
        HistoricalCandidateSnapshot(
            symbol="A", trading_day="2025-11-12", grade_at_pick="A",
            grade_reason="", theme="X", theme_role="leader",
            previous_consecutive_boards=2,
            payload_json=(
                '{"previous_consecutive_boards": 2,'
                ' "same_theme_rising_count": 6,'
                ' "seal_amount_cny": 200000000.0,'
                ' "five_min_speed_pct": 4.0,'
                ' "auction_change_pct": 1.0}'
            ),
            created_at="t",
        ),
        HistoricalCandidateSnapshot(
            symbol="B", trading_day="2025-11-13", grade_at_pick="C",
            grade_reason="", theme="X", theme_role="follower",
            previous_consecutive_boards=0,
            payload_json='{"previous_consecutive_boards": 0}',
            created_at="t",
        ),
    ]

    results = find_similar_setups_in_snapshots(
        query_symbol="QUERY",
        query_vector=query,
        snapshots=snaps,
        similarity_threshold=0.9,
        limit=10,
    )
    # A 完全相同 → 1.0；B 几乎为零向量 → 低于 0.9
    symbols = [r.match_symbol for r in results]
    assert symbols == ["A"]
    assert results[0].similarity >= 0.99
    assert results[0].match_grade_at_pick == "A"


def test_mock_adapter_find_similar_setups_returns_list():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    out = adapter.find_similar_setups("600519", lookback_days=30, similarity_threshold=0.5)
    assert isinstance(out, list)
    for item in out:
        assert item.query_symbol == "600519"
        assert 0.0 <= item.similarity <= 1.0
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_similar_setups.py -k "find_similar_setups_filters_by_threshold or mock_adapter_find_similar_setups" -v`
Expected: FAIL。

- [ ] **Step 3: 在 `similar_setups.py` 加 search 函数**

追加到 `src/aegis_alpha/extensions/similar_setups.py`：

```python
import json

from aegis_alpha.models import HistoricalCandidateSnapshot, SimilarSetupResult


def find_similar_setups_in_snapshots(
    *,
    query_symbol: str,
    query_vector: SetupVector,
    snapshots: list[HistoricalCandidateSnapshot],
    similarity_threshold: float = 0.7,
    limit: int = 10,
) -> list[SimilarSetupResult]:
    """Score each snapshot against the query and return matches above threshold."""
    results: list[SimilarSetupResult] = []
    for snap in snapshots:
        if snap.symbol == query_symbol:
            continue
        try:
            payload = json.loads(snap.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        snap_vector = vectorize_setup(payload)
        sim = cosine_similarity(query_vector, snap_vector)
        if sim < similarity_threshold:
            continue
        feature_diffs: dict[str, float] = {}
        for i, axis in enumerate(
            ("previous_consecutive_boards", "same_theme_rising_count",
             "seal_amount_cny", "five_min_speed_pct", "auction_change_pct")
        ):
            feature_diffs[axis] = round(
                snap_vector.values[i] - query_vector.values[i], 4
            )
        results.append(
            SimilarSetupResult(
                query_symbol=query_symbol,
                match_symbol=snap.symbol,
                match_trading_day=snap.trading_day,
                similarity=round(sim, 4),
                match_grade_at_pick=snap.grade_at_pick,
                match_outcome_summary="",  # 由 storage 层加 outcome join 填
                feature_diffs=feature_diffs,
                notes=[],
            )
        )
    results.sort(key=lambda r: r.similarity, reverse=True)
    return results[: max(1, limit)]
```

- [ ] **Step 4: 在 `protocols.py` 加 adapter 方法签名**

```python
def find_similar_setups(
    self,
    symbol: str,
    *,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[SimilarSetupResult]: ...
```

并把 `SimilarSetupResult` 加到现有 import。

- [ ] **Step 5: 实现 mock adapter**

在 `mock_market_data.py` 顶部 import 增 `SimilarSetupResult`，类末追加：

```python
def find_similar_setups(
    self,
    symbol: str,
    *,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[SimilarSetupResult]:
    return [
        SimilarSetupResult(
            query_symbol=symbol,
            match_symbol="000858",
            match_trading_day="2025-11-12",
            similarity=0.85,
            match_grade_at_pick="A",
            match_outcome_summary="sealed_second_board=True",
            feature_diffs={
                "previous_consecutive_boards": 0.0,
                "same_theme_rising_count": -0.05,
                "seal_amount_cny": -0.10,
                "five_min_speed_pct": 0.05,
                "auction_change_pct": 0.0,
            },
            notes=["mock 相似形态"],
        ),
    ]
```

- [ ] **Step 6: 实现 jvquant adapter**

`adapters/jvquant/adapter.py` import 增 `SimilarSetupResult`，类末追加：

```python
def find_similar_setups(
    self,
    symbol: str,
    *,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[SimilarSetupResult]:
    """Search historical candidate snapshots stored by P4 backfill for setups
    similar to the most recent snapshot for `symbol`.

    Returns an empty list when no recent snapshot for `symbol` exists or when
    the historical pool is empty.
    """
    from datetime import date, timedelta

    from aegis_alpha.extensions.similar_setups import (
        find_similar_setups_in_snapshots,
        vectorize_setup,
    )

    store = self._store  # type: ignore[attr-defined]
    if store is None:
        return []
    today = date.today()
    start_day = (today - timedelta(days=max(1, lookback_days))).isoformat()
    end_day = today.isoformat()

    snaps = store.list_historical_snapshots_between(
        start_day=start_day, end_day=end_day, symbol=symbol
    )
    if not snaps:
        return []
    latest = snaps[-1]
    try:
        import json as _json
        latest_payload = _json.loads(latest.payload_json or "{}")
    except Exception:
        latest_payload = {}
    query_vec = vectorize_setup(latest_payload)

    pool = store.list_historical_snapshots_between(
        start_day=start_day, end_day=end_day
    )
    return find_similar_setups_in_snapshots(
        query_symbol=symbol,
        query_vector=query_vec,
        snapshots=pool,
        similarity_threshold=similarity_threshold,
        limit=10,
    )
```

如果 `JvQuantMarketDataAdapter` 还没有 `_store` 属性，请打开 adapter 构造器加 optional `store` 参数（默认 `None`），让 MCP server 注入：在 `JvQuantMarketDataAdapter.__init__` 末尾加 `self._store = None`，并补一个 `set_store(self, store)` 方法供 server 端注入。

最简策略是：MCP server 的 `_call_tool` 在每次调用前给 adapter 注入 `store`，无需持久关联。如果不想改 adapter 构造器，让 `find_similar_setups` 接收一个 `_store=None` 参数从外部注入也行。

**避免破坏**：若上述 `_store` 注入复杂度过高，可让 jvquant `find_similar_setups` 直接返回 `[]` 作为 placeholder，让 MCP 工具层自己组装：在 `mcp/server.py:find_similar_setups` 工具实现里，直接用 `_call_store` 拿到 store + adapter（通过 `_call_tool`），自己跑 `find_similar_setups_in_snapshots`。本方案更简单，**优先采用**：jvquant adapter 内 `find_similar_setups` 返回 `[]`（placeholder），真正的搜索逻辑放在 MCP server 工具里（Task 10）。

修改后 jvquant 实现：

```python
def find_similar_setups(
    self,
    symbol: str,
    *,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[SimilarSetupResult]:
    # P6 starter: real search runs in MCP layer (combines adapter + store).
    # See mcp/server.py:find_similar_setups.
    return []
```

- [ ] **Step 7: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_similar_setups.py -v`
Expected: 7 PASS。

- [ ] **Step 8: 提交**

```bash
git add src/aegis_alpha/extensions/similar_setups.py \
    src/aegis_alpha/protocols.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py \
    tests/extensions/test_similar_setups.py
git commit -m "Add find_similar_setups_in_snapshots + adapter methods"
```

---

### Task 10: MCP 工具 find_similar_setups（组合 adapter + store）

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p6_tools.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_mcp_p6_tools.py`：

```python
def test_find_similar_setups_tool_returns_list():
    from aegis_alpha.mcp.server import find_similar_setups

    result = find_similar_setups("600519", 90, 0.5)
    assert isinstance(result, list) or isinstance(result, dict)


def test_find_similar_setups_rejects_empty_symbol():
    from aegis_alpha.mcp.server import find_similar_setups

    res = find_similar_setups("", 90, 0.5)
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k find_similar_setups -v`
Expected: FAIL。

- [ ] **Step 3: 实现 MCP tool**

在 `src/aegis_alpha/mcp/server.py` 末尾（`get_capital_flow_slices` 之后）追加：

```python
@mcp.tool
def find_similar_setups(
    symbol: str,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[dict] | dict:
    """Find historical candidate snapshots structurally similar to the most
    recent snapshot of `symbol` (5-dim cosine similarity)."""
    from datetime import date, timedelta
    import json as _json

    from aegis_alpha.extensions.similar_setups import (
        find_similar_setups_in_snapshots,
        vectorize_setup,
    )

    safe_symbol = symbol.strip()
    if not safe_symbol:
        return {"data_mode": "unavailable", "error": "symbol is required"}
    safe_lookback = max(1, min(int(lookback_days or 90), 365))
    safe_threshold = max(0.0, min(float(similarity_threshold or 0.7), 1.0))

    def _run(store: AegisAlphaStore) -> list[dict]:
        today = date.today()
        start_day = (today - timedelta(days=safe_lookback)).isoformat()
        end_day = today.isoformat()
        snaps_for_symbol = store.list_historical_snapshots_between(
            start_day=start_day, end_day=end_day, symbol=safe_symbol
        )
        if not snaps_for_symbol:
            return []
        latest = snaps_for_symbol[-1]
        try:
            latest_payload = _json.loads(latest.payload_json or "{}")
        except Exception:
            latest_payload = {}
        query_vec = vectorize_setup(latest_payload)
        pool = store.list_historical_snapshots_between(
            start_day=start_day, end_day=end_day
        )
        results = find_similar_setups_in_snapshots(
            query_symbol=safe_symbol,
            query_vector=query_vec,
            snapshots=pool,
            similarity_threshold=safe_threshold,
            limit=10,
        )
        return [r.model_dump() for r in results]

    return _call_store(_run)
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k find_similar_setups -v`
Expected: PASS。

- [ ] **Step 5: 加 yaml include**

在 `.hermes/config/aegis-alpha-mcp.yaml` `include:` 列表追加：

```yaml
        - find_similar_setups
```

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p6_tools.py
git commit -m "Expose find_similar_setups MCP tool"
```

---

## 子系统 D — 次新股专用通道（Tasks 11–12）

### Task 11: NewStockCandidate 模型 + adapter 方法

**Files:**
- Modify: `src/aegis_alpha/models.py`
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Create: `src/aegis_alpha/extensions/new_stocks.py`
- Create: `tests/extensions/test_new_stocks.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/extensions/test_new_stocks.py`：

```python
from aegis_alpha.models import NewStockCandidate


def test_new_stock_candidate_model_construct():
    cand = NewStockCandidate(
        symbol="688001",
        name="mock-次新-1",
        listing_date="2026-04-15",
        days_since_listing=47,
        free_float_market_cap_cny=2_500_000_000.0,
        current_change_pct=8.4,
        notes=["mock 次新"],
    )
    assert cand.days_since_listing == 47
    assert cand.free_float_market_cap_cny == 2_500_000_000.0


def test_classify_new_stock_tier_smallcap_recent():
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    tier = classify_new_stock_tier(days_since_listing=20, free_float_cny=500_000_000)
    assert tier == "tier_a_smallcap_recent"


def test_classify_new_stock_tier_largecap():
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    tier = classify_new_stock_tier(days_since_listing=60, free_float_cny=10_000_000_000.0)
    assert tier == "tier_c_largecap"


def test_classify_new_stock_tier_aged_out():
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    tier = classify_new_stock_tier(days_since_listing=200, free_float_cny=2_000_000_000.0)
    assert tier == "tier_aged_out"


def test_mock_adapter_get_new_stock_candidates_returns_list():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    out = adapter.get_new_stock_candidates()
    assert isinstance(out, list)
    assert all(isinstance(c, NewStockCandidate) for c in out)
    assert all(c.days_since_listing < 365 for c in out)


def test_jvquant_adapter_get_new_stock_candidates_placeholder():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    out = adapter.get_new_stock_candidates()
    assert out == []
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_new_stocks.py -v`
Expected: FAIL。

- [ ] **Step 3: 加 `NewStockCandidate` 模型 + Literal**

在 `models.py` Literal 区追加：

```python
NewStockTier = Literal[
    "tier_a_smallcap_recent",
    "tier_b_midcap_recent",
    "tier_c_largecap",
    "tier_aged_out",
    "unknown",
]
```

并在文件末尾追加：

```python
class NewStockCandidate(BaseModel):
    symbol: str
    name: str
    listing_date: str
    days_since_listing: int = 0
    free_float_market_cap_cny: float = 0.0
    current_change_pct: float = 0.0
    tier: NewStockTier = "unknown"
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
```

- [ ] **Step 4: 写 `extensions/new_stocks.py`**

```python
from __future__ import annotations

from aegis_alpha.models import NewStockTier


_AGED_OUT_DAYS = 180
_SMALLCAP_THRESHOLD_CNY = 1_000_000_000.0
_LARGECAP_THRESHOLD_CNY = 5_000_000_000.0
_RECENT_DAYS = 30


def classify_new_stock_tier(
    *, days_since_listing: int, free_float_cny: float
) -> NewStockTier:
    if days_since_listing > _AGED_OUT_DAYS:
        return "tier_aged_out"
    if free_float_cny >= _LARGECAP_THRESHOLD_CNY:
        return "tier_c_largecap"
    if days_since_listing <= _RECENT_DAYS and free_float_cny < _SMALLCAP_THRESHOLD_CNY:
        return "tier_a_smallcap_recent"
    return "tier_b_midcap_recent"
```

- [ ] **Step 5: protocols + mock + jvquant**

`protocols.py`：

```python
def get_new_stock_candidates(self) -> list[NewStockCandidate]: ...
```

import 增 `NewStockCandidate`。

mock：

```python
def get_new_stock_candidates(self) -> list[NewStockCandidate]:
    from aegis_alpha.extensions.new_stocks import classify_new_stock_tier

    days = 22
    cap = 600_000_000.0
    return [
        NewStockCandidate(
            symbol="688001",
            name="mock-次新-科创",
            listing_date="2026-05-10",
            days_since_listing=days,
            free_float_market_cap_cny=cap,
            current_change_pct=8.4,
            tier=classify_new_stock_tier(
                days_since_listing=days, free_float_cny=cap,
            ),
            notes=["mock smallcap recent"],
            provider="mock",
            data_mode="mock",
        ),
        NewStockCandidate(
            symbol="301099",
            name="mock-次新-创业",
            listing_date="2026-04-20",
            days_since_listing=42,
            free_float_market_cap_cny=2_500_000_000.0,
            current_change_pct=4.5,
            tier=classify_new_stock_tier(
                days_since_listing=42, free_float_cny=2_500_000_000.0,
            ),
            notes=["mock midcap"],
            provider="mock",
            data_mode="mock",
        ),
    ]
```

import 增 `NewStockCandidate`。

jvquant：

```python
def get_new_stock_candidates(self) -> list[NewStockCandidate]:
    # P6 starter: jvQuant 次新通道字段映射尚未确认。
    return []
```

import 增 `NewStockCandidate`。

- [ ] **Step 6: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/extensions/test_new_stocks.py -v`
Expected: 6 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/aegis_alpha/models.py src/aegis_alpha/protocols.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py \
    src/aegis_alpha/extensions/new_stocks.py \
    tests/extensions/test_new_stocks.py
git commit -m "Add NewStockCandidate + tier classifier + adapter wiring"
```

---

### Task 12: get_new_stock_candidates MCP tool

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p6_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p6_tools.py`：

```python
def test_get_new_stock_candidates_returns_list():
    from aegis_alpha.mcp.server import get_new_stock_candidates

    out = get_new_stock_candidates()
    assert isinstance(out, list)
    if out:
        item = out[0]
        assert "symbol" in item and "tier" in item
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k new_stock -v`
Expected: FAIL。

- [ ] **Step 3: 实现工具**

在 `mcp/server.py` 末尾追加：

```python
@mcp.tool
def get_new_stock_candidates() -> list[dict]:
    """Return today's new-stock candidates classified by free-float and listing days."""
    return _call_tool(
        lambda adapter: [c.model_dump() for c in adapter.get_new_stock_candidates()]
    )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k new_stock -v`
Expected: PASS。

- [ ] **Step 5: yaml include**

```yaml
        - get_new_stock_candidates
```

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p6_tools.py
git commit -m "Expose get_new_stock_candidates MCP tool"
```

---

## 子系统 E — 停牌处理（Tasks 13–15）

### Task 13: 迁移 m0006 + SuspendedStock 模型

**Files:**
- Create: `src/aegis_alpha/db_migrations_files/m0006_p6_extensions.py`
- Create: `tests/test_db_migrations_p6.py`
- Modify: `src/aegis_alpha/models.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_db_migrations_p6.py`：

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_p6_migration_creates_suspended_stocks_table(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "suspended_stocks" in names
    assert current_version(db) >= 6


def test_p6_indexes_exist(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_suspended_day" in names
```

并追加到 `tests/test_p5_models.py`（沿用既有 P5 测试文件）：

```python
def test_suspended_stock_model_construct():
    from aegis_alpha.models import SuspendedStock

    s = SuspendedStock(
        symbol="600519", name="贵州茅台",
        suspension_start_day="2026-05-25",
        suspension_end_day="",
        reason="重大事项",
    )
    assert s.symbol == "600519"
    assert s.suspension_end_day == ""
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_db_migrations_p6.py tests/test_p5_models.py -k suspended -v`
Expected: FAIL。

- [ ] **Step 3: 写迁移**

写入 `src/aegis_alpha/db_migrations_files/m0006_p6_extensions.py`：

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS suspended_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            suspension_start_day TEXT NOT NULL,
            suspension_end_day TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(symbol, suspension_start_day)
        );
        CREATE INDEX IF NOT EXISTS idx_suspended_day
            ON suspended_stocks (suspension_start_day);
        CREATE INDEX IF NOT EXISTS idx_suspended_symbol
            ON suspended_stocks (symbol);
        """
    )
```

- [ ] **Step 4: 加 `SuspendedStock` 模型**

在 `models.py` 末尾追加：

```python
class SuspendedStock(BaseModel):
    symbol: str
    name: str = ""
    suspension_start_day: str
    suspension_end_day: str = ""
    reason: str = ""
    notes: list[str] = Field(default_factory=list)
    provider: str = "mock"
    data_mode: str = "mock"
```

- [ ] **Step 5: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_db_migrations_p6.py tests/test_p5_models.py -k suspended -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/db_migrations_files/m0006_p6_extensions.py \
    src/aegis_alpha/models.py \
    tests/test_db_migrations_p6.py \
    tests/test_p5_models.py
git commit -m "Add migration m0006: suspended_stocks + SuspendedStock model"
```

---

### Task 14: 停牌 storage + adapter

**Files:**
- Modify: `src/aegis_alpha/storage.py`
- Modify: `src/aegis_alpha/protocols.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Create: `src/aegis_alpha/extensions/suspended_stocks.py`
- Create: `tests/extensions/test_suspended_stocks.py`
- Create/Modify: `tests/test_p6_storage.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_p6_storage.py`：

```python
from aegis_alpha.models import SuspendedStock
from aegis_alpha.storage import AegisAlphaStore


def test_save_and_list_suspended_stocks(tmp_path):
    store = AegisAlphaStore(str(tmp_path / "p6.db"))
    store.init_db()

    a = SuspendedStock(
        symbol="600519", name="A", suspension_start_day="2026-05-25",
        suspension_end_day="", reason="重大事项",
    )
    b = SuspendedStock(
        symbol="000001", name="B", suspension_start_day="2026-05-26",
        suspension_end_day="2026-05-28", reason="重大资产重组",
    )
    store.save_suspended_stock(a, created_at="t1")
    store.save_suspended_stock(b, created_at="t2")

    rows = store.list_suspended_stocks(trading_day="2026-05-26")
    symbols = {r.symbol for r in rows}
    # A 仍处于停牌（end_day 为空）；B 在 2026-05-26 也是停牌
    assert symbols == {"600519", "000001"}

    rows_after = store.list_suspended_stocks(trading_day="2026-05-29")
    # B 已复牌（2026-05-28 截止）；A 仍未复牌
    after_symbols = {r.symbol for r in rows_after}
    assert after_symbols == {"600519"}
```

并写入 `tests/extensions/test_suspended_stocks.py`：

```python
def test_is_symbol_suspended_returns_true_when_present():
    from aegis_alpha.models import SuspendedStock
    from aegis_alpha.extensions.suspended_stocks import is_symbol_suspended

    rows = [
        SuspendedStock(symbol="600519", suspension_start_day="2026-05-20",
                       suspension_end_day=""),
    ]
    assert is_symbol_suspended("600519", trading_day="2026-05-25", suspended=rows)


def test_is_symbol_suspended_false_when_resumed():
    from aegis_alpha.models import SuspendedStock
    from aegis_alpha.extensions.suspended_stocks import is_symbol_suspended

    rows = [
        SuspendedStock(symbol="600519", suspension_start_day="2026-05-20",
                       suspension_end_day="2026-05-22"),
    ]
    assert not is_symbol_suspended("600519", trading_day="2026-05-25", suspended=rows)


def test_mock_adapter_get_suspended_stocks():
    from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter

    adapter = MockMarketDataAdapter()
    out = adapter.get_suspended_stocks(trading_day="2026-06-01")
    assert isinstance(out, list)
    assert all(s.data_mode == "mock" for s in out)
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p6_storage.py tests/extensions/test_suspended_stocks.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 storage 方法**

打开 `storage.py`，import 区追加 `SuspendedStock`。在 `AegisAlphaStore` 类内（紧挨 P5 capital flow 方法之后）追加：

```python
def save_suspended_stock(
    self, entry: SuspendedStock, *, created_at: str
) -> None:
    with self._connect() as conn:
        conn.execute(
            """
            INSERT INTO suspended_stocks (
                symbol, suspension_start_day, suspension_end_day, reason,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, suspension_start_day) DO UPDATE SET
                suspension_end_day = excluded.suspension_end_day,
                reason = excluded.reason,
                payload_json = excluded.payload_json
            """,
            (
                entry.symbol,
                entry.suspension_start_day,
                entry.suspension_end_day,
                entry.reason,
                entry.model_dump_json(),
                created_at,
            ),
        )

def list_suspended_stocks(
    self, *, trading_day: str = ""
) -> list[SuspendedStock]:
    """List suspended stocks. If trading_day given, only return entries that
    are active on that day (start_day <= trading_day < end_day, or end_day blank)."""
    with self._connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM suspended_stocks ORDER BY suspension_start_day ASC"
        ).fetchall()
    out: list[SuspendedStock] = []
    for row in rows:
        s = SuspendedStock.model_validate_json(row[0])
        if not trading_day:
            out.append(s)
            continue
        if s.suspension_start_day > trading_day:
            continue
        if s.suspension_end_day and s.suspension_end_day < trading_day:
            continue
        out.append(s)
    return out
```

注意：边界比较是字符串比较（`YYYY-MM-DD` 格式可直接字典序），且复牌日 `suspension_end_day < trading_day` 视为已复牌。`suspension_end_day` 含义是「最后一个停牌日」；`trading_day == suspension_end_day` 仍按停牌处理。

- [ ] **Step 4: 写 `extensions/suspended_stocks.py`**

```python
from __future__ import annotations

from aegis_alpha.models import SuspendedStock


def is_symbol_suspended(
    symbol: str,
    *,
    trading_day: str,
    suspended: list[SuspendedStock],
) -> bool:
    for s in suspended:
        if s.symbol != symbol:
            continue
        if s.suspension_start_day > trading_day:
            continue
        if s.suspension_end_day and s.suspension_end_day < trading_day:
            continue
        return True
    return False
```

- [ ] **Step 5: 实现 protocols + mock + jvquant**

`protocols.py` 类内：

```python
def get_suspended_stocks(self, trading_day: str = "") -> list[SuspendedStock]: ...
```

import 增 `SuspendedStock`。

mock：

```python
def get_suspended_stocks(self, trading_day: str = "") -> list[SuspendedStock]:
    return [
        SuspendedStock(
            symbol="600519", name="mock-停牌-1",
            suspension_start_day="2026-05-25", suspension_end_day="",
            reason="重大事项", provider="mock", data_mode="mock",
        ),
    ]
```

import 增 `SuspendedStock`。

jvquant placeholder：

```python
def get_suspended_stocks(self, trading_day: str = "") -> list[SuspendedStock]:
    # P6 starter: jvQuant 停牌字段映射尚未对齐。
    return []
```

- [ ] **Step 6: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_p6_storage.py tests/extensions/test_suspended_stocks.py -v`
Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add src/aegis_alpha/storage.py src/aegis_alpha/protocols.py \
    src/aegis_alpha/adapters/mock_market_data.py \
    src/aegis_alpha/adapters/jvquant/adapter.py \
    src/aegis_alpha/extensions/suspended_stocks.py \
    tests/test_p6_storage.py tests/extensions/test_suspended_stocks.py
git commit -m "Add suspended_stocks storage + adapter wiring"
```

---

### Task 15: get_suspended_stocks MCP tool

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p6_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p6_tools.py`：

```python
def test_get_suspended_stocks_returns_list():
    from aegis_alpha.mcp.server import get_suspended_stocks

    out = get_suspended_stocks("2026-06-01")
    assert isinstance(out, list)
    if out:
        assert "symbol" in out[0]
        assert "suspension_start_day" in out[0]
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k suspended -v`
Expected: FAIL。

- [ ] **Step 3: 实现工具**

```python
@mcp.tool
def get_suspended_stocks(trading_day: str = "") -> list[dict]:
    """Return suspended stocks active on the given trading day."""
    safe_day = trading_day.strip()
    return _call_tool(
        lambda adapter: [
            s.model_dump() for s in adapter.get_suspended_stocks(safe_day)
        ]
    )
```

- [ ] **Step 4: GREEN + yaml include**

```yaml
        - get_suspended_stocks
```

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k suspended -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p6_tools.py
git commit -m "Expose get_suspended_stocks MCP tool"
```

---

## 子系统 F — Parquet 历史层（Tasks 16–19）

### Task 16: 可选依赖组 + history_store 包骨架

**Files:**
- Modify: `pyproject.toml`
- Create: `src/aegis_alpha/history_store/__init__.py`
- Create: `tests/history_store/__init__.py`
- Create: `tests/history_store/test_availability.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/history_store/__init__.py`（空文件）。

写入 `tests/history_store/test_availability.py`：

```python
def test_is_history_store_available_returns_bool():
    from aegis_alpha.history_store import is_history_store_available

    val = is_history_store_available()
    assert isinstance(val, bool)


def test_history_store_unavailable_error_message():
    from aegis_alpha.history_store import history_store_unavailable_error

    msg = history_store_unavailable_error()
    assert "history-store extras not installed" in msg
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/history_store/test_availability.py -v`
Expected: FAIL（模块未创建）。

- [ ] **Step 3: 修改 pyproject.toml — 增加 history-store 组**

打开 `pyproject.toml`。在 `[project.optional-dependencies]` 之下追加：

```toml
history-store = [
    "pyarrow>=15.0.0,<20.0.0",
    "duckdb>=0.10.0,<2.0.0",
]
```

- [ ] **Step 4: 创建 `history_store/__init__.py`**

```python
"""P6 Parquet history store. Optional dependencies: pyarrow + duckdb."""

from __future__ import annotations


def is_history_store_available() -> bool:
    """Return True iff pyarrow and duckdb can be imported."""
    try:
        import pyarrow  # noqa: F401
        import duckdb  # noqa: F401
    except ImportError:
        return False
    return True


def history_store_unavailable_error() -> str:
    return (
        "history-store extras not installed: install with "
        "`pip install '.[history-store]'` "
        "(pyarrow + duckdb)."
    )
```

- [ ] **Step 5: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/history_store/test_availability.py -v`
Expected: 2 PASS。

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml \
    src/aegis_alpha/history_store/__init__.py \
    tests/history_store/__init__.py \
    tests/history_store/test_availability.py
git commit -m "Add history_store package skeleton + history-store optional deps"
```

---

### Task 17: MinuteBarWriter

**Files:**
- Create: `src/aegis_alpha/history_store/parquet_writer.py`
- Create: `tests/history_store/test_parquet_writer.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/history_store/test_parquet_writer.py`：

```python
import pytest

from aegis_alpha.history_store import is_history_store_available

if not is_history_store_available():
    pytest.skip("pyarrow / duckdb not installed", allow_module_level=True)


def test_minute_bar_writer_writes_one_partition(tmp_path):
    from aegis_alpha.history_store.parquet_writer import MinuteBarWriter

    writer = MinuteBarWriter(root_dir=str(tmp_path))
    bars = [
        {"time": "09:30:00", "last_price": 100.0, "volume": 1000.0, "average_price": 100.0},
        {"time": "09:31:00", "last_price": 100.5, "volume": 800.0, "average_price": 100.2},
    ]
    path = writer.write_minute_bars(
        symbol="600519", trading_day="2026-06-01", bars=bars,
    )
    import pathlib
    assert pathlib.Path(path).exists()
    assert "600519" in path
    assert "2026-06-01" in path


def test_minute_bar_writer_overwrites_existing_partition(tmp_path):
    from aegis_alpha.history_store.parquet_writer import MinuteBarWriter

    writer = MinuteBarWriter(root_dir=str(tmp_path))
    bars1 = [{"time": "09:30:00", "last_price": 100.0, "volume": 1000.0, "average_price": 100.0}]
    bars2 = [{"time": "09:30:00", "last_price": 105.0, "volume": 2000.0, "average_price": 105.0}]
    writer.write_minute_bars(symbol="X", trading_day="2026-06-01", bars=bars1)
    path = writer.write_minute_bars(symbol="X", trading_day="2026-06-01", bars=bars2)

    import pyarrow.parquet as pq
    table = pq.read_table(path)
    assert table.num_rows == 1
    last_price = table.column("last_price")[0].as_py()
    assert abs(last_price - 105.0) < 1e-9
```

- [ ] **Step 2: 跑确认 RED**（如本地装了 history-store extras）

Run: `PYTHONPATH=src .venv/bin/pytest tests/history_store/test_parquet_writer.py -v`
Expected: FAIL（模块未创建）。

如果 `pyarrow` / `duckdb` 没装，测试会 skip。在主开发流程中先 `.venv/bin/pip install '.[history-store]'`。

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/history_store/parquet_writer.py`：

```python
from __future__ import annotations

import pathlib
from typing import Any


class MinuteBarWriter:
    """Write minute bars to Parquet partitioned by symbol/trading_day.

    Layout: {root_dir}/minute_bars/{symbol}/{trading_day}.parquet
    """

    def __init__(self, root_dir: str) -> None:
        self.root_dir = pathlib.Path(root_dir)
        self._minute_dir = self.root_dir / "minute_bars"

    def _partition_path(self, symbol: str, trading_day: str) -> pathlib.Path:
        return self._minute_dir / symbol / f"{trading_day}.parquet"

    def write_minute_bars(
        self,
        *,
        symbol: str,
        trading_day: str,
        bars: list[dict[str, Any]],
    ) -> str:
        """Overwrite the (symbol, trading_day) partition with the given bars.
        Returns the absolute filepath of the written Parquet file.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self._partition_path(symbol, trading_day)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not bars:
            # 空数据写一个空文件
            schema = pa.schema(
                [
                    ("time", pa.string()),
                    ("last_price", pa.float64()),
                    ("volume", pa.float64()),
                    ("average_price", pa.float64()),
                ]
            )
            table = pa.Table.from_pylist([], schema=schema)
        else:
            normalized = [
                {
                    "time": str(b.get("time", "")),
                    "last_price": float(b.get("last_price", 0.0)),
                    "volume": float(b.get("volume", 0.0)),
                    "average_price": float(b.get("average_price", 0.0)),
                }
                for b in bars
            ]
            table = pa.Table.from_pylist(normalized)
        pq.write_table(table, str(path))
        return str(path)
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/history_store/test_parquet_writer.py -v`
Expected: 2 PASS（前提是装了 history-store extras）。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/history_store/parquet_writer.py \
    tests/history_store/test_parquet_writer.py
git commit -m "Add MinuteBarWriter for Parquet history layer"
```

---

### Task 18: MinuteBarReader（DuckDB 查询）

**Files:**
- Create: `src/aegis_alpha/history_store/parquet_reader.py`
- Create: `tests/history_store/test_parquet_reader.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/history_store/test_parquet_reader.py`：

```python
import pytest

from aegis_alpha.history_store import is_history_store_available

if not is_history_store_available():
    pytest.skip("pyarrow / duckdb not installed", allow_module_level=True)


def test_minute_bar_reader_returns_rows_for_partition(tmp_path):
    from aegis_alpha.history_store.parquet_writer import MinuteBarWriter
    from aegis_alpha.history_store.parquet_reader import MinuteBarReader

    writer = MinuteBarWriter(root_dir=str(tmp_path))
    bars = [
        {"time": "09:30:00", "last_price": 100.0, "volume": 1000.0, "average_price": 100.0},
        {"time": "09:31:00", "last_price": 100.5, "volume": 800.0, "average_price": 100.2},
    ]
    writer.write_minute_bars(symbol="600519", trading_day="2026-06-01", bars=bars)

    reader = MinuteBarReader(root_dir=str(tmp_path))
    rows = reader.read_minute_bars(
        symbol="600519", start_day="2026-06-01", end_day="2026-06-01"
    )
    assert len(rows) == 2
    assert rows[0]["time"] == "09:30:00"


def test_minute_bar_reader_returns_empty_for_missing_partition(tmp_path):
    from aegis_alpha.history_store.parquet_reader import MinuteBarReader

    reader = MinuteBarReader(root_dir=str(tmp_path))
    rows = reader.read_minute_bars(
        symbol="ZZZ", start_day="2026-06-01", end_day="2026-06-01"
    )
    assert rows == []
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/history_store/test_parquet_reader.py -v`
Expected: FAIL。

- [ ] **Step 3: 写实现**

写入 `src/aegis_alpha/history_store/parquet_reader.py`：

```python
from __future__ import annotations

import pathlib
from typing import Any


class MinuteBarReader:
    """Read minute bars from Parquet via DuckDB for date-range queries."""

    def __init__(self, root_dir: str) -> None:
        self.root_dir = pathlib.Path(root_dir)
        self._minute_dir = self.root_dir / "minute_bars"

    def read_minute_bars(
        self, *, symbol: str, start_day: str, end_day: str
    ) -> list[dict[str, Any]]:
        import duckdb

        symbol_dir = self._minute_dir / symbol
        if not symbol_dir.exists():
            return []

        glob = str(symbol_dir / "*.parquet")
        query = (
            "SELECT time, last_price, volume, average_price, "
            f"regexp_extract(filename, '([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})\\.parquet$', 1) AS trading_day "
            f"FROM read_parquet('{glob}', filename=true) "
            "WHERE trading_day BETWEEN ? AND ? "
            "ORDER BY trading_day, time"
        )
        try:
            con = duckdb.connect()
            rows = con.execute(query, (start_day, end_day)).fetchall()
            cols = ["time", "last_price", "volume", "average_price", "trading_day"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception as exc:
            # 没分区或查询失败时返回 []，让上层 MCP 工具优雅降级
            return []
        finally:
            try:
                con.close()
            except Exception:
                pass
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/history_store/test_parquet_reader.py -v`
Expected: 2 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/history_store/parquet_reader.py \
    tests/history_store/test_parquet_reader.py
git commit -m "Add MinuteBarReader using DuckDB"
```

---

### Task 19: query_minute_bars MCP 工具（优雅降级）

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p6_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p6_tools.py`：

```python
def test_query_minute_bars_returns_list_or_unavailable_dict():
    from aegis_alpha.mcp.server import query_minute_bars

    res = query_minute_bars("600519", "2026-06-01", "2026-06-01")
    if isinstance(res, dict):
        assert res.get("data_mode") == "unavailable"
    else:
        assert isinstance(res, list)


def test_query_minute_bars_rejects_empty_args():
    from aegis_alpha.mcp.server import query_minute_bars

    res = query_minute_bars("", "2026-06-01", "2026-06-01")
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k minute_bars -v`
Expected: FAIL。

- [ ] **Step 3: 实现工具**

在 `mcp/server.py` 末尾追加：

```python
@mcp.tool
def query_minute_bars(symbol: str, start_day: str, end_day: str) -> list[dict] | dict:
    """Query Parquet-stored minute bars for a symbol over a date range.

    Returns a list of bar dicts. If history-store extras (pyarrow + duckdb)
    are not installed, returns {"data_mode": "unavailable", "error": ...}.
    """
    from aegis_alpha.history_store import (
        history_store_unavailable_error,
        is_history_store_available,
    )

    safe_symbol = symbol.strip()
    safe_start = start_day.strip()
    safe_end = end_day.strip()
    if not (safe_symbol and safe_start and safe_end):
        return {
            "data_mode": "unavailable",
            "error": "symbol / start_day / end_day are required",
        }
    if not is_history_store_available():
        return {
            "data_mode": "unavailable",
            "error": history_store_unavailable_error(),
        }

    from aegis_alpha.history_store.parquet_reader import MinuteBarReader

    reader = MinuteBarReader(root_dir="data")
    return reader.read_minute_bars(
        symbol=safe_symbol, start_day=safe_start, end_day=safe_end,
    )
```

- [ ] **Step 4: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k minute_bars -v`
Expected: PASS。

- [ ] **Step 5: yaml include**

```yaml
        - query_minute_bars
```

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p6_tools.py
git commit -m "Expose query_minute_bars MCP tool with graceful degradation"
```

---

## 子系统 G — 假设分析（Tasks 20–21）

### Task 20: simulate_outcome 纯函数

**Files:**
- Create: `src/aegis_alpha/feedback/hypothesis.py`
- Create: `tests/feedback/test_hypothesis.py`
- Modify: `src/aegis_alpha/models.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/feedback/test_hypothesis.py`：

```python
def test_simulate_outcome_changes_grade_when_seal_amount_doubled(tmp_path):
    """If we hypothesize the seal amount is 2x larger, the rule may upgrade grade.
    With the existing P4 rule_changes (no auto-upgrade), grade stays 'B' but
    we still receive a structured comparison."""
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
    assert out.original_grade == "B"
    assert out.applied_hypothesis == {"seal_amount_cny": 200_000_000.0}
    # The result includes a delta map between original and hypothetical payload
    assert "seal_amount_cny" in out.payload_diff


def test_simulate_outcome_returns_none_when_snapshot_payload_invalid():
    from aegis_alpha.models import HistoricalCandidateSnapshot
    from aegis_alpha.feedback.hypothesis import simulate_outcome, HypothesisInputs

    snap = HistoricalCandidateSnapshot(
        symbol="X", trading_day="2026-05-30", grade_at_pick="C",
        grade_reason="", theme="Y", theme_role="follower",
        previous_consecutive_boards=0,
        payload_json="not valid json",
        created_at="t",
    )
    out = simulate_outcome(
        HypothesisInputs(snapshot=snap, hypothesis={"seal_amount_cny": 1})
    )
    assert out is None
```

并在 `tests/feedback/__init__.py` 不存在时新建（空文件）。

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -v`
Expected: FAIL。

- [ ] **Step 3: 在 `models.py` 加 `HypothesisOutcome`**

```python
class HypothesisOutcome(BaseModel):
    symbol: str
    trading_day: str
    original_grade: str = "C"
    hypothetical_grade: str = "C"
    applied_hypothesis: dict[str, Any] = Field(default_factory=dict)
    payload_diff: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 写实现**

写入 `src/aegis_alpha/feedback/hypothesis.py`：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aegis_alpha.models import HistoricalCandidateSnapshot, HypothesisOutcome


@dataclass(frozen=True)
class HypothesisInputs:
    snapshot: HistoricalCandidateSnapshot
    hypothesis: dict[str, Any]


def simulate_outcome(inputs: HypothesisInputs) -> HypothesisOutcome | None:
    """Apply `hypothesis` (a dict of field overrides) to the snapshot's payload
    and return a structured comparison.

    Returns None when the snapshot payload is not valid JSON.
    """
    try:
        payload = json.loads(inputs.snapshot.payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

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

    # P6 starter: until a real re-grading hook is wired, the hypothetical grade
    # is left equal to the original grade. The structured diff is the artifact.
    return HypothesisOutcome(
        symbol=inputs.snapshot.symbol,
        trading_day=inputs.snapshot.trading_day,
        original_grade=inputs.snapshot.grade_at_pick,
        hypothetical_grade=inputs.snapshot.grade_at_pick,
        applied_hypothesis=dict(inputs.hypothesis),
        payload_diff=payload_diff,
        notes=[
            "starter: re-grading hook not yet wired; only payload diff returned"
        ],
    )
```

- [ ] **Step 5: 跑确认 GREEN**

Run: `PYTHONPATH=src .venv/bin/pytest tests/feedback/test_hypothesis.py -v`
Expected: 2 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/aegis_alpha/feedback/hypothesis.py \
    src/aegis_alpha/models.py \
    tests/feedback/test_hypothesis.py
git commit -m "Add simulate_outcome hypothesis pure function"
```

---

### Task 21: simulate_outcome MCP 工具

**Files:**
- Modify: `src/aegis_alpha/mcp/server.py`
- Modify: `.hermes/config/aegis-alpha-mcp.yaml`
- Test: `tests/test_mcp_p6_tools.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_mcp_p6_tools.py`：

```python
def test_simulate_outcome_rejects_empty_args():
    from aegis_alpha.mcp.server import simulate_outcome

    res = simulate_outcome("", "2026-05-30", "{}")
    assert isinstance(res, dict)
    assert res.get("data_mode") == "unavailable"


def test_simulate_outcome_returns_unavailable_when_no_snapshot():
    from aegis_alpha.mcp.server import simulate_outcome

    res = simulate_outcome("ZZZ", "2026-05-30", "{}")
    assert isinstance(res, dict)
    # 当快照不存在时也走 unavailable 分支
    assert res.get("data_mode") == "unavailable"
```

- [ ] **Step 2: 跑确认 RED**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k simulate_outcome -v`
Expected: FAIL。

- [ ] **Step 3: 实现工具**

```python
@mcp.tool
def simulate_outcome(
    symbol: str, trading_day: str, hypothesis_json: str
) -> dict:
    """Apply a hypothesis (JSON-encoded dict of field overrides) to the
    historical snapshot for (symbol, trading_day) and return structured diff."""
    import json as _json

    from aegis_alpha.feedback.hypothesis import simulate_outcome as _simulate
    from aegis_alpha.feedback.hypothesis import HypothesisInputs

    safe_symbol = symbol.strip()
    safe_day = trading_day.strip()
    if not (safe_symbol and safe_day):
        return {"data_mode": "unavailable",
                "error": "symbol and trading_day are required"}
    try:
        hypothesis = _json.loads(hypothesis_json or "{}")
    except _json.JSONDecodeError as exc:
        return {"data_mode": "unavailable",
                "error": f"hypothesis_json invalid: {exc}"}
    if not isinstance(hypothesis, dict):
        return {"data_mode": "unavailable",
                "error": "hypothesis_json must decode to an object"}

    def _run(store: AegisAlphaStore) -> dict:
        snap = store.get_historical_snapshot(safe_symbol, safe_day)
        if snap is None:
            return {"data_mode": "unavailable",
                    "error": "no historical snapshot for given symbol/day"}
        out = _simulate(HypothesisInputs(snapshot=snap, hypothesis=hypothesis))
        if out is None:
            return {"data_mode": "unavailable",
                    "error": "snapshot payload not valid JSON"}
        return out.model_dump()

    return _call_store(_run)
```

- [ ] **Step 4: 跑 GREEN + yaml include**

```yaml
        - simulate_outcome
```

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_mcp_p6_tools.py -k simulate_outcome -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/aegis_alpha/mcp/server.py .hermes/config/aegis-alpha-mcp.yaml \
    tests/test_mcp_p6_tools.py
git commit -m "Expose simulate_outcome MCP tool"
```

---

## 子系统 H — 文档与回归（Tasks 22–23）

### Task 22: README + SKILL.md 同步 P6

**Files:**
- Modify: `README.md`
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: README MCP Tools 列表 + jvQuant 列表追加 7 个工具**

打开 `/Users/faillonexie/Projects/aegis-alpha/README.md`。在「MCP Tools」简单列表中加：

```markdown
- `find_similar_setups`
- `get_new_stock_candidates`
- `get_suspended_stocks`
- `query_minute_bars`
- `simulate_outcome`
- `get_weekly_position`
- `get_dragon_tiger_seats_today`  # （如未来需要：本计划暂不暴露 active_seats，只是给 dragon-tiger placeholder 改了语义；保留行作记号即可，否则跳过）
```

注意 `get_weekly_position` 在 P6 暂未注册为 MCP tool（是 adapter 方法）。可以选择**不**把 `get_weekly_position` 写入 README — 因为它没暴露给 Hermes。本任务只需追加：

```markdown
- `find_similar_setups`
- `get_new_stock_candidates`
- `get_suspended_stocks`
- `query_minute_bars`
- `simulate_outcome`
```

5 个新 MCP 工具。

并在 jvQuant 工具签名列表追加：

```markdown
- `find_similar_setups(symbol, lookback_days, similarity_threshold)`
- `get_new_stock_candidates()`
- `get_suspended_stocks(trading_day)`
- `query_minute_bars(symbol, start_day, end_day)`
- `simulate_outcome(symbol, trading_day, hypothesis_json)`
```

- [ ] **Step 2: 加 P6 段落**

在 P5 数据扩展段落后追加：

```markdown
P6 进阶事件与生态（自 2026-06 起）增加了 7 个能力：

- 板块事件 — `THEME_LEADER_BREAK_BOARD` / `SECTOR_ROTATION` 加入 `MarketEventType`；检测器在 `extensions/sector_events.py`，runner 在 P6 起步阶段不会自动调用，由后续 issue 接入。
- 跨周期校验 — adapter 增 `get_weekly_position(symbol)`（mock 完整 / jvquant placeholder）；候选契约新增 `weekly_health_score ∈ [0, 100]`，由 jvquant `build_one_candidate` 通过 `compute_weekly_health_score` 自动注入。
- 相似形态搜索 — `find_similar_setups(symbol, lookback_days, similarity_threshold)` 在 P4 历史快照上做 5 维余弦匹配（连板高度 / 同题材数 / 封单 / 涨速 / 竞价）。
- 次新股专用通道 — `get_new_stock_candidates()` 返回按上市天数与流通市值分层（`tier_a_smallcap_recent` / `tier_b_midcap_recent` / `tier_c_largecap` / `tier_aged_out`）的次新股候选。
- 停牌处理 — `suspended_stocks` 表 + `get_suspended_stocks(trading_day)`；候选拉取链路可在 P6 后续接 `is_symbol_suspended` 过滤掉停牌股。
- Parquet 历史层（可选 extras） — `pip install '.[history-store]'` 启用 pyarrow + duckdb；`MinuteBarWriter` 写入按 `{symbol}/{trading_day}.parquet` 分区，`MinuteBarReader` 通过 DuckDB 跨分区查询；MCP 工具 `query_minute_bars` 在依赖缺失时优雅降级返回 `data_mode=unavailable`。
- 假设分析 — `simulate_outcome(symbol, trading_day, hypothesis_json)` 在历史快照上做单股假设回测，返回结构化的 `payload_diff`。

P6 阈值（如 `_MESSY_BREAK_THRESHOLD`、`_HOT_MONEY_NET_BUY_THRESHOLD`、`_AGED_OUT_DAYS`）目前是 starter 常量，待 P7 历史校准。
```

- [ ] **Step 3: SKILL.md Required Tools + Workflow**

打开 `/Users/faillonexie/Projects/aegis-alpha/.hermes/skills/second-board-radar/SKILL.md`。在 Core / Useful 工具列表追加：

```text
- `find_similar_setups`
- `get_new_stock_candidates`
- `get_suspended_stocks`
- `query_minute_bars`
- `simulate_outcome`
```

并在 Standard Workflow 追加 21 项：

```text
21. P6 进阶能力（按需使用）：
    - `find_similar_setups(symbol, lookback_days, similarity_threshold)` 在复盘候选时找相似历史样本；当返回的 `similarity ≥ 0.85` 且 `match_grade_at_pick = A`，可作为「这个形态历史上确实经常打成功」的弱证据，但不要替代当下行情判断。
    - `get_new_stock_candidates()` 返回的 `tier_aged_out` 不应再按次新处理；`tier_a_smallcap_recent` 才是典型的次新打板候选。
    - `get_suspended_stocks(trading_day)` 在每次拉候选前检查；候选若出现在停牌列表中应直接 REJECT 并提示数据脏。
    - `query_minute_bars(symbol, start_day, end_day)` 仅在 history-store extras 安装后可用；返回 `data_mode=unavailable` 时直接告诉用户分钟级历史层未启用。
    - `simulate_outcome(symbol, trading_day, hypothesis_json)` 在用户问「如果当时封单是 X 亿，评级会变吗？」时调用；返回 `payload_diff` 是结构化对比，不是确定性结论。
    - 候选契约里的 `weekly_health_score` ≥ 70 表示周线位置健康，可加分；< 30 应在评级原因里点出周线劣势。
```

- [ ] **Step 4: 提交**

```bash
git add README.md .hermes/skills/second-board-radar/SKILL.md
git commit -m "Document P6 MCP tools and workflow guidance"
```

---

### Task 23: 全量回归 + smoke

**Files:** （只验证，不写新文件，除非发现 bug）

- [ ] **Step 1: 全量单测**

Run: `PYTHONPATH=src .venv/bin/pytest tests/ -q --no-header 2>&1 | tail -10`
Expected: 仅余 P3 已知的 2 个 `_time_or_unknown` / `_seal_quality_score` 失败（其他 P0–P5 测试 + 全部 P6 新测试通过）。

如有新失败，回到对应 task 修复，写新 commit（不要 amend）。

- [ ] **Step 2: compileall**

Run: `.venv/bin/python -m compileall src scripts tests -q`
Expected: 无 SyntaxError。

- [ ] **Step 3: smoke check**

Run: `PYTHONPATH=src .venv/bin/python scripts/smoke_check.py`
Expected: 退出码 0。

- [ ] **Step 4: import 7 个新 MCP tool**

Run: `PYTHONPATH=src .venv/bin/python -c "from aegis_alpha.mcp.server import find_similar_setups, get_new_stock_candidates, get_suspended_stocks, query_minute_bars, simulate_outcome; print('ok')"`
Expected: 输出 `ok`。

- [ ] **Step 5: history-store 可选依赖独立验证**

如果 history-store extras 已安装：

```bash
PYTHONPATH=src .venv/bin/python -c "from aegis_alpha.history_store import is_history_store_available; print(is_history_store_available())"
```

Expected: `True`。如果输出 `False`，说明 extras 未装（不阻塞 P6 完成 — 计划允许 history_store 为可选）。

- [ ] **Step 6: 不需要新提交**（仅验证）。如发现回归，修复后单独 commit。

---

## Self-Review Checklist

| 项 | 状态 |
|----|------|
| A. 板块事件：`THEME_LEADER_BREAK_BOARD` + `SECTOR_ROTATION` 检测器 + 模型 | ✅ Tasks 1–3 |
| B. 跨周期：`WeeklyPosition` + `weekly_health_score` + adapter + compact MCP | ✅ Tasks 4–6 |
| C. 相似形态：`SetupVector` + cosine + `find_similar_setups` 在历史快照上 + MCP | ✅ Tasks 7–10 |
| D. 次新：`NewStockCandidate` + tier 分类器 + adapter + MCP | ✅ Tasks 11–12 |
| E. 停牌：m0006 迁移 + storage + `is_symbol_suspended` + MCP | ✅ Tasks 13–15 |
| F. Parquet：可选依赖组 + MinuteBarWriter + Reader（DuckDB） + MCP 优雅降级 | ✅ Tasks 16–19 |
| G. 假设分析：`simulate_outcome` + MCP | ✅ Tasks 20–21 |
| H. 文档同步 + 全量回归 | ✅ Tasks 22–23 |
| 不重复 `THEME_DIVERGENCE`（已在 P3 落地） | ✅ Task 1 / Task 2 注明 |
| 所有 ON CONFLICT DO UPDATE 不覆盖 `created_at` | ✅ m0006 + storage 方法遵循 P5 模式 |
| Parquet 依赖缺失时 MCP 工具优雅降级 | ✅ Task 19 |
| 不修改 LLM 模型名（`claude-opus-4-7`、`deepseek-v4-pro`） | ✅ 本计划无 LLM 模型变更 |
| 所有候选契约新字段默认值（`weekly_health_score=50.0`） | ✅ Task 4 |
| 跨子系统弱耦合（A/B/C/D/E/F/G 独立可交付） | ✅ 子系统目录隔离 |
| Worktree base = main HEAD（`.claude/settings.json: worktree.baseRef = head`） | ✅（沿用） |

## 已知限制 / P7 留底

- **THEME_LEADER_BREAK_BOARD / SECTOR_ROTATION 未接入 runner**：检测器函数已就绪，但 runner event loop 不会主动调用。让用户在评审时手动触发，或在 P7 把它和 `seal_timeline.divergence.detect_theme_divergence` 一并接入。
- **`weekly_health_score` 权重是 starter**：`compute_weekly_health_score` 使用 `position 40% + uptrend 40% + ma 20%`。等 P4 backfill 数据足够后可用 backtest 校准。
- **`find_similar_setups` 不带 outcome join**：当前只返回 `match_grade_at_pick`，不携带「这只历史样本第二天到底封板了没有」。Outcome join 等 review_outcomes 表数据足够后再补，避免空结果误导。
- **`SetupVector` 5 维偏少**：未来可加封板时间、最大封单、市场闸门等。本期先做最小可用维度。
- **次新股 / 停牌 jvquant 路径都是 placeholder**：等 jvQuant 字段映射明确后，单独 issue 接入。
- **`MinuteBarWriter` 不带索引表**：Reader 通过文件系统扫描；规模到 5000 symbols × 240 days 时性能仍可接受，但 P7 可加 SQLite 索引。
- **`simulate_outcome` 不重新跑评级**：当前只返回 `payload_diff`，不调 `candidate_grade(...)`。下一轮接入时把现有评级规则函数化，让 `simulate_outcome` 真正复用。
- **README 注：`get_weekly_position` 是 adapter 方法，非 MCP tool**。如果 Hermes 想直接看周线，未来再补一个 MCP 包装。

完成 P6 后，Hermes 可在解释二板候选时再多 5 个新维度（板块事件 + 周线 + 相似历史 + 次新分层 + 假设回放）；Parquet 历史层为后续高频回测打底。
