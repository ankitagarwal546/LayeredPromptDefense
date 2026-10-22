"""Logging setup. Log lines carry metadata only (ids, config, timings), never document or summary text."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Idempotent: safe to call on every app creation (no duplicate handlers)."""
    numeric = logging.getLevelName(level.upper())
    if not isinstance(numeric, int):
        raise ValueError(f"Unknown log level {level!r}")
    logger = logging.getLogger("injection_defense")
    logger.setLevel(numeric)
    if not any(getattr(h, "_injection_defense", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._injection_defense = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
