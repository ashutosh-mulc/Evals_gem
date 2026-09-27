"""
Test group registry — declarative mapping of app function groups to question_type patterns.

Allows the automator to run targeted subsets of the dataset by app function
(volume, camera, music, notes, etc.) instead of the full dataset at once.

Usage in config:
    // Run only volume and camera tests
    "test_groups": ["volume", "camera"]

    // Or comma-separated string
    "test_groups": "volume,camera,music"

    // Run all (default — no filtering)
    "test_groups": "all"

    // Omit key entirely → run all (backward compatible)

When test_groups is set, the automator filters the dataset before evaluation,
keeping only entries whose question_type matches one of the selected groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass(frozen=True)
class TestGroup:
    """A functional test group (e.g., volume, camera, notes).

    Attributes:
        name:        Canonical group name (e.g., "volume", "camera").
        description: Human-readable description.
        patterns:    Substrings to match against question_type (case-insensitive).
        app_keys:    App keys involved (for state collector lookup).
    """
    name: str
    description: str
    patterns: list[str]
    app_keys: list[str]


# ── Registry ───────────────────────────────────────────────────────

TEST_GROUPS: dict[str, TestGroup] = {
    "volume": TestGroup(
        name="volume",
        description="Volume up/down/set/mute/unmute",
        patterns=["volume"],
        app_keys=["device"],
    ),
    "camera": TestGroup(
        name="camera",
        description="Camera photo/video capture",
        patterns=["camera"],
        app_keys=["device"],
    ),
    "music": TestGroup(
        name="music",
        description="Media control: play/pause/skip/replay/like/dislike/seek",
        patterns=["mediacontrol"],
        app_keys=["device_mediacontrol"],
    ),
    "notifications": TestGroup(
        name="notifications",
        description="Read/not-read/auto notifications",
        patterns=["notification"],
        app_keys=["notification"],
    ),
    "datetime": TestGroup(
        name="datetime",
        description="Time and date queries",
        patterns=["datetime_time", "datetime_date"],
        app_keys=["device"],
    ),
    "battery": TestGroup(
        name="battery",
        description="Battery level queries (glasses/companion)",
        patterns=["battery"],
        app_keys=["device"],
    ),
    "dnd": TestGroup(
        name="dnd",
        description="Do Not Disturb on/off",
        patterns=["dnd"],
        app_keys=["device"],
    ),
    "notes": TestGroup(
        name="notes",
        description="Samsung Notes create/read/edit/delete",
        patterns=["samsung_notes", "samsungnotes"],
        app_keys=["samsungnote"],
    ),
    "reminders": TestGroup(
        name="reminders",
        description="Samsung Reminders create/list/delete",
        patterns=["samsung_reminder", "samsungreminders"],
        app_keys=["samsungreminder"],
    ),
    "maps": TestGroup(
        name="maps",
        description="Google Maps navigation/search",
        patterns=["google_maps", "googlemaps"],
        app_keys=["googlemaps"],
    ),
    "calendar": TestGroup(
        name="calendar",
        description="Samsung/Google Calendar create/view",
        patterns=["samsung_calendar", "google_calendar"],
        app_keys=["samsungcalendar", "googlecalendar"],
    ),
    "clock": TestGroup(
        name="clock",
        description="Clock alarm/timer/stopwatch/launch",
        patterns=["clock"],
        app_keys=["clockalarm", "clocktimer", "clockstopwatch"],
    ),
    "messages": TestGroup(
        name="messages",
        description="Samsung Messages send/read",
        patterns=["samsung_message"],
        app_keys=["samsungmessage"],
    ),
    "spotify": TestGroup(
        name="spotify",
        description="Spotify play/search/control",
        patterns=["spotify"],
        app_keys=["spotify"],
    ),
    "whatsapp": TestGroup(
        name="whatsapp",
        description="WhatsApp send/read messages",
        patterns=["whatsapp"],
        app_keys=["whatsapp"],
    ),
    "translate": TestGroup(
        name="translate",
        description="Google Translate",
        patterns=["google_translate"],
        app_keys=["googletranslate"],
    ),
    "youtube_music": TestGroup(
        name="youtube_music",
        description="YouTube Music play/search",
        patterns=["youtube_music", "youtubemusic"],
        app_keys=["youtubemusic"],
    ),
    "voicerecorder": TestGroup(
        name="voicerecorder",
        description="Samsung Voice Recorder",
        patterns=["samsung_voicerecorder", "samsungvoicerecorder"],
        app_keys=["samsungvoicerecorder"],
    ),
    "call": TestGroup(
        name="call",
        description="Samsung Call dial/end",
        patterns=["samsung_call"],
        app_keys=["call"],
    ),
    "keep": TestGroup(
        name="keep",
        description="Google Keep notes",
        patterns=["google_keep"],
        app_keys=["googlekeep"],
    ),
    "mail": TestGroup(
        name="mail",
        description="Google Mail read/send",
        patterns=["google_mail"],
        app_keys=["googlemail"],
    ),
    "tasks": TestGroup(
        name="tasks",
        description="Google Tasks",
        patterns=["google_tasks"],
        app_keys=["googletasks"],
    ),
}


# ── Public API ─────────────────────────────────────────────────────

def list_groups() -> list[str]:
    """Return sorted list of all test group names."""
    return sorted(TEST_GROUPS.keys())


def get_group_for_question_type(question_type: str) -> Optional[str]:
    """Find which test group a question_type belongs to.

    Args:
        question_type: e.g., "online_device_volume_up"

    Returns:
        Group name (e.g., "volume") or None if no group matches.
    """
    qt_lower = (question_type or "").lower()
    if not qt_lower:
        return None

    for name, group in TEST_GROUPS.items():
        for pattern in group.patterns:
            if pattern in qt_lower:
                return name

    return None


def filter_dataset_by_group(
    dataset: list[dict],
    groups: Union[str, list[str]],
) -> list[dict]:
    """Filter a dataset to only entries matching the given test group(s).

    Args:
        dataset: List of dataset entries (each must have "question_type").
        groups:  A single group name (str) or list of group names.

    Returns:
        Filtered list of dataset entries.
    """
    if isinstance(groups, str):
        groups = [groups]

    # Validate group names
    for g in groups:
        if g not in TEST_GROUPS:
            return []

    # Collect all patterns from selected groups
    all_patterns: list[str] = []
    for g in groups:
        all_patterns.extend(TEST_GROUPS[g].patterns)

    filtered = []
    for entry in dataset:
        qt_lower = (entry.get("question_type", "")).lower()
        if any(p in qt_lower for p in all_patterns):
            filtered.append(entry)

    return filtered


def resolve_config_groups(config: dict) -> Optional[list[str]]:
    """Parse the "test_groups" field from a config dict.

    Accepts:
    - None or missing key → None (run all, no filtering)
    - "all" → None (run all, no filtering)
    - "" → None (run all, no filtering)
    - "volume" → ["volume"]
    - "volume,camera" → ["volume", "camera"]
    - ["volume", "camera"] → ["volume", "camera"]

    Args:
        config: The full config dict.

    Returns:
        List of validated group names, or None if no filtering.

    Raises:
        ValueError: If a group name is not in TEST_GROUPS.
    """
    raw = config.get("test_groups")
    if raw is None:
        return None

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw or raw.lower() == "all":
            return None
        groups = [g.strip() for g in raw.split(",")]
    elif isinstance(raw, list):
        groups = raw
    else:
        return None

    # Validate
    for g in groups:
        if g not in TEST_GROUPS:
            raise ValueError(
                f"Unknown test group '{g}'. "
                f"Available groups: {', '.join(list_groups())}"
            )

    return groups if groups else None
