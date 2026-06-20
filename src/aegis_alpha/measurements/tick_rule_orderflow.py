from __future__ import annotations

from typing import Any


_CAVEAT = (
    "tick-rule 推断方向,非交易所真值 BS flag;A股实测精度约70-80%,"
    "且封板博弈时系统性虚高,不可作为主动买入真值。"
)


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


def tick_rule_big_buy_ratio_proxy(
    trades: list[dict[str, Any]],
    *,
    big_trade_threshold_cny: float = 1_000_000.0,
    limit_up_price: float = 0.0,
) -> dict[str, Any]:
    """大单主动买入占比代理(facts,明标非真值)。

    占比 = 大单主动买金额 / (大单主动买 + 大单主动卖)金额。
    封板虚高:当最后成交价触及/接近 limit_up_price 时置警告。
    弱证据:买点资金确认层,主链 #5→#7 不依赖此值。
    """
    if not trades:
        return {
            "data_mode": "unavailable",
            "tick_rule_big_buy_ratio_proxy": 0.0,
            "is_exchange_truth": False,
            "method": "tick_rule",
            "accuracy_caveat": _CAVEAT,
            "sealing_distortion_warning": False,
        }
    directed = infer_tick_directions(trades)
    big_buy = 0.0
    big_sell = 0.0
    for t in directed:
        amount = float(t["price"]) * float(t["volume"])
        if amount < big_trade_threshold_cny:
            continue
        if t["side"] == "buy":
            big_buy += amount
        elif t["side"] == "sell":
            big_sell += amount
    denom = big_buy + big_sell
    ratio = round(big_buy / denom, 6) if denom > 0 else 0.0

    last_price = float(trades[-1]["price"])
    sealing = bool(limit_up_price > 0 and last_price >= limit_up_price * 0.999)

    return {
        "data_mode": "computed",
        "tick_rule_big_buy_ratio_proxy": ratio,
        "big_buy_amount_cny": round(big_buy, 2),
        "big_sell_amount_cny": round(big_sell, 2),
        "big_trade_threshold_cny": big_trade_threshold_cny,
        "is_exchange_truth": False,
        "method": "tick_rule",
        "accuracy_caveat": _CAVEAT,
        "sealing_distortion_warning": sealing,
        "notes": [
            "弱证据:买点资金确认层,主链 #5→#7 不依赖此值。",
            "封板时此代理高估主动买入,sealing_distortion_warning=true 时不可信。",
        ],
    }
