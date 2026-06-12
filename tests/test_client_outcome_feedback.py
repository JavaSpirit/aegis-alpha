"""TDD: client-outcome feedback via existing correction pipeline.

Task 7.4 — CLIENT_OUTCOME correction type flows through the pipeline and
surfaces a memory suggestion with status="needs_human_review".

RED phase: run before CHANGE 1 + CHANGE 2; all tests should FAIL.
GREEN phase: run after CHANGE 1 + CHANGE 2; all tests should PASS.
"""
from __future__ import annotations


def test_record_client_outcome_correction_accepted(tmp_path) -> None:
    """record_agent_review_correction normalises CLIENT_OUTCOME without ValidationError."""
    from aegis_alpha.models import AgentReviewCorrection
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "co_test.db"))

    # Should NOT raise pydantic ValidationError
    correction = AgentReviewCorrection(
        review_id="review-co-1",
        symbol="000001",
        correction_type="CLIENT_OUTCOME",
        comment="client confirms theme_lifecycle_stage=ebb is a strong veto",
    )
    saved = store.save_agent_review_correction(correction)

    assert saved.correction_id, "correction_id should be auto-assigned"
    assert saved.correction_type == "CLIENT_OUTCOME"


def test_client_outcome_summary_surfaces_memory_suggestion(tmp_path) -> None:
    """After one CLIENT_OUTCOME correction, the summary recommends a memory action
    with status='needs_human_review' and a non-empty suggested_patch."""
    from aegis_alpha.models import AgentReviewCorrection
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "co_summary_test.db"))
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-co-2",
            symbol="000001",
            correction_type="CLIENT_OUTCOME",
            comment="client confirms theme_lifecycle_stage=ebb is a strong veto",
        )
    )

    summary = store.agent_correction_summary(limit=10)

    assert summary.by_type.get("CLIENT_OUTCOME", 0) == 1

    # Must surface at least one memory action for CLIENT_OUTCOME
    co_memory_actions = [
        a for a in summary.recommended_actions
        if a.correction_type == "CLIENT_OUTCOME" and a.target == "memory"
    ]
    assert co_memory_actions, (
        "Expected at least one recommended_action with target='memory' and "
        "correction_type='CLIENT_OUTCOME'"
    )

    action = co_memory_actions[0]
    assert action.status == "needs_human_review", (
        f"Expected status='needs_human_review', got {action.status!r}. "
        "Client outcomes must never be auto-applied."
    )
    assert action.suggested_patch, "suggested_patch must be non-empty"
    assert "Aegis Alpha" in action.suggested_patch or "human" in action.suggested_patch.lower()


def test_client_outcome_proposals_have_needs_human_review(tmp_path) -> None:
    """save_correction_action_proposals for a CLIENT_OUTCOME summary produces a
    proposal with needs_human_review (never ready_to_apply)."""
    from aegis_alpha.models import AgentReviewCorrection
    from aegis_alpha.storage import AegisAlphaStore

    store = AegisAlphaStore(str(tmp_path / "co_proposal_test.db"))
    store.save_agent_review_correction(
        AgentReviewCorrection(
            review_id="review-co-3",
            correction_type="CLIENT_OUTCOME",
            comment="client confirms ebb veto",
        )
    )

    summary = store.agent_correction_summary(limit=10)
    proposals = store.save_correction_action_proposals(summary)

    co_proposals = [p for p in proposals if p.correction_type == "CLIENT_OUTCOME"]
    assert co_proposals, "Expected at least one proposal with correction_type='CLIENT_OUTCOME'"

    for p in co_proposals:
        assert p.status == "pending", (
            "New proposals must start as 'pending' — they are never auto-applied"
        )
