"""Configuration for Samsung Clock Timer app."""

APP_KEY = "clocktimer"
GROUP = "samsung"
FEATURE = "clock_timer"

PACKAGE_NAME = "com.sec.android.app.clockpackage"
ACTIVITY_NAME = "com.sec.android.app.clockpackage/com.sec.android.app.clockpackage.ClockPackage"

# Timer tab is tab 3 of 4 at the bottom of the Clock app.
# Coordinates are screen ratios (floats 0-1) scaled by device resolution at runtime.
TIMER_TAB_X = 0.731
TIMER_TAB_Y = 0.900

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['click', 0.227, 0.711],
        ['click_stop_notification', 0.370, 0.159],
        ['close_app']
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['click', 0.227, 0.711],
        ['click_stop_notification', 0.370, 0.159],
        ['close_app']
    ],
    "pause": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "restart": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "stop": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],
        ['click', TIMER_TAB_X, TIMER_TAB_Y],
        ['screenshot'],
        ['click', 0.227, 0.711],
        ['click_stop_notification', 0.370, 0.159],
        ['close_app']
    ],
}

