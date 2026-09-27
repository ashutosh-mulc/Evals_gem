"""Configuration for Samsung Camera app."""

APP_KEY = "samsungcamera"
GROUP = "samsung"
FEATURE = "camera"

PACKAGE_NAME = "com.sec.android.app.camera"
ACTIVITY_NAME = "com.sec.android.app.camera/.Camera"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "click": [
        ['screenshot']
    ],
    "check": [
        ['screenshot']
    ],

    "videostart": [
        ['screenshot']
    ],
    "videostop": [
        ['screenshot']
    ],
    "exit": [
        ['screenshot']
    ],
}

