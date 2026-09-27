"""Configuration for Google Calendar app."""

APP_KEY = "googlecalendar"
GROUP = "google"
FEATURE = "calendar"

PACKAGE_NAME = "com.google.android.calendar"
ACTIVITY_NAME = "com.google.android.calendar/com.android.calendar.AllInOneActivity"


ACTIONS = {
    "read": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 1200], ['screenshot'], ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 1200], ['screenshot'], ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 1200], ['screenshot'], ['close_app']
    ],
}

