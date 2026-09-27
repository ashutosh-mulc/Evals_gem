"""
Deterministic judge handlers for this app.
"""

from ..judge_helpers import handle_app_state, handle_camera, handle_video, handle_launch, handle_exit

# Maps (app_key, action) → handler function
HANDLERS = {
    ("samsungcamera", "click"): handle_camera,
    ("samsungcamera", "videostart"): handle_video,
    ("samsungcamera", "videostop"): handle_video,
    ("samsungcamera", "launch"): handle_launch,
    ("samsungcamera", "exit"): handle_exit,
}
