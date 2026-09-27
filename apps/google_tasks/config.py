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
        ['screenshot']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', COMPLETED_HEADER_ID], ['swipe', 600, 1500, 600, 500], ['screenshot'], ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
}
