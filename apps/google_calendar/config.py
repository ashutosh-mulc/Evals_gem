"""Configuration for Google Calendar app."""

APP_KEY = "googlecalendar"
GROUP = "google"
FEATURE = "calendar"

PACKAGE_NAME = "com.google.android.calendar"
ACTIVITY_NAME = "com.google.android.calendar/com.android.calendar.AllInOneActivity"


# Calendar reopens in whichever view was used last (Month, Day, ...), so create/modify/delete
# force Week view through the menu. Neither element has a unique resource-id the code can rely
# on, but both have an exact content-desc.
MENU_BUTTON_DESC = "Show Calendar List and Settings drawer"   # top-left three-line button
WEEK_VIEW_DESC = "Week view"                                  # entry in that drawer

ACTIONS = {
    "read": [
        ['open_activity', ACTIVITY_NAME],  # open Calendar (in whichever view it was last left)
        ['screenshot'],                    # capture the calendar
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],              # open Calendar (in whichever view it was last left)
        ['tap_content_desc', MENU_BUTTON_DESC],        # open the top-left menu drawer
        ['tap_content_desc', WEEK_VIEW_DESC],          # switch to Week view
        ['screenshot'],                                # capture the week with the new event
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],              # open Calendar (in whichever view it was last left)
        ['tap_content_desc', MENU_BUTTON_DESC],        # open the top-left menu drawer
        ['tap_content_desc', WEEK_VIEW_DESC],          # switch to Week view
        ['screenshot'],                                # capture the week with the modified event
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],              # open Calendar (in whichever view it was last left)
        ['tap_content_desc', MENU_BUTTON_DESC],        # open the top-left menu drawer
        ['tap_content_desc', WEEK_VIEW_DESC],          # switch to Week view
        ['screenshot'],                                # capture the week (deleted event gone)
        ['close_app'],                                 # force-stop so the next action starts from a cold app
    ],
}

