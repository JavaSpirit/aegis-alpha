from __future__ import annotations

import logging
import os


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
PROJECT_LOGGER_NAME = "aegis_alpha"
_HANDLER_MARKER = "_aegis_alpha_handler"


def configure_logging(level: str | int | None = None) -> logging.Logger:
    resolved_level = _resolve_level(level or os.environ.get("AEGIS_ALPHA_LOG_LEVEL", "INFO"))
    logger = logging.getLogger(PROJECT_LOGGER_NAME)
    logger.setLevel(resolved_level)
    logger.propagate = False

    if not any(getattr(handler, _HANDLER_MARKER, False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)

    for handler in logger.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            handler.setLevel(resolved_level)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    if not name:
        return logging.getLogger(PROJECT_LOGGER_NAME)
    if name == PROJECT_LOGGER_NAME or name.startswith(f"{PROJECT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{PROJECT_LOGGER_NAME}.{name}")


def _resolve_level(level: str | int) -> int:
    if isinstance(level, int):
        return level

    normalized = level.strip().upper()
    resolved = logging.getLevelName(normalized)
    if isinstance(resolved, int):
        return resolved
    raise ValueError(f"Unknown log level: {level}")
