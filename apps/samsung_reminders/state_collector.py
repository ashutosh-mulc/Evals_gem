"""
State collector for Samsung Reminders.

Extracted from XRClawStateCollector._collect_reminders_state() and the
reminders branch of capture_pre_state().

Supports modes: create, modify, delete, launch, read, noread.
- create: A new reminder with matching title exists (uses pre-state diff).
- modify: A reminder's title or completed status changed since pre-state.
- delete: A reminder matching the search term existed pre-query and is gone post-query.
- launch: Samsung Reminder app is in the foreground.
- read:   The reminder content is fetched and returned for the LLM judge to compare
          against the AI's spoken response. Deterministic check verifies the reminder
          exists; the LLM judge handles the content accuracy comparison.
- noread: Same as read — verifies the reminder exists. The VLM judge evaluates
          whether the AI correctly did NOT read the reminder (negative test).
"""

from __future__ import annotations

from ..helpers import (
    extract_keyword,
    pre_items_by_id,
    new_or_changed,
    result,
    get_foreground_package_with_fallback,
)

APP_KEYS = ("samsungreminder",)
ACCESSOR = "reminders"
PACKAGE_NAME = "com.samsung.android.app.reminder"


def _format_reminder_details(reminder) -> str:
    """Build a human-readable description of a reminder including time/date/frequency."""
    parts = [f"title='{reminder.title}'"]
    if getattr(reminder, "description", ""):
        parts.append(f"description='{reminder.description[:200]}'")
    if getattr(reminder, "date_time", ""):
        parts.append(f"date_time='{reminder.date_time}'")
    if getattr(reminder, "date", ""):
        parts.append(f"date='{reminder.date}'")
    if getattr(reminder, "time", ""):
        parts.append(f"time='{reminder.time}'")
    if getattr(reminder, "all_day", False):
        parts.append("all_day=True")
    if getattr(reminder, "frequency", ""):
        parts.append(f"frequency='{reminder.frequency}'")
    if getattr(reminder, "recurrence", ""):
        parts.append(f"recurrence='{reminder.recurrence}'")
    if getattr(reminder, "recurrence_days", ""):
        parts.append(f"recurrence_days='{reminder.recurrence_days}'")
    parts.append(f"completed={reminder.completed}")
    return ", ".join(parts)



def capture_pre(dm) -> dict:
    """Snapshot current reminders state before the agent acts."""
    reminders = dm.reminders.find_reminders()
    return {"reminders": [r.to_dict() for r in reminders], "count": len(reminders)}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Samsung Reminders state after the agent has acted."""
    app_name = app_key
    search_term = extract_keyword(gt_answer)

    # ── Launch mode: verify Samsung Reminder is in foreground ──
    if mode == "launch":
        fg_info = get_foreground_package_with_fallback(dm)
        foreground_pkg = fg_info["resolved"]
        actual_state = {"foreground_info": fg_info}
        verified = foreground_pkg is not None and PACKAGE_NAME in (foreground_pkg or "")
        rating = 5 if verified else 0
        analysis = (
            f"Launch verification: foreground app is '{foreground_pkg}'. "
            f"Expected Samsung Reminder ('{PACKAGE_NAME}'). "
            f"{'App is in foreground.' if verified else 'Samsung Reminder is NOT in foreground.'}"
        )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Read / Noread mode: fetch reminder content for LLM judge comparison ──
    if mode in ("read", "noread"):
        reminders = dm.reminders.find_reminders()
        actual_state = {
            "reminders": [r.to_dict() for r in reminders],
            "count": len(reminders),
        }
        matching = [r for r in reminders if search_term and search_term in r.title.lower()]

        if matching:
            reminder = matching[0]
            verified = True
            rating = 5  # Base rating; LLM judge will refine if it runs
            mode_label = "Noread" if mode == "noread" else "Read"
            analysis = (
                f"{mode_label} verification: reminder found — {_format_reminder_details(reminder)}. "
                f"AI's spoken response should be compared against this content by the LLM judge."
            )

            res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
            res["method"] = "xrclaw_read"
            return res
        else:
            verified = False
            rating = 0
            mode_label = "Noread" if mode == "noread" else "Read"
            analysis = (
                f"{mode_label} verification: no reminder matching '{search_term}' found "
                f"({len(reminders)} reminders exist on device)."
            )
            return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Standard create/modify/delete flow ──
    reminders = dm.reminders.find_reminders()
    actual_state = {
        "reminders": [r.to_dict() for r in reminders],
        "count": len(reminders),
    }

    pre_by_id = pre_items_by_id(pre_state, "reminders")
    pre_flag = "" if pre_by_id is not None else " [No pre-query snapshot; existence-only check, weaker guarantee.]"

    if mode == "delete":
        matching_post = [r for r in reminders if search_term and search_term in r.title.lower()]
        if pre_by_id is None:
            verified = len(matching_post) == 0
            rating = 5 if verified else 0
            analysis = (
                f"Delete verification: {len(reminders)} reminders remain. "
                f"Searched for '{search_term}' — {'not found (deleted)' if verified else 'still found'}.{pre_flag}"
            )
        else:
            existed_before = any(search_term and search_term in (v.get("title") or "").lower() for v in pre_by_id.values())
            if not existed_before:
                verified, rating = False, 0
                analysis = (
                    f"Cannot confirm delete: no reminder matching '{search_term}' existed before this query "
                    f"({len(pre_by_id)} reminders pre-existed)."
                )
            else:
                verified = len(matching_post) == 0
                rating = 5 if verified else 0
                analysis = (
                    f"Delete verification: matching reminder existed pre-query, {len(reminders)} remain post-query. "
                    f"Searched for '{search_term}' — {'not found (deleted)' if verified else 'still found'}."
                )
    else:
        candidates = reminders if pre_by_id is None else new_or_changed(reminders, pre_by_id, ("title", "completed"))
        matching = [r for r in candidates if search_term and search_term in r.title.lower()]
        if matching:
            verified = True
            rating = 5
            reminder = matching[0]
            analysis = f"New/changed reminder found — {_format_reminder_details(reminder)}.{pre_flag}"

        else:
            verified = False
            rating = 0
            analysis = (
                f"No new/changed reminder found matching '{search_term}' "
                f"({len(reminders)} reminders total"
                f"{'' if pre_by_id is None else f', {len(pre_by_id)} pre-existed'}).{pre_flag}"
            )

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)
