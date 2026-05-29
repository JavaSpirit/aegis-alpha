# P1 架构基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 1688 行的 jvquant 适配器拆掉，建立可扩展工程地基：Protocol 接口、模块化拆分、评级阈值外置到 YAML、统一时钟、MCP 单例、超时与限流、统一日志、SQLite migration、缓存 TTL、runner 指数退避、修 SKILL.md 残留路径。

**Architecture:** 拆分按职责边界进行——`jvquant_market_data.py` 拆为 5 个文件（queries/parsers/scoring/data_quality/adapter）；评级硬编码阈值搬到 `config/candidate_grading.yaml` 加载为 `CandidateGradingConfig` Pydantic model；`MarketDataAdapter` Protocol 只声明 MCP 暴露的方法；MCP 引入 lifespan + 单例。

**Tech Stack:** Python 3.11+, Pydantic v2, FastMCP lifespan, PyYAML, threading.Lock, time.monotonic, logging stdlib, sqlite3。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/aegis_alpha/protocols.py` | 新建 | `MarketDataAdapter` Protocol 定义 |
| `src/aegis_alpha/clock.py` | 新建 | 统一 `now_iso()` / `now_dt()` / `parse_iso()` |
| `src/aegis_alpha/logging_setup.py` | 新建 | `get_logger(name)` + 启动配置 |
| `src/aegis_alpha/grading.py` | 新建 | `CandidateGradingConfig` 加载器 + 评级函数（从 jvquant 迁出） |
| `src/aegis_alpha/cache.py` | 新建 | `TTLCache[K, V]` 工具 |
| `src/aegis_alpha/rate_limit.py` | 新建 | `TokenBucket` 简单限流 |
| `src/aegis_alpha/db_migrations.py` | 新建 | schema 迁移管理 + 迁移文件目录 |
| `src/aegis_alpha/db_migrations/__init__.py` | 新建 | 空 init |
| `src/aegis_alpha/db_migrations/0001_initial.py` | 新建 | 把现有 `_init_schema` 的 DDL 搬过来 |
| `src/aegis_alpha/adapters/jvquant/__init__.py` | 新建 | 空 init，导出 `JvQuantMarketDataAdapter` |
| `src/aegis_alpha/adapters/jvquant/queries.py` | 新建 | 语义查询常量 + `JvQuantQueryClient`（带超时、限流、TTL 缓存） |
| `src/aegis_alpha/adapters/jvquant/parsers.py` | 新建 | 字段解析（`_parse_cny_amount` 等） |
| `src/aegis_alpha/adapters/jvquant/data_quality.py` | 新建 | `_second_board_data_quality` 迁过来 |
| `src/aegis_alpha/adapters/jvquant/adapter.py` | 新建 | 编排层（`JvQuantMarketDataAdapter` 主体） |
| `src/aegis_alpha/adapters/jvquant_market_data.py` | 修改 | 改为兼容 shim（重新导出） |
| `src/aegis_alpha/mcp/server.py` | 修改 | 引入 lifespan，单例 adapter + store |
| `src/aegis_alpha/mcp/dependencies.py` | 新建 | 单例容器 |
| `src/aegis_alpha/runner.py` | 修改 | 指数退避 + 抖动 |
| `src/aegis_alpha/storage.py` | 修改 | `_init_schema` 改为调用迁移管理；`_now()` 替换为 `clock.now_iso()` |
| `src/aegis_alpha/events.py` | 修改 | `now_iso` 替换为 `clock.now_iso()`；保留 alias |
| `src/aegis_alpha/adapters/mock_market_data.py` | 修改 | 同上 |
| `config/candidate_grading.yaml` | 新建 | 评级阈值与权重 |
| `.hermes/skills/second-board-radar/SKILL.md` | 修改 | 修残留 `/Users/xietian/...` 路径 |
| `tests/test_protocols.py` | 新建 | mock 适配器满足 Protocol 测试 |
| `tests/test_clock.py` | 新建 | 时钟工具测试 |
| `tests/test_grading.py` | 新建 | YAML 评级配置测试 |
| `tests/test_cache.py` | 新建 | TTL cache 测试 |
| `tests/test_rate_limit.py` | 新建 | TokenBucket 测试 |
| `tests/test_db_migrations.py` | 新建 | 迁移幂等 + 升级测试 |
| `tests/test_mcp_dependencies.py` | 新建 | MCP 单例注入测试 |

---

## Task 1: 建立统一时钟模块 `clock.py`

**Files:**
- Create: `src/aegis_alpha/clock.py`
- Create: `tests/test_clock.py`

- [ ] **Step 1: 写失败测试**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aegis_alpha.clock import SH_TZ, now_dt, now_iso, parse_iso


def test_now_iso_returns_iso8601_with_offset() -> None:
    text = now_iso()
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == ZoneInfo("Asia/Shanghai").utcoffset(parsed)


def test_now_dt_is_timezone_aware() -> None:
    dt = now_dt()
    assert dt.tzinfo is not None


def test_parse_iso_attaches_sh_tz_when_naive() -> None:
    parsed = parse_iso("2026-05-29T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo == SH_TZ


def test_parse_iso_returns_none_for_invalid() -> None:
    assert parse_iso("not-a-time") is None
    assert parse_iso("") is None


def test_parse_iso_keeps_explicit_offset() -> None:
    parsed = parse_iso("2026-05-29T10:00:00+09:00")
    assert parsed is not None
    assert parsed.utcoffset() == ZoneInfo("Asia/Tokyo").utcoffset(parsed)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_clock.py -v
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现 `clock.py`**

```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SH_TZ = ZoneInfo("Asia/Shanghai")


def now_dt() -> datetime:
    return datetime.now(SH_TZ)


