"""
Deterministic judge handlers for Samsung Clock.
"""

from ..judge_helpers import handle_app_state

HANDLERS = {
    ("clockalarm", "launch"): handle_app_state,
}
