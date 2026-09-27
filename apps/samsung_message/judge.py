"""
Deterministic judge handlers for this app.
"""

from ..judge_helpers import handle_app_state, handle_launch

# Maps (app_key, action) → handler function
HANDLERS = {
    ("message", "disambiguation"): handle_app_state,
    ("message", "draft"): handle_app_state,
    ("message", "launch"): handle_launch,
    ("message", "notsend"): handle_app_state,
    ("message", "read"): handle_app_state,
    ("message", "send"): handle_app_state,
}
