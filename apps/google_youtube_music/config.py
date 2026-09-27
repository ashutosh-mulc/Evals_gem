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

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "play": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', MINI_PLAYER_RESOURCE_ID], ['screenshot'], ['close_app']
    ],
    "playlistcreate": [
        ['open_activity', ACTIVITY_NAME], ['tap_text', LIBRARY_TAB_TEXT], ['screenshot'], ['close_app']
    ],
    "playlistplay": [
        ['open_activity', ACTIVITY_NAME], ['tap_text', LIBRARY_TAB_TEXT], ['screenshot'], ['close_app']
    ],
    "podcastnext": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', MINI_PLAYER_RESOURCE_ID], ['screenshot'], ['close_app']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', MINI_PLAYER_RESOURCE_ID], ['screenshot'], ['close_app']
    ],
    "visualcreate": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', MINI_PLAYER_RESOURCE_ID], ['screenshot'], ['close_app']
    ],
    "playlistvisualcreate": [
        ['open_activity', ACTIVITY_NAME], ['tap_text', LIBRARY_TAB_TEXT], ['screenshot'], ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', MINI_PLAYER_RESOURCE_ID], ['screenshot'], ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', MINI_PLAYER_RESOURCE_ID], ['screenshot'], ['close_app']
    ],
}