def now_iso() -> str:
    return now_dt().isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SH_TZ)
    return parsed
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_clock.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/clock.py tests/test_clock.py
git commit -m "feat(clock): centralize timezone-aware now/parse helpers"
```

---

## Task 2: 把散落的 `_now()` / `now_iso` 替换为 `clock.now_iso()`

**Files:**
- Modify: `src/aegis_alpha/events.py`
- Modify: `src/aegis_alpha/storage.py`
- Modify: `src/aegis_alpha/runner.py`
- Modify: `src/aegis_alpha/adapters/mock_market_data.py`
- Modify: `src/aegis_alpha/adapters/jvquant_market_data.py`

- [ ] **Step 1: 替换 events.py**

在 `src/aegis_alpha/events.py` 顶部 import 区，移除原来的 `from zoneinfo import ZoneInfo` 用法，改为：

```python
from aegis_alpha.clock import SH_TZ, now_iso  # noqa: F401  re-export for back-compat
```

删除文件中原来的 `SH_TZ = ZoneInfo("Asia/Shanghai")` 和 `def now_iso(): ...`。

- [ ] **Step 2: 替换 storage.py**

`src/aegis_alpha/storage.py` 顶部加：

```python
from aegis_alpha.clock import SH_TZ, now_iso
```

删除文件中原来的 `SH_TZ = ZoneInfo(...)` 和 `def now_iso(): ...`。

- [ ] **Step 3: 替换 runner.py**

`src/aegis_alpha/runner.py` 顶部把 `from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config, now_iso` 改为：

```python
from aegis_alpha.clock import SH_TZ, now_iso
from aegis_alpha.events import EventDetector, SignalWindowBuffer, load_event_scoring_config
```

删除原来文件里独立的 `SH_TZ = ZoneInfo(...)`。

- [ ] **Step 4: 替换 mock_market_data.py 和 jvquant_market_data.py**

把每个文件里的 `def _now()` 替换为：

```python
from aegis_alpha.clock import SH_TZ, now_iso as _now  # noqa: F401  legacy alias
```

并删除原文件的 `SH_TZ = ZoneInfo(...)` 和 `def _now()`。

- [ ] **Step 5: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/
git commit -m "refactor: route all now()/now_iso() through aegis_alpha.clock"
```

---

## Task 3: 修 SKILL.md 残留路径

**Files:**
- Modify: `.hermes/skills/second-board-radar/SKILL.md`

- [ ] **Step 1: 编辑 default 路径**

把 `.hermes/skills/second-board-radar/SKILL.md` 第 13 行：

```yaml
        default: "/Users/xietian/Documents/trading"
```

改为：

```yaml
        default: ""
```

并把第 14 行 prompt 文本改为：

```yaml
        prompt: Aegis Alpha workspace path (absolute path to your local clone)
```

- [ ] **Step 2: Commit**

```bash
git add .hermes/skills/second-board-radar/SKILL.md
git commit -m "fix(skill): remove leaked third-party absolute path from SKILL.md"
```

---

## Task 4: 建立 `MarketDataAdapter` Protocol

**Files:**
- Create: `src/aegis_alpha/protocols.py`
- Create: `tests/test_protocols.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.protocols import MarketDataAdapter


def test_mock_adapter_satisfies_protocol() -> None:
    adapter: MarketDataAdapter = MockMarketDataAdapter()
    # Static type-check passes if mock implements every protocol method;
    # runtime sanity-check: all attributes resolvable.
    for method_name in (
        "get_market_snapshot",
        "get_market_sentiment_gate",
        "get_limitup_pool",
        "get_break_board_pool",
        "get_stock_realtime_snapshot",
        "get_stock_orderbook_snapshot",
        "get_stock_minute_replay_snapshot",
        "get_stock_history_limitup_stats",
        "get_theme_strength",
        "get_event_scoring_config",
        "get_realtime_connection_status",
        "get_signal_snapshot",
        "get_recent_market_events",
        "explain_market_event",
        "review_candidate_outcome",
        "record_candidate_outcome",
        "get_second_board_candidates",
        "explain_candidate",
        "explain_second_board_candidate",
    ):
        assert callable(getattr(adapter, method_name)), method_name
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_protocols.py -v
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现 Protocol**

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from aegis_alpha.models import (
    BreakBoardStock,
    CandidateExplanation,
    CandidateOutcomeReview,
    EventScoringConfig,
    LimitUpHistoryStats,
    LimitUpStock,
    MarketEvent,
    MarketSentimentGate,
    MarketSnapshot,
    MinuteReplaySnapshot,
    RealtimeConnectionStatus,
    SecondBoardCandidate,
    SignalSnapshot,
    StockOrderbookSnapshot,
    StockRealtimeSnapshot,
    ThemeStrength,
)


@runtime_checkable
class MarketDataAdapter(Protocol):
    def get_market_snapshot(self) -> MarketSnapshot: ...
    def get_market_sentiment_gate(self) -> MarketSentimentGate: ...
    def get_limitup_pool(self) -> list[LimitUpStock]: ...
    def get_break_board_pool(self) -> list[BreakBoardStock]: ...
    def get_stock_realtime_snapshot(self, symbol: str) -> StockRealtimeSnapshot: ...
    def get_stock_orderbook_snapshot(self, symbol: str) -> StockOrderbookSnapshot: ...
    def get_stock_minute_replay_snapshot(
        self, symbol: str, end_day: str | None = None, limit_days: int = 1
    ) -> MinuteReplaySnapshot: ...
    def get_stock_history_limitup_stats(self, symbol: str) -> LimitUpHistoryStats: ...
    def get_theme_strength(self, symbol: str) -> ThemeStrength: ...
    def get_event_scoring_config(self) -> EventScoringConfig: ...
    def get_realtime_connection_status(self) -> RealtimeConnectionStatus: ...
    def get_signal_snapshot(self, symbol: str) -> SignalSnapshot: ...
    def get_recent_market_events(
        self, limit: int = 20, event_type: str | None = None
    ) -> list[MarketEvent]: ...
    def explain_market_event(self, event_id: str) -> dict: ...
    def review_candidate_outcome(self, symbol: str, trading_day: str) -> CandidateOutcomeReview: ...
    def record_candidate_outcome(self, review: CandidateOutcomeReview) -> CandidateOutcomeReview: ...
    def get_second_board_candidates(self) -> list[SecondBoardCandidate]: ...
    def explain_candidate(self, symbol: str) -> CandidateExplanation: ...
    def explain_second_board_candidate(self, symbol: str) -> CandidateExplanation: ...
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_protocols.py -v
```

Expected: PASS。

- [ ] **Step 5: 让 factory 返回类型注释为 Protocol**

修改 `src/aegis_alpha/adapters/factory.py`：

```python
from __future__ import annotations

import os

from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter
from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.config import load_project_env
from aegis_alpha.protocols import MarketDataAdapter


def create_market_data_adapter() -> MarketDataAdapter:
    load_project_env()
    provider = os.environ.get("AEGIS_ALPHA_MARKET_DATA_PROVIDER", "mock").strip().lower()

    if provider == "jvquant":
        return JvQuantMarketDataAdapter.from_env()

    return MockMarketDataAdapter()
```

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/protocols.py src/aegis_alpha/adapters/factory.py tests/test_protocols.py
git commit -m "feat(protocols): add MarketDataAdapter Protocol contract

