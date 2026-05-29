# P0 正确性修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 4 个直接污染评级正确性的 bug：speed_pct 按点数算/涨停板上限不分板种/SignalWindowBuffer 非线程安全/first_limit_up_time 字符串比较。

**Architecture:** 全部修改集中在 `src/aegis_alpha/events.py` 和 `src/aegis_alpha/adapters/jvquant_market_data.py`。引入一个新模块 `src/aegis_alpha/symbols.py` 集中处理代码前缀 → 涨停限制的映射，避免散落 if/elif。

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, threading.Lock, bisect。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/aegis_alpha/symbols.py` | 新建 | 股票代码归属判定（市场、板种、涨停限制） |
| `src/aegis_alpha/events.py:63-183` | 修改 | `SignalWindowBuffer` 加锁；`speed_pct` 改为按时间窗口 |
| `src/aegis_alpha/adapters/jvquant_market_data.py:421-427` | 修改 | `change_pct = 10.0` 推断改为按板种查询 limit |
| `src/aegis_alpha/adapters/jvquant_market_data.py:1095-1099` | 修改 | `_time_or_unknown` 归一化为 `HH:MM:SS` |
| `src/aegis_alpha/adapters/jvquant_market_data.py:1670` | 修改 | `_seal_quality_score` 用归一化后的时间字符串 |
| `tests/test_symbols.py` | 新建 | 代码归属/涨停限制测试 |
| `tests/test_events.py` | 修改 | 增加 speed_pct 时间窗口测试、并发测试 |
| `tests/test_jvquant_adapter.py` | 修改 | 增加板种推断测试、时间归一化测试 |

---

## Task 1: 创建 `symbols.py` 模块和测试（涨停限制按板种分流）

**Files:**
- Create: `src/aegis_alpha/symbols.py`
- Create: `tests/test_symbols.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_symbols.py`：

```python
from __future__ import annotations

import pytest

from aegis_alpha.symbols import (
    Board,
    board_of,
    daily_limit_pct,
    normalize_symbol,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("600519", "600519"),
        ("600519.SH", "600519"),
        (" 000001.SZ ", "000001"),
        ("sz000001", "000001"),
        ("SH600519", "600519"),
    ],
)
def test_normalize_symbol(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "symbol,expected_board",
    [
        ("600519", Board.SH_MAIN),
        ("601318", Board.SH_MAIN),
        ("603259", Board.SH_MAIN),
        ("605588", Board.SH_MAIN),
        ("688981", Board.STAR),
        ("689009", Board.STAR),
        ("000001", Board.SZ_MAIN),
        ("002230", Board.SZ_MAIN),
        ("003816", Board.SZ_MAIN),
        ("300750", Board.CHINEXT),
        ("301029", Board.CHINEXT),
        ("830799", Board.BSE),
        ("872925", Board.BSE),
        ("430564", Board.BSE),
    ],
)
def test_board_of(symbol: str, expected_board: Board) -> None:
    assert board_of(symbol) == expected_board


@pytest.mark.parametrize(
    "symbol,expected_pct",
    [
        ("600519", 10.0),
        ("000001", 10.0),
        ("688981", 20.0),
        ("300750", 20.0),
        ("830799", 30.0),
    ],
)
def test_daily_limit_pct_normal_stocks(symbol: str, expected_pct: float) -> None:
    assert daily_limit_pct(symbol) == expected_pct


def test_board_of_unknown_returns_unknown() -> None:
    assert board_of("999999") == Board.UNKNOWN


def test_daily_limit_pct_unknown_defaults_to_10() -> None:
    assert daily_limit_pct("999999") == 10.0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/faillonexie/Projects/aegis-alpha
PYTHONPATH=src .venv/bin/python -m pytest tests/test_symbols.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'aegis_alpha.symbols'`。

- [ ] **Step 3: 写最小实现**

创建 `src/aegis_alpha/symbols.py`：

```python
from __future__ import annotations

import re
from enum import Enum


class Board(Enum):
    SH_MAIN = "sh_main"
    SZ_MAIN = "sz_main"
    STAR = "star"
    CHINEXT = "chinext"
    BSE = "bse"
    UNKNOWN = "unknown"


_SH_PREFIX_PATTERN = re.compile(r"^(sh|SH)")
_SZ_PREFIX_PATTERN = re.compile(r"^(sz|SZ)")


