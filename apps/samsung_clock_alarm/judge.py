"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("clockalarm", "create"): handle_app_state,
    ("clockalarm", "delete"): handle_app_state,
    ("clockalarm", "disable"): handle_app_state,
    ("clockalarm", "modify"): handle_app_state,
    ("clockalarm", "stop"): handle_app_state,
}
