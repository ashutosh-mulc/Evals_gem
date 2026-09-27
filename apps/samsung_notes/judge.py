"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("samsungnote", "create"): handle_app_state,
    ("samsungnote", "delete"): handle_app_state,
    ("samsungnote", "launch"): handle_app_state,
    ("samsungnote", "modify"): handle_app_state,
    ("samsungnote", "read"): handle_app_state,
    ("samsungnote", "visualcreate"): handle_app_state,
}