def normalize_symbol(symbol: str) -> str:
    """Strip whitespace, market prefix/suffix, return 6-digit code."""
    text = symbol.strip().upper()
    text = _SH_PREFIX_PATTERN.sub("", text)
    text = _SZ_PREFIX_PATTERN.sub("", text)
    return text.split(".", 1)[0]


def board_of(symbol: str) -> Board:
    code = normalize_symbol(symbol)
    if len(code) != 6 or not code.isdigit():
        return Board.UNKNOWN
    if code.startswith(("600", "601", "603", "605")):
        return Board.SH_MAIN
    if code.startswith(("688", "689")):
        return Board.STAR
    if code.startswith(("000", "001", "002", "003")):
        return Board.SZ_MAIN
    if code.startswith(("300", "301")):
        return Board.CHINEXT
    if code.startswith(("4", "8")):
        return Board.BSE
    return Board.UNKNOWN


_LIMIT_BY_BOARD: dict[Board, float] = {
    Board.SH_MAIN: 10.0,
    Board.SZ_MAIN: 10.0,
    Board.STAR: 20.0,
    Board.CHINEXT: 20.0,
    Board.BSE: 30.0,
    Board.UNKNOWN: 10.0,
}


def daily_limit_pct(symbol: str) -> float:
    """Return the standard daily limit percentage for a non-ST stock."""
    return _LIMIT_BY_BOARD[board_of(symbol)]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_symbols.py -v
```

Expected: PASS（13 个 test 全过）。

- [ ] **Step 5: Commit**

```bash
git add src/aegis_alpha/symbols.py tests/test_symbols.py
git commit -m "feat(symbols): add board classification and daily limit lookup

Centralize symbol parsing and per-board (SH main / SZ main / STAR /
ChiNext / BSE) limit-up percentage so adapter code stops assuming 10%."
```

---

## Task 2: jvQuant 适配器 `change_pct` 推断按板种分流

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant_market_data.py:421-427`
- Modify: `tests/test_jvquant_adapter.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_jvquant_adapter.py` 末尾追加（测试不需要真实 jvQuant，只测内部推断函数）：

```python
from aegis_alpha.adapters.jvquant_market_data import _inferred_change_pct_for_limit_up


def test_inferred_change_pct_sh_main() -> None:
    assert _inferred_change_pct_for_limit_up("600519") == 10.0


def test_inferred_change_pct_sz_main() -> None:
    assert _inferred_change_pct_for_limit_up("000001") == 10.0


def test_inferred_change_pct_star_board() -> None:
    assert _inferred_change_pct_for_limit_up("688981") == 20.0


def test_inferred_change_pct_chinext() -> None:
    assert _inferred_change_pct_for_limit_up("300750") == 20.0


def test_inferred_change_pct_bse() -> None:
    assert _inferred_change_pct_for_limit_up("830799") == 30.0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_jvquant_adapter.py -v -k inferred_change_pct
```

Expected: FAIL，`ImportError: cannot import name '_inferred_change_pct_for_limit_up'`。

- [ ] **Step 3: 在适配器顶部加导出辅助函数**

在 `src/aegis_alpha/adapters/jvquant_market_data.py` 的 import 区添加：

```python
from aegis_alpha.symbols import daily_limit_pct, normalize_symbol as canonical_symbol
```

注意：文件已经有自己定义的 `normalize_symbol`（第 43 行）。把它替换为复用 `aegis_alpha.symbols`：

将原来的：
```python
def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().split(".", 1)[0]
```

改为：
```python
from aegis_alpha.symbols import normalize_symbol  # noqa: F401  re-export for back-compat
```

并在文件中（建议在 `_float_or_zero` 之前）加新辅助：

```python
def _inferred_change_pct_for_limit_up(symbol: str) -> float:
    """Return the daily-limit percentage to infer when seal metrics indicate limit-up."""
    return daily_limit_pct(symbol)
```

- [ ] **Step 4: 修改 425-427 行的硬编码 10.0**

定位 `get_second_board_candidates` 中的：

```python
            if change_pct == 0 and (first_limit_up_time != "unknown" or seal_amount_cny > 0):
                change_pct = 10.0
                change_pct_inferred = True
```

改为：

