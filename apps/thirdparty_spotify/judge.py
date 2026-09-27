"""
Deterministic judge handlers for this app.
"""

from ..judge_helpers import handle_launch

# Maps (app_key, action) → handler function
HANDLERS = {
    ("spotify", "launch"): handle_launch,
}
