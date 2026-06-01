import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_p7_p6_thresholds_yaml_exists():
    path = REPO_ROOT / "config" / "p6_thresholds.yaml"
    assert path.exists(), "config/p6_thresholds.yaml should exist after P7"
    text = path.read_text(encoding="utf-8")
    for marker in (
        "contrarian_pool", "sector_events", "new_stocks",
        "limitup_driver", "intraday_pattern",
    ):
        assert marker in text, f"p6_thresholds.yaml missing section {marker}"


def test_p7_starter_constants_carry_calibrate_marker():
    """Each P6 extensions module should mention CALIBRATE near every starter
    constant, so future readers see this is a starter, not settled value."""
    targets = (
        "src/aegis_alpha/extensions/contrarian_pool.py",
        "src/aegis_alpha/extensions/sector_events.py",
        "src/aegis_alpha/extensions/new_stocks.py",
        "src/aegis_alpha/extensions/limitup_driver.py",
        "src/aegis_alpha/extensions/intraday_pattern.py",
    )
    for rel in targets:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "CALIBRATE" in text, f"{rel} should carry # CALIBRATE markers"


def test_p7_jvquant_active_seats_today_uses_placeholder_signal():
    pytest = __import__("pytest")
    try:
        from aegis_alpha.adapters.jvquant.adapter import JvQuantMarketDataAdapter
    except ImportError:
        pytest.skip("jvquant adapter unavailable")
    adapter = JvQuantMarketDataAdapter.__new__(JvQuantMarketDataAdapter)
    rows = adapter.get_active_seats_today("2026-06-01")
    if rows:
        assert rows[0].get("data_mode") == "placeholder"
