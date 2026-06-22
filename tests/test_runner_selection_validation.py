from __future__ import annotations

from aegis_alpha.runner import AegisAlphaRunner


def test_validation_advisory_never_raises(monkeypatch):
    r = AegisAlphaRunner(connect=False)
    def boom(*a, **k):
        raise RuntimeError("validation exploded")
    monkeypatch.setattr(r, "_run_selection_validation", boom, raising=False)
    # enable so the hook reaches _run_selection_validation
    r.config["selection_validation"] = {"enabled": True, "after": "00:00"}
    try:
        r.validate_selections_next_day()
    except Exception as exc:  # pragma: no cover
        assert False, f"hook must be advisory, raised: {exc}"


def test_validation_disabled_by_config(monkeypatch):
    r = AegisAlphaRunner(connect=False)
    r.config["selection_validation"] = {"enabled": False}
    # should early-return [] without touching _run_selection_validation
    called = {"v": False}
    def mark(*a, **k):
        called["v"] = True
        return []
    monkeypatch.setattr(r, "_run_selection_validation", mark, raising=False)
    result = r.validate_selections_next_day()
    assert result == []
    assert called["v"] is False


def test_validation_skips_when_no_prior_audit(tmp_path, monkeypatch):
    config_path = tmp_path / "runner.yaml"
    config_path.write_text(
        f"""
storage:
  sqlite_path: "{tmp_path / 'empty.db'}"
  status_path: "{tmp_path / 'status.json'}"
selection_validation:
  enabled: true
  after: "00:00"
""".strip()
    )
    r = AegisAlphaRunner(str(config_path), connect=False)
    r.config["selection_validation"] = {"enabled": True, "after": "00:00"}
    # empty store → no prior audit → returns [] without exception
    result = r.validate_selections_next_day()
    assert result == []
