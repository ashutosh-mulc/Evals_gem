"""Configuration for Thirdparty Spotify app."""

APP_KEY = "spotify"
GROUP = "thirdparty"
FEATURE = "spotify"

PACKAGE_NAME = "com.spotify.music"
ACTIVITY_NAME = "com.spotify.music/com.spotify.music.MainActivity"

# UI tree resource-id for mini player → full player tap (screen-size independent)
NOW_PLAYING_BAR_ID = "com.spotify.music:id/now_playing_bar_layout"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "play": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', NOW_PLAYING_BAR_ID], ['screenshot'], ['close_app']
    ],
    "playlistplay": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', NOW_PLAYING_BAR_ID], ['screenshot'], ['close_app']
    ],
    "podcastnext": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', NOW_PLAYING_BAR_ID], ['screenshot'], ['close_app']
    ],
    "create": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', NOW_PLAYING_BAR_ID], ['screenshot'], ['close_app']
    ],
    "modify": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', NOW_PLAYING_BAR_ID], ['screenshot'], ['close_app']
    ],
    "delete": [
        ['open_activity', ACTIVITY_NAME], ['tap_resource_id', NOW_PLAYING_BAR_ID], ['screenshot'], ['close_app']
    ],
}

