from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, time as day_time, timedelta
from pathlib import Path
from typing import Any

from aegis_alpha.clock import now_dt, now_iso
from aegis_alpha.config import load_project_env
from aegis_alpha.runner import status_payload
from aegis_alpha.storage import AegisAlphaStore, default_db_path


DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEFAULT_PROVIDER = os.environ.get("HERMES_PROVIDER", "deepseek")
DEFAULT_OUTPUT_DIR = Path("data") / "mvp_pilot"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _previous_business_day(value: date) -> date:
    current = value - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _next_business_day(value: date) -> date:
    current = value + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _suggest_prepare_as_of(today: date, now_time: day_time) -> date:
    if today.weekday() >= 5:
        return _previous_business_day(today)
    if now_time < day_time(15, 30):
        return _previous_business_day(today)
    return today


def latest_audit_day(store: AegisAlphaStore) -> str:
    with store._connect() as conn:
        row = conn.execute(
            "SELECT as_of_day FROM selection_audits ORDER BY as_of_day DESC, created_at DESC LIMIT 1"
        ).fetchone()
    return str(row[0]) if row else ""


def audit_to_dict(audit: Any) -> dict[str, Any]:
    return audit.model_dump() if hasattr(audit, "model_dump") else dict(audit or {})


def audit_symbols(audit: Any) -> list[str]:
    return [str(pick.symbol).split(".", 1)[0] for pick in getattr(audit, "picks", []) if pick.symbol]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def update_env_key(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    rendered = f"{key}={value}"
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            output.append(rendered)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(rendered)
    path.write_text("\n".join(output).rstrip() + "\n")


def write_subscription_files(
    *,
    audit: Any,
    as_of_day: str,
    output_dir: Path,
    update_env_local: bool = False,
) -> dict[str, Any]:
    symbols = audit_symbols(audit)
    symbol_text = ",".join(symbols)
    output_dir.mkdir(parents=True, exist_ok=True)
    env_path = output_dir / f"jvquant_symbols_{as_of_day}.env"
    json_path = output_dir / f"jvquant_symbols_{as_of_day}.json"
    env_path.write_text(f"export JVQUANT_SUBSCRIBE_SYMBOLS={symbol_text}\n")
    write_json(
        json_path,
        {
            "as_of_day": as_of_day,
            "created_at": now_iso(),
            "symbols": symbols,
            "env": {"JVQUANT_SUBSCRIBE_SYMBOLS": symbol_text},
            "notes": [
                "Source this env file in a shell, or run prepare --update-env-local before restarting launchd runner.",
                "This only subscribes the runner; it does not place orders.",
            ],
        },
    )
    env_local_updated = False
    if update_env_local:
        update_env_key(repo_root() / ".env.local", "JVQUANT_SUBSCRIBE_SYMBOLS", symbol_text)
        env_local_updated = True
    return {
        "symbols": symbols,
        "env_path": str(env_path),
        "json_path": str(json_path),
        "env_local_updated": env_local_updated,
    }


def run_hermes(prompt: str, *, provider: str, model: str, timeout_seconds: int, max_turns: int) -> dict[str, Any]:
    cmd = [
        "hermes",
        "chat",
        "-s",
        "second-board-radar",
        "--provider",
        provider,
        "--model",
        model,
        "--max-turns",
        str(max_turns),
        "-Q",
        "-q",
        prompt,
    ]
    result = subprocess.run(
        cmd,
        cwd=str(repo_root()),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def prepare_prompt(as_of_day: str, candidate_limit: int, top_n: int, *, provider: str, model: str) -> str:
    return f"""
你是 Aegis Alpha 的每日 MVP pilot 编排 agent。请站在 {as_of_day} 收盘，只使用当日及以前可知事实，生成下一交易日观察池。

硬性流程：
1. 调用 get_daily_strategy_candidate_pool(as_of_day="{as_of_day}", limit={candidate_limit})。
2. 基于现有策略选择 Top{top_n}，不要读取未来 target_day 结果。
3. 调用 record_selection_audit(as_of_day="{as_of_day}", picks_json=..., rejected_json=..., candidate_pool_size={candidate_limit}, provider="{provider}", model="{model}")。
4. picks_json 每只必须包含 symbol、rank、relative_reason、caveats；rejected_json 至少包含 2 个 near-miss 的 why_rejected 和 beat_by。
5. 如果 record_selection_audit 返回 audit_quality=incomplete 或 audit_quality_warnings，必须补全后重新调用。

输出：
- Top{top_n} 代码和名称
- 每只票覆盖原策略因子：10日成交额、T-1量能、板块持续性、前高/突破状态、盘口/大单代理、同板块共振代理、新闻/公告代理、missing真值
- audit_id、audit_quality、equals_baseline、confidence_label
- 简短说明明天 runner 应订阅这些 symbol

只输出研究观察，不输出买卖指令。
""".strip()


def command_cron_context(args: argparse.Namespace) -> int:
    load_project_env()
    store = AegisAlphaStore(args.db_path or default_db_path())
    today = _parse_iso_date(args.today) if args.today else now_dt().date()
    now_time = datetime.strptime(args.now_time, "%H:%M").time() if args.now_time else now_dt().time()
    latest_audit = latest_audit_day(store)

    if args.mode == "prepare":
        as_of_day = args.as_of_day or _suggest_prepare_as_of(today, now_time).isoformat()
        target_day = _next_business_day(_parse_iso_date(as_of_day)).isoformat()
        task = "prepare_watchlist"
    else:
        as_of_day = args.as_of_day or latest_audit
        target_day = args.target_day or today.isoformat()
        task = "report_alerts"

    payload = {
        "run_type": "hermes_cron_context",
        "mode": args.mode,
        "task": task,
        "created_at": now_iso(),
        "today": today.isoformat(),
        "now_time": now_time.strftime("%H:%M"),
        "suggested_as_of_day": as_of_day,
        "suggested_target_day": target_day,
        "latest_selection_audit_day": latest_audit,
        "candidate_limit": args.candidate_limit,
        "top_n": args.top_n,
        "runner_status": status_payload(),
        "instructions": [
            "This script only provides dynamic context for Hermes cron.",
            "Hermes must still use the second-board-radar skill and Aegis Alpha MCP tools for judgment.",
            "Do not treat suggested business-day dates as exchange-calendar truth; if provider data is unavailable, step back to the latest available trading day and say so.",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def explain_prompt(report: dict[str, Any]) -> str:
    compact = json.dumps(report, ensure_ascii=False, indent=2)
    return f"""
请基于下面的 Aegis Alpha MVP pilot facts 生成简短中文报告。不要调用额外工具，不要输出买卖指令。

要求：
- 用 triggered、trigger_outcome_label、post_hoc_attribution_label 区分主策略触发、强势延续未触发、二板接力路径、未启动。
- 明确 exact/proxy/missing 数据边界。
- 如果 runner 或 validation 不可用，说明不可用，不脑补。
- 输出“现在应关注什么”和“盘后应复盘什么”，但不要写成交易建议。

facts:
{compact}
""".strip()


def command_prepare(args: argparse.Namespace) -> int:
    load_project_env()
    output_dir = args.output_dir
    db_path = args.db_path or default_db_path()
    store = AegisAlphaStore(db_path)
    as_of_day = args.as_of_day or now_dt().date().isoformat()
    hermes_result: dict[str, Any] | None = None

    if not args.skip_hermes:
        prompt = prepare_prompt(
            as_of_day,
            args.candidate_limit,
            args.top_n,
            provider=args.provider,
            model=args.model,
        )
        try:
            hermes_result = run_hermes(
                prompt,
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                max_turns=args.max_turns,
            )
        except subprocess.TimeoutExpired as exc:
            hermes_result = {
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "error": f"timeout after {args.timeout_seconds}s",
            }
        write_json(output_dir / f"hermes_prepare_{as_of_day}.json", hermes_result)
        if hermes_result.get("returncode") not in {0, None}:
            print(json.dumps(hermes_result, ensure_ascii=False, indent=2))
            return int(hermes_result.get("returncode") or 1)

    audit = store.get_selection_audit_by_day(as_of_day)
    if audit is None:
        print(json.dumps({"data_mode": "unavailable", "error": f"no selection audit for {as_of_day}"}, ensure_ascii=False, indent=2))
        return 2

    subscription = write_subscription_files(
        audit=audit,
        as_of_day=as_of_day,
        output_dir=output_dir,
        update_env_local=args.update_env_local,
    )
    payload = {
        "run_type": "mvp_prepare",
        "created_at": now_iso(),
        "as_of_day": as_of_day,
        "db_path": str(db_path),
        "audit": audit_to_dict(audit),
        "subscription": subscription,
        "hermes_stdout": hermes_result.get("stdout", "") if hermes_result else "",
    }
    write_json(output_dir / f"prepare_{as_of_day}.json", payload)
    write_prepare_markdown(output_dir / f"prepare_{as_of_day}.md", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def write_prepare_markdown(path: Path, payload: dict[str, Any]) -> None:
    audit = payload["audit"]
    subscription = payload["subscription"]
    lines = [
        f"# MVP Pilot Prepare {payload['as_of_day']}",
        "",
        f"- audit_id: `{audit.get('audit_id', '')}`",
        f"- confidence: `{audit.get('confidence_label', '')}`",
        f"- equals_baseline: `{audit.get('equals_baseline')}`",
        f"- symbols: `{','.join(subscription.get('symbols', []))}`",
        f"- env file: `{subscription.get('env_path', '')}`",
        f"- .env.local updated: `{subscription.get('env_local_updated')}`",
        "",
        "## Picks",
    ]
    for pick in audit.get("picks", []):
        lines.append(f"- {pick.get('rank')}. `{pick.get('symbol')}` {pick.get('relative_reason', '')}")
    lines.extend(["", "## Notes", "Research/watchlist only. No order instruction."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def command_export_subscription(args: argparse.Namespace) -> int:
    load_project_env()
    store = AegisAlphaStore(args.db_path or default_db_path())
    as_of_day = args.as_of_day or latest_audit_day(store)
    if not as_of_day:
        print(json.dumps({"data_mode": "unavailable", "error": "no selection audit found"}, ensure_ascii=False, indent=2))
        return 2
    audit = store.get_selection_audit_by_day(as_of_day)
    if audit is None:
        print(json.dumps({"data_mode": "unavailable", "error": f"no selection audit for {as_of_day}"}, ensure_ascii=False, indent=2))
        return 2
    payload = write_subscription_files(
        audit=audit,
        as_of_day=as_of_day,
        output_dir=args.output_dir,
        update_env_local=args.update_env_local,
    )
    payload["as_of_day"] = as_of_day
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    load_project_env()
    from aegis_alpha.mcp import server

    output_dir = args.output_dir
    store = AegisAlphaStore(args.db_path or default_db_path())
    as_of_day = args.as_of_day or latest_audit_day(store)
    target_day = args.target_day or now_dt().date().isoformat()
    if not as_of_day:
        print(json.dumps({"data_mode": "unavailable", "error": "no selection audit found"}, ensure_ascii=False, indent=2))
        return 2
    audit = store.get_selection_audit_by_day(as_of_day)
    if audit is None:
        print(json.dumps({"data_mode": "unavailable", "error": f"no selection audit for {as_of_day}"}, ensure_ascii=False, indent=2))
        return 2
    symbols = "|".join(audit_symbols(audit))
    validation: dict[str, Any]
    try:
        validation = server.get_selection_trigger_validation(as_of_day, target_day, args.window_start, args.window_end)
    except Exception as exc:
        validation = {"data_mode": "unavailable", "error": type(exc).__name__}

    next_day_outcome: dict[str, Any] | None = None
    if args.include_next_day:
        try:
            next_day_outcome = server.get_second_board_next_day_outcomes(target_day, symbols, limit=max(1, len(audit_symbols(audit))))
        except Exception as exc:
            next_day_outcome = {"data_mode": "unavailable", "error": type(exc).__name__}

    alerts = [alert.model_dump() for alert in store.list_alerts(status="" if args.all_alerts else "pending", limit=args.alert_limit)]
    payload = {
        "run_type": "mvp_report",
        "created_at": now_iso(),
        "as_of_day": as_of_day,
        "target_day": target_day,
        "window": {"start": args.window_start, "end": args.window_end},
        "audit": audit_to_dict(audit),
        "runner_status": status_payload(),
        "alerts": alerts,
        "validation": validation,
        "next_day_outcome": next_day_outcome,
        "notes": [
            "Facts-only MVP pilot report.",
            "post_hoc_attribution_label is for after-the-fact explanation only.",
            "No order instruction is generated.",
        ],
    }
    write_json(output_dir / f"report_{as_of_day}_{target_day}.json", payload)
    write_report_markdown(output_dir / f"report_{as_of_day}_{target_day}.md", payload)

    if args.hermes_explain:
        try:
            hermes = run_hermes(
                explain_prompt(payload),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                max_turns=args.max_turns,
            )
        except subprocess.TimeoutExpired as exc:
            hermes = {
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "error": f"timeout after {args.timeout_seconds}s",
            }
        write_json(output_dir / f"report_explain_{as_of_day}_{target_day}.json", hermes)
        (output_dir / f"report_explain_{as_of_day}_{target_day}.md").write_text(hermes.get("stdout", "").rstrip() + "\n")
        payload["hermes_explain_returncode"] = hermes.get("returncode")
        payload["hermes_explain_path"] = str(output_dir / f"report_explain_{as_of_day}_{target_day}.md")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def write_report_markdown(path: Path, payload: dict[str, Any]) -> None:
    validation = payload.get("validation") or {}
    status = payload.get("runner_status") or {}
    lines = [
        f"# MVP Pilot Report {payload['as_of_day']} -> {payload['target_day']}",
        "",
        f"- runner: `{status.get('state', 'unknown')}` subscribed={status.get('subscribed', [])}",
        f"- validation: `{validation.get('data_mode', 'unknown')}` trigger_rate={validation.get('trigger_rate', '')}",
        f"- alerts: `{len(payload.get('alerts', []))}`",
        "",
        "## Picks Validation",
    ]
    for item in validation.get("per_pick", []) if isinstance(validation, dict) else []:
        lines.append(
            "- `{symbol}` triggered={triggered} trigger_outcome={trigger_outcome} "
            "post_hoc={post_hoc} max_gain={max_gain} window_end={window_end}".format(
                symbol=item.get("symbol", ""),
                triggered=item.get("triggered"),
                trigger_outcome=item.get("trigger_outcome_label", ""),
                post_hoc=item.get("post_hoc_attribution_label", ""),
                max_gain=item.get("max_gain_pct"),
                window_end=item.get("window_end_pct"),
            )
        )
    lines.extend(["", "## Recent Alerts"])
    for alert in payload.get("alerts", [])[:20]:
        lines.append(f"- `{alert.get('severity')}` {alert.get('title')} {alert.get('body', '')}")
    lines.extend(["", "Research/watchlist only. No order instruction."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aegis Alpha local MVP pilot automation.")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Ask Hermes to create today's selection audit and export runner symbols.")
    prepare.add_argument("--as-of-day", default="")
    prepare.add_argument("--candidate-limit", type=int, default=12)
    prepare.add_argument("--top-n", type=int, default=3)
    prepare.add_argument("--provider", default=DEFAULT_PROVIDER)
    prepare.add_argument("--model", default=DEFAULT_MODEL)
    prepare.add_argument("--timeout-seconds", type=int, default=360)
    prepare.add_argument("--max-turns", type=int, default=18)
    prepare.add_argument("--skip-hermes", action="store_true", help="Only export subscription files from an existing audit.")
    prepare.add_argument("--update-env-local", action="store_true", help="Write JVQUANT_SUBSCRIBE_SYMBOLS into .env.local.")
    prepare.set_defaults(func=command_prepare)

    export = sub.add_parser("export-subscription", help="Export JVQUANT_SUBSCRIBE_SYMBOLS from an existing audit.")
    export.add_argument("--as-of-day", default="")
    export.add_argument("--update-env-local", action="store_true")
    export.set_defaults(func=command_export_subscription)

    report = sub.add_parser("report", help="Build a local report from runner alerts and selection validation.")
    report.add_argument("--as-of-day", default="")
    report.add_argument("--target-day", default="")
    report.add_argument("--window-start", default="09:31")
    report.add_argument("--window-end", default="10:00")
    report.add_argument("--alert-limit", type=int, default=20)
    report.add_argument("--all-alerts", action="store_true")
    report.add_argument("--include-next-day", action="store_true")
    report.add_argument("--hermes-explain", action="store_true")
    report.add_argument("--provider", default=DEFAULT_PROVIDER)
    report.add_argument("--model", default=DEFAULT_MODEL)
    report.add_argument("--timeout-seconds", type=int, default=180)
    report.add_argument("--max-turns", type=int, default=8)
    report.set_defaults(func=command_report)

    context = sub.add_parser("cron-context", help="Print dynamic context for Hermes cron jobs without running an agent.")
    context.add_argument("mode", choices=["prepare", "report"])
    context.add_argument("--today", default="", help="YYYY-MM-DD override for tests.")
    context.add_argument("--now-time", default="", help="HH:MM override for tests.")
    context.add_argument("--as-of-day", default="")
    context.add_argument("--target-day", default="")
    context.add_argument("--candidate-limit", type=int, default=12)
    context.add_argument("--top-n", type=int, default=3)
    context.set_defaults(func=command_cron_context)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
