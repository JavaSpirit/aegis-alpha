from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegis_alpha.config import load_project_env


@dataclass(frozen=True)
class Probe:
    name: str
    query: str
    sort_key: str = "涨跌幅"


PROBES = [
    Probe(
        name="second_board_speed_capital",
        query="昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,5分钟涨幅,资金流向,主力资金,价格,成交额,行业",
    ),
    Probe(
        name="second_board_seal_metrics",
        query="昨日涨停,今日涨幅大于5,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单量,封单金额,涨停封成比,价格,成交额,行业",
    ),
    Probe(
        name="today_limitup_seal_metrics",
        query="今日涨停,非ST,股票代码,股票简称,涨跌幅,首次涨停时间,封单量,封单金额,涨停封成比,价格,成交额,行业",
    ),
    Probe(
        name="multi_board_seal_metrics",
        query="连板数大于1,非ST,股票代码,股票简称,涨跌幅,连板数,首次涨停时间,封单量,封单金额,涨停封成比,价格,成交额,行业",
    ),
    Probe(
        name="break_board_pool",
        query="炸板,非ST,股票代码,股票简称,涨跌幅,炸板次数,价格,成交额,行业",
    ),
]


def _sample_rows(fields: list[str], rows: list[list[Any]], limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, list):
            continue
        samples.append({field: row[index] for index, field in enumerate(fields) if index < len(row)})
    return samples


def probe_fields(sample_limit: int) -> list[dict[str, Any]]:
    load_project_env()

    from jvQuant import sql_client
    import os
    import logging

    token = os.environ.get("JVQUANT_TOKEN", "")
    if not token:
        raise ValueError("JVQUANT_TOKEN missing")

    client = sql_client.Construct(token=token, log_level=logging.ERROR)
    results: list[dict[str, Any]] = []
    for probe in PROBES:
        payload = client.query(probe.query, 1, 1, probe.sort_key)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        fields = data.get("fields", []) if isinstance(data, dict) else []
        rows = data.get("list", []) if isinstance(data, dict) else []
        results.append(
            {
                "name": probe.name,
                "query": probe.query,
                "count": data.get("count", len(rows)) if isinstance(data, dict) else 0,
                "fields": fields,
                "samples": _sample_rows(fields, rows, sample_limit),
            }
        )
    return results


def render_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# jvQuant Field Probe",
        "",
        "This file is generated from read-only jvQuant semantic queries. It records observed fields, not contractual API guarantees.",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result['name']}",
                "",
                f"Query: `{result['query']}`",
                "",
                f"Count: `{result['count']}`",
                "",
                "Fields:",
                "",
            ]
        )
        for field in result["fields"]:
            lines.append(f"- `{field}`")
        lines.extend(["", "Sample rows:", "", "```json"])
        lines.append(json.dumps(result["samples"], ensure_ascii=False, indent=2))
        lines.extend(["```", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe jvQuant semantic-query fields without printing secrets.")
    parser.add_argument("--sample-limit", type=int, default=3)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    results = probe_fields(args.sample_limit)
    content = (
        json.dumps(results, ensure_ascii=False, indent=2)
        if args.format == "json"
        else render_markdown(results)
    )
    if args.output:
        args.output.write_text(content + "\n")
    else:
        print(content)


if __name__ == "__main__":
    main()
