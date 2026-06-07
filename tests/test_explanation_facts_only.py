from aegis_alpha.models import CandidateExplanation


def test_explanation_is_facts_not_grade():
    fields = set(CandidateExplanation.model_fields)
    assert "grade" not in fields
    assert "grade_reason" not in fields
    assert "observations" in fields
    assert "risks" in fields
