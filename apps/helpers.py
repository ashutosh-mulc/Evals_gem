"""
Shared helpers for app state collectors.

These functions were extracted from XRClawStateCollector's instance methods
so that per-app verifier modules can use them without inheriting from the
collector class. Each function is a standalone utility — no ``self``.
"""

from __future__ import annotations

import re
from typing import Dict, Optional


# ── Keyword / content extraction ──────────────────────────────────

def extract_keyword(text: str) -> str:
    """
    Extract a meaningful search phrase from the ground-truth answer.

    Tries to find quoted text first, then "Note Title: X" / "Title: X" patterns,
    then falls back to a short SEQUENCE of significant words (not just the first one).
    A single common word (e.g. "books") is an easy accidental substring match
    against an unrelated pre-existing item; requiring several consecutive words
    to match makes a coincidental hit far less likely.
    """
    # Look for text in single or double quotes
    quoted = re.search(r'["\']([^"\']+)["\']', text)
    if quoted:
        return quoted.group(1).lower().strip()

    # Look for "Note Title: X" or "Title: X" pattern (common in gt_answer)
    # Capture the title text up to a comma or end of string
    title_pattern = re.search(r'(?:note\s+)?title:\s*([^,]+)', text, re.IGNORECASE)
    if title_pattern:
        return title_pattern.group(1).lower().strip()

    # Look for time patterns (e.g., "4pm", "7:30", "10 seconds")
    # This helps alarm and timer queries where the key info is a time value
    time_pattern = re.search(r'\b(\d{1,2}[:\s]?\d{2}\s*[ap]m?)\b', text, re.IGNORECASE)
    if time_pattern:
        return time_pattern.group(1).lower().strip()
    time_pattern2 = re.search(r'\b(\d{1,2}\s*[ap]m)\b', text, re.IGNORECASE)
    if time_pattern2:
        return time_pattern2.group(1).lower().strip()
    duration_pattern = re.search(r'\b(\d+\s*seconds?)\b', text, re.IGNORECASE)
    if duration_pattern:
        return duration_pattern.group(1).lower().strip()

    # Fall back to a short phrase of significant words (skip common words)
    stop_words = {
        "a", "an", "the", "create", "modify", "delete", "note", "notes", "reminder",
        "event", "calendar", "titled", "named", "called", "with", "content",
        "containing", "set", "add", "remove", "is", "to", "for", "and",
        "title", "successfully", "created", "image", "may", "show", "running",
        "time", "buttons", "delete", "resume", "options", "alarm", "clock",
        "timer", "seconds", "tasks", "one", "second", "third", "items",
        "about", "containing", "expected", "date", "calender", "successfully",
        "succesfully", "shows", "recurrence", "settings", "enabled", "disabled",
        "state", "am", "pm", "succesfully",
    }
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    significant = [w for w in words if w not in stop_words]
    if len(significant) >= 2:
        return " ".join(significant[:4])
    if significant:
        return significant[0]

    return text.lower().strip()[:30]


def extract_content_from_gt(gt_answer: str) -> str:
    """
    Extract the 'content' portion from a ground-truth answer string.

    gt_answer typically looks like:
      "A note titled 'Shopping List' with content 'milk and eggs'"
      "Add a banana to your shopping list"

    We try to extract quoted content first, then fall back to text after
    'content' keyword, then to the whole string minus the title.
    """
    # Try to find content in quotes after "content" keyword
    content_match = re.search(r"content\s*['\"]([^'\"]+)['\"]", gt_answer, re.IGNORECASE)
    if content_match:
        return content_match.group(1).lower().strip()

    # Try to find any quoted text (second quote pair if title is first)
    quotes = re.findall(r"['\"]([^'\"]+)['\"]", gt_answer)
    if len(quotes) >= 2:
        return quotes[1].lower().strip()

    # Fall back: text after "with" or "add" keyword
    after_with = re.search(r'(?:with|add|containing)\s+(.+)', gt_answer, re.IGNORECASE)
    if after_with:
        return after_with.group(1).lower().strip()

    return ""


