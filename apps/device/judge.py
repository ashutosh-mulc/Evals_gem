"""
Deterministic judge handlers for all device-level queries.

Merged from: device_volume, device_datetime, device_battery, device_dnd,
device_mediacontrol, device_notification.
"""

from .judge_rules import (
    handle_time,
    handle_date,
    handle_battery,
    handle_volume,
    handle_dnd,
    handle_mediacontrol,
    handle_media_like_dislike,
)
from ..judge_helpers import handle_camera, handle_video

HANDLERS = {
    # Volume
    ("device", "up"): handle_volume,
    ("device", "down"): handle_volume,
    # ("device", "set"): handle_volume,
    # ("device", "uprelative"): handle_volume,
    # ("device", "downrelative"): handle_volume,
    ("device", "mute"): handle_volume,
    ("device", "unmute"): handle_volume,

    # DateTime
    ("device", "time"): handle_time,
    ("device", "date"): handle_date,

    # Battery
    ("device", "glasses"): handle_battery,
    ("device", "phone"): handle_battery,
    ("device", "companion"): handle_battery,

    # DND
    ("device", "on"): handle_dnd,
    ("device", "off"): handle_dnd,

    # MediaControl
    ("device", "play"): handle_mediacontrol,
    ("device", "pause"): handle_mediacontrol,
    ("device", "resume"): handle_mediacontrol,
    ("device", "replay"): handle_mediacontrol,
    ("device", "previous"): handle_mediacontrol,
    ("device", "skip"): handle_mediacontrol,
    ("device", "like"): handle_media_like_dislike,
    ("device", "dislike"): handle_media_like_dislike,

    # Camera/Video (online_device_camera_click, online_device_video_videostart, ...)
    ("device", "click"): handle_camera,
    ("device", "videostart"): handle_video,
    ("device", "videostop"): handle_video,

    # Notification — no deterministic handlers (uses VLM judge)
}

