"""Configuration for Thirdparty Whatsapp app."""

APP_KEY = "whatsapp"
GROUP = "thirdparty"
FEATURE = "whatsapp"

PACKAGE_NAME = "com.whatsapp"
ACTIVITY_NAME = "com.whatsapp/.HomeActivity"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "call": [
        ['screenshot']
    ],
    "messagesend": [
        ['click', 182, 1148], ['screenshot']
    ],
    "messagereply": [
        ['click', 182, 1148], ['screenshot']
    ],
    "disambiguation": [
        ['screenshot']
    ],
    "notsend": [
        ['screenshot']
    ],
    "callsend": [
        ['screenshot']
    ],
    "send": [
        ['click', 182, 1148], ['screenshot']
    ],
}

