"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("googlekeep", "create"): handle_app_state,
    ("googlekeep", "delete"): handle_app_state,
    ("googlekeep", "launch"): handle_app_state,
    ("googlekeep", "modify"): handle_app_state,
    ("googlekeep", "read"): handle_app_state,
    ("googlekeep", "visualcreate"): handle_app_state,
}
