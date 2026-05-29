from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from aegis_alpha.agent_eval import build_agent_replay_messages, evaluate_agent_replay_response
from aegis_alpha.config import load_project_env
from aegis_alpha.models import MarketEvent, SignalSnapshot
from aegis_alpha.replay import run_orderbook_replay_fixture


DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"


def call_deepseek(messages: list[dict[str, str]], *, model: str, timeout_seconds: int) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY missing")
    payload = {
        "model": model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "temperature": 0.2,
        "max_tokens": 1200,
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


def force_stale(snapshot: SignalSnapshot) -> SignalSnapshot:
    data = snapshot.model_dump()
    data["provider_timestamp"] = "2000-01-01T09:35:00+08:00"
    data["data_timestamp"] = "2000-01-01T09:35:00+08:00"
    data["received_at"] = "2026-05-29T09:35:30+08:00"
    data["freshness_status"] = "stale"
    data["notes"] = [*snapshot.notes, "forced_stale_for_agent_smoke_test"]
    return SignalSnapshot.model_validate(data)


def force_stale_events(events: list[MarketEvent]) -> list[MarketEvent]:
    stale_events = []
    for event in events:
        data = event.model_dump()
        data["provider_timestamp"] = "2000-01-01T09:35:00+08:00"
        data["received_at"] = "2026-05-29T09:35:30+08:00"
        data["freshness_status"] = "stale"
        payload = dict(data.get("data") or {})
        payload["provider_timestamp"] = "2000-01-01T09:35:00+08:00"
        payload["data_timestamp"] = "2000-01-01T09:35:00+08:00"
        payload["received_at"] = "2026-05-29T09:35:30+08:00"
        payload["freshness_status"] = "stale"
        data["data"] = payload
        stale_events.append(MarketEvent.model_validate(data))
    return stale_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DeepSeek smoke test against offline Aegis Alpha replay events.")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--stale", action="store_true", help="Force stale timestamps to test grade capping.")
    parser.add_argument("--output", type=Path, help="Optional path for the full smoke-test JSON result.")
    args = parser.parse_args()

    load_project_env()
    snapshot, events = run_orderbook_replay_fixture()
    if args.stale:
        snapshot = force_stale(snapshot)
        events = force_stale_events(events)
    messages = build_agent_replay_messages(snapshot, events)
    response = call_deepseek(messages, model=args.model, timeout_seconds=args.timeout_seconds)
    content = response["choices"][0]["message"]["content"]
    evaluation = evaluate_agent_replay_response(content, expected_freshness_status=snapshot.freshness_status)
    result = {
        "provider": "deepseek",
        "model": args.model,
        "scenario": "offline_second_board_orderbook_replay",
        "input_summary": {
            "symbol": snapshot.symbol,
            "freshness_status": snapshot.freshness_status,
            "event_types": [event.event_type for event in events],
            "data_mode": snapshot.data_mode,
            "provider": snapshot.provider,
        },
        "agent_content": content,
        "evaluation": evaluation,
        "usage": response.get("usage", {}),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)
    return 0 if evaluation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
