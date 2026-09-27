"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
"""

from ..judge_helpers import handle_app_state

# Maps (app_key, action) → handler function
HANDLERS = {
    ("googlemaps", "addstop"): handle_app_state,
    ("googlemaps", "eta"): handle_app_state,
    ("googlemaps", "launch"): handle_app_state,
    ("googlemaps", "query"): handle_app_state,
    ("googlemaps", "querynavigate"): handle_app_state,
    ("googlemaps", "startnavigate"): handle_app_state,
    ("googlemaps", "stopnavigate"): handle_app_state,
}
