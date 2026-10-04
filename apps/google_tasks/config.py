"""Configuration for Google Tasks app."""

APP_KEY = "googletasks"
GROUP = "google"
FEATURE = "tasks"

PACKAGE_NAME = "com.google.android.apps.tasks"
ACTIVITY_NAME = "com.google.android.apps.tasks/.ui.TaskListsActivity"

# UI tree resource-id for the "Completed (N)" expandable header
COMPLETED_HEADER_ID = "com.google.android.apps.tasks:id/completed_header"

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],  # open Tasks; the new task shows in the default list
        ['screenshot'],                    # capture the task list
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],          # open Tasks
        ['tap_resource_id', COMPLETED_HEADER_ID],  # expand the "Completed (N)" section
        # Swipe DOWN (finger moves from 21% to 64% of screen height) = pull-to-refresh,
        # so the list reflects the agent's change. Ratios, not pixels, so it is resolution-independent.
        ['swipe', 0.556, 0.214, 0.556, 0.641],
        ['screenshot'],                            # capture open tasks + expanded Completed list
        ['close_app'],                             # force-stop so the next action starts from a cold app
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],  # open Tasks; the deleted task should be absent from the list
        ['screenshot'],                    # capture the task list
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
}
