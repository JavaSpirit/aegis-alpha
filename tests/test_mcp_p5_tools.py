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


def test_get_limit_down_pool_returns_list():
    from aegis_alpha.mcp.server import get_limit_down_pool

    rows = get_limit_down_pool("2026-05-30")
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["pool_kind"] == "limit_down"


def test_get_st_pool_returns_list():
    from aegis_alpha.mcp.server import get_st_pool

    rows = get_st_pool("2026-05-30")
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["pool_kind"] == "st"


def test_compact_candidate_includes_limitup_driver_and_pattern():
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "limitup_driver_type" in item
        assert "intraday_pattern" in item


def test_get_capital_flow_slices_returns_three_dicts():
    from aegis_alpha.mcp.server import get_capital_flow_slices

    rows = get_capital_flow_slices("600519", "2026-05-30")
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert {r["window"] for r in rows} == {
        "pre_first_seal_5m", "post_break_1m", "tail_30m"
    }


def test_compact_candidate_includes_weekly_health_score():
    from aegis_alpha.mcp.server import get_second_board_candidates_compact

    items = get_second_board_candidates_compact(limit=5)
    assert items
    for item in items:
        assert "weekly_health_score" in item
        assert 0.0 <= item["weekly_health_score"] <= 100.0
