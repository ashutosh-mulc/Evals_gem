"""Configuration for Samsung Clock Alarm app."""

APP_KEY = "clockalarm"
GROUP = "samsung"
FEATURE = "clock_alarm"

PACKAGE_NAME = "com.sec.android.app.clockpackage"
ACTIVITY_NAME = "com.sec.android.app.clockpackage/com.sec.android.app.clockpackage.ClockPackage"

# Alarm tab is the leftmost of 4 bottom tabs (Alarm, World Clock, Stopwatch, Timer).
# Coordinates are screen ratios (floats 0-1) scaled by device resolution at runtime.
ALARM_TAB_X = 0.267
ALARM_TAB_Y = 0.900

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],
        ['click', ALARM_TAB_X, ALARM_TAB_Y],
        ['swipe', 0.556, 0.437, 0.556, 0.278],
        ['screenshot'],
        ['close_app']
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME],
        ['click', ALARM_TAB_X, ALARM_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],
        ['click', ALARM_TAB_X, ALARM_TAB_Y],
        ['swipe', 0.556, 0.437, 0.556, 0.278],
        ['screenshot'],
        ['close_app']
    ],
    "stop": [
        ['open_activity', ACTIVITY_NAME],
        ['click', ALARM_TAB_X, ALARM_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "disable": [
        ['open_activity', ACTIVITY_NAME],
        ['click', ALARM_TAB_X, ALARM_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],
        ['click', ALARM_TAB_X, ALARM_TAB_Y],
        ['swipe', 0.556, 0.437, 0.556, 0.278],
        ['screenshot'],
        ['close_app']
    ],
}

