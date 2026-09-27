"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("clocktimer", "create"): handle_app_state,
    ("clocktimer", "delete"): handle_app_state,
    ("clocktimer", "modify"): handle_app_state,
    ("clocktimer", "pause"): handle_app_state,
    ("clocktimer", "restart"): handle_app_state,
    ("clocktimer", "stop"): handle_app_state,
}
