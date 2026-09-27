"""Configuration for Samsung Clock Stopwatch app."""

APP_KEY = "clockstopwatch"
GROUP = "samsung"
FEATURE = "clock_stopwatch"

PACKAGE_NAME = "com.sec.android.app.clockpackage"
ACTIVITY_NAME = "com.sec.android.app.clockpackage/com.sec.android.app.clockpackage.ClockPackage"

# Stopwatch tab is tab 2 of 4 at the bottom of the Clock app.
# Coordinates are screen ratios (floats 0-1) scaled by device resolution at runtime.
STOPWATCH_TAB_X = 0.578
STOPWATCH_TAB_Y = 0.900

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "start": [
        ['open_activity', ACTIVITY_NAME],
        ['click', STOPWATCH_TAB_X, STOPWATCH_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "lap": [
        ['open_activity', ACTIVITY_NAME],
        ['click', STOPWATCH_TAB_X, STOPWATCH_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "stop": [
        ['open_activity', ACTIVITY_NAME],
        ['click', STOPWATCH_TAB_X, STOPWATCH_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
    "reset": [
        ['open_activity', ACTIVITY_NAME],
        ['click', STOPWATCH_TAB_X, STOPWATCH_TAB_Y],
        ['screenshot'],
        ['close_app']
    ],
}

