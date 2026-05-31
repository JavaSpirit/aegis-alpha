from __future__ import annotations

import uuid

from aegis_alpha.clock import now_iso
from aegis_alpha.models import AgentAlert, AlertSeverity
from aegis_alpha.storage import AegisAlphaStore


class AlertStore:
    def __init__(self, store: AegisAlphaStore) -> None:
        self.store = store

    def create(
        self,
        *,
        title: str,
        severity: AlertSeverity = "info",
        body: str = "",
        event_id: str = "",
        symbol: str = "",
        theme: str = "",
    ) -> AgentAlert:
        if event_id:
            existing = self.store.get_alert_by_event(event_id)
            if existing is not None:
                return existing
        alert = AgentAlert(
            alert_id=str(uuid.uuid4()),
            event_id=event_id,
            symbol=symbol,
            theme=theme,
            severity=severity,
            status="pending",
            title=title.strip(),
            body=body.strip(),
            created_at=now_iso(),
        )
        self.store.save_alert(alert)
        return alert

    def acknowledge(self, alert_id: str, *, note: str = "") -> AgentAlert:
        alert = self.store.get_alert(alert_id)
        if alert is None:
            raise KeyError(f"alert not found: {alert_id}")
        timestamp = now_iso()
        notes = list(alert.notes)
        if note.strip():
            notes.append(f"{timestamp} {note.strip()}")
        updated = alert.model_copy(
            update={"status": "acknowledged", "acknowledged_at": timestamp, "notes": notes}
        )
        self.store.save_alert(updated)
        return updated

    def list_pending(self, *, limit: int = 50) -> list[AgentAlert]:
        return self.store.list_alerts(status="pending", limit=limit)

    def list_recent(self, *, limit: int = 50) -> list[AgentAlert]:
        return self.store.list_alerts(status="", limit=limit)
