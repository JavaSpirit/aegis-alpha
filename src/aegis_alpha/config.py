from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []

    if "AEGIS_ALPHA_PROJECT_ROOT" in os.environ:
        roots.append(Path(os.environ["AEGIS_ALPHA_PROJECT_ROOT"]))

    roots.append(Path.cwd())

    entrypoint = Path(sys.argv[0]).resolve()
    if ".venv" in entrypoint.parts and "bin" in entrypoint.parts:
        try:
            roots.append(entrypoint.parents[2])
        except IndexError:
            pass

    return roots


def load_project_env() -> None:
    """Load local project env values without overriding exported variables."""

    env_file = os.environ.get("AEGIS_ALPHA_ENV_FILE")
    candidates = [Path(env_file)] if env_file else []
    for root in _candidate_roots():
        candidates.extend([root / ".env.local", root / ".env"])

    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
