"""Configuration for Samsung Clock Timer app."""

APP_KEY = "clocktimer"
GROUP = "samsung"
FEATURE = "clock_timer"

PACKAGE_NAME = "com.sec.android.app.clockpackage"
ACTIVITY_NAME = "com.sec.android.app.clockpackage/com.sec.android.app.clockpackage.ClockPackage"

# The bottom tab bar (Alarm, World clock, Stopwatch, Timer) has no resource-ids, but each
# tab has an exact content-desc, so tap_content_desc finds it on any screen size.
TIMER_TAB_DESC = "Timer"

# The two coordinate taps after the screenshot in create/modify/delete are unchanged and their
# purpose is not documented. They stay as screen ratios: the running-timer screen animates
# continuously, so `uiautomator dump` fails there ("could not get idle state") and no
# id/text/content-desc tap can work.

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the timer the agent created
        ['click', 0.227, 0.711],                   # unchanged coordinate tap (see note above)
        ['click_stop_notification', 0.370, 0.159], # unchanged: waits 15 s, then taps this spot (see note above)
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the timer screen
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the modified timer
        ['click', 0.227, 0.711],                   # unchanged coordinate tap (see note above)
        ['click_stop_notification', 0.370, 0.159], # unchanged: waits 15 s, then taps this spot (see note above)
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "pause": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the paused timer
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "restart": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the restarted timer
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "stop": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the stopped timer
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],          # open Clock (it may open on any tab)
        ['tap_content_desc', TIMER_TAB_DESC],      # switch to the Timer tab
        ['screenshot'],                            # capture the timer screen (deleted timer gone)
        ['click', 0.227, 0.711],                   # unchanged coordinate tap (see note above)
        ['click_stop_notification', 0.370, 0.159], # unchanged: waits 15 s, then taps this spot (see note above)
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
}

