from __future__ import annotations

from aegis_alpha.models import SelectionPick, RejectedCandidate, SelectionAudit

FORBIDDEN = {"grade", "score", "passed", "probability", "reject", "meets_threshold"}


def _flatten_keys(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _flatten_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _flatten_keys(item)
    return keys


def test_build_selection_audit():
    audit = SelectionAudit(
        audit_id="a1",
        as_of_day="2026-06-19",
        picks=[SelectionPick(symbol="002491", rank=1, relative_reason="胜过高封单额的X", caveats=["盘外新闻未确认"])],
        rejected=[RejectedCandidate(symbol="300475", why_rejected="题材分歧", beat_by="002491")],
        baseline={"seal_amount": ["600000"], "seal_ratio": ["002491"], "first_seal_time": ["600000"]},
        equals_baseline=False,
        confidence_label="exploratory",
        candidate_pool_size=55,
    )
    assert audit.picks[0].symbol == "002491"
    assert audit.picks[0].rank == 1
    assert audit.rejected[0].beat_by == "002491"
    assert audit.equals_baseline is False


def test_philosophy_guard_no_forbidden_fields():
    audit = SelectionAudit(audit_id="x", as_of_day="2026-06-19")
    keys = _flatten_keys(audit.model_dump())
    assert not (FORBIDDEN & keys), f"forbidden fields: {FORBIDDEN & keys}"


def test_defaults_minimal():
    audit = SelectionAudit(audit_id="x", as_of_day="2026-06-19")
    assert audit.picks == []
    assert audit.rejected == []
    assert audit.equals_baseline is False
    assert audit.confidence_label == "exploratory"
