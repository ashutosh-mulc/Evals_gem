"""
Deterministic judge handlers for this app.

All actions use the generic XRClaw state collector handler.
Launch action uses handle_launch to check if app process is running.
"""

from ..judge_helpers import handle_app_state, handle_launch

# Maps (app_key, action) → handler function
HANDLERS = {
    ("youtubemusic", "launch"): handle_launch,
    ("youtubemusic", "create"): handle_app_state,
    ("youtubemusic", "delete"): handle_app_state,
    ("youtubemusic", "modify"): handle_app_state,
    ("youtubemusic", "play"): handle_app_state,
    ("youtubemusic", "playlistcreate"): handle_app_state,
    ("youtubemusic", "playlistplay"): handle_app_state,
    ("youtubemusic", "podcastnext"): handle_app_state,
}
