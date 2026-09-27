"""Configuration for Samsung Message app."""

APP_KEY = "message"
GROUP = "samsung"
FEATURE = "message"

PACKAGE_NAME = "com.google.android.apps.messaging"
ACTIVITY_NAME = "com.google.android.apps.messaging/com.google.android.apps.messaging.ui.ConversationListActivity"


ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "send": [
        ['click', 201, 947], ['screenshot']
    ],
    "draft": [
        ['click', 298, 1591], ['screenshot']
    ],
    "disambiguation": [
        ['screenshot']
    ],
    "notsend": [
        ['screenshot']
    ],
}

