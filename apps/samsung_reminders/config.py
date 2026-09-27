"""Configuration for Samsung Reminders app."""

APP_KEY = "samsungreminder"
GROUP = "samsung"
FEATURE = "reminder"

PACKAGE_NAME = "com.samsung.android.app.reminder"
ACTIVITY_NAME = "com.samsung.android.app.reminder/.ui.list.main.MainListActivity"
OPEN_TRASH_ACTIVITY_INTENT="com.samsung.android.app.reminder.action.VIEW_TRASH"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['click', 400, 1200], ['screenshot'], ['close_app']
    ],
    "modify": [
        # e.g. "mark today's medication reminder as complete" — after the agent
        # acts, navigate into the "Completed" category tile so the screenshot
        # shows the reminder in its new (completed) state for VLM judge context.
        # No unique resource-id exists for this tile (all 6 category tiles share
        # resource-id "category_name"); content-desc is the only distinguishing
        # signal, and it includes a variable item count (e.g. "Completed, 1 item"),
        # hence prefix_match=True.
        ['open_activity', ACTIVITY_NAME], ['tap_content_desc', 'Completed', True], ['screenshot'], ['close_app']
    ],
    "delete": [
        # After the agent deletes a reminder, open the Trash bin via intent
        # so the screenshot shows the deleted reminder for VLM judge context.
        ['open_activity', ACTIVITY_NAME], ['open_intent_action', OPEN_TRASH_ACTIVITY_INTENT], ['screenshot'], ['close_app']
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
    "noread": [
        ['open_activity', ACTIVITY_NAME], ['screenshot'], ['close_app']
    ],
}

