"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("googletranslate", "create"): handle_app_state,
    ("googletranslate", "delete"): handle_app_state,
    ("googletranslate", "launch"): handle_app_state,
    ("googletranslate", "modify"): handle_app_state,
    ("googletranslate", "start"): handle_app_state,
}
