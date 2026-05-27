from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from aegis_alpha.config import load_project_env


SH_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_CONFIG = Path("config/jvquant_capability_probes.json")


@dataclass(frozen=True)
class Probe:
    name: str
    capability: str
    query: str
    sort_key: str = "涨跌幅"


def _now() -> str:
    return datetime.now(SH_TZ).isoformat(timespec="seconds")


def load_probes(path: Path) -> list[Probe]:
    data = json.loads(path.read_text())
    probes = data.get("probes", [])
    return [
        Probe(
            name=str(item["name"]),
            capability=str(item.get("capability") or item["name"]),
            query=str(item["query"]),
            sort_key=str(item.get("sort_key") or ""),
        )
        for item in probes
    ]


def _sample_rows(fields: list[str], rows: list[list[Any]], limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, list):
            continue
        samples.append({field: row[index] for index, field in enumerate(fields) if index < len(row)})
    return samples


def probe_fields(probes: list[Probe], sample_limit: int) -> list[dict[str, Any]]:
    load_project_env()

    from jvQuant import sql_client
    import os
    import logging

    token = os.environ.get("JVQUANT_TOKEN", "")
    if not token:
        raise ValueError("JVQUANT_TOKEN missing")

    client = sql_client.Construct(token=token, log_level=logging.ERROR)
    results: list[dict[str, Any]] = []
    for probe in probes:
        observed_at = _now()
        error = ""
        try:
            payload = client.query(probe.query, 1, 1, probe.sort_key)
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            fields = data.get("fields", []) if isinstance(data, dict) else []
            rows = data.get("list", []) if isinstance(data, dict) else []
            count = data.get("count", len(rows)) if isinstance(data, dict) else 0
        except Exception as exc:
            fields = []
            rows = []
            count = 0
            error = f"{type(exc).__name__}: {exc}"
        status = "unknown"
        if fields and not error:
            status = "available" if int(count or 0) > 0 else "fields_observed_empty_result"
        results.append(
            {
                "name": probe.name,
                "capability": probe.capability,
                "query": probe.query,
                "sort_key": probe.sort_key,
                "status": status,
                "observed_at": observed_at,
                "authority": "observed_probe" if fields and not error else "unknown",
                "count": count,
                "fields": fields,
                "samples": _sample_rows(fields, rows, sample_limit),
                "error": error,
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
                f"Capability: `{result['capability']}`",
                "",
                f"Query: `{result['query']}`",
                "",
                f"Status: `{result['status']}`",
                "",
                f"Authority: `{result['authority']}`",
                "",
                f"Observed at: `{result['observed_at']}`",
                "",
                f"Count: `{result['count']}`",
                "",
                "Fields:",
                "",
            ]
        )
        for field in result["fields"]:
            lines.append(f"- `{field}`")
        if result["error"]:
            lines.extend(["", f"Error: `{result['error']}`"])
        lines.extend(["", "Sample rows:", "", "```json"])
        lines.append(json.dumps(result["samples"], ensure_ascii=False, indent=2))
        lines.extend(["```", ""])
    return "\n".join(lines)


def render_matrix(results: list[dict[str, Any]]) -> str:
    lines = [
        "# jvQuant Capability Matrix",
        "",
        "This matrix is generated from configured read-only jvQuant semantic-query probes.",
        "",
        "| Capability | Probe | Status | Authority | Count | Observed Fields | Notes |",
        "|---|---|---:|---|---:|---|---|",
    ]
    for result in results:
        fields = ", ".join(f"`{field}`" for field in result["fields"][:8])
        if len(result["fields"]) > 8:
            fields += ", ..."
        notes = result["error"] or "Observed by probe; not a contractual field definition."
        lines.append(
            "| {capability} | {name} | {status} | {authority} | {count} | {fields} | {notes} |".format(
                capability=result["capability"],
                name=result["name"],
                status=result["status"],
                authority=result["authority"],
                count=result["count"],
                fields=fields or "-",
                notes=notes.replace("|", "\\|"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe jvQuant semantic-query fields without printing secrets.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--sample-limit", type=int, default=3)
    parser.add_argument("--format", choices=["json", "markdown", "matrix"], default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    results = probe_fields(load_probes(args.config), args.sample_limit)
    if args.format == "json":
        content = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.format == "matrix":
        content = render_matrix(results)
    else:
        content = render_markdown(results)
    if args.output:
        args.output.write_text(content + "\n")
    else:
        print(content)


if __name__ == "__main__":
    main()
