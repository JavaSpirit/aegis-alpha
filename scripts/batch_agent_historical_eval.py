from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from aegis_alpha.agent_eval import parsed_grades
from aegis_alpha.config import load_project_env
from aegis_alpha.models import AgentReview
from aegis_alpha.storage import AegisAlphaStore, default_db_path, now_iso
from smoke_agent_historical_snapshot import evaluate_historical_snapshot


DEFAULT_TIMES = "2026-05-29T09:30:00+08:00,2026-05-29T09:45:00+08:00,2026-05-29T10:00:00+08:00,2026-05-29T10:30:00+08:00,2026-05-29T11:00:00+08:00,2026-05-29T11:30:00+08:00"


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch DeepSeek evaluation for historical local SignalSnapshot rows.")
    parser.add_argument("--target-times", default=DEFAULT_TIMES, help="Comma-separated ISO timestamps.")
    parser.add_argument("--symbols", default="600519,000001")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-store", action="store_true", help="Persist each case and the batch summary to SQLite agent_reviews.")
    args = parser.parse_args()

    load_project_env()
    db_path = args.db_path or default_db_path()
    target_times = [item.strip() for item in args.target_times.split(",") if item.strip()]
    symbols = [item.strip().upper().split(".", 1)[0] for item in args.symbols.split(",") if item.strip()]
    results = []
    grade_counts: Counter[str] = Counter()
    passed_count = 0
    failed_count = 0

    for target_time in target_times:
        try:
            result = evaluate_historical_snapshot(
                db_path=db_path,
                target_time=target_time,
                symbols=symbols,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
            )
            passed = bool(result["evaluation"]["passed"])
            if passed:
                passed_count += 1
            else:
                failed_count += 1
            for grade in parsed_grades(result["evaluation"].get("parsed") or {}):
                grade_counts[grade] += 1
        except Exception as exc:
            failed_count += 1
            result = {
                "target_time": target_time,
                "symbols": symbols,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "evaluation": {"passed": False},
            }
        results.append(result)

    report = {
        "run_type": "batch_agent_historical_eval",
        "created_at": now_iso(),
        "provider": "deepseek",
        "model": args.model,
        "db_path": str(db_path),
        "target_times": target_times,
        "symbols": symbols,
        "summary": {
            "case_count": len(results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "grade_counts": dict(sorted(grade_counts.items())),
        },
        "results": results,
    }
    if args.write_store:
        store = AegisAlphaStore(db_path)
        for result in results:
            store.save_agent_review(review_from_result(result, run_type="historical_snapshot_eval"))
        store.save_agent_review(
            AgentReview(
                run_type="batch_agent_historical_eval",
                target_time=",".join(target_times),
                symbols=symbols,
                provider="deepseek",
                model=args.model,
                passed=failed_count == 0,
                grades=list(grade_counts.elements()),
                summary=report["summary"],
                payload={key: value for key, value in report.items() if key != "results"},
            )
        )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    output = args.output or Path("data") / "agent_eval_runs" / f"batch_{now_iso().replace(':', '').replace('+', '_')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n")
    print(text)
    print(f"\nSaved report: {output}")
    return 0 if failed_count == 0 else 2


def review_from_result(result: dict, *, run_type: str) -> AgentReview:
    evaluation = result.get("evaluation") or {}
    parsed = evaluation.get("parsed") or {}
    return AgentReview(
        run_type=run_type,
        target_time=str(result.get("target_time") or ""),
        symbols=[str(item) for item in result.get("symbols", [])],
        provider=str(result.get("provider") or "deepseek"),
        model=str(result.get("model") or ""),
        passed=bool(evaluation.get("passed")),
        grades=parsed_grades(parsed),
        summary={
            "checks": evaluation.get("checks", []),
            "usage": result.get("usage", {}),
        },
        payload=result,
    )


if __name__ == "__main__":
    raise SystemExit(main())
