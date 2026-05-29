from __future__ import annotations

from typing import Any


SIGNAL_SNAPSHOT_FIELD_UNITS: dict[str, str] = {
    "price": "CNY price.",
    "change_pct": "Percent value. 2.04 means 2.04%, not 204%.",
    "speed_1m_pct": "Percent value over the local 1-minute window. 0.0929 means 0.0929%, not 9.29%.",
    "speed_3m_pct": "Percent value over the local 3-minute window. 0.0929 means 0.0929%, not 9.29%.",
    "speed_5m_pct": "Percent value over the local 5-minute window. 0.0929 means 0.0929%, not 9.29%.",
    "speed_10m_pct": "Percent value over the local 10-minute window. 0.0929 means 0.0929%, not 9.29%.",
    "big_order_net_inflow_cny": "CNY amount. Current realtime lv2 implementation is a coarse large-trade accumulation unless direction is confirmed.",
    "big_order_net_inflow_ratio": "Ratio value. 0.0311 means 3.11%.",
    "orderbook_quality_score": "0-100 internal score estimated from lv10 depth.",
    "ask_pressure_score": "0-100 internal score estimated from lv10 depth and seal decay.",
    "seal_amount_cny": "CNY amount estimated from best bid when price is near limit-up; not exchange-authoritative queue size.",
    "seal_decay_pct": "Percent value. 59.41 means 59.41%, not 5941%.",
    "sell_wall_amount_cny": "CNY amount estimated from best ask depth.",
}


AGENT_INTERPRETATION_RULES = [
    "All fields ending with _pct are already percent values: 0.0929 means 0.0929%, not 9.29%.",
    "Fields ending with _ratio are ratios: 0.0311 means 3.11%.",
    "Fields ending with _score are 0-100 internal scores unless documented otherwise.",
    "Fields ending with _cny are CNY amounts.",
    "Realtime orderbook fields are internal estimates from lv10 depth unless official provider evidence says otherwise.",
    "Do not describe seal_amount_cny or orderbook_quality_score as exchange-authoritative Level-2 queue position.",
    "If freshness_status is stale during intraday analysis, cap grade at B or reject analysis.",
    "Never issue direct buy, sell, order, sweep-board, or queue-board instructions.",
]


def signal_snapshot_agent_context() -> dict[str, Any]:
    return {
        "field_units": SIGNAL_SNAPSHOT_FIELD_UNITS,
        "interpretation_rules": AGENT_INTERPRETATION_RULES,
    }


def signal_snapshot_agent_context_text() -> str:
    lines = ["Aegis Alpha SignalSnapshot field units and interpretation rules:"]
    for name, unit in SIGNAL_SNAPSHOT_FIELD_UNITS.items():
        lines.append(f"- {name}: {unit}")
    lines.append("Rules:")
    for rule in AGENT_INTERPRETATION_RULES:
        lines.append(f"- {rule}")
    return "\n".join(lines)
