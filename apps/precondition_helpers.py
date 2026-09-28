"""
Shared helpers for precondition modules.

These utilities parse gt_answer strings to extract entity names (note titles,
reminder titles, etc.) and provide common report-building functions.
"""

from __future__ import annotations

import re
from typing import Optional


def extract_title_from_gt(gt_answer: str) -> Optional[str]:
    """Extract a title from a gt_answer string.

    Handles patterns like:
        "A note titled 'Shopping List' with content 'milk and eggs'"
        "A reminder titled 'Buy groceries'"
        "An event titled 'Team Meeting'"
        "An alarm at 07:00"

    Returns:
        The extracted title string, or None if no title found.
    """
    if not gt_answer:
        return None

    # Try quoted title: titled 'X' or titled "X"
    match = re.search(r"titled\s+['\"](.+?)['\"]", gt_answer, re.IGNORECASE)
    if match:
        return match.group(1)

    # Try "titled X" without quotes (up to next comma/period/with)
    match = re.search(r"titled\s+(.+?)(?:\s+with\s|[,\.]|$)", gt_answer, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


def extract_description_from_gt(gt_answer: str) -> str:
    """Extract a description/content field from a gt_answer string, for building
    the item a precondition creates (distinct from apps.helpers.extract_content_from_gt,
    which extracts content for verify()-time comparison against actual state).

    Handles: "with content 'milk and eggs'" or "with description '...'"
    """
    if not gt_answer:
        return ""

    match = re.search(r"with content\s+['\"](.+?)['\"]", gt_answer, re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"with description\s+['\"](.+?)['\"]", gt_answer, re.IGNORECASE)
    if match:
        return match.group(1)

    return ""


def extract_time_from_gt(gt_answer: str) -> Optional[str]:
    """Extract a time string from a gt_answer.

    Handles: "An alarm at 07:00", "An alarm at 7 AM", "A timer set for 5 minutes"
    """
    if not gt_answer:
        return None

    # Try "at HH:MM"
    match = re.search(r"at\s+(\d{1,2}:\d{2})", gt_answer, re.IGNORECASE)
    if match:
        return match.group(1)

    # Try "at N AM/PM"
    match = re.search(r"at\s+(\d{1,2}\s*[APap][Mm])", gt_answer, re.IGNORECASE)
    if match:
        time_str = match.group(1).upper().replace(" ", "")
        # Convert "7AM" → "07:00", "7PM" → "19:00"
        hour = int(re.match(r"(\d+)", time_str).group(1))
        if "PM" in time_str and hour != 12:
            hour += 12
        elif "AM" in time_str and hour == 12:
            hour = 0
        return f"{hour:02d}:00"

    # Try "for N minutes" (timer)
    match = re.search(r"for\s+(\d+)\s*minutes?", gt_answer, re.IGNORECASE)
    if match:
        return f"{match.group(1)} minutes"

    return None


def parse_duration_to_seconds(duration_str: str) -> int:
    """Parse a duration string like "5 minutes" into seconds.

    Handles: "N minutes", "N hours", "N seconds", "HH:MM" (treats as minutes).

    Returns:
        Duration in seconds. Defaults to 300 (5 min) if unparseable.
    """
    if not duration_str:
        return 300

    # "N minutes"
    match = re.search(r"(\d+)\s*minutes?", duration_str, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 60

    # "N hours"
    match = re.search(r"(\d+)\s*hours?", duration_str, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 3600

    # "N seconds"
    match = re.search(r"(\d+)\s*seconds?", duration_str, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # "HH:MM" — treat as minutes total
    match = re.search(r"(\d{1,2}):(\d{2})", duration_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return hours * 3600 + minutes * 60

    # Bare number — assume seconds
    match = re.search(r"(\d+)", duration_str)
    if match:
        return int(match.group(1))

    return 300



def extract_time_from_question(question: str, action: str) -> Optional[str]:
    """Extract the relevant alarm time from the question text.

    For 'modify': extracts the FROM time (e.g. "from 4PM to 6PM" → "16:00").
    For 'delete'/'disable': extracts the mentioned time (e.g. "6PM" → "18:00").
    For 'stop'/'read': returns None (any alarm is fine).

    Handles patterns:
        - "4PM", "4 PM", "6PM", "6 PM"
        - "4:30 PM", "4:30PM"
        - "16:00", "07:00"
    """
    if not question:
        return None

    def _parse_ampm(time_str: str) -> Optional[str]:
        """Convert '4PM' / '4 PM' / '4:30 PM' → 'HH:MM' 24h."""
        time_str = time_str.upper().replace(" ", "")
        m = re.match(r"(\d{1,2})(?::(\d{2}))?([AP]M)", time_str)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if "PM" in m.group(3) and hour != 12:
            hour += 12
        elif "AM" in m.group(3) and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    def _find_first_time(text: str) -> Optional[str]:
        """Find the first time mention in text."""
        # Try HH:MM AM/PM (e.g. "4:30 PM")
        m = re.search(r"(\d{1,2}:\d{2}\s*[APap][Mm])", text)
        if m:
            return _parse_ampm(m.group(1))
        # Try N AM/PM (e.g. "4PM", "4 PM")
        m = re.search(r"(\d{1,2}\s*[APap][Mm])", text)
        if m:
            return _parse_ampm(m.group(1))
        # Try 24h HH:MM (e.g. "16:00")
        m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
        if m:
            return m.group(1)
        return None

    if action == "modify":
        # Extract the FROM time: "from 4PM to 6PM" → "16:00"
        m = re.search(r"from\s+(.+?)\s+to\s", question, re.IGNORECASE)
        if m:
            return _find_first_time(m.group(1))
        # Fallback: first time in question
        return _find_first_time(question)

    if action in ("delete", "disable"):
        # Extract the time mentioned (e.g. "the 6PM alarm" → "18:00")
        return _find_first_time(question)

    # stop, read: any alarm is fine
    return None


def extract_duration_from_question(question: str, action: str) -> Optional[str]:
    """Extract the relevant timer duration from the question text.

    For 'modify': extracts the FROM duration (e.g. "from 10 minutes to 20 minutes" → "10 minutes").
    For other actions: returns None (any timer is fine).

    Handles patterns:
        - "N minutes", "N mins", "N hours", "N seconds"
    """
    if not question:
        return None

    def _find_first_duration(text: str) -> Optional[str]:
        m = re.search(r"(\d+)\s*(?:minutes?|mins?)", text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} minutes"
        m = re.search(r"(\d+)\s*hours?", text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} hours"
        m = re.search(r"(\d+)\s*seconds?", text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} seconds"
        return None

    if action == "modify":
        # Extract the FROM duration: "from 10 minutes to 20 minutes" → "10 minutes"
        m = re.search(r"from\s+(.+?)\s+to\s", question, re.IGNORECASE)
        if m:
            return _find_first_duration(m.group(1))
        return _find_first_duration(question)

    return None

def clear_clock_state(statecollector_dm):
    """Clear all alarms, timers, reset stopwatch, and force-stop Clock app.

    Used by clock preconditions for launch actions to ensure a clean state
    before a new evaluation sequence begins.

    Args:
        statecollector_dm: The XRClaw DeviceManager instance (has .alarms, .timers,
        and .stopwatch).

    Returns:
        Dict with counts: {"alarms": int, "timers": int, "stopwatch_reset": bool}
    """
    cleared = {"alarms": 0, "timers": 0, "stopwatch_reset": False}
    try:
        alarms = statecollector_dm.alarms.find_alarms()
        for alarm in alarms:
            statecollector_dm.alarms.delete_alarm(alarm.id)
        cleared["alarms"] = len(alarms)
    except Exception:
        pass
    try:
        timers = statecollector_dm.timers.find_timers()
        for timer in timers:
            statecollector_dm.timers.delete_timer(timer.id)
        cleared["timers"] = len(timers)
    except Exception:
        pass
    try:
        statecollector_dm.stopwatch.reset_stopwatch()
        cleared["stopwatch_reset"] = True
    except Exception:
        pass
    return cleared


def report(passed=True, set_items=None, checked=None, failed=None, skipped=None):

    """Build a standard precondition report dict."""
    return {
        "passed": passed,
        "set": set_items or [],
        "checked": checked or [],
        "failed": failed or [],
        "skipped": skipped,
    }
