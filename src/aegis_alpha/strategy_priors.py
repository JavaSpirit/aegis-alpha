from __future__ import annotations

"""Strategy prior loader — pure file I/O, no network calls.

Mirrors the style of events.py / load_event_scoring_config.
Loads every *.yaml under config/strategy_priors/ and returns validated
StrategyPrior instances. The program NEVER uses these priors to filter or
reject candidates; they are guidance fed to the agent at query time.
"""

from pathlib import Path

import yaml

from aegis_alpha.models import StrategyPrior

__all__ = [
    "project_root",
    "load_strategy_priors",
    "load_active_strategy_prior",
]

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "config" / "strategy_priors"


def project_root() -> Path:
    """Return the repository root (two levels above src/aegis_alpha/)."""
    return Path(__file__).resolve().parents[2]


def load_strategy_priors(path: str | Path | None = None) -> list[StrategyPrior]:
    """Load all *.yaml files from the strategy_priors config directory.

    Args:
        path: Directory to scan. Defaults to ``config/strategy_priors/``
              relative to the repo root. A non-existent directory returns ``[]``.

    Returns:
        List of validated :class:`StrategyPrior` instances (one per YAML file).
        Order follows filesystem iteration; callers should not rely on it.
    """
    dir_path = Path(path) if path is not None else _DEFAULT_DIR
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    priors: list[StrategyPrior] = []
    for yaml_file in sorted(dir_path.glob("*.yaml")):
        payload = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        priors.append(StrategyPrior.model_validate(payload))
    return priors


def load_active_strategy_prior(path: str | Path | None = None) -> StrategyPrior | None:
    """Return the first prior with ``is_active == True``, or ``None``.

    Args:
        path: Passed directly to :func:`load_strategy_priors`.
    """
    for prior in load_strategy_priors(path):
        if prior.is_active:
            return prior
    return None
