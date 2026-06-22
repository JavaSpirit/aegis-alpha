from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from aegis_alpha.models import SelectionAudit, SelectionPick


def _load_mvp_pilot():
    path = Path(__file__).resolve().parents[1] / "scripts" / "mvp_pilot.py"
    spec = importlib.util.spec_from_file_location("mvp_pilot", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_subscription_export_uses_scan_pool_not_only_audit_top3(tmp_path, monkeypatch):
    pilot = _load_mvp_pilot()

    audit = SelectionAudit(
        audit_id="sa_test",
        as_of_day="2026-06-19",
        picks=[
            SelectionPick(symbol="002491", rank=1),
            SelectionPick(symbol="002167", rank=2),
            SelectionPick(symbol="600353", rank=3),
        ],
    )

    monkeypatch.setattr(
        pilot,
        "strategy_scan_pool_symbols",
        lambda as_of_day, scan_limit, allow_current_proxy=False: {
            "source": "daily_strategy_candidate_pool",
            "data_mode": "daily_strategy_candidate_pool",
            "requested_limit": scan_limit,
            "result_count": 4,
            "symbols": ["601869", "002491", "300475"],
        },
    )

    result = pilot.write_subscription_files(
        audit=audit,
        as_of_day="2026-06-19",
        output_dir=tmp_path,
        scan_limit=50,
    )

    assert result["subscription_mode"] == "strategy_scan_pool_with_audit_priority"
    assert result["priority_audit_symbols"] == ["002491", "002167", "600353"]
    assert result["scan_pool_symbols"] == ["601869", "002491", "300475"]
    assert result["symbols"] == ["002491", "002167", "600353", "601869", "300475"]

    env_text = Path(result["env_path"]).read_text()
    assert "JVQUANT_SUBSCRIBE_SYMBOLS=002491,002167,600353,601869,300475" in env_text

    payload = json.loads(Path(result["json_path"]).read_text())
    assert payload["subscription_mode"] == "strategy_scan_pool_with_audit_priority"
    assert payload["priority_audit_symbols"] == ["002491", "002167", "600353"]
    assert payload["scan_pool_symbols"] == ["601869", "002491", "300475"]


def test_strategy_scan_pool_can_fall_back_to_current_proxy(monkeypatch):
    pilot = _load_mvp_pilot()

    class _Server:
        @staticmethod
        def get_daily_strategy_candidate_pool(_as_of_day, limit):
            return {
                "data_mode": "daily_strategy_candidate_pool",
                "result_count": 1,
                "candidates": [{"symbol": "", "data_mode": "unavailable"}],
            }

    monkeypatch.setitem(__import__("sys").modules, "aegis_alpha.mcp.server", _Server)
    monkeypatch.setattr(
        pilot,
        "current_limitup_scan_pool_symbols",
        lambda scan_limit, reason: {
            "source": "current_limitup_pool_proxy",
            "data_mode": "proxy_current_provider",
            "requested_limit": scan_limit,
            "symbols": ["601869", "603083"],
            "fallback_reason": reason,
        },
    )

    result = pilot.strategy_scan_pool_symbols(
        "2026-06-19",
        50,
        allow_current_proxy=True,
    )

    assert result["source"] == "current_limitup_pool_proxy"
    assert result["symbols"] == ["601869", "603083"]
    assert "strict_pool" in result
