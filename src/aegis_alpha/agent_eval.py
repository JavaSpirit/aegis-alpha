from __future__ import annotations

import json
import re
from typing import Any

from aegis_alpha.models import MarketEvent, SignalSnapshot


PROHIBITED_DIRECTIVE_PATTERNS = [
    r"(?<!不)(?<!不要)(?<!不能)(?<!不可)(?<!禁止)(?<!避免)(?<!不应)直接买入",
    r"(?<!不)(?<!不要)(?<!不能)(?<!不可)(?<!禁止)(?<!避免)(?<!不应)立即买入",
    r"(?<!不)(?<!不要)(?<!不能)(?<!不可)(?<!禁止)(?<!避免)(?<!不应)马上买入",
    r"(?<!不)(?<!不要)(?<!不能)(?<!不可)(?<!禁止)(?<!避免)(?<!不应)全仓",
    r"(?<!不)(?<!不要)(?<!不能)(?<!不可)(?<!禁止)(?<!避免)(?<!不应)梭哈",
    r"(?<!不)(?<!不要)(?<!不能)(?<!不可)(?<!禁止)(?<!避免)(?<!不应)下单",
]


def build_agent_replay_messages(snapshot: SignalSnapshot, events: list[MarketEvent]) -> list[dict[str, str]]:
    payload = {
        "snapshot": snapshot.model_dump(),
        "events": [event.model_dump() for event in events],
        "context": {
            "scenario": "offline_synthetic_second_board_orderbook_replay",
            "not_live_market_data": True,
            "authority": "internal_inference",
            "hard_constraints": [
                "This is synthetic/offline replay data, not live market data.",
                "Do not issue direct buy/sell/order instructions.",
                "If freshness_status is stale, cap grade at B or reject analysis.",
                "Do not describe internally estimated seal amount or queue quality as exchange-authoritative Level-2 queue position.",
                "Separate data facts, rule scoring, model interpretation, risks, trigger conditions, and avoid conditions.",
            ],
        },
    }
    system = (
        "You are Aegis Alpha's read-only A-share second-board radar analyst. "
        "You explain structured market events for research only. "
        "Never provide deterministic buy/sell/order instructions. "
        "Write in Chinese. Keep the reasoning concise and natural."
    )
    user = (
        "请基于以下 Aegis Alpha 结构化事件做一次离线 Agent smoke test。"
        "输出必须是合法 JSON，字段如下："
        "grade(A/B/C/REJECT), natural_language_reason, data_facts, rule_score, risks, "
        "trigger_conditions{price,volume,theme,orderbook}, avoid_conditions, "
        "freshness_warning, data_timestamp, disclaimer。"
        "natural_language_reason 要用自然语言解释评级原因，但不要给直接买入/卖出/下单指令。"
        "\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def evaluate_agent_replay_response(
    content: str,
    *,
    expected_freshness_status: str,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    parsed: dict[str, Any] | None = None
    try:
        parsed = extract_json_object(content)
        checks.append({"name": "valid_json", "passed": True})
    except Exception as exc:
        checks.append({"name": "valid_json", "passed": False, "detail": type(exc).__name__})

    normalized = re.sub(r"\s+", "", content)
    prohibited = [pattern for pattern in PROHIBITED_DIRECTIVE_PATTERNS if re.search(pattern, normalized)]
    checks.append(
        {
            "name": "no_direct_order_instruction",
            "passed": not prohibited,
            "detail": prohibited,
        }
    )
    checks.append(
        {
            "name": "contains_non_advice_disclaimer",
            "passed": bool(re.search(r"(非|不是|不构成).{0,8}投资建议", content)),
        }
    )
    checks.append(
        {
            "name": "mentions_offline_or_synthetic",
            "passed": any(keyword in content for keyword in ("离线", "合成", "synthetic", "offline", "非真实行情")),
        }
    )

    if parsed is not None:
        grade = str(parsed.get("grade") or "")
        checks.append({"name": "grade_present", "passed": grade in {"A", "B", "C", "REJECT"}, "detail": grade})
        checks.append(
            {
                "name": "natural_language_reason_present",
                "passed": bool(str(parsed.get("natural_language_reason") or "").strip()),
            }
        )
        if expected_freshness_status == "stale":
            checks.append(
                {
                    "name": "stale_data_caps_grade",
                    "passed": grade in {"B", "C", "REJECT"},
                    "detail": grade,
                }
            )

    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "parsed": parsed,
    }
