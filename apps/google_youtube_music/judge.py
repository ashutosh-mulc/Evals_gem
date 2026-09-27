"""
Deterministic judge handlers for this app.

Launch action uses handle_launch to check if app process is running.
"""

from ..judge_helpers import handle_launch

# Maps (app_key, action) → handler function
HANDLERS = {
    ("youtubemusic", "launch"): handle_launch,
}
