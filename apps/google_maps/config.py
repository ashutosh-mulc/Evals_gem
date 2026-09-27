"""Configuration for Google Maps app."""

APP_KEY = "googlemaps"
GROUP = "google"
FEATURE = "maps"

PACKAGE_NAME = "com.google.android.apps.maps"
ACTIVITY_NAME = "com.google.android.apps.maps/com.google.android.maps.MapsActivity"

ACTIONS = {
    "launch": [
        ['screenshot']
    ],
    "query": [
        ['back'], ['screenshot']
    ],
    "eta": [
        ['back'], ['screenshot']
    ],
    "startnavigate": [
        ['back'], ['screenshot']
    ],
    "stopnavigate": [
        ['back'], ['screenshot']
    ],
    "addstop": [
        ['back'], ['screenshot']
    ],
    "querynavigate": [
        ['back'], ['screenshot']
    ],
}