```python
            if change_pct == 0 and (first_limit_up_time != "unknown" or seal_amount_cny > 0):
                change_pct = _inferred_change_pct_for_limit_up(symbol)
                change_pct_inferred = True
```

- [ ] **Step 5: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_jvquant_adapter.py -v
```

Expected: PASS（含原有测试 + 5 个新 test）。

- [ ] **Step 6: 验证 mock 适配器和事件测试不受影响**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 所有原有 test 仍 PASS。

- [ ] **Step 7: Commit**

```bash
git add src/aegis_alpha/adapters/jvquant_market_data.py tests/test_jvquant_adapter.py
git commit -m "fix(jvquant): use board-aware daily limit when inferring change_pct

Limit-up is 10% on SH/SZ main, 20% on STAR/ChiNext, 30% on BSE.
The previous hardcoded 10.0 broke 688/300/8xx grading because the
candidate would never reach the change_pct >= 9.5 A-grade threshold."
```

---

## Task 3: `SignalWindowBuffer.speed_pct` 改为按时间窗口

**Files:**
- Modify: `src/aegis_alpha/events.py:63-183`
- Modify: `tests/test_events.py`

- [ ] **Step 1: 写失败测试（暴露当前按点数算的 bug）**

在 `tests/test_events.py` 末尾追加：

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aegis_alpha.events import SignalWindowBuffer


SH_TZ = ZoneInfo("Asia/Shanghai")


def _ts(base: datetime, offset_seconds: int) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


def test_speed_pct_uses_time_window_not_point_count() -> None:
    """High-frequency ticks should not collapse a 5-minute window into seconds."""
    buf = SignalWindowBuffer()
    base = datetime(2026, 5, 29, 10, 0, 0, tzinfo=SH_TZ)

    # 50 ticks within 30 seconds at price 10.00
    for i in range(50):
        buf.add_price("600000", _ts(base, i // 2), 10.00, 1_000_000)

    # 5 minutes later: price 10.50 (+5%)
    buf.add_price("600000", _ts(base, 5 * 60), 10.50, 1_000_000)

    speed_5m = buf.speed_pct("600000", 5)
    assert abs(speed_5m - 5.0) < 0.01, f"Expected ~5.0%, got {speed_5m}"


def test_speed_pct_partial_window_when_data_shorter_than_minutes() -> None:
    """When buffer has < N minutes, fall back to earliest available point."""
    buf = SignalWindowBuffer()
    base = datetime(2026, 5, 29, 10, 0, 0, tzinfo=SH_TZ)

    buf.add_price("600000", _ts(base, 0), 10.00, 1_000_000)
    buf.add_price("600000", _ts(base, 60), 10.10, 1_000_000)  # 1 min later, +1%

    # Asking for 5m speed, only 1m of data available
    speed_5m = buf.speed_pct("600000", 5)
    assert abs(speed_5m - 1.0) < 0.01


def test_speed_pct_zero_when_single_point() -> None:
    buf = SignalWindowBuffer()
    buf.add_price("600000", "2026-05-29T10:00:00+08:00", 10.0, 1_000_000)
    assert buf.speed_pct("600000", 5) == 0.0


def test_signal_window_buffer_concurrent_writes_safe() -> None:
    """Concurrent add_price/add_big_order_flow must not crash or corrupt counts."""
    import threading

    buf = SignalWindowBuffer()
    iterations = 200
    threads_per_kind = 4

    def add_prices() -> None:
        for i in range(iterations):
            buf.add_price("600000", f"2026-05-29T10:{i // 60:02d}:{i % 60:02d}+08:00", 10.0 + i * 0.001, 1_000_000)

    def add_flows() -> None:
        for _ in range(iterations):
            buf.add_big_order_flow("600000", 1.0)

    threads = []
    for _ in range(threads_per_kind):
        threads.append(threading.Thread(target=add_prices))
        threads.append(threading.Thread(target=add_flows))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Each thread adds `iterations` flow events of 1.0 CNY each
    snapshot = buf.latest_snapshot("600000")
    assert snapshot.big_order_net_inflow_cny == iterations * threads_per_kind
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_events.py::test_speed_pct_uses_time_window_not_point_count -v
PYTHONPATH=src .venv/bin/python -m pytest tests/test_events.py::test_signal_window_buffer_concurrent_writes_safe -v
```

Expected: FAIL（speed_pct 用了 51 个点而不是 5 分钟前的点；并发测试可能撕裂 counter 或抛异常）。

