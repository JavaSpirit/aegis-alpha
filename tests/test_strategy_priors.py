from __future__ import annotations

"""Tests for StrategyPrior model + loader (Phase 5, Task 5.1).

Philosophy guard: the StrategyPrior model must contain ONLY soft-range guidance
fields — never any pass/fail/filter/score/grade field. These tests enforce that
contract at model and YAML level.
"""

import json
from pathlib import Path

import pytest

from aegis_alpha.models import StrategyPrior, StrategyPriorThreshold
from aegis_alpha.strategy_priors import load_active_strategy_prior, load_strategy_priors

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FORBIDDEN_FIELDS = {"passed", "meets_threshold", "reject", "filter", "grade", "score", "probability"}


def _flatten_keys(obj: object) -> set[str]:
    """Recursively collect all dict keys in a nested structure."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _flatten_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _flatten_keys(item)
    return keys


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------

class TestStrategyPriorModel:
    def test_build_minimal(self) -> None:
        threshold = StrategyPriorThreshold(
            name="avg_turnover_10d",
            ideal_low=5_000_000_000.0,
            ideal_high=None,
            unit="cny",
            rationale="近10日均成交量需大于50亿，确保流动性与资金承接。",
        )
        prior = StrategyPrior(
            prior_id="client_10pt",
            label="客户二板买点策略（10 点）",
            source="客户口述策略",
            is_active=True,
            thresholds=[threshold],
            guidance_notes=["T-1 缩量调整。"],
        )
        assert prior.prior_id == "client_10pt"
        assert prior.is_active is True
        assert len(prior.thresholds) == 1
        assert prior.thresholds[0].ideal_low == 5_000_000_000.0
        assert prior.thresholds[0].ideal_high is None

    def test_philosophy_guard_no_forbidden_fields(self) -> None:
        """model_dump() must contain NONE of the forbidden pass/fail/filter fields."""
        threshold = StrategyPriorThreshold(
            name="ma5_slope_degrees",
            ideal_low=30.0,
            ideal_high=60.0,
            unit="degrees",
            rationale="5日均线斜率30–60度，趋势向上但不过热。",
        )
        prior = StrategyPrior(
            prior_id="test",
            label="test",
            source="test",
            thresholds=[threshold],
        )
        dumped = prior.model_dump()
        all_keys = _flatten_keys(dumped)
        violations = FORBIDDEN_FIELDS & all_keys
        assert not violations, f"Forbidden pass/fail fields found in model_dump: {violations}"

    def test_default_caixin_placeholder(self) -> None:
        prior = StrategyPrior(prior_id="x", label="x", source="x")
        assert prior.caixin_alignment.startswith("placeholder")

    def test_override_policy_content(self) -> None:
        prior = StrategyPrior(prior_id="x", label="x", source="x")
        assert "事实为准" in prior.override_policy

    def test_disclaimer_not_program_filter(self) -> None:
        prior = StrategyPrior(prior_id="x", label="x", source="x")
        assert "not a program filter" in prior.disclaimer

    def test_threshold_open_ended_both_sides(self) -> None:
        """Both ideal_low and ideal_high can be None (fully open-ended)."""
        t = StrategyPriorThreshold(name="some_metric", unit="pct", rationale="test")
        assert t.ideal_low is None
        assert t.ideal_high is None


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

class TestLoadStrategyPriors:
    def test_load_active_returns_client_10pt(self) -> None:
        prior = load_active_strategy_prior()
        assert prior is not None
        assert prior.prior_id == "client_10pt"
        assert prior.is_active is True

    def test_thresholds_avg_turnover(self) -> None:
        prior = load_active_strategy_prior()
        assert prior is not None
        names = [t.name for t in prior.thresholds]
        assert "avg_turnover_10d" in names
        t = next(t for t in prior.thresholds if t.name == "avg_turnover_10d")
        assert t.ideal_low == 5_000_000_000.0
        assert t.ideal_high is None
        assert t.unit == "cny"

    def test_thresholds_ma5_slope(self) -> None:
        prior = load_active_strategy_prior()
        assert prior is not None
        names = [t.name for t in prior.thresholds]
        assert "ma5_slope_degrees" in names
        t = next(t for t in prior.thresholds if t.name == "ma5_slope_degrees")
        assert t.ideal_low == 30.0
        assert t.ideal_high == 60.0
        assert t.unit == "degrees"

    def test_guidance_notes_non_empty(self) -> None:
        prior = load_active_strategy_prior()
        assert prior is not None
        assert len(prior.guidance_notes) > 0

    def test_caixin_alignment_placeholder(self) -> None:
        prior = load_active_strategy_prior()
        assert prior is not None
        assert prior.caixin_alignment.startswith("placeholder")

    def test_override_policy_and_disclaimer_present(self) -> None:
        prior = load_active_strategy_prior()
        assert prior is not None
        assert "事实为准" in prior.override_policy
        assert "not a program filter" in prior.disclaimer

    def test_missing_dir_returns_empty_list(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "no_such_dir"
        result = load_strategy_priors(nonexistent)
        assert result == []

    def test_load_strategy_priors_returns_list(self) -> None:
        priors = load_strategy_priors()
        assert isinstance(priors, list)
        assert len(priors) >= 1

    def test_no_forbidden_fields_in_loaded_prior(self) -> None:
        """Philosophy guard on the loaded YAML-backed prior."""
        prior = load_active_strategy_prior()
        assert prior is not None
        all_keys = _flatten_keys(prior.model_dump())
        violations = FORBIDDEN_FIELDS & all_keys
        assert not violations, f"Forbidden fields in loaded prior: {violations}"
