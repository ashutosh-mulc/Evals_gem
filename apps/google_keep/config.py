"""Configuration for Google Keep app."""

APP_KEY = "googlekeep"
GROUP = "google"
FEATURE = "keep"

PACKAGE_NAME = "com.google.android.keep"
ACTIVITY_NAME = "com.google.android.keep/.activities.BrowseActivity"

# No tap on a note: only a newly added note moves to the top of the grid. Editing an existing
# note keeps its position, so no fixed position or "first card" identifies the affected note.
# Every action therefore opens Keep, pulls to refresh, and captures the notes grid.

# Swipe DOWN (finger moves from 21% to 64% of screen height) = pull-to-refresh, so the grid
# reflects the agent's change. Ratios, not pixels, so it is resolution-independent.
REFRESH_SWIPE = ['swipe', 0.556, 0.214, 0.556, 0.641]

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],  # open Keep; a newly added note appears first in the grid
        REFRESH_SWIPE,                     # pull-to-refresh the grid
        ['screenshot'],                    # capture the notes grid
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "visualcreate": [
        ['open_activity', ACTIVITY_NAME],  # open Keep; a newly added note appears first in the grid
        REFRESH_SWIPE,                     # pull-to-refresh the grid
        ['screenshot'],                    # capture the notes grid
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],  # open Keep; an edited note keeps its grid position
        REFRESH_SWIPE,                     # pull-to-refresh the grid
        ['screenshot'],                    # capture the notes grid
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],  # open Keep; the deleted note should be gone from the grid
        REFRESH_SWIPE,                     # pull-to-refresh the grid
        ['screenshot'],                    # capture the notes grid
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
    "read": [
        ['open_activity', ACTIVITY_NAME],  # open Keep; the grid lists the notes to read
        REFRESH_SWIPE,                     # pull-to-refresh the grid
        ['screenshot'],                    # capture the notes grid
        ['close_app'],                     # force-stop so the next action starts from a cold app
    ],
}

