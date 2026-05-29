from __future__ import annotations

import argparse
import json
from pathlib import Path

from aegis_alpha.config import load_project_env
from aegis_alpha.storage import AegisAlphaStore, default_db_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect recent stored Aegis Alpha agent reviews.")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--full", action="store_true", help="Print full payloads instead of compact rows.")
    args = parser.parse_args()

    load_project_env()
    store = AegisAlphaStore(args.db_path or default_db_path())
    reviews = store.recent_agent_reviews(args.limit)
    if args.full:
        payload = [review.model_dump() for review in reviews]
    else:
        payload = [
            {
                "review_id": review.review_id,
                "created_at": review.created_at,
                "run_type": review.run_type,
                "target_time": review.target_time,
                "symbols": review.symbols,
                "provider": review.provider,
                "model": review.model,
                "passed": review.passed,
                "grades": review.grades,
                "summary": review.summary,
            }
            for review in reviews
        ]
    print(json.dumps({"reviews": payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
