"""Configuration for Google Mail app."""

APP_KEY = "googlemail"
GROUP = "google"
FEATURE = "mail"

PACKAGE_NAME = "com.google.android.gm"
ACTIVITY_NAME = "com.google.android.gm/.GmailActivity"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "search": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "thread_read": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
}

