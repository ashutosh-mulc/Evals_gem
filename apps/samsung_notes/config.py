"""Configuration for Samsung Notes app."""

APP_KEY = "samsungnote"
GROUP = "samsung"
FEATURE = "notes"

PACKAGE_NAME = "com.samsung.android.app.notes"
ACTIVITY_NAME = "com.samsung.android.app.notes/.memolist.MemoListActivity"

ACTIONS = {
    "launch": [
        ["screenshot"]
    ],
    "create": [
        ["open_activity", ACTIVITY_NAME],
        # ["click", 400, 1200],
        ["screenshot"],
        ["close_app"]
    ],
    "visualcreate": [
        ["open_activity", ACTIVITY_NAME],
        # ["click", 400, 1200],
        ["screenshot"],
        ["close_app"]
    ],
    "modify": [
        ["open_activity", ACTIVITY_NAME],
        # ["click", 400, 1200],
        ["screenshot"],
        ["close_app"]
    ],
    "delete": [
        ["open_activity", ACTIVITY_NAME],
        # ["click", 400, 1200],
        ["screenshot"],
        ["close_app"]
    ],
    "read": [
        ["open_activity", ACTIVITY_NAME],
        ["screenshot"],
        ["close_app"]
    ]
}