def content_overlaps(gt_answer: str, actual_content: str) -> bool:
    """
    Check if the actual content overlaps with the expected answer.
    Uses simple word overlap heuristic.

    XRClaw may append trailing garbage bytes to content — strip non-printable
    characters before comparison.
    """
    if not actual_content:
        return False

    # Strip non-printable / non-ASCII characters that XRClaw may append
    # (e.g. Unicode replacement characters U+FFFD appear as trailing garbage)
    actual_content = actual_content.encode("ascii", errors="ignore").decode("ascii")
    actual_content = "".join(
        c for c in actual_content if c.isprintable() or c in "\n\r\t"
    )

    # Strip punctuation so quoted words match unquoted words
    # (e.g. "'milk'" in gt_answer matches "milk" in actual_content)
    import string
    strip_chars = string.punctuation + "'\""
    gt_words = set(gt_answer.lower().translate(str.maketrans("", "", strip_chars)).split())
    actual_words = set(actual_content.lower().translate(str.maketrans("", "", strip_chars)).split())
    overlap = gt_words & actual_words
    # At least 2 significant words should overlap (excluding stop words)
    stop_words = {"a", "an", "the", "with", "and", "to", "for", "is", "titled", "content"}
    significant_overlap = overlap - stop_words
    return len(significant_overlap) >= 2


# ── Pre-state diffing ─────────────────────────────────────────────

def pre_items_by_id(pre_state: dict, list_key: str) -> Optional[Dict]:
    """
    Return {id: item_dict} from a pre-query snapshot (see capture_pre_state()),
    or None if no snapshot was captured — the latter tells callers to fall back
    to the weaker existence-only check instead of pre/post diffing.
    """
    if not pre_state:
        return None
    items = pre_state.get(list_key)
    if items is None:
        return None
    return {item.get("id"): item for item in items if item.get("id")}


def new_or_changed(items, pre_by_id: dict, compare_fields) -> list:
    """
    Return the subset of `items` (XRClaw dataclass instances exposing
    .to_dict()) that are either absent from pre_by_id (created since the
    snapshot) or whose tracked fields differ from the pre-query version
    (modified in place). Used so create/modify verification only counts
    items the agent actually touched during this query, not a stale match
    left over from an earlier run of the same query.
    """
    result = []
    for item in items:
        d = item.to_dict()
        prev = pre_by_id.get(d.get("id"))
        if prev is None or any(prev.get(f) != d.get(f) for f in compare_fields):
            result.append(item)
    return result


# ── Holiday filtering (for calendar) ──────────────────────────────

def is_holiday_event(event) -> bool:
    """Check if an event is a public holiday/observance from Google Calendar."""
    title = (getattr(event, "title", "") or "").lower()
    # Google Calendar holiday events typically have titles like "Independence Day"
    # and are all-day events from the "en.usa#holiday@group.v.calendar.google.com" calendar
    holiday_keywords = [
        "holiday", "observance", "day off", "independence day",
        "memorial day", "labor day", "thanksgiving", "christmas",
        "new year", "martin luther", "presidents day", "veterans day",
        "juneteenth", "columbus day", "indigenous peoples",
    ]
    return any(kw in title for kw in holiday_keywords)


def filter_holidays(events) -> list:
    """Filter out public holiday/observance events from Google Calendar."""
    return [e for e in events if not is_holiday_event(e)]


# ── Result builders ───────────────────────────────────────────────

# `method` values meaning the collector actually verified the app state
VERIFIED_METHODS = {"xrclaw", "xrclaw_read"}


def result(app_name, verified, rating, analysis, actual_state, expected) -> dict:
    """Build a successful state collector verification result."""
    return {
        "method": "xrclaw",
        "app_name": app_name,
        "verified": verified,
        "rating": rating,
        "analysis": analysis,
        "actual_state": actual_state,
        "expected": expected,
    }


def unsupported_result(app_name, expected) -> dict:
    """Build a result for unsupported apps (caller should fall back to LLM)."""
    return {
        "method": "xrclaw_unsupported",
        "app_name": app_name,
        "verified": False,
        "rating": 0,
        "analysis": f"App '{app_name}' is not supported by state collector verification.",
        "actual_state": {},
        "expected": expected,
    }


def error_result(app_name, expected, error_msg) -> dict:
    """Build an error result (caller should fall back to LLM)."""
    return {
        "method": "xrclaw_error",
        "app_name": app_name,
        "verified": False,
        "rating": 0,
        "analysis": f"State collector verification error: {error_msg}",
        "actual_state": {},
        "expected": expected,
    }


def xrclaw_unavailable_result(app_name, analysis, actual_state, expected) -> dict:
    """Build a result for queries that XRClaw cannot verify (fall back to VLM with gt_answer)."""
    return {
        "method": "xrclaw_unavailable",
        "app_name": app_name,
        "verified": False,
        "rating": 0,
        "analysis": analysis,
        "actual_state": actual_state,
        "expected": expected,
    }


