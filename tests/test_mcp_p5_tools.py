def test_get_dragon_tiger_tool_returns_dict():
    from aegis_alpha.mcp.server import get_dragon_tiger

    result = get_dragon_tiger("600519", "2026-05-30")
    assert isinstance(result, dict)
    assert result.get("symbol") == "600519"
    assert "seats" in result


def test_get_active_seats_today_tool_returns_list():
    from aegis_alpha.mcp.server import get_active_seats_today

    result = get_active_seats_today("2026-05-30")
    assert isinstance(result, list)
    if result:
        assert "hot_money_alias" in result[0]
