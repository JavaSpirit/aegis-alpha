from __future__ import annotations

import os
import subprocess
import sys

from aegis_alpha.logging_setup import get_logger
from aegis_alpha.models import AgentAlert


_LOGGER = get_logger(__name__)


def _enabled() -> bool:
    raw = os.environ.get("AEGIS_ALPHA_ENABLE_DESKTOP_NOTIFICATIONS", "false").strip().lower()
    return raw in {"1", "true", "yes", "y"}


def notify_macos(alert: AgentAlert) -> bool:
    if not _enabled():
        return False
    if sys.platform != "darwin":
        _LOGGER.debug("event=desktop_notify_skip platform=%s", sys.platform)
        return False
    title = alert.title.replace("\"", "'")[:120]
    body = alert.body.replace("\"", "'")[:240] or alert.title
    script = f'display notification "{body}" with title "Aegis Alpha" subtitle "{title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=3,
            capture_output=True,
        )
        return True
    except Exception as exc:
        _LOGGER.warning("event=desktop_notify_failed error=%s", type(exc).__name__)
        return False
