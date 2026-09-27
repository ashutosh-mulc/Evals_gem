"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("samsungreminder", "create"): handle_app_state,
    ("samsungreminder", "delete"): handle_app_state,
    ("samsungreminder", "launch"): handle_app_state,
    ("samsungreminder", "modify"): handle_app_state,
    ("samsungreminder", "noread"): handle_app_state,
    ("samsungreminder", "read"): handle_app_state,
}