# ── Foreground detection ──────────────────────────────────────────

def get_foreground_package_with_fallback(dm) -> dict:
    """Get foreground app info via ADB dumpsys, returning an enriched dict.

    Queries 4 dumpsys fields that exist on the target device (Android 14+):
      - topResumedActivity (dumpsys activity activities) — activity-level
      - ResumedActivity    (dumpsys activity activities) — activity-level
      - mCurrentFocus      (dumpsys window)              — window-level
      - mFocusedApp        (dumpsys window)              — window-level

    Activity-level fields report which app's activity is in the resumed
    state.  Window-level fields report which window has input focus —
    this can be a system UI overlay (notification panel, volume slider)
    rather than the app activity, so system UI is filtered from the
    resolved value but kept in the dict for diagnostics.

    Returns a dict with keys:
      - topResumedActivity: package name or None
      - ResumedActivity: package name or None
      - mCurrentFocus: package name or None (system UI filtered)
      - mFocusedApp: package name or None (system UI filtered)
      - resolved: best-effort single package name (priority: activity-level
        over window-level), or None if all fields are empty
      - source: which field was used for 'resolved', or None
    """
    _SYSTEM_UI_PACKAGES = {"com.android.systemui"}

    def _extract_pkg(output: str, exclude_system_ui: bool = False) -> Optional[str]:
        """Extract the last non-null package from dumpsys output.

        Uses regex to find ``pkg/`` patterns (e.g. ``com.samsung.android.calendar/``).
        Takes the last match because dumpsys can list multiple entries
        (e.g. mFocusedApp lists all focused app tokens); the last non-null
        entry is the most recent / currently active one.
        """
        last_pkg = None
        for match in re.finditer(r"(\w+(?:\.\w+)+)/", output):
            pkg = match.group(1)
            if exclude_system_ui and pkg in _SYSTEM_UI_PACKAGES:
                continue
            last_pkg = pkg
        return last_pkg

    info = {
        "topResumedActivity": None,
        "ResumedActivity": None,
        "mCurrentFocus": None,
        "mFocusedApp": None,
        "resolved": None,
        "source": None,
    }

    # Field 1: topResumedActivity (dumpsys activity activities)
    try:
        output = dm._adb.shell(
            "dumpsys activity activities | grep topResumedActivity", timeout=10
        )
        pkg = _extract_pkg(output)
        if pkg:
            info["topResumedActivity"] = pkg
    except Exception:
        pass

    # Field 2: ResumedActivity (dumpsys activity activities)
    # grep ResumedActivity also matches topResumedActivity as a substring,
    # so filter for lines starting with "ResumedActivity:" only.
    try:
        output = dm._adb.shell(
            "dumpsys activity activities | grep ResumedActivity", timeout=10
        )
        for line in output.split("\n"):
            if line.strip().startswith("ResumedActivity:"):
                pkg = _extract_pkg(line)
                if pkg:
                    info["ResumedActivity"] = pkg
                    break
    except Exception:
        pass

    # Field 3: mCurrentFocus (dumpsys window)
    # Can return "null" — _extract_pkg naturally skips null tokens since
    # they don't contain "/" and ".".
    try:
        output = dm._adb.shell(
            "dumpsys window | grep mCurrentFocus", timeout=10
        )
        pkg = _extract_pkg(output, exclude_system_ui=True)
        if pkg:
            info["mCurrentFocus"] = pkg
    except Exception:
        pass

    # Field 4: mFocusedApp (dumpsys window)
    # Can return "null" and multiple entries — _extract_pkg takes the last
    # non-null, non-system-UI package.
    try:
        output = dm._adb.shell(
            "dumpsys window | grep mFocusedApp", timeout=10
        )
        pkg = _extract_pkg(output, exclude_system_ui=True)
        if pkg:
            info["mFocusedApp"] = pkg
    except Exception:
        pass

    # Compute resolved: prioritize activity-level over window-level
    for field, pkg in [
        ("topResumedActivity", info["topResumedActivity"]),
        ("ResumedActivity", info["ResumedActivity"]),
        ("mFocusedApp", info["mFocusedApp"]),
        ("mCurrentFocus", info["mCurrentFocus"]),
    ]:
        if pkg:
            info["resolved"] = pkg
            info["source"] = field
            break

    return info

