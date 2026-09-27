"""
Unified logging setup for the MAIRE processes (coordinator, agent_tester, judge_worker).

Usage:
    from common.logging_config import setup_logging

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


def setup_logging(level: str = "debug", log_file: str | None = None) -> None:
    """
    Configure logging for a MAIRE component.

    The log file gets everything at ``level``. The console gets INFO and above
    only, so debug payload dumps (base64 audio etc.) stay out of the terminal.

    Args:
        level: Log level string (e.g. "debug", "info"). Empty string = debug.
        log_file: If provided, also log to this file.
    """
    log_level = _LEVEL_MAP.get(level.lower(), logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(max(log_level, logging.INFO))
    handlers: list[logging.Handler] = [console]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=log_level, format=LOG_FORMAT, handlers=handlers, force=True)
