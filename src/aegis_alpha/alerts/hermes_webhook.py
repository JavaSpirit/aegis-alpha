from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from typing import Any

from aegis_alpha.clock import now_iso
from aegis_alpha.logging_setup import get_logger
from aegis_alpha.models import AgentAlert


_LOGGER = get_logger(__name__)


def hermes_webhook_enabled(config: dict[str, Any]) -> bool:
    cfg = config.get("hermes_webhook", {}) or {}
    raw = cfg.get("enabled", os.environ.get("AEGIS_ALPHA_HERMES_WEBHOOK_ENABLED", "false"))
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def hermes_webhook_url(config: dict[str, Any]) -> str:
    cfg = config.get("hermes_webhook", {}) or {}
    env_key = str(cfg.get("url_env") or "HERMES_AEGIS_WEBHOOK_URL")
    return str(cfg.get("url") or os.environ.get(env_key, "")).strip()


def hermes_webhook_secret(config: dict[str, Any]) -> str:
    cfg = config.get("hermes_webhook", {}) or {}
    env_key = str(cfg.get("secret_env") or "HERMES_AEGIS_WEBHOOK_SECRET")
    return str(cfg.get("secret") or os.environ.get(env_key, "")).strip()


def hermes_webhook_timeout(config: dict[str, Any]) -> float:
    cfg = config.get("hermes_webhook", {}) or {}
    try:
        return max(0.2, float(cfg.get("timeout_seconds", 3)))
    except (TypeError, ValueError):
        return 3.0


def hermes_event_type(alert: AgentAlert) -> str:
    title = alert.title.strip().split(" ", 1)[0].lower()
    if title == "buypoint_alert":
        return "aegis.buy_point_alert"
    if title == "selection_validation":
        return "aegis.selection_validation"
    if title:
        return f"aegis.{title}"
    return "aegis.alert"


def build_hermes_alert_payload(alert: AgentAlert, *, source: str = "aegis-runner") -> dict[str, Any]:
    payload = alert.model_dump()
    event_type = hermes_event_type(alert)
    return {
        "event_type": event_type,
        "source": source,
        "sent_at": now_iso(),
        "alert": payload,
        "summary": {
            "title": alert.title,
            "severity": alert.severity,
            "symbol": alert.symbol,
            "theme": alert.theme,
            "body": alert.body,
            "event_id": alert.event_id,
        },
    }


def _signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def post_alert_to_hermes(alert: AgentAlert, config: dict[str, Any], *, source: str = "aegis-runner") -> bool:
    if not hermes_webhook_enabled(config):
        return False
    url = hermes_webhook_url(config)
    secret = hermes_webhook_secret(config)
    if not url or not secret:
        _LOGGER.warning("event=hermes_webhook_skip reason=missing_url_or_secret")
        return False

    payload = build_hermes_alert_payload(alert, source=source)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": payload["event_type"],
        "X-GitHub-Delivery": alert.event_id or alert.alert_id,
        "X-Hub-Signature-256": _signature(body, secret),
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=hermes_webhook_timeout(config)) as response:
            ok = 200 <= response.status < 300
            if not ok:
                _LOGGER.warning("event=hermes_webhook_failed status=%s", response.status)
            return ok
    except (urllib.error.URLError, TimeoutError) as exc:
        _LOGGER.warning("event=hermes_webhook_failed error=%s", type(exc).__name__)
        return False
    except Exception as exc:
        _LOGGER.warning("event=hermes_webhook_failed error=%s", type(exc).__name__)
        return False
