"""
Unified logging setup for MAIRE.

Replaces the duplicated logging.basicConfig blocks in coordinator.py,
agent_tester.py, and judge_worker.py with a single function.

Usage:
    from config.logging_config import setup_logging

    setup_logging(level="debug", log_file="/path/to/component.log")
"""

from __future__ import annotations

import logging
import sys

# Standard format used across all MAIRE components
LOG_FORMAT = '%(asctime)s\t%(levelname)s\t%(module)s\t%(process)s\t%(thread)s\t%(message)s'

_LEVEL_MAP = {
    "": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def setup_logging(
    level: str = "debug",
    log_file: str | None = None,
    fmt: str = LOG_FORMAT,
) -> None:
    """
    Configure logging for a MAIRE component.

    Args:
        level: Log level string (e.g. "debug", "info"). Empty string = debug.
        log_file: If provided, also log to this file. Otherwise console only.
        fmt: Log format string.
    """
    log_level = _LEVEL_MAP.get(level.lower(), logging.DEBUG)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=log_level,
        format=fmt,
        handlers=handlers,
        force=True,  # Override any prior config
    )
