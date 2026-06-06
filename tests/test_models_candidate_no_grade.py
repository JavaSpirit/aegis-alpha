from aegis_alpha.models import SecondBoardCandidate


def test_candidate_has_no_program_grade_fields():
    fields = set(SecondBoardCandidate.model_fields)
    assert "grade" not in fields
    assert "grade_reason" not in fields
    assert "estimated_seal_probability" not in fields


def test_candidate_still_carries_measured_facts():
    fields = set(SecondBoardCandidate.model_fields)
    for fact in ("five_min_speed_pct", "big_order_net_inflow_ratio", "seal_to_turnover_ratio"):
        assert fact in fields
