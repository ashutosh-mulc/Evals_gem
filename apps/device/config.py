"""Configuration for all device-level queries (volume, battery, DND, etc.)."""

APP_KEY = "device"
GROUP = "device"

# All device features handled by this module
FEATURES = ("volume", "datetime", "battery", "dnd", "mediacontrol", "notification")


PACKAGE_NAME = ""
ACTIVITY_NAME = ""

# Volume settings intent — opens Samsung Sound/Volume Settings page so the
# post-state screenshot shows the volume slider for judge verification.
_VOLUME_SETTINGS = "com.android.settings/.SubSettings --es :settings:show_fragment com.samsung.android.settings.asbase.audio.SecVolumeSettings"

# ── Per-feature action definitions ──────────────────────────────
ACTIONS = {
    # Volume
    "volume": {
        "up":          [["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
        "down":        [["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
        "set":         [["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
        "uprelative":  [["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
        "downrelative":[["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
        "mute":        [["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
        "unmute":      [["open_activity", _VOLUME_SETTINGS], ["screenshot"]],
    },
    # DateTime
    "datetime": {
        "time": [["screenshot"]],
        "date": [["screenshot"]],
    },
    # Battery
    "battery": {
        "glasses": [["screenshot"]],
        "phone": [["screenshot"]],
        "companion": [["screenshot"]],
    },
    # DND
    "dnd": {
        "on": [["screenshot"]],
        "off": [["screenshot"]],
    },
    # MediaControl
    "mediacontrol": {
        "play": [["screenshot"]],
        "pause": [["screenshot"]],
        "resume": [["screenshot"]],
        "replay": [["screenshot"]],
        "previous": [["screenshot"]],
        "skip": [["screenshot"]],
        "like": [["log_analysis"]],
        "dislike": [["log_analysis"]],
    },
    # Notification
    "notification": {
        "read": [["open_notification_panel"], ["wait", 2], ["screenshot"] ],
        "notread": [["open_notification_panel"], ["wait", 2], ["screenshot"]],
        "auto": [["open_notification_panel"], ["wait", 2], ["screenshot"]],
    },

}

