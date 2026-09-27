"""
State collector for Google Keep.

No XRClaw state collector — this app uses screenshot + VLM judge.
"""

from __future__ import annotations

from ..helpers import result

APP_KEYS = ("googlekeep",)
ACCESSOR = None

def capture_pre(dm) -> dict:
    """No pre-state capture for this app."""
    return {}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """No state collector verification — falls back to VLM judge."""
    from ..helpers import unsupported_result
    return unsupported_result(app_key, gt_answer)
