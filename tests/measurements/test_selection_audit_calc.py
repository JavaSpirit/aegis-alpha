from __future__ import annotations

from aegis_alpha.feedback.selection_audit import (
    compute_audit_id,
    compute_equals_baseline,
    compute_confidence_label,
)


def test_audit_id_idempotent():
    a = compute_audit_id("2026-06-19", ["002491", "300475"])
    b = compute_audit_id("2026-06-19", ["300475", "002491"])  # order-independent
    assert a == b
    c = compute_audit_id("2026-06-19", ["002491"])
    assert c != a


def test_equals_baseline_true_when_matches_a_baseline():
    picks = ["002491", "300475"]
    baseline = {
        "seal_amount": ["600000", "999999"],
        "seal_ratio": ["002491", "300475"],   # identical set to picks
        "first_seal_time": ["111111", "222222"],
    }
    assert compute_equals_baseline(picks, baseline) is True


def test_equals_baseline_false_when_distinct():
    picks = ["002491", "300475"]
    baseline = {
        "seal_amount": ["600000", "999999"],
        "seal_ratio": ["111111", "222222"],
        "first_seal_time": ["333333", "444444"],
    }
    assert compute_equals_baseline(picks, baseline) is False


def test_equals_baseline_false_when_empty_picks_or_baseline():
    assert compute_equals_baseline([], {"seal_amount": ["x"]}) is False
    assert compute_equals_baseline(["002491"], {}) is False


def test_confidence_label_exploratory_below_10_days():
    assert compute_confidence_label(accumulated_days=3) == "exploratory"
    assert compute_confidence_label(accumulated_days=9) == "exploratory"


def test_confidence_label_low_or_medium_at_or_above_10():
    assert compute_confidence_label(accumulated_days=10) in {"low", "medium"}
    assert compute_confidence_label(accumulated_days=30) in {"low", "medium"}