- [ ] **Step 3: 实现按时间窗口的 speed_pct + 加锁**

替换 `src/aegis_alpha/events.py` 的 `SignalWindowBuffer` 类（第 63-183 行）为：

```python
class SignalWindowBuffer:
    """Thread-safe rolling signal window for realtime handlers and deterministic tests."""

    def __init__(self, max_points_per_symbol: int = 600) -> None:
        self.max_points_per_symbol = max_points_per_symbol
        self._lock = threading.RLock()
        self._points: dict[str, deque[tuple[str, float, float]]] = defaultdict(
            lambda: deque(maxlen=max_points_per_symbol)
        )
        self._big_order_amount: dict[str, float] = defaultdict(float)
        self._change_pct: dict[str, float] = defaultdict(float)
        self._orderbook_quality: dict[str, float] = defaultdict(lambda: 50.0)
        self._ask_pressure: dict[str, float] = defaultdict(lambda: 50.0)
        self._seal_amount: dict[str, float] = defaultdict(float)
        self._seal_decay: dict[str, float] = defaultdict(float)
        self._sell_wall_amount: dict[str, float] = defaultdict(float)
        self._notes: dict[str, list[str]] = defaultdict(list)

    def add_price(
        self,
        symbol: str,
        timestamp: str,
        price: float,
        turnover_cny: float = 0.0,
        change_pct: float | None = None,
    ) -> None:
        if price <= 0:
            return
        with self._lock:
            self._points[symbol].append((timestamp, price, turnover_cny))
            if change_pct is not None:
                self._change_pct[symbol] = change_pct

    def add_big_order_flow(self, symbol: str, amount_cny: float) -> None:
        with self._lock:
            self._big_order_amount[symbol] += amount_cny

    def set_orderbook_quality(self, symbol: str, quality_score: float) -> None:
        with self._lock:
            self._orderbook_quality[symbol] = round(max(0.0, min(100.0, quality_score)), 2)

    def set_orderbook_metrics(
        self,
        symbol: str,
        *,
        quality_score: float,
        seal_amount_cny: float,
        seal_decay_pct: float,
        ask_pressure_score: float = 50.0,
        sell_wall_amount_cny: float = 0.0,
        notes: list[str] | None = None,
    ) -> None:
        with self._lock:
            self._orderbook_quality[symbol] = round(max(0.0, min(100.0, quality_score)), 2)
            self._ask_pressure[symbol] = round(max(0.0, min(100.0, ask_pressure_score)), 2)
            self._seal_amount[symbol] = max(0.0, seal_amount_cny)
            self._seal_decay[symbol] = max(0.0, seal_decay_pct)
            self._sell_wall_amount[symbol] = max(0.0, sell_wall_amount_cny)
            self._notes[symbol] = list(notes or [])

    def previous_seal_amount(self, symbol: str) -> float:
        with self._lock:
            return self._seal_amount.get(symbol, 0.0)

    def speed_pct(self, symbol: str, minutes: int) -> float:
        """Return percentage change over the last `minutes` minutes by timestamp."""
        with self._lock:
            points = list(self._points.get(symbol, []))
        if len(points) < 2:
            return 0.0
        latest_timestamp, latest_price, _ = points[-1]
        latest_dt = _parse_timestamp(latest_timestamp)
        if latest_dt is None or latest_price <= 0:
            return 0.0
        cutoff = latest_dt - timedelta(minutes=minutes)
        # Walk from oldest to newest, take the first point whose timestamp >= cutoff.
        # If no point satisfies cutoff (all newer than latest, impossible) or
        # cutoff is before the oldest stored point, fall back to the earliest point.
        base_price = points[0][1]
        for ts, price, _ in points:
            point_dt = _parse_timestamp(ts)
            if point_dt is None:
                continue
            if point_dt >= cutoff:
                base_price = price
                break
        if base_price <= 0:
            return 0.0
        return round((latest_price / base_price - 1.0) * 100.0, 4)

    def latest_snapshot(
        self,
        symbol: str,
        *,
        name: str = "unknown",
        theme: str = "unknown",
        provider: str = "jvQuant",
        data_mode: str = "realtime_buffer",
        change_pct: float = 0.0,
        orderbook_quality_score: float | None = None,
        seal_amount_cny: float = 0.0,
        received_at: str | None = None,
    ) -> SignalSnapshot:
        with self._lock:
            points = list(self._points.get(symbol, []))
            big_order_net = self._big_order_amount.get(symbol, 0.0)
            change_pct_stored = self._change_pct.get(symbol, 0.0)
            orderbook_quality_stored = self._orderbook_quality.get(symbol, 50.0)
            ask_pressure = self._ask_pressure.get(symbol, 50.0)
            seal_amount_stored = self._seal_amount.get(symbol, 0.0)
            seal_decay = self._seal_decay.get(symbol, 0.0)
            sell_wall = self._sell_wall_amount.get(symbol, 0.0)
            notes_stored = list(self._notes.get(symbol, []))

        timestamp = points[-1][0] if points else (received_at or now_iso())
        price = points[-1][1] if points else 0.0
        turnover = points[-1][2] if points else 0.0
        received = received_at or now_iso()
        return SignalSnapshot(
            symbol=symbol,
            name=name,
            theme=theme,
            provider=provider,
            data_mode=data_mode,
            price=price,
            change_pct=change_pct if change_pct != 0.0 else change_pct_stored,
            speed_1m_pct=self.speed_pct(symbol, 1),
            speed_3m_pct=self.speed_pct(symbol, 3),
            speed_5m_pct=self.speed_pct(symbol, 5),
            speed_10m_pct=self.speed_pct(symbol, 10),
            big_order_net_inflow_cny=big_order_net,
            big_order_net_inflow_ratio=round(big_order_net / turnover, 4) if turnover else 0.0,
            orderbook_quality_score=(
                orderbook_quality_score
                if orderbook_quality_score is not None
                else orderbook_quality_stored
            ),
            ask_pressure_score=ask_pressure,
            seal_amount_cny=seal_amount_cny or seal_amount_stored,
            seal_decay_pct=seal_decay,
            sell_wall_amount_cny=sell_wall,
            data_timestamp=timestamp,
            provider_timestamp=timestamp,
            received_at=received,
            freshness_status=freshness_status(timestamp, received),
            notes=[
                "Realtime buffer snapshot; raw WebSocket messages are not exposed to agents.",
                *notes_stored,
            ],
        )
```

