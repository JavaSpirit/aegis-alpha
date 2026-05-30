from __future__ import annotations

from aegis_alpha.models import SignalEvidence, SignalMetadata


def unavailable_metadata(*, source_field: str, timestamp: str, limitation: str) -> SignalMetadata:
    return SignalMetadata(
        source="jvquant.semantic_query",
        source_field=source_field,
        timestamp=timestamp,
        confidence="unavailable",
        usable_for_grading=False,
        limitations=[limitation],
        evidence=[
            SignalEvidence(
                authority="internal_inference",
                source="aegis_alpha.adapters.jvquant",
                detail=limitation,
                observed_at=timestamp,
            )
        ],
    )
