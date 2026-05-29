from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from aegis_alpha.agent_context import signal_snapshot_agent_context
from aegis_alpha.agent_eval import evaluate_agent_replay_response
from aegis_alpha.config import load_project_env
from aegis_alpha.storage import default_db_path


DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"


def latest_near_snapshots(db_path: Path, symbols: list[str], target_time: str) -> list[dict]:
    snapshots = []
    with sqlite3.connect(db_path) as conn:
        for symbol in symbols:
            row = conn.execute(
                """
                SELECT payload_json, ABS(strftime('%s', data_timestamp) - strftime('%s', ?)) AS delta
                FROM signal_snapshots
                WHERE symbol = ?
                ORDER BY delta ASC, id DESC
                LIMIT 1
                """,
                (target_time, symbol),
            ).fetchone()
            if row is None:
                continue
            payload = json.loads(row[0])
            payload["target_time"] = target_time
            payload["seconds_from_target"] = int(row[1])
            snapshots.append(payload)
    return snapshots


def call_deepseek(messages: list[dict[str, str]], *, model: str, timeout_seconds: int) -> dict:
    import urllib.error
    import urllib.request

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY missing")
    payload = {
        "model": model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "temperature": 0.1,
        "max_tokens": 1600,
        "stream": False,
    }
    request = urllib.request.Request(
        DEEPSEEK_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {body[:500]}") from exc


def build_messages(*, target_time: str, snapshots: list[dict]) -> list[dict[str, str]]:
    context = signal_snapshot_agent_context()
    system = (
        "你是 Aegis Alpha 的只读 A股盘中观察分析员。你只能基于结构化数据做研究解释。"
        "不要给买入、卖出、下单、扫板、排板等确定性交易指令。"
        "如果数据不是二板/涨停候选，要明确说不适合打板观察。输出中文合法 JSON。"
    )
    user = (
        f"下面是 Aegis Alpha 从本地 SQLite 取出的 {target_time} 附近历史盘中截面。"
        "请假装你站在该时间点，只把这些作为当时事实数据来评价，但必须说明这是历史回放，不是当前实时行情。"
        "必须严格遵守 agent_context 中的字段单位，尤其是 _pct 字段已经是百分比数值。"
        "输出 JSON 字段：market_context, per_symbol[{symbol, grade, natural_language_reason, data_facts, risks, "
        "trigger_conditions, avoid_conditions}], overall_conclusion, disclaimer。"
        "评级只能用 A/B/C/REJECT；不适合打板的标的请给 C 或 REJECT。不要直接建议买入/下单。\n\n"
        + json.dumps(
            {
                "target_time": target_time,
                "agent_context": context,
                "snapshots": snapshots,
            },
            ensure_ascii=False,
        )
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def evaluate_historical_snapshot(
    *,
    db_path: Path,
    target_time: str,
    symbols: list[str],
    model: str,
    timeout_seconds: int,
) -> dict:
    snapshots = latest_near_snapshots(db_path, symbols, target_time)
    if not snapshots:
        raise ValueError("No historical snapshots found for requested symbols.")

    response = call_deepseek(
        build_messages(target_time=target_time, snapshots=snapshots),
        model=model,
        timeout_seconds=timeout_seconds,
    )
    content = response["choices"][0]["message"]["content"]
    evaluation = evaluate_agent_replay_response(content, expected_freshness_status="fresh")
    return {
        "provider": "deepseek",
        "model": model,
        "target_time": target_time,
        "symbols": symbols,
        "agent_context": signal_snapshot_agent_context(),
        "input_snapshots": snapshots,
        "agent_content": content,
        "evaluation": evaluation,
        "usage": response.get("usage", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DeepSeek evaluation for historical local SignalSnapshot rows.")
    parser.add_argument("--target-time", default="2026-05-29T10:00:00+08:00")
    parser.add_argument("--symbols", default="600519,000001")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    load_project_env()
    db_path = args.db_path or default_db_path()
    symbols = [item.strip().upper().split(".", 1)[0] for item in args.symbols.split(",") if item.strip()]
    result = evaluate_historical_snapshot(
        db_path=db_path,
        target_time=args.target_time,
        symbols=symbols,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)
    return 0 if evaluation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
