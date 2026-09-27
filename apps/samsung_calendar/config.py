"""Configuration for Samsung Calendar app."""

APP_KEY = "samsungcalendar"
GROUP = "samsung"
FEATURE = "calendar"

PACKAGE_NAME = "com.samsung.android.calendar"
ACTIVITY_NAME = "com.samsung.android.calendar/com.samsung.android.app.calendar.activity.MainActivity"


ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
}

