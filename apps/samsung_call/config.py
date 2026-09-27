"""Configuration for Samsung Call app."""

APP_KEY = "call"
GROUP = "samsung"
FEATURE = "call"

PACKAGE_NAME = "com.samsung.android.dialer"
ACTIVITY_NAME = "com.samsung.android.dialer/.DialtactsActivity"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "send": [
        ['open_activity', ACTIVITY_NAME], ['screenshot']
    ],
    "visualsend": [
        ['screenshot']
    ],
    "videostart": [
        ['open_activity', ACTIVITY_NAME], ['screenshot']
    ],
    "disambiguation": [
        ['screenshot']
    ],
    "notsend": [
        ['screenshot']
    ],
}