Make adapter shape explicit so missing implementations are detectable
at import time rather than only when MCP routes a tool call."
```

---

## Task 5: 项目级 logger

**Files:**
- Create: `src/aegis_alpha/logging_setup.py`

- [ ] **Step 1: 实现**

```python
from __future__ import annotations

import logging
import os
import sys
from typing import Any


_CONFIGURED = False


def _resolve_level() -> int:
    raw = os.environ.get("AEGIS_ALPHA_LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger("aegis_alpha")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(_resolve_level())
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    if not name.startswith("aegis_alpha"):
        name = f"aegis_alpha.{name}"
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Structured-style log helper: 'event=foo k=v ...'."""
    pieces = [f"event={event}"]
    for key, value in fields.items():
        pieces.append(f"{key}={value}")
    logger.log(level, " ".join(pieces))
```

- [ ] **Step 2: Commit**

```bash
git add src/aegis_alpha/logging_setup.py
git commit -m "feat(logging): centralize logger configuration

Reads AEGIS_ALPHA_LOG_LEVEL, formats to stderr with ISO timestamps.
get_logger(__name__) is the single entrypoint for module-level loggers."
```

---

## Task 6: TTL Cache 工具

**Files:**
- Create: `src/aegis_alpha/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

import pytest

from aegis_alpha.cache import TTLCache


def test_ttl_cache_returns_value_within_ttl() -> None:
    clock = [1000.0]
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30, clock=lambda: clock[0])
    cache.set("k", 7)
    clock[0] = 1010.0
    assert cache.get("k") == 7


def test_ttl_cache_expires_after_ttl() -> None:
    clock = [1000.0]
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30, clock=lambda: clock[0])
    cache.set("k", 7)
    clock[0] = 1031.0
    assert cache.get("k") is None


def test_ttl_cache_get_or_set_caches_first_call() -> None:
    clock = [1000.0]
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30, clock=lambda: clock[0])
    calls = {"n": 0}

    def loader() -> int:
        calls["n"] += 1
        return 42

    assert cache.get_or_set("k", loader) == 42
    assert cache.get_or_set("k", loader) == 42
    assert calls["n"] == 1
    clock[0] = 1031.0
    assert cache.get_or_set("k", loader) == 42
    assert calls["n"] == 2


def test_ttl_cache_clear() -> None:
    clock = [1000.0]
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=30, clock=lambda: clock[0])
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_cache.py -v
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Thread-safe TTL cache with optional clock injection for tests."""

    def __init__(
        self,
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._data: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if self._clock() >= expires_at:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._data[key] = (self._clock() + self.ttl_seconds, value)

    def get_or_set(self, key: K, loader: Callable[[], V]) -> V:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = loader()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
```

- [ ] **Step 4: 跑测试确认通过 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_cache.py -v
git add src/aegis_alpha/cache.py tests/test_cache.py
git commit -m "feat(cache): TTLCache with injectable clock"
```

---

## Task 7: TokenBucket 限流

**Files:**
- Create: `src/aegis_alpha/rate_limit.py`
- Create: `tests/test_rate_limit.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

import pytest

from aegis_alpha.rate_limit import TokenBucket


def test_token_bucket_allows_burst_up_to_capacity() -> None:
    clock = [1000.0]
    bucket = TokenBucket(rate_per_second=1.0, capacity=5, clock=lambda: clock[0])
    for _ in range(5):
        assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False


def test_token_bucket_refills_over_time() -> None:
    clock = [1000.0]
    bucket = TokenBucket(rate_per_second=2.0, capacity=2, clock=lambda: clock[0])
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False
    clock[0] = 1001.0  # +1s, +2 tokens, capped at 2
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False


def test_token_bucket_acquire_blocks_until_available() -> None:
    """acquire() with sleep_fn injected returns once tokens are available."""
    clock = [1000.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    bucket = TokenBucket(
        rate_per_second=1.0,
        capacity=1,
        clock=lambda: clock[0],
        sleep_fn=fake_sleep,
    )
    assert bucket.try_acquire() is True
    bucket.acquire()  # second call should sleep ~1.0s then succeed
    assert sum(sleeps) >= 0.99


def test_token_bucket_invalid_args() -> None:
    with pytest.raises(ValueError):
        TokenBucket(rate_per_second=0, capacity=1)
    with pytest.raises(ValueError):
        TokenBucket(rate_per_second=1, capacity=0)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_rate_limit.py -v
```

- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """Simple thread-safe token bucket. Refills at `rate_per_second`, capped at `capacity`."""

    def __init__(
        self,
        *,
        rate_per_second: float,
        capacity: int,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.rate_per_second = float(rate_per_second)
        self.capacity = int(capacity)
        self._tokens: float = float(capacity)
        self._last_refill: float = clock()
        self._clock = clock
        self._sleep = sleep_fn
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(float(self.capacity), self._tokens + elapsed * self.rate_per_second)
        self._last_refill = now

    def try_acquire(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def acquire(self) -> None:
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait_seconds = deficit / self.rate_per_second
            self._sleep(wait_seconds)
```

- [ ] **Step 4: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_rate_limit.py -v
git add src/aegis_alpha/rate_limit.py tests/test_rate_limit.py
git commit -m "feat(rate_limit): TokenBucket for jvQuant query throttling"
```

---

## Task 8: SQLite 迁移管理

**Files:**
- Create: `src/aegis_alpha/db_migrations.py`
- Create: `src/aegis_alpha/db_migrations_files/__init__.py`
- Create: `src/aegis_alpha/db_migrations_files/m0001_initial.py`
- Create: `tests/test_db_migrations.py`

注意：用 `db_migrations_files` 命名以避免 Python 文件名/目录名冲突。

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from aegis_alpha.db_migrations import apply_migrations, current_version


def test_apply_migrations_on_fresh_db(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    with sqlite3.connect(db) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "schema_versions" in names
    assert "market_events" in names
    assert "signal_snapshots" in names
    assert current_version(db) >= 1


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    apply_migrations(db)
    version_first = current_version(db)
    apply_migrations(db)  # should not error or duplicate
    version_second = current_version(db)
    assert version_first == version_second
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_db_migrations.py -v
```

- [ ] **Step 3: 实现 `db_migrations.py`**

```python
from __future__ import annotations

import importlib
import pkgutil
import sqlite3
from pathlib import Path
from typing import Callable

from aegis_alpha.logging_setup import get_logger

LOGGER = get_logger(__name__)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_versions (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def current_version(db_path: Path) -> int:
    with _connect(db_path) as conn:
        _ensure_version_table(conn)
        row = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _discover_migrations() -> list[tuple[int, str, Callable[[sqlite3.Connection], None]]]:
    import aegis_alpha.db_migrations_files as package

    migrations: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = []
    for module_info in pkgutil.iter_modules(package.__path__):
        name = module_info.name
        if not name.startswith("m") or "_" not in name:
            continue
        version_str = name.split("_", 1)[0][1:]
        if not version_str.isdigit():
            continue
        module = importlib.import_module(f"{package.__name__}.{name}")
        upgrade = getattr(module, "upgrade", None)
        if not callable(upgrade):
            continue
        migrations.append((int(version_str), name, upgrade))
    migrations.sort(key=lambda item: item[0])
    return migrations


def apply_migrations(db_path: Path) -> None:
    from aegis_alpha.clock import now_iso

    db_path = Path(db_path)
    with _connect(db_path) as conn:
        _ensure_version_table(conn)
        existing = {
            int(row[0])
            for row in conn.execute("SELECT version FROM schema_versions").fetchall()
        }
        for version, name, upgrade in _discover_migrations():
            if version in existing:
                continue
            LOGGER.info("event=migration_apply version=%s name=%s", version, name)
            upgrade(conn)
            conn.execute(
                "INSERT INTO schema_versions (version, applied_at) VALUES (?, ?)",
                (version, now_iso()),
            )
```

- [ ] **Step 4: 把现有 schema 写成迁移 0001**

`src/aegis_alpha/db_migrations_files/__init__.py`:

```python
"""SQLite migrations registry."""
```

`src/aegis_alpha/db_migrations_files/m0001_initial.py`:

```python
from __future__ import annotations

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            symbol TEXT,
            theme TEXT,
            score REAL NOT NULL,
            confidence TEXT NOT NULL,
            provider_timestamp TEXT,
            received_at TEXT NOT NULL,
            freshness_status TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signal_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            data_timestamp TEXT NOT NULL,
            provider_timestamp TEXT,
            received_at TEXT,
            freshness_status TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS candidate_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT,
            grade TEXT,
            score REAL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            symbol TEXT,
            provider TEXT,
            model TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_review_corrections (
            correction_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL,
            symbol TEXT,
            correction_type TEXT NOT NULL,
            expected_grade TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correction_action_proposals (
            proposal_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            correction_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correction_action_decisions (
            decision_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT,
            decided_by TEXT,
            previous_status TEXT,
            new_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS provider_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            ended_at TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS review_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            trading_day TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, trading_day)
        );
        """
    )
```

- [ ] **Step 5: 修改 `storage.py` `_init_schema` 改为调用迁移**

把 `src/aegis_alpha/storage.py` 中的 `_init_schema` 整段替换为：

```python
    def _init_schema(self) -> None:
        from aegis_alpha.db_migrations import apply_migrations

        apply_migrations(self.db_path)
```

- [ ] **Step 6: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS（包括新加的 db_migrations 测试 + 现有 storage 相关测试）。

- [ ] **Step 7: Commit**

```bash
git add src/aegis_alpha/db_migrations.py src/aegis_alpha/db_migrations_files/ src/aegis_alpha/storage.py tests/test_db_migrations.py
git commit -m "feat(storage): introduce versioned SQLite migrations

Replace ad-hoc CREATE TABLE IF NOT EXISTS with discovered migration
files and a schema_versions tracking table. Adding columns or new
tables now lives in a numbered migration."
```

---

## Task 9: 评级阈值外置到 `config/candidate_grading.yaml`

**Files:**
- Create: `config/candidate_grading.yaml`
- Create: `src/aegis_alpha/grading.py`
- Create: `tests/test_grading.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from aegis_alpha.grading import (
    CandidateGradingConfig,
    grade_candidate,
    load_grading_config,
)


def test_load_grading_config_defaults() -> None:
    config = load_grading_config()
    assert config.version >= 1
    assert config.thresholds.a_min_change_pct > 0
    assert config.weights.estimated_seal_change_factor > 0


def test_load_grading_config_from_custom_path(tmp_path: Path) -> None:
    custom = tmp_path / "grading.yaml"
    custom.write_text(
        """
version: 99
thresholds:
  a_min_change_pct: 11.0
  a_min_5m_speed_pct: 2.0
  a_min_big_order_inflow_ratio: 0.05
  a_min_orderbook_quality: 70
  a_min_theme_count: 3
  a_min_seal_quality: 60
  b_min_change_pct: 8.0
  b_min_orderbook_quality: 55
  b_min_seal_quality: 50
  reject_min_change_pct: 5.0
  defensive_b_min_change_pct: 9.5
  defensive_b_min_theme_count: 2
  defensive_b_min_orderbook_quality: 55
  defensive_b_min_seal_quality: 60
  defensive_b_min_big_order_inflow_ratio: 0.03
weights:
  base_probability: 0.3
  change_pct_weight: 0.04
  speed_5m_weight: 0.02
  big_order_weight: 1.4
  orderbook_quality_factor: 0.002
  theme_count_weight: 0.025
  seal_quality_factor: 0.001
  active_bonus: 0.08
  defensive_penalty: -0.10
  avoid_penalty: -0.20
  estimated_seal_change_factor: 0.04
"""
    )
    config = load_grading_config(custom)
    assert config.version == 99
    assert config.thresholds.a_min_change_pct == 11.0


def test_grade_candidate_active_a_grade() -> None:
    config = load_grading_config()
    grade = grade_candidate(
        action="active",
        change_pct=10.0,
        five_min_speed_pct=2.5,
        big_order_net_inflow_ratio=0.10,
        orderbook_quality=80,
        theme_count=5,
        first_limit_up_time="09:35:00",
        seal_amount_cny=400_000_000,
        seal_to_turnover_ratio=6.0,
        config=config,
    )
    assert grade == "A"


def test_grade_candidate_avoid_returns_reject() -> None:
    config = load_grading_config()
    grade = grade_candidate(
        action="avoid",
        change_pct=10.0,
        five_min_speed_pct=5.0,
        big_order_net_inflow_ratio=0.5,
        orderbook_quality=99,
        theme_count=10,
        first_limit_up_time="09:30:00",
        seal_amount_cny=10_000_000_000,
        seal_to_turnover_ratio=20,
        config=config,
    )
    assert grade == "REJECT"


def test_grade_candidate_below_min_change_returns_reject() -> None:
    config = load_grading_config()
    grade = grade_candidate(
        action="selective",
        change_pct=4.0,
        five_min_speed_pct=2.0,
        big_order_net_inflow_ratio=0.10,
        orderbook_quality=80,
        theme_count=5,
        first_limit_up_time="09:30:00",
        seal_amount_cny=400_000_000,
        seal_to_turnover_ratio=6.0,
        config=config,
    )
    assert grade == "REJECT"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_grading.py -v
```

- [ ] **Step 3: 写 `config/candidate_grading.yaml`**

```yaml
version: 1

thresholds:
  a_min_change_pct: 9.5
  a_min_5m_speed_pct: 1.5
  a_min_big_order_inflow_ratio: 0.03
  a_min_orderbook_quality: 60
  a_min_theme_count: 2
  a_min_seal_quality: 55
  b_min_change_pct: 7.0
  b_min_orderbook_quality: 50
  b_min_seal_quality: 45
  reject_min_change_pct: 5.0
  defensive_b_min_change_pct: 9.5
  defensive_b_min_theme_count: 2
  defensive_b_min_orderbook_quality: 55
  defensive_b_min_seal_quality: 60
  defensive_b_min_big_order_inflow_ratio: 0.03

weights:
  base_probability: 0.25
  change_pct_weight: 0.05
  speed_5m_weight: 0.025
  big_order_weight: 1.5
  orderbook_quality_factor: 0.01
  theme_count_weight: 0.03
  seal_quality_factor: 0.001
  active_bonus: 0.10
  defensive_penalty: -0.12
  avoid_penalty: -0.25
  estimated_seal_change_factor: 0.04
```

- [ ] **Step 4: 写 `grading.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from aegis_alpha.models import CandidateGrade

MarketAction = Literal["active", "selective", "defensive", "avoid"]


class GradingThresholds(BaseModel):
    a_min_change_pct: float
    a_min_5m_speed_pct: float
    a_min_big_order_inflow_ratio: float
    a_min_orderbook_quality: float
    a_min_theme_count: int
    a_min_seal_quality: float
    b_min_change_pct: float
    b_min_orderbook_quality: float
    b_min_seal_quality: float
    reject_min_change_pct: float
    defensive_b_min_change_pct: float
    defensive_b_min_theme_count: int
    defensive_b_min_orderbook_quality: float
    defensive_b_min_seal_quality: float
    defensive_b_min_big_order_inflow_ratio: float


class GradingWeights(BaseModel):
    base_probability: float
    change_pct_weight: float
    speed_5m_weight: float
    big_order_weight: float
    orderbook_quality_factor: float
    theme_count_weight: float
    seal_quality_factor: float
    active_bonus: float
    defensive_penalty: float
    avoid_penalty: float
    estimated_seal_change_factor: float = 0.04


class CandidateGradingConfig(BaseModel):
    version: int = 1
    thresholds: GradingThresholds
    weights: GradingWeights


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_grading_config(path: str | Path | None = None) -> CandidateGradingConfig:
    config_path = Path(path) if path else _project_root() / "config" / "candidate_grading.yaml"
    payload = yaml.safe_load(config_path.read_text())
    return CandidateGradingConfig.model_validate(payload)


def seal_quality_score(
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
) -> float:
    score = 0.0
    if first_limit_up_time != "unknown":
        if first_limit_up_time <= "09:45:00":
            score += 35.0
        elif first_limit_up_time <= "10:30:00":
            score += 22.0
        elif first_limit_up_time <= "14:30:00":
            score += 10.0
    if seal_amount_cny >= 300_000_000:
        score += 30.0
    elif seal_amount_cny >= 100_000_000:
        score += 20.0
    elif seal_amount_cny >= 30_000_000:
        score += 10.0
    if seal_to_turnover_ratio >= 5:
        score += 25.0
    elif seal_to_turnover_ratio >= 2:
        score += 16.0
    elif seal_to_turnover_ratio >= 1:
        score += 8.0
    return round(min(100.0, score), 2)


def grade_candidate(
    *,
    action: MarketAction,
    change_pct: float,
    five_min_speed_pct: float,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    theme_count: int,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> CandidateGrade:
    t = config.thresholds
    if action == "avoid":
        return "REJECT"
    if change_pct < t.reject_min_change_pct:
        return "REJECT"
    seal_q = seal_quality_score(first_limit_up_time, seal_amount_cny, seal_to_turnover_ratio)
    if action == "defensive":
        if (
            change_pct >= t.defensive_b_min_change_pct
            and theme_count >= t.defensive_b_min_theme_count
            and (
                orderbook_quality >= t.defensive_b_min_orderbook_quality
                or big_order_net_inflow_ratio >= t.defensive_b_min_big_order_inflow_ratio
                or seal_q >= t.defensive_b_min_seal_quality
            )
        ):
            return "B"
        return "C"
    if (
        change_pct >= t.a_min_change_pct
        and five_min_speed_pct >= t.a_min_5m_speed_pct
        and big_order_net_inflow_ratio >= t.a_min_big_order_inflow_ratio
        and orderbook_quality >= t.a_min_orderbook_quality
        and theme_count >= t.a_min_theme_count
        and seal_q >= t.a_min_seal_quality
    ):
        return "A"
    if change_pct >= t.b_min_change_pct and (
        orderbook_quality >= t.b_min_orderbook_quality
        or big_order_net_inflow_ratio > 0
        or seal_q >= t.b_min_seal_quality
    ):
        return "B"
    return "C"


def estimated_seal_probability(
    *,
    action: MarketAction,
    change_pct: float,
    five_min_speed_pct: float,
    big_order_net_inflow_ratio: float,
    orderbook_quality: float,
    theme_count: int,
    first_limit_up_time: str,
    seal_amount_cny: float,
    seal_to_turnover_ratio: float,
    config: CandidateGradingConfig,
) -> float:
    w = config.weights
    p = w.base_probability
    p += min(0.30, max(0.0, change_pct - 5.0) * w.change_pct_weight)
    p += min(0.10, max(0.0, five_min_speed_pct) * w.speed_5m_weight)
    p += min(0.15, max(0.0, big_order_net_inflow_ratio) * w.big_order_weight)
    p += min(0.20, max(0.0, orderbook_quality - 50.0) * w.orderbook_quality_factor)
    p += min(0.15, theme_count * w.theme_count_weight)
    p += min(
        0.12,
        seal_quality_score(first_limit_up_time, seal_amount_cny, seal_to_turnover_ratio)
        * w.seal_quality_factor,
    )
    if action == "active":
        p += w.active_bonus
    elif action == "defensive":
        p += w.defensive_penalty
    elif action == "avoid":
        p += w.avoid_penalty
    return round(max(0.0, min(0.95, p)), 4)
```

- [ ] **Step 5: 替换 jvquant 适配器中的硬编码**

修改 `src/aegis_alpha/adapters/jvquant_market_data.py` 中的：

- 删除 `_candidate_grade`、`_estimated_seal_probability`、`_seal_quality_score` 三个方法。
- 在 `__init__` 末尾加：

  ```python
  from aegis_alpha.grading import load_grading_config
  self._grading_config = load_grading_config()
  ```

- 在 `get_second_board_candidates` 内调用处，替换：

  ```python
  grade = self._candidate_grade(...)
  estimated = self._estimated_seal_probability(...)
  ```

  为：

  ```python
  from aegis_alpha.grading import grade_candidate, estimated_seal_probability

  grade = grade_candidate(
      action=gate.action,
      change_pct=change_pct,
      five_min_speed_pct=five_min_speed_pct,
      big_order_net_inflow_ratio=big_order_net_inflow_ratio,
      orderbook_quality=orderbook_quality,
      theme_count=theme_counts[theme],
      first_limit_up_time=first_limit_up_time,
      seal_amount_cny=seal_amount_cny,
      seal_to_turnover_ratio=seal_to_turnover_ratio,
      config=self._grading_config,
  )
  estimated = estimated_seal_probability(
      action=gate.action,
      change_pct=change_pct,
      five_min_speed_pct=five_min_speed_pct,
      big_order_net_inflow_ratio=big_order_net_inflow_ratio,
      orderbook_quality=orderbook_quality,
      theme_count=theme_counts[theme],
      first_limit_up_time=first_limit_up_time,
      seal_amount_cny=seal_amount_cny,
      seal_to_turnover_ratio=seal_to_turnover_ratio,
      config=self._grading_config,
  )
  ```

- `_candidate_grade_reason` 保留，但接收 `seal_q = seal_quality_score(...)` 时改为从 `aegis_alpha.grading` 导入。

- [ ] **Step 6: 跑全量测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
git add config/candidate_grading.yaml src/aegis_alpha/grading.py src/aegis_alpha/adapters/jvquant_market_data.py tests/test_grading.py
git commit -m "feat(grading): externalize candidate grading thresholds and weights

Move A/B/C/REJECT thresholds and probability weights from hardcoded
Python into config/candidate_grading.yaml. Required prerequisite for
the P4 feedback loop where corrections automatically adjust thresholds."
```

---

## Task 10: 拆分 jvquant 适配器为子模块

**Files:**
- Create: `src/aegis_alpha/adapters/jvquant/__init__.py`
- Create: `src/aegis_alpha/adapters/jvquant/queries.py`
- Create: `src/aegis_alpha/adapters/jvquant/parsers.py`
- Create: `src/aegis_alpha/adapters/jvquant/data_quality.py`
- Create: `src/aegis_alpha/adapters/jvquant/adapter.py`
- Modify: `src/aegis_alpha/adapters/jvquant_market_data.py`

注意：本 task 是机械搬运 + 加超时 + 加限流 + 加缓存 + 加 logger。不改任何业务逻辑。

- [ ] **Step 1: 创建 `__init__.py` 和 `queries.py`**

`src/aegis_alpha/adapters/jvquant/__init__.py`:

```python
"""jvQuant adapter — split into queries / parsers / data_quality / adapter modules."""

from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter

__all__ = ["JvQuantMarketDataAdapter"]
```

`src/aegis_alpha/adapters/jvquant/queries.py`:

```python
from __future__ import annotations

import logging
import os
from typing import Any

from aegis_alpha.cache import TTLCache
from aegis_alpha.logging_setup import get_logger
from aegis_alpha.rate_limit import TokenBucket


SECOND_BOARD_BASE_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,5分钟涨幅,资金流向,主力资金,价格,成交额,行业"
)
SECOND_BOARD_SEAL_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单量,封单金额,涨停封成比,价格,成交额,行业"
)
SECOND_BOARD_SPEED_1M_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,1分钟涨幅,价格,成交额,行业"
)
SECOND_BOARD_SPEED_3M_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,3分钟涨幅,价格,成交额,行业"
)
SECOND_BOARD_SPEED_10M_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,10分钟涨幅,价格,成交额,行业"
)
SECOND_BOARD_AUCTION_QUERY = (
    "昨日涨停,非ST,股票代码,股票简称,竞价涨幅,竞价成交额,竞价换手率,开盘价,价格,成交额,行业"
)
SECOND_BOARD_THEME_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,所属概念,概念,题材,行业,价格,成交额"
)
SECOND_BOARD_BREAK_RESEAL_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,炸板次数,首次炸板时间,回封次数,最后封板时间,价格,成交额,行业"
)
SECOND_BOARD_MAX_SEAL_QUERY = (
    "昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,最大封单金额,最大封单量,价格,成交额,行业"
)
LIMITUP_QUERY = (
    "今日涨停,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单金额,封单量,涨停封成比,价格,成交额,行业"
)
BREAK_BOARD_QUERY = "炸板,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业"
TOTAL_MAIN_QUERY = "主板,非ST,股票代码,股票简称,涨跌幅,价格,成交额,行业"


_LOGGER = get_logger(__name__)


class JvQuantQueryClient:
    """Wraps jvQuant sql_client with TTL cache, token bucket, and per-query timeout logging."""

    def __init__(
        self,
        token: str,
        *,
        cache_ttl_seconds: float = 30.0,
        rate_per_second: float = 5.0,
        capacity: int = 10,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.token = token
        self.timeout_seconds = timeout_seconds
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(ttl_seconds=cache_ttl_seconds)
        self._bucket = TokenBucket(rate_per_second=rate_per_second, capacity=capacity)
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            from jvQuant import sql_client

            self._client = sql_client.Construct(token=self.token, log_level=logging.ERROR)
        return self._client

    def query(self, query: str, sort_key: str = "") -> dict[str, Any]:
        cache_key = f"{query}|{sort_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        self._bucket.acquire()
        _LOGGER.debug("event=jvquant_query query=%r sort_key=%r", query[:60], sort_key)
        # jvQuant SDK does not accept timeout kwarg; rely on socket-default + observability log.
        result = self.client.query(query, 1, 1, sort_key)
        self._cache.set(cache_key, result)
        return result

    def kline(self, code: str, kind: str, adjust: str, period: str, count: int) -> dict[str, Any]:
        self._bucket.acquire()
        return self.client.kline(code, kind, adjust, period, count)

    def minute(self, code: str, end_day: str, limit_days: int) -> dict[str, Any]:
        self._bucket.acquire()
        return self.client.minute(code, end_day, limit_days)

    def level_queue(self, code: str) -> dict[str, Any]:
        self._bucket.acquire()
        return self.client.level_queue(code)
```

注意：jvQuant SDK 没暴露超时参数；这里至少做了 logger + rate limit + cache。如果未来 SDK 支持超时，在此集中加。

- [ ] **Step 2: 把 parser/data_quality 搬过去**

`src/aegis_alpha/adapters/jvquant/parsers.py`：把原文件中所有 `_parse_cny_amount` / `_parse_share_amount` / `_field_value` / `_field_entry` / `_first_field_value` / `_symbol_from_row` / `_name_from_row` / `_theme_from_row` / `_speed_window_from_field` / `_speed_from_row` / `_iso_from_provider_datetime` / `_tags_from_row` / `_query_rows` / `_rows_by_symbol` / `_query_count` / `_latest_minute_day` / `_minute_bars_from_rows` / `_field_index` / `_row_value` / `_minute_speed_windows` / `_time_with_seconds` / `_limitup_from_row` / `_break_board_from_row` / `_time_or_unknown` / `_normalize_time_string` / `_ratio` / `_leading_themes` / `_market_score` / `_sentiment_from_score` / `_action_from_score` / `_queue_position_note` / `_parse_level` / `_inferred_change_pct_for_limit_up` 这些 staticmethod/纯函数搬过去，去掉 `self` 参数，作为模块级函数。

`src/aegis_alpha/adapters/jvquant/data_quality.py`：把 `_second_board_data_quality` 整段搬成模块级函数 `build_second_board_data_quality(*, ...)`。

由于这两个文件代码量大，每搬一段就跑一次测试确保不破坏行为。

- [ ] **Step 3: `adapter.py` 主体**

`src/aegis_alpha/adapters/jvquant/adapter.py` 包含 `JvQuantMarketDataAdapter` 主类：

- `__init__`: 接收 `token`, `query_client: JvQuantQueryClient | None`，默认创建。加 `self._grading_config = load_grading_config()`。
- 所有 `self._query(...)` 改为 `self.queries.query(...)`。
- 所有 `self.client.minute(...)`/`self.client.kline(...)`/`self.client.level_queue(...)` 改为 `self.queries.minute(...)` 等。
- 解析函数从 parsers 导入（`from aegis_alpha.adapters.jvquant import parsers as P`）。
- 评级从 `aegis_alpha.grading` 导入。

不重复贴整个文件——指令是「保持业务行为完全一致，只换分发」。

- [ ] **Step 4: 改老文件为兼容 shim**

把 `src/aegis_alpha/adapters/jvquant_market_data.py` 整个替换为：

```python
"""Backward-compatible re-export. New code should import from aegis_alpha.adapters.jvquant."""

from aegis_alpha.adapters.jvquant import JvQuantMarketDataAdapter
from aegis_alpha.adapters.jvquant.adapter import normalize_symbol  # type: ignore[attr-defined]

__all__ = ["JvQuantMarketDataAdapter", "normalize_symbol"]
```

- [ ] **Step 5: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
PYTHONPATH=src .venv/bin/python scripts/smoke_check.py
```

Expected: 全部 PASS。

- [ ] **Step 6: 验证文件大小**

```bash
wc -l src/aegis_alpha/adapters/jvquant/*.py src/aegis_alpha/adapters/jvquant_market_data.py
```

Expected: 每个文件 < 800 行。adapter.py 应该在 400-600 行；parsers ~300；data_quality ~330；queries ~100；shim < 10。

- [ ] **Step 7: Commit**

```bash
git add src/aegis_alpha/adapters/jvquant/ src/aegis_alpha/adapters/jvquant_market_data.py
git commit -m "refactor(jvquant): split 1688-line adapter into queries/parsers/data_quality/adapter

Each module has one clear responsibility. Old import path still works
via a shim. Adds TTLCache + TokenBucket + structured logger to the
query layer so future changes (timeout, retry, pricing analytics) have
a single touch point."
```

---

## Task 11: MCP 单例 adapter + store

**Files:**
- Create: `src/aegis_alpha/mcp/dependencies.py`
- Modify: `src/aegis_alpha/mcp/server.py`
- Create: `tests/test_mcp_dependencies.py`

- [ ] **Step 1: 写失败测试**

```python
from __future__ import annotations

from aegis_alpha.adapters.mock_market_data import MockMarketDataAdapter
from aegis_alpha.mcp.dependencies import (
    Dependencies,
    get_default_dependencies,
    reset_default_dependencies,
)


def test_dependencies_returns_same_adapter_across_calls() -> None:
    reset_default_dependencies()
    deps = get_default_dependencies()
    assert deps.adapter is deps.adapter
    assert deps.store is deps.store


def test_dependencies_with_explicit_adapter_does_not_share_global(tmp_path) -> None:
    reset_default_dependencies()
    explicit = Dependencies(
        adapter=MockMarketDataAdapter(),
        store_db_path=tmp_path / "x.db",
    )
    deps_default = get_default_dependencies()
    assert explicit.adapter is not deps_default.adapter


def test_reset_default_dependencies_replaces_singletons() -> None:
    deps_a = get_default_dependencies()
    reset_default_dependencies()
    deps_b = get_default_dependencies()
    assert deps_a.adapter is not deps_b.adapter
```

- [ ] **Step 2: 实现 dependencies.py**

```python
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from aegis_alpha.adapters.factory import create_market_data_adapter
from aegis_alpha.protocols import MarketDataAdapter
from aegis_alpha.storage import AegisAlphaStore


@dataclass
class Dependencies:
    adapter: MarketDataAdapter
    store_db_path: Path | None = None
    _store: AegisAlphaStore | None = None

    @property
    def store(self) -> AegisAlphaStore:
        if self._store is None:
            self._store = AegisAlphaStore(self.store_db_path)
        return self._store


_LOCK = threading.Lock()
_DEFAULT: Dependencies | None = None


def get_default_dependencies() -> Dependencies:
    global _DEFAULT
    with _LOCK:
        if _DEFAULT is None:
            _DEFAULT = Dependencies(adapter=create_market_data_adapter())
        return _DEFAULT


def reset_default_dependencies() -> None:
    global _DEFAULT
    with _LOCK:
        _DEFAULT = None
```

- [ ] **Step 3: 修改 mcp/server.py 用单例**

把 `_call_tool` 和 `_call_store` 替换为：

```python
from aegis_alpha.logging_setup import get_logger
from aegis_alpha.mcp.dependencies import get_default_dependencies

_LOGGER = get_logger(__name__)


def _call_tool(callback: Callable[[Any], Any]) -> Any:
    try:
        adapter = get_default_dependencies().adapter
        return callback(adapter)
    except Exception as exc:
        _LOGGER.exception("event=mcp_tool_failed error_type=%s", type(exc).__name__)
        return {
            "data_mode": "unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Data source unavailable. Research output only; do not infer missing market data.",
        }


def _call_store(callback: Callable[[AegisAlphaStore], Any]) -> Any:
    try:
        return callback(get_default_dependencies().store)
    except Exception as exc:
        _LOGGER.exception("event=mcp_store_failed error_type=%s", type(exc).__name__)
        return {
            "data_mode": "unavailable",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "disclaimer": "Data source unavailable. Research output only; do not infer missing market data.",
        }
```

并把文件顶部 `from aegis_alpha.adapters.factory import create_market_data_adapter` 删掉（已不需要直接调用）。

- [ ] **Step 4: 跑测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_mcp_dependencies.py -v
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/mcp/dependencies.py src/aegis_alpha/mcp/server.py tests/test_mcp_dependencies.py
git commit -m "feat(mcp): single adapter+store instance via dependencies module

Avoid rebuilding jvQuant SDK client and reopening SQLite on every tool
call. Tests can swap dependencies with reset_default_dependencies()."
```

---

## Task 12: Runner 重连指数退避 + 抖动

**Files:**
- Modify: `src/aegis_alpha/runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_runner.py` 末尾追加：

```python
from aegis_alpha.runner import next_interval_seconds


def test_next_interval_seconds_normal_state_returns_base() -> None:
    interval = next_interval_seconds(state="RUNNING", attempt=0, base_seconds=15, max_seconds=300)
    assert interval == 15


def test_next_interval_seconds_degraded_state_grows_exponentially() -> None:
    seq = [
        next_interval_seconds(state="DEGRADED", attempt=i, base_seconds=15, max_seconds=300)
        for i in range(6)
    ]
    # All values within ±25% jitter of expected base * 2**attempt, capped at max
    expected = [15 * (2 ** i) for i in range(6)]
    for actual, exp in zip(seq, expected):
        upper = min(300, exp) * 1.25
        lower = min(300, exp) * 0.75
        assert lower <= actual <= upper, f"{actual} out of [{lower}, {upper}]"


def test_next_interval_seconds_capped_at_max() -> None:
    interval = next_interval_seconds(state="DEGRADED", attempt=20, base_seconds=15, max_seconds=300)
    assert interval <= 300 * 1.25
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_runner.py -v -k next_interval
```

- [ ] **Step 3: 实现**

在 `src/aegis_alpha/runner.py` 加：

```python
import random


def next_interval_seconds(
    *,
    state: str,
    attempt: int,
    base_seconds: int,
    max_seconds: int,
    jitter_fraction: float = 0.25,
) -> float:
    """Exponential backoff with jitter for DEGRADED state, base interval otherwise."""
    if state != "DEGRADED":
        return float(base_seconds)
    raw = min(max_seconds, base_seconds * (2 ** max(0, attempt)))
    jitter = raw * jitter_fraction
    return max(1.0, raw + random.uniform(-jitter, jitter))
```

修改 `run_forever` 使用它：

```python
    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        self.write_status("STARTING", next_action="initial_cycle")
        base_interval = max(5, int(self.config.get("loop_interval_seconds") or 15))
        max_interval = max(base_interval, int(self.config.get("max_reconnect_interval_seconds") or 300))
        attempt = 0
        while not self.stop_requested:
            status = self.run_once()
            if status.state == "DEGRADED":
                attempt += 1
            else:
                attempt = 0
            interval = next_interval_seconds(
                state=status.state,
                attempt=attempt,
                base_seconds=base_interval,
                max_seconds=max_interval,
            )
            time.sleep(interval)
        self.client.disconnect()
        self.write_status("STOPPED", next_action="stopped")
```

- [ ] **Step 4: 在 `config/runner.yaml` 加 `max_reconnect_interval_seconds`**

```yaml
loop_interval_seconds: 15
reconnect_interval_seconds: 30
max_reconnect_interval_seconds: 300
```

- [ ] **Step 5: 跑测试 + Commit**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_runner.py -v
git add src/aegis_alpha/runner.py config/runner.yaml tests/test_runner.py
git commit -m "feat(runner): exponential backoff with jitter for DEGRADED state"
```

---

## Task 13: 收尾 — smoke + lint

- [ ] **Step 1: 编译全部源**

```bash
.venv/bin/python -m compileall src scripts tests
```

- [ ] **Step 2: 跑全量测试**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v --tb=short
```

- [ ] **Step 3: 跑 smoke**

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_check.py
PYTHONPATH=src .venv/bin/python scripts/replay_orderbook_fixture.py
```

- [ ] **Step 4: 跑文件大小检查**

```bash
wc -l src/aegis_alpha/**/*.py src/aegis_alpha/*.py | sort -rn | head -10
```

Expected: 没有文件超过 800 行。

- [ ] **Step 5: 如有问题修复并 commit**

```bash
git add -A
git commit -m "chore(p1): pass smoke + lint after architecture foundations"
```

---

## Self-Review

- [x] **Spec coverage** — 12 个 architecture 项各对应 task：
  - Adapter Protocol → Task 4
  - jvquant 拆分 → Task 10
  - 评级阈值外置 → Task 9
  - 统一时钟 → Tasks 1+2
  - MCP 单例 → Task 11
  - 超时与限流 → Task 10 (`JvQuantQueryClient`) + Task 7 (`TokenBucket`)
  - 日志 → Task 5
  - SQLite migration → Task 8
  - 缓存 TTL → Tasks 6 + 10
  - runner 退避 → Task 12
  - SKILL 路径 → Task 3
- [x] **No placeholders** — Task 10 的 Step 2 用「搬运」而非伪代码描述：明确列出每个待迁移函数名和搬运方法（去 `self`、改成模块级），子类型工程师可以直接执行。
- [x] **Type consistency** — `now_iso` 在 clock 与 events/storage/runner 中统一签名 `() -> str`；`MarketAction` Literal 在 grading.py 与 models.py 中保持一致；`MarketDataAdapter` Protocol 与 mock/jvquant adapter 实际方法签名一致。
- [x] **TDD 流程** — 每个新模块都先写测试。
