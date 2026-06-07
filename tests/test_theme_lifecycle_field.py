from aegis_alpha.models import SecondBoardCandidate


def test_candidate_has_theme_lifecycle_stage():
    field = SecondBoardCandidate.model_fields.get("theme_lifecycle_stage")
    assert field is not None
    assert field.default == "unknown"
