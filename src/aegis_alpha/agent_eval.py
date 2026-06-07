from __future__ import annotations

import json
import re
from typing import Any

from aegis_alpha.agent_context import signal_snapshot_agent_context
from aegis_alpha.models import MarketEvent, SignalSnapshot


REQUIRED_FACTORS = (
    "market_emotion",
    "theme_position",
    "float_size",
    "volume_energy",
    "reseal_strength",
)

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
            "signal_snapshot_context": signal_snapshot_agent_context(),
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
        "freshness_warning, data_timestamp, disclaimer, "
        "promotion_likelihood(high/medium/low 三选一，代表晋级三板概率分档), "
        "factor_analysis{market_emotion(市场情绪), theme_position(题材所在位置), "
        "float_size(股本大小), volume_energy(量能), reseal_strength(回封力度)}。"
        "必须逐项给出 factor_analysis 的五个维度理由，并给出 promotion_likelihood(high/medium/low)"
        "与综合 grade；不得只给笼统总结。"
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
            "passed": bool(re.search(r"(非|不是|不构成|不作为|不能作为).{0,12}(投资建议|交易建议|交易指令|操作指令)", content)),
        }
    )
    checks.append(
        {
            "name": "mentions_offline_or_synthetic",
            "passed": any(keyword in content for keyword in ("离线", "合成", "历史", "回放", "synthetic", "offline", "非真实行情")),
        }
    )

    if parsed is not None:
        # Validates the AGENT's self-reported grade (agent judgment), not a program grade.
        grades = parsed_grades(parsed)
        checks.append(
            {
                "name": "grade_present",
                "passed": bool(grades) and all(grade in {"A", "B", "C", "REJECT"} for grade in grades),
                "detail": grades,
            }
        )
        checks.append(
            {
                "name": "natural_language_reason_present",
                "passed": parsed_has_natural_language_reason(parsed),
            }
        )
        likelihoods = parsed_promotion_likelihoods(parsed)
        checks.append(
            {
                "name": "promotion_likelihood_present",
                "passed": bool(likelihoods) and all(v in {"high", "medium", "low"} for v in likelihoods),
                "detail": likelihoods,
            }
        )
        factor_analyses = parsed_factor_analyses(parsed)
        checks.append(
            {
                "name": "five_factors_present",
                "passed": bool(factor_analyses) and all(
                    isinstance(fa, dict) and all(
                        bool(str(fa.get(key) or "").strip()) for key in REQUIRED_FACTORS
                    )
                    for fa in factor_analyses
                ),
                "detail": [list(fa.keys()) if isinstance(fa, dict) else fa for fa in factor_analyses],
            }
        )
        if expected_freshness_status == "stale":
            checks.append(
                {
                    "name": "stale_data_caps_grade",
                    "passed": bool(grades) and all(grade in {"B", "C", "REJECT"} for grade in grades),
                    "detail": grades,
                }
            )
            checks.append(
                {
                    "name": "stale_data_caps_promotion",
                    "passed": bool(likelihoods) and all(v in {"medium", "low"} for v in likelihoods),
                    "detail": likelihoods,
                }
            )

    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "parsed": parsed,
    }


def parsed_grades(parsed: dict[str, Any]) -> list[str]:
    grade = str(parsed.get("grade") or "")
    if grade:
        return [grade]
    items = parsed.get("per_symbol")
    if isinstance(items, list):
        return [str(item.get("grade") or "") for item in items if isinstance(item, dict)]
    return []


def parsed_has_natural_language_reason(parsed: dict[str, Any]) -> bool:
    if str(parsed.get("natural_language_reason") or "").strip():
        return True
    items = parsed.get("per_symbol")
    if isinstance(items, list) and items:
        return all(
            isinstance(item, dict) and bool(str(item.get("natural_language_reason") or "").strip())
            for item in items
        )
    return False


def parsed_promotion_likelihoods(parsed: dict[str, Any]) -> list[str]:
    """Mirror of parsed_grades for promotion_likelihood values."""
    value = str(parsed.get("promotion_likelihood") or "")
    if value:
        return [value]
    items = parsed.get("per_symbol")
    if isinstance(items, list):
        return [
            str(item.get("promotion_likelihood") or "")
            for item in items
            if isinstance(item, dict)
        ]
    return []


def parsed_factor_analyses(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the factor_analysis dict(s): top-level as [dict] or one per per_symbol item."""
    fa = parsed.get("factor_analysis")
    if isinstance(fa, dict):
        return [fa]
    items = parsed.get("per_symbol")
    if isinstance(items, list):
        return [
            item.get("factor_analysis") or {}
            for item in items
            if isinstance(item, dict)
        ]
    return []
