"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("clockstopwatch", "lap"): handle_app_state,
    ("clockstopwatch", "reset"): handle_app_state,
    ("clockstopwatch", "start"): handle_app_state,
    ("clockstopwatch", "stop"): handle_app_state,
}
