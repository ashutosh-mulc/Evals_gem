"""Configuration for Google Translate app."""

APP_KEY = "googletranslate"
GROUP = "google"
FEATURE = "translate"

PACKAGE_NAME = "com.google.android.apps.translate"
ACTIVITY_NAME = "com.google.android.apps.translate/.TranslateActivity"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "start": [
        ['screenshot'], ['close_app']
    ],
    "create": [
        ['screenshot'], ['close_app']
    ],
    "modify": [
        ['screenshot'], ['close_app']
    ],
    "delete": [
        ['screenshot'], ['close_app']
    ],
}