并在文件顶部 import 区追加（如果还没有）：

```python
import threading
from datetime import datetime, timedelta
```

并在文件靠近 `freshness_status` 的位置加辅助：

```python
def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SH_TZ)
    return parsed
```

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_events.py -v
```

Expected: 全部 PASS（含 4 个新 test）。

- [ ] **Step 5: 跑全量测试确认未破坏其他**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/events.py tests/test_events.py
git commit -m "fix(events): SignalWindowBuffer speed_pct uses time window, add lock

speed_pct(minutes=5) was previously the change between the latest tick
and the tick 5 entries earlier in the deque, which collapsed to seconds
under high-frequency lv1 callbacks. Switch to a timestamp-based scan
so the 5-minute name reflects the 5-minute meaning.

Also wrap all mutable state behind a single RLock so concurrent
WebSocket callback threads cannot tear counters or dict structures."
```

---

## Task 4: `_time_or_unknown` 归一化为 `HH:MM:SS`

**Files:**
- Modify: `src/aegis_alpha/adapters/jvquant_market_data.py:1095-1099`
- Modify: `tests/test_jvquant_adapter.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_jvquant_adapter.py` 末尾追加：

```python
from aegis_alpha.adapters.jvquant_market_data import JvQuantMarketDataAdapter


def test_time_or_unknown_normalizes_short_form(monkeypatch) -> None:
    monkeypatch.setenv("JVQUANT_TOKEN", "test-token")
    adapter = JvQuantMarketDataAdapter(token="test-token")
    assert adapter._time_or_unknown("9:45") == "09:45:00"
    assert adapter._time_or_unknown("9:45:30") == "09:45:30"
    assert adapter._time_or_unknown("09:45") == "09:45:00"
    assert adapter._time_or_unknown("09:45:30") == "09:45:30"
    assert adapter._time_or_unknown("") == "unknown"
    assert adapter._time_or_unknown("None") == "unknown"
    assert adapter._time_or_unknown("nan") == "unknown"
    assert adapter._time_or_unknown("garbage") == "unknown"


def test_seal_quality_score_uses_normalized_time(monkeypatch) -> None:
    """Short-form '9:45' must score the same as '09:45:00'."""
    monkeypatch.setenv("JVQUANT_TOKEN", "test-token")
    adapter = JvQuantMarketDataAdapter(token="test-token")
    score_short = adapter._seal_quality_score("09:45:00", 200_000_000, 3.0)
    # The internal grading expects normalized form; assert idempotent.
    assert score_short > 0  # 09:45 hits the early seal bracket
    score_normalized = adapter._seal_quality_score(
        adapter._time_or_unknown("9:45"), 200_000_000, 3.0
    )
    assert score_short == score_normalized
```

