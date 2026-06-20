from __future__ import annotations

from typing import Any


def infer_tick_directions(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """用 tick-rule 从价格序列推断每笔主动方向。

    升 → buy, 降 → sell, 平/首笔 → neutral。
    这是推断代理,NOT 交易所真值 BS flag。
    输入不被修改;返回新列表,每项是原 dict 加上 'side' 键。
    """
    out: list[dict[str, Any]] = []
    prev_price: float | None = None
    for t in trades:
        price = float(t["price"])
        if prev_price is None or price == prev_price:
            side = "neutral"
        elif price > prev_price:
            side = "buy"
        else:
            side = "sell"
        out.append({**t, "side": side})
        prev_price = price
    return out
