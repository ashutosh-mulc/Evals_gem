"""Configuration for Samsung Call app."""

APP_KEY = "call"
GROUP = "samsung"
FEATURE = "call"

PACKAGE_NAME = "com.samsung.android.dialer"
ACTIVITY_NAME = "com.samsung.android.dialer/.DialtactsActivity"

# The Phone app reopens on whichever tab was used last (Keypad, Recents or Contacts), so the
# actions that open it tap the Recents tab explicitly. The bottom tabs have exact content-descs.
RECENTS_TAB_DESC = "Recents"

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "send": [
        ['open_activity', ACTIVITY_NAME],          # open Phone (it may open on any tab)
        ['tap_content_desc', RECENTS_TAB_DESC],    # switch to the Recents tab (call log)
        ['screenshot'],                            # capture the call log with the latest call
    ],
    "visualsend": [
        # Screenshot only: captures whatever the agent left on screen.
        ['screenshot'],
    ],
    "videostart": [
        ['open_activity', ACTIVITY_NAME],          # open Phone (it may open on any tab)
        ['tap_content_desc', RECENTS_TAB_DESC],    # switch to the Recents tab (call log)
        ['screenshot'],                            # capture the call log with the latest call
    ],
    "disambiguation": [
        # Screenshot only: captures whatever the agent left on screen.
        ['screenshot'],
    ],
    "notsend": [
        # Screenshot only: captures whatever the agent left on screen.
        ['screenshot'],
    ],
}

