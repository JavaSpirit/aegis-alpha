from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


OBSERVER_TOOLS = {
    "get_realtime_symbol_context",
    "get_intraday_theme_context",
    "get_intraday_market_context",
    "record_agent_observation",
    "get_agent_observation",
    "list_agent_observations",
    "notify_agent_observation",
}


def _tool_include(path: Path) -> set[str]:
    payload = yaml.safe_load(path.read_text())
    return set(payload["mcp_servers"]["aegis_alpha"]["tools"]["include"])


def test_observer_tools_are_exposed_to_hermes_mcp_snippet():
    include = _tool_include(ROOT / ".hermes" / "config" / "aegis-alpha-mcp.yaml")
    assert OBSERVER_TOOLS <= include


def test_observer_tools_are_exposed_to_hermes_project_config_template():
    include = _tool_include(ROOT / ".hermes" / "config" / "config.example.yaml")
    assert OBSERVER_TOOLS <= include


def test_second_board_skill_documents_observer_contract():
    skill = (ROOT / ".hermes" / "skills" / "second-board-radar" / "SKILL.md").read_text()
    for tool in OBSERVER_TOOLS:
        assert tool in skill
    assert "Agent 市场观察" in skill
    assert "不要自填或口头承诺 notification grade" in skill
