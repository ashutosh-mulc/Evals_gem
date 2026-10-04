"""Configuration for Samsung Reminders app."""

APP_KEY = "samsungreminder"
GROUP = "samsung"
FEATURE = "reminder"

PACKAGE_NAME = "com.samsung.android.app.reminder"
ACTIVITY_NAME = "com.samsung.android.app.reminder/.ui.list.main.MainListActivity"
OPEN_TRASH_ACTIVITY_INTENT="com.samsung.android.app.reminder.action.VIEW_TRASH"

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],  # open Reminder; the list shows each reminder's title and date/time
        ['screenshot'],                    # capture the list (no positional tap needed)
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "modify": [
        # e.g. "mark today's medication reminder as complete": open the "Completed"
        # category so the screenshot shows the reminder in its new state.
        ['open_activity', ACTIVITY_NAME],  # open Reminder (main list with the 6 category tiles)
        # All 6 tiles share resource-id "category_name" and the tile has no content-desc
        # on SM-M346B, so match its visible label text.
        ['tap_text', 'Completed'],         # open the Completed list
        ['screenshot'],                    # capture the Completed list (newest completion on top)
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "delete": [
        # After the agent deletes a reminder, show the Recycle bin.
        # The VIEW_TRASH intent is only honoured on a cold start (verified on SM-M346B: it is
        # ignored while the app is in the foreground or alive in the background), so
        # force-stop first instead of open_activity.
        ['close_app'],                                           # force-stop so the intent cold-starts the app
        ['open_intent_action', OPEN_TRASH_ACTIVITY_INTENT],      # open the Recycle bin directly
        ['screenshot'],                                          # capture the Recycle bin
        ['close_app'],                                           # force-stop so the next action starts from a cold app
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME],  # open Reminder; the list shows the reminders to read
        ['screenshot'],                    # capture the list
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "noread": [
        ['open_activity', ACTIVITY_NAME],  # open Reminder; the list shows which reminders exist (or don't)
        ['screenshot'],                    # capture the list
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
}

