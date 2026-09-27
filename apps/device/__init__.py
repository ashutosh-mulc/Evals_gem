"""Device app plugin — all device-level queries (volume, battery, DND, etc.)."""

from .config import APP_KEY, GROUP, FEATURES, PACKAGE_NAME, ACTIVITY_NAME, ACTIONS
from .state_collector import APP_KEYS, ACCESSOR, capture_pre, verify
from .judge import HANDLERS
from .consent import CONSENT_RULES

__all__ = [
    "APP_KEY", "GROUP", "FEATURES", "PACKAGE_NAME", "ACTIVITY_NAME", "ACTIONS",
    "APP_KEYS", "ACCESSOR", "capture_pre", "verify",
    "HANDLERS", "CONSENT_RULES",
]