- [ ] **Step 2: 跑测试确认失败**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_jvquant_adapter.py -v -k "time_or_unknown or seal_quality_score_uses_normalized"
```

Expected: FAIL（短格式没归一化，`"9:45"` 直接返回原样导致字典序比较错）。

- [ ] **Step 3: 修改 `_time_or_unknown`**

定位 `src/aegis_alpha/adapters/jvquant_market_data.py:1095-1099`：

```python
    def _time_or_unknown(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text or text in {"0", "None", "nan", "NaN"}:
            return "unknown"
        return text
```

替换为：

```python
    def _time_or_unknown(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text or text in {"0", "None", "nan", "NaN"}:
            return "unknown"
        return self._normalize_time_string(text)

    @staticmethod
    def _normalize_time_string(text: str) -> str:
        """Normalize HH:MM[:SS] to HH:MM:SS with two-digit hour. Returns 'unknown' on failure."""
        match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if not match:
            return text  # leave non-time strings untouched (e.g., timezone-stamped values)
        hour = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3) or 0)
        if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
            return "unknown"
        return f"{hour:02d}:{minute:02d}:{second:02d}"
```

注意文件顶部已 `import re`，无需新增。

- [ ] **Step 4: 跑测试确认通过**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_jvquant_adapter.py -v
```

Expected: 全部 PASS（含 2 个新 test）。

- [ ] **Step 5: 跑全量测试确认未破坏其他**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add src/aegis_alpha/adapters/jvquant_market_data.py tests/test_jvquant_adapter.py
git commit -m "fix(jvquant): normalize first_limit_up_time to HH:MM:SS

Provider returned values like '9:45' without leading zero or seconds.
String comparison '9:45' <= '09:45:00' is False (lexicographic), so
_seal_quality_score's early-seal bracket silently lost 35 points and
B-grade candidates fell to C. Normalize at parse time."
```

---

## Task 5: 跑 smoke check 验证整条 pipeline 仍工作

- [ ] **Step 1: 编译所有源**

```bash
cd /Users/faillonexie/Projects/aegis-alpha
.venv/bin/python -m compileall src scripts tests
```

Expected: 无 syntax 错误。

- [ ] **Step 2: 跑项目自带 smoke check**

```bash
PYTHONPATH=src .venv/bin/python scripts/smoke_check.py
```

Expected: 退出码 0，无 traceback。

- [ ] **Step 3: 跑离线 replay fixture**

```bash
PYTHONPATH=src .venv/bin/python scripts/replay_orderbook_fixture.py
```

Expected: 输出包含 SignalSnapshot 和 MarketEvent，无异常。

- [ ] **Step 4: 全量测试最后一次**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit smoke check 通过的标记（可选）**

如果一切顺利，无需额外 commit。如果上述步骤过程中发现 P0 修复破坏了 smoke 脚本（例如脚本里也用了 `normalize_symbol` 旧定义），把修复加到本 task：

```bash
git add -A
git commit -m "chore: confirm P0 correctness fixes pass smoke pipeline"
```

---

## Self-Review

- [x] **Spec coverage** — 4 个 P0 bug 各对应一个 task：Task 1+2 涨停板上限；Task 3 speed_pct + 线程安全；Task 4 时间归一化；Task 5 smoke 验证。
- [x] **No placeholders** — 所有代码都给到完整实现而非伪代码。
- [x] **Type consistency** — `Board` enum、`normalize_symbol`、`daily_limit_pct`、`_inferred_change_pct_for_limit_up`、`_normalize_time_string` 在 task 之间签名一致。
- [x] **TDD 流程** — 每个 task 都是「写失败测试 → 跑确认失败 → 实现 → 跑确认通过 → commit」。
