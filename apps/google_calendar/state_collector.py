"""
State collector for Google Calendar.

Google Calendar events sync into the Samsung Calendar content provider,
so the verification logic is identical to Samsung Calendar — only the
package name for launch verification differs.

Supports modes: create, modify, delete, launch, read.
"""

from __future__ import annotations

import re

from ..helpers import (
    extract_keyword,
    pre_items_by_id,
    new_or_changed,
    result,
    get_foreground_package_with_fallback,
)

APP_KEYS = ("googlecalendar",)
PACKAGE_NAME = "com.google.android.calendar"


def capture_pre(dm) -> dict:
    """Snapshot current calendar events before the agent acts."""
    events = _filter_holidays(dm.calendar.find_events())
    return {"events": [e.to_dict() for e in events], "count": len(events)}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Google Calendar state after the agent has acted."""
    app_name = app_key
    import datetime as _dt

    # ── Launch mode: verify Google Calendar is in foreground ──
    if mode == "launch":
        fg_info = get_foreground_package_with_fallback(dm)
        foreground_pkg = fg_info["resolved"]
        actual_state = {"foreground_info": fg_info}
        verified = foreground_pkg is not None and PACKAGE_NAME in (foreground_pkg or "")
        rating = 5 if verified else 0
        analysis = (
            f"Launch verification: foreground app is '{foreground_pkg}'. "
            f"Expected Google Calendar ('{PACKAGE_NAME}'). "
            f"{'App is in foreground.' if verified else 'Google Calendar is NOT in foreground.'}"
        )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Read mode: search for matching events, but always send all events to VLM ──
    if mode == "read":
        search_term = _extract_calendar_search_term(question, gt_answer)

        # Get ALL non-holiday events for VLM (search may fail → false negatives)
        all_events = _filter_holidays(dm.calendar.find_events())

        # Search using the content provider LIKE query
        if search_term:
            events = dm.calendar.find_events(query=search_term)
        else:
            events = all_events
        events = _filter_holidays(events)

        if events:
            matching = events
            actual_state = {
                "matching_events": [e.to_dict() for e in matching],
                "count": len(matching),
                "total_non_holiday_events": len(events),
                "all_events": [e.to_dict() for e in all_events],
                "total_events": len(all_events),
            }

            verified = True
            rating = 5
            event = matching[0]
            start_date = getattr(event, "start_date", "") or ""
            time_str = start_date or "N/A"

            analysis = (
                f"Read verification: {len(matching)} event(s) matching '{search_term}'. "
                f"First match: '{event.title}'. "
                f"Location: {event.location or 'N/A'}. Start: {time_str}. "
                f"AI's spoken response should be compared against this content by the LLM judge."
            )
            res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
            res["method"] = "xrclaw_read"
            return res
        else:
            all_events = _filter_holidays(dm.calendar.find_events())
            upcoming = sorted(
                [e for e in all_events if getattr(e, "start_date", "")],
                key=lambda e: getattr(e, "start_date", ""),
            )[:5]
            if upcoming:
                actual_state = {
                    "upcoming_events": [e.to_dict() for e in upcoming],
                    "count": len(upcoming),
                    "all_events": [e.to_dict() for e in all_events],
                    "total_events": len(all_events),
                }

                verified = True
                rating = 5
                analysis = (
                    f"Read verification: no events matched '{search_term}'. "
                    f"Returning {len(upcoming)} upcoming events for LLM judge comparison. "
                    f"Events: {[(e.title, getattr(e, 'start_date', '')) for e in upcoming]}"
                )

            else:
                actual_state = {"events": [], "count": 0}
                verified = False
                rating = 0
                analysis = f"Read verification: no events found on device."
            res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
            res["method"] = "xrclaw_read"
            return res

    # ── Create/Delete/Modify: pure set difference, NO search term ──
    events = _filter_holidays(dm.calendar.find_events())
    pre_by_id = pre_items_by_id(pre_state, "events")
    pre_flag = "" if pre_by_id is not None else " [No pre-query snapshot; existence-only check, weaker guarantee.]"

    def _fmt_time(event):
        start_date = getattr(event, "start_date", "") or ""
        if not start_date:
            return ""
        return f" Start: {start_date}."


    if mode == "delete":
        post_ids = {e.id for e in events}
        if pre_by_id is not None:
            deleted = [
                {"id": eid, "title": v.get("title", ""), "start_date": v.get("start_date", "")}
                for eid, v in pre_by_id.items()
                if eid not in post_ids
            ]

            actual_state = {
                "deleted_events": deleted,
                "count": len(deleted),
                "total_remaining": len(events),
                "all_events": [e.to_dict() for e in events],
            }

            if deleted:
                verified = True
                rating = 5
                deleted_titles = [d.get("title", "") for d in deleted[:5]]
                analysis = (
                    f"Delete verification: {len(deleted)} event(s) deleted "
                    f"(pre: {len(pre_by_id)}, post: {len(events)}). "
                    f"Deleted events: {deleted_titles}.{pre_flag}"
                )
            else:
                verified = False
                rating = 0
                analysis = (
                    f"Delete verification: no events were deleted "
                    f"(pre: {len(pre_by_id)}, post: {len(events)} — no change).{pre_flag}"
                )
        else:
            actual_state = {
                "events": [e.to_dict() for e in events],
                "count": len(events),
                "total_remaining": len(events),
            }
            verified = False
            rating = 0
            analysis = (
                f"Delete verification: no pre-state snapshot, cannot diff. "
                f"{len(events)} events currently on device.{pre_flag}"
            )

    elif mode == "modify":
        if pre_by_id is not None:
            changed = new_or_changed(
                events, pre_by_id, ("title", "description", "location", "start_date", "end_date")
            )

        else:
            changed = []

        actual_state = {
            "changed_events": [e.to_dict() for e in changed],
            "count": len(changed),
            "total_events": len(events),
            "all_events": [e.to_dict() for e in events],
        }


        if changed:
            event = changed[0]
            verified = True
            rating = 5
            analysis = (
                f"Modified event '{event.title}' found (changed since pre-state). "
                f"Location: {event.location or 'N/A'}.{_fmt_time(event)}{pre_flag}"
            )
        else:
            verified = False
            rating = 0
            if pre_by_id is not None:
                analysis = (
                    f"No events were modified since pre-state "
                    f"(pre: {len(pre_by_id)}, post: {len(events)} — no changes detected).{pre_flag}"
                )
            else:
                analysis = (
                    f"No pre-state snapshot, cannot detect modifications. "
                    f"{len(events)} events on device.{pre_flag}"
                )

    else:
        if pre_by_id is not None:
            pre_ids = set(pre_by_id.keys())
            new_events = [e for e in events if e.id not in pre_ids]
        else:
            new_events = events

        actual_state = {
            "new_events": [e.to_dict() for e in new_events],
            "count": len(new_events),
            "total_events": len(events),
            "all_events": [e.to_dict() for e in events],
        }


        if new_events:
            event = new_events[0]
            verified = True
            rating = 5
            new_titles = [e.title for e in new_events[:5]]
            analysis = (
                f"New event '{event.title}' found. "
                f"Location: {event.location or 'N/A'}.{_fmt_time(event)} "
                f"All new events: {new_titles}. "
                f"(pre: {len(pre_by_id) if pre_by_id is not None else 'N/A'}, post: {len(events)})"
                f"{pre_flag}"
            )
        else:
            verified = False
            rating = 0
            if pre_by_id is not None:
                analysis = (
                    f"No new events created since pre-state "
                    f"(pre: {len(pre_by_id)}, post: {len(events)} — no new events).{pre_flag}"
                )
            else:
                analysis = (
                    f"No pre-state snapshot, cannot diff. "
                    f"{len(events)} events on device.{pre_flag}"
                )

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)


# ── Calendar-specific helpers (shared with samsung_calendar) ───────

def _is_holiday_event(event) -> bool:
    desc = (event.description or "").lower()
    return any(marker in desc for marker in [
        "to hide observances",
        "public holiday",
        "observance\n",
    ])


def _filter_holidays(events) -> list:
    return [e for e in events if not _is_holiday_event(e)]


def _extract_calendar_search_term(question: str, gt_answer: str) -> str:
    quoted = re.search(r'["\']([^"\']+)["\']', question)
    if quoted:
        return quoted.group(1).lower().strip()

    title_match = re.search(r'(?:titled|called|named)\s+([^,]+?)(?:\s+(?:at|on|for|from|tomorrow|today)\b|[,\.]|$)', question, re.IGNORECASE)
    if title_match:
        return title_match.group(1).lower().strip()

    event_match = re.search(r'(?:create|add|set|schedule)\s+(?:an?\s+)?(?:event|meeting|appointment|reminder)\s+(?:titled|called|named|with|for)\s+([^,]+?)(?:\s+(?:at|on|for|from|tomorrow|today)\b|[,\.]|$)', question, re.IGNORECASE)
    if event_match:
        return event_match.group(1).lower().strip()

    with_match = re.search(r'(?:meeting|event|appointment|1:1|one\s+to\s+one|call|sync)\s+with\s+([^,]+?)(?:\s+(?:at|on|for|from|tomorrow|today)\b|[,\.]|$)', question, re.IGNORECASE)
    if with_match:
        return with_match.group(1).lower().strip()

    read_keyword = re.search(
        r'\b(meeting|meetings|appointment|appointments|event|events|call|calls|sync|lunch|birthday|party)\b',
        question, re.IGNORECASE
    )
    if read_keyword:
        return read_keyword.group(1).lower().strip()

    question_no_time = re.sub(r'\b\d{1,2}[:\s]?\d{2}\s*[ap]m?\b', '', question, flags=re.IGNORECASE)
    question_no_time = re.sub(r'\b\d{1,2}\s*[ap]m\b', '', question_no_time, flags=re.IGNORECASE)
    term = extract_keyword(question_no_time)
    if term:
        return term

    return extract_keyword(gt_answer)
