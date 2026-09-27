"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("googlecalendar", "create"): handle_app_state,
    ("googlecalendar", "delete"): handle_app_state,
    ("googlecalendar", "modify"): handle_app_state,
    ("googlecalendar", "read"): handle_app_state,
}
