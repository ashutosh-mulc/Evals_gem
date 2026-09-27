"""
State collector for Samsung Clock Alarm.

Extracted from XRClawStateCollector._collect_alarm_state() and the
alarms branch of capture_pre_state().

Supports modes: launch, create, modify, read, delete, stop, disable.

The gt_answer is expected to contain the alarm time (e.g., "7:30") and/or
a label (e.g., "Morning Alarm"). The verification extracts a time pattern
and/or keyword from the gt_answer and matches against actual alarms.
"""

from __future__ import annotations

import re

from ..helpers import (
    extract_keyword,
    pre_items_by_id,
    new_or_changed,
    result,
    verify_launch,
    PRE_FLAG,
)

APP_KEYS = ("clockalarm",)
PACKAGE_NAME = "com.sec.android.app.clockpackage"


def capture_pre(dm) -> dict:
    """Snapshot current alarms state before the agent acts."""
    alarms = dm.alarms.find_alarms()
    return {"alarms": [a.to_dict() for a in alarms], "count": len(alarms)}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Samsung Clock Alarm state after the agent has acted."""
    app_name = app_key

    # ── Launch mode: verify Clock app is in foreground ──
    if mode == "launch":
        return verify_launch(dm, app_name, PACKAGE_NAME, "Clock", gt_answer)

    alarms = dm.alarms.find_alarms()
    actual_state = {
        "alarms": [a.to_dict() for a in alarms],
        "count": len(alarms),
    }

    pre_by_id = pre_items_by_id(pre_state, "alarms")
    pre_flag = "" if pre_by_id is not None else PRE_FLAG


    # Extract expected alarm time from gt_answer (e.g., "7:30", "07:30", "730")
    expected_time = None
    time_match = re.search(r'\b(\d{1,2}):(\d{2})\b', gt_answer)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        expected_time = f"{hour:02d}:{minute:02d}"
    else:
        # Try "7 30" or "730" format
        time_match = re.search(r'\b(\d{1,2})\s*(\d{2})\b', gt_answer)
        if time_match:
            hour, minute = int(time_match.group(1)), int(time_match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                expected_time = f"{hour:02d}:{minute:02d}"

    # Also extract a label keyword (quoted text or significant word)
    search_term = extract_keyword(gt_answer)

    def _matches(a):
        if expected_time and a.time == expected_time:
            return True
        return bool(search_term) and search_term in a.label.lower()

    # ── Read mode: return alarm list for LLM judge comparison ──
    if mode == "read":
        verified = True
        rating = 5
        analysis = (
            f"Read verification: {len(alarms)} alarms on device: "
            f"{[(a.time, a.label, a.enabled) for a in alarms]}. "
            f"AI's spoken response should be compared against this state by the LLM judge."
        )
        res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
        res["method"] = "xrclaw_read"
        return res

    # ── Stop mode: stop a ringing alarm (alarm still exists, just dismissed) ──
    if mode == "stop":
        # Stopping a ringing alarm doesn't delete it — it just dismisses the alert.
        matching = [a for a in alarms if _matches(a)]
        if matching:
            alarm = matching[0]
            verified = True
            rating = 5
            analysis = (
                f"Alarm stop verification: alarm time='{alarm.time}', label='{alarm.label}' "
                f"still exists (not deleted). Stopping a ringing alarm dismisses the alert only."
            )
        else:
            verified = False
            rating = 0
            analysis = (
                f"Alarm stop verification: no alarm matching time='{expected_time}' or "
                f"label='{search_term}' found. {len(alarms)} alarms exist."
            )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Disable mode: alarm should now be disabled (enabled=False) ──
    if mode == "disable":
        matching = [a for a in alarms if _matches(a)]
        if matching:
            alarm = matching[0]
            if pre_by_id is not None:
                # With pre-state: verify enabled changed True → False
                pre_alarm = pre_by_id.get(alarm.id)
                pre_enabled = pre_alarm.get("enabled", True) if pre_alarm else None
                verified = not alarm.enabled and pre_enabled
                rating = 5 if verified else 0
                analysis = (
                    f"Alarm disable verification: alarm time='{alarm.time}', label='{alarm.label}', "
                    f"enabled={alarm.enabled} (was enabled={pre_enabled} pre-query)."
                    f"{'' if verified else ' Alarm was already disabled or still enabled.'}"
                )
            else:
                verified = not alarm.enabled
                rating = 5 if verified else 0
                analysis = (
                    f"Alarm disable verification: alarm time='{alarm.time}', label='{alarm.label}', "
                    f"enabled={alarm.enabled}.{pre_flag}"
                )
        else:
            verified = False
            rating = 0
            analysis = (
                f"Alarm disable verification: no alarm matching time='{expected_time}' or "
                f"label='{search_term}' found. {len(alarms)} alarms exist."
            )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    if mode == "delete":
        # For delete mode, verify the alarm no longer exists
        matching_post = [a for a in alarms if _matches(a)]
        if pre_by_id is None:
            verified = len(matching_post) == 0
            rating = 5 if verified else 0
            analysis = (
                f"Delete verification: {len(alarms)} alarms remain. "
                f"Searched for time='{expected_time}' or label='{search_term}' — "
                f"{'not found (deleted successfully)' if verified else 'still found (delete failed)'}.{pre_flag}"
            )
        else:
            existed_before = any(
                (expected_time and v.get("time") == expected_time) or
                (search_term and search_term in (v.get("label") or "").lower())
                for v in pre_by_id.values()
            )
            if not existed_before:
                verified, rating = False, 0
                analysis = (
                    f"Cannot confirm delete: no alarm matching time='{expected_time}' or label='{search_term}' "
                    f"existed before this query ({len(pre_by_id)} alarms pre-existed)."
                )
            else:
                verified = len(matching_post) == 0
                rating = 5 if verified else 0
                analysis = (
                    f"Delete verification: matching alarm existed pre-query, {len(alarms)} remain post-query. "
                    f"Searched for time='{expected_time}' or label='{search_term}' — "
                    f"{'not found (deleted successfully)' if verified else 'still found (delete failed)'}."
                )
    else:
        # For create/modify: only consider alarms that are NEW or CHANGED since
        # pre_state — otherwise a pre-existing alarm at the same time/label
        # (e.g. from a prior run of this same query) trivially satisfies the match.
        candidates = alarms if pre_by_id is None else new_or_changed(alarms, pre_by_id, ("time", "label", "enabled"))
        matching = [a for a in candidates if _matches(a)]

        if matching:
            alarm = matching[0]
            verified = True
            rating = 5
            analysis = (
                f"New/changed alarm found: time='{alarm.time}', label='{alarm.label}', "
                f"enabled={alarm.enabled}. "
                f"Matched on: {'time' if expected_time and alarm.time == expected_time else 'label'}.{pre_flag}"
            )
        else:
            verified = False
            rating = 0
            analysis = (
                f"No new/changed alarm found matching time='{expected_time}' or label='{search_term}'. "
                f"{len(alarms)} alarms exist on device"
                f"{'' if pre_by_id is None else f', {len(pre_by_id)} pre-existed'}: "
                f"{[a.time for a in alarms]}.{pre_flag}"
            )

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)
