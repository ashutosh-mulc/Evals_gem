"""Configuration for Google Youtube Music app."""

APP_KEY = "youtubemusic"
GROUP = "google"
FEATURE = "youtubemusic"

PACKAGE_NAME = "com.google.android.apps.youtube.music"
ACTIVITY_NAME = "com.google.android.apps.youtube.music/com.google.android.apps.youtube.music.activities.MusicActivity"

# UI tree resource-id for mini player → full player tap (screen-size independent)
MINI_PLAYER_RESOURCE_ID = "com.google.android.apps.youtube.music:id/mini_player_metadata"

# Bottom navigation tabs are identified by text (all share resource-id "text1")
LIBRARY_TAB_TEXT = "Library"

# A tab tap right after a cold start is ignored while the Home feed is still loading (verified on
# SM-M346B: the tap lands but the screen stays on Home), so wait before tapping the Library tab.
WAIT_FOR_HOME_FEED = ['wait', 4]

ACTIONS = {
    "launch": [
        # The agent already left the app open; just capture whatever is on screen.
        ['screenshot'],
    ],
    "play": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        ['tap_resource_id', MINI_PLAYER_RESOURCE_ID],        # expand the mini player to the full Now Playing screen
        ['screenshot'],                                      # capture the Now Playing screen
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "playlistcreate": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        WAIT_FOR_HOME_FEED,                                  # let the Home feed finish loading
        ['tap_text', LIBRARY_TAB_TEXT],                      # open the Library tab, where playlists are listed
        ['screenshot'],                                      # capture the Library tab
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "playlistplay": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        WAIT_FOR_HOME_FEED,                                  # let the Home feed finish loading
        ['tap_text', LIBRARY_TAB_TEXT],                      # open the Library tab, where playlists are listed
        ['screenshot'],                                      # capture the Library tab
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "podcastnext": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        ['tap_resource_id', MINI_PLAYER_RESOURCE_ID],        # expand the mini player to the full Now Playing screen
        ['screenshot'],                                      # capture the Now Playing screen
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        ['tap_resource_id', MINI_PLAYER_RESOURCE_ID],        # expand the mini player to the full Now Playing screen
        ['screenshot'],                                      # capture the Now Playing screen
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "visualcreate": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        ['tap_resource_id', MINI_PLAYER_RESOURCE_ID],        # expand the mini player to the full Now Playing screen
        ['screenshot'],                                      # capture the Now Playing screen
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "playlistvisualcreate": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        WAIT_FOR_HOME_FEED,                                  # let the Home feed finish loading
        ['tap_text', LIBRARY_TAB_TEXT],                      # open the Library tab, where playlists are listed
        ['screenshot'],                                      # capture the Library tab
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        ['tap_resource_id', MINI_PLAYER_RESOURCE_ID],        # expand the mini player to the full Now Playing screen
        ['screenshot'],                                      # capture the Now Playing screen
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME],                    # open YouTube Music
        ['tap_resource_id', MINI_PLAYER_RESOURCE_ID],        # expand the mini player to the full Now Playing screen
        ['screenshot'],                                      # capture the Now Playing screen
        ['close_app'],                                       # force-stop so the next action starts from a cold app
    ],
}


