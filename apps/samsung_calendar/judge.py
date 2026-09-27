"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("samsungcalendar", "create"): handle_app_state,
    ("samsungcalendar", "delete"): handle_app_state,
    ("samsungcalendar", "launch"): handle_app_state,
    ("samsungcalendar", "modify"): handle_app_state,
    ("samsungcalendar", "read"): handle_app_state,
}
