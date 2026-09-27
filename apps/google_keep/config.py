"""Configuration for Google Keep app."""

APP_KEY = "googlekeep"
GROUP = "google"
FEATURE = "keep"

PACKAGE_NAME = "com.google.android.keep"
ACTIVITY_NAME = "com.google.android.keep/.activities.BrowseActivity"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 600], ['screenshot'], ['close_app']
    ],
    "visualcreate": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 600], ['screenshot'], ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 600], ['screenshot'], ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 600], ['screenshot'], ['close_app']
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
}

