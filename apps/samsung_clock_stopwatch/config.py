"""Configuration for Samsung Clock Stopwatch app."""

APP_KEY = "clockstopwatch"
GROUP = "samsung"
FEATURE = "clock_stopwatch"

PACKAGE_NAME = "com.sec.android.app.clockpackage"
ACTIVITY_NAME = "com.sec.android.app.clockpackage/com.sec.android.app.clockpackage.ClockPackage"

# The bottom tab bar (Alarm, World clock, Stopwatch, Timer) has no resource-ids, but each
# tab has an exact content-desc, so tap_content_desc finds it on any screen size.
STOPWATCH_TAB_DESC = "Stopwatch"

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "start": [
        ['open_activity', ACTIVITY_NAME],              # open Clock (it may open on any tab)
        ['tap_content_desc', STOPWATCH_TAB_DESC],      # switch to the Stopwatch tab
        ['screenshot'],                                # capture the running stopwatch
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
    "lap": [
        ['open_activity', ACTIVITY_NAME],              # open Clock (it may open on any tab)
        ['tap_content_desc', STOPWATCH_TAB_DESC],      # switch to the Stopwatch tab
        ['screenshot'],                                # capture the stopwatch with its lap list
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
    "stop": [
        ['open_activity', ACTIVITY_NAME],              # open Clock (it may open on any tab)
        ['tap_content_desc', STOPWATCH_TAB_DESC],      # switch to the Stopwatch tab
        ['screenshot'],                                # capture the stopped stopwatch
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
    "reset": [
        ['open_activity', ACTIVITY_NAME],              # open Clock (it may open on any tab)
        ['tap_content_desc', STOPWATCH_TAB_DESC],      # switch to the Stopwatch tab
        ['screenshot'],                                # capture the reset stopwatch (00:00)
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
}

