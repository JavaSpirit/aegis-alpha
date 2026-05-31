from __future__ import annotations

from pathlib import Path

from aegis_alpha.alerts.store import AlertStore
from aegis_alpha.storage import AegisAlphaStore


def _store(tmp_path: Path) -> AegisAlphaStore:
    return AegisAlphaStore(tmp_path / "test.db")


def test_create_alert_assigns_id_and_persists(tmp_path: Path) -> None:
    store = AlertStore(_store(tmp_path))

    alert = store.create(
        title="Theme leader broken",
        body="LDR theme=AI broken at 13:30",
        severity="warning",
        event_id="evt_1",
        symbol="LDR",
        theme="AI",
    )

    assert alert.alert_id
    assert alert.status == "pending"
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].alert_id == alert.alert_id


def test_create_dedupes_on_event_id(tmp_path: Path) -> None:
    store = AlertStore(_store(tmp_path))
    store.create(title="A", severity="info", event_id="evt_1")
    store.create(title="A again", severity="info", event_id="evt_1")

    pending = store.list_pending()
    assert len(pending) == 1


def test_acknowledge_marks_status(tmp_path: Path) -> None:
    store = AlertStore(_store(tmp_path))
    alert = store.create(title="A", severity="info")

    acked = store.acknowledge(alert.alert_id, note="seen")

    assert acked.status == "acknowledged"
    assert acked.acknowledged_at
    assert any("seen" in note for note in acked.notes)
    assert store.list_pending() == []
