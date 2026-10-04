"""Configuration for Samsung Clock: the alarm feature plus the generic clock launch.

Both online_samsung_clock_launch and online_samsung_clock_alarm_* map to the
"clockalarm" app key, so they live in one app directory.
"""

APP_KEY = "clockalarm"
GROUP = "samsung"
FEATURES = ("clock_alarm", "clock")

PACKAGE_NAME = "com.sec.android.app.clockpackage"
ACTIVITY_NAME = "com.sec.android.app.clockpackage/com.sec.android.app.clockpackage.ClockPackage"

# The bottom tab bar (Alarm, World clock, Stopwatch, Timer) has no resource-ids, but each
# tab has an exact content-desc, so tap_content_desc finds it on any screen size.
ALARM_TAB_DESC = "Alarm"

# Intentional swipe (kept as is) that refreshes the alarm page. The finger moves from 44% to 28%
# of the screen height. Ratios, not pixels, so it is resolution-independent.
SCROLL_ALARM_LIST = ['swipe', 0.556, 0.437, 0.556, 0.278]

ACTIONS = {
    "clock_alarm": {
        "launch": [
            # The agent already left the app open; just capture whatever is on screen.
            ['screenshot'],
        ],
        "create": [
            ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
            ['tap_content_desc', ALARM_TAB_DESC],      # switch to the Alarm tab
            SCROLL_ALARM_LIST,                         # swipe to refresh the page (intentional)
            ['screenshot'],                            # capture the alarm list
            ['close_app'],                             # force-stop so the next action starts from a cold app
        ],
        "read": [
            ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
            ['tap_content_desc', ALARM_TAB_DESC],      # switch to the Alarm tab
            ['screenshot'],                            # capture the alarm list
            ['close_app'],                             # force-stop so the next action starts from a cold app
        ],
        "modify": [
            ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
            ['tap_content_desc', ALARM_TAB_DESC],      # switch to the Alarm tab
            SCROLL_ALARM_LIST,                         # swipe to refresh the page (intentional)
            ['screenshot'],                            # capture the alarm list
            ['close_app'],                             # force-stop so the next action starts from a cold app
        ],
        "stop": [
            ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
            ['tap_content_desc', ALARM_TAB_DESC],      # switch to the Alarm tab
            ['screenshot'],                            # capture the alarm list after stopping a ringing alarm
            ['close_app'],                             # force-stop so the next action starts from a cold app
        ],
        "disable": [
            ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
            ['tap_content_desc', ALARM_TAB_DESC],      # switch to the Alarm tab
            ['screenshot'],                            # capture the alarm list (alarm toggled off)
            ['close_app'],                             # force-stop so the next action starts from a cold app
        ],
        "delete": [
            ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
            ['tap_content_desc', ALARM_TAB_DESC],      # switch to the Alarm tab
            SCROLL_ALARM_LIST,                         # swipe to refresh the page (intentional)
            ['screenshot'],                            # capture the alarm list (deleted alarm gone)
            ['close_app'],                             # force-stop so the next action starts from a cold app
        ],
    },
    "clock": {
        "launch": [
            # The agent already left the app open; just capture whatever is on screen.
            ['screenshot'],
        ],
    },
}
