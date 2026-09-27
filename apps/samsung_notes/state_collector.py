"""
State collector for Samsung Notes.

Extracted from XRClawStateCollector._collect_notes_state() and the
notes branch of capture_pre_state().
"""

from __future__ import annotations

from ..helpers import (
    extract_keyword,
    extract_content_from_gt,
    content_overlaps,
    pre_items_by_id,
    new_or_changed,
    result,
    get_foreground_package_with_fallback,
)

APP_KEYS = ("samsungnote",)
ACCESSOR = "notes"
PACKAGE_NAME = "com.samsung.android.app.notes"


def _find_notes_with_content(dm) -> list:
    """Find notes and fetch full content for each.

    XRClaw's find_notes() returns note IDs and titles but leaves content empty.
    We call get_notes() with the IDs to retrieve the full content field.
    """
    notes = dm.notes.find_notes()
    if not notes:
        return []
    ids = [n.id for n in notes]
    return dm.notes.get_notes(ids)


def capture_pre(dm) -> dict:
    """Snapshot current notes before the agent acts."""
    notes = _find_notes_with_content(dm)
    return {"notes": [n.to_dict() for n in notes], "count": len(notes)}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Samsung Notes state after the agent has acted.

    Supports modes: create, modify, delete, launch, read.
    """
    app_name = app_key

    # ── Launch mode: verify Samsung Notes is in foreground ──
    if mode == "launch":
        fg_info = get_foreground_package_with_fallback(dm)
        foreground_pkg = fg_info["resolved"]
        actual_state = {"foreground_info": fg_info}
        samsung_notes_pkg = PACKAGE_NAME
        verified = foreground_pkg is not None and samsung_notes_pkg in (foreground_pkg or "")
        rating = 5 if verified else 0
        analysis = (
            f"Launch verification: foreground app is '{foreground_pkg}'. "
            f"Expected Samsung Notes ('{samsung_notes_pkg}'). "
            f"{'App is in foreground.' if verified else 'Samsung Notes is NOT in foreground.'}"
        )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Read mode: fetch note content for LLM judge comparison ──
    if mode == "read":
        notes = _find_notes_with_content(dm)
        actual_state = {
            "notes": [n.to_dict() for n in notes],
            "count": len(notes),
        }
        search_term = extract_keyword(gt_answer)
        matching = [n for n in notes if search_term and search_term in n.title.lower()]

        if matching:
            note = matching[0]
            verified = True
            rating = 5  # Base rating; LLM judge will refine if it runs
            analysis = (
                f"Read verification: note '{note.title}' found with content: '{note.content[:500]}'. "
                f"AI's spoken response should be compared against this content by the LLM judge."
            )
            res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
            res["method"] = "xrclaw_read"
            return res
        else:
            verified = False
            rating = 0
            analysis = (
                f"Read verification: no note matching '{search_term}' found "
                f"({len(notes)} notes exist on device)."
            )
            return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Standard create/modify/delete flow ──
    notes = _find_notes_with_content(dm)
    actual_state = {
        "notes": [n.to_dict() for n in notes],
        "count": len(notes),
    }

    pre_by_id = pre_items_by_id(pre_state, "notes")
    pre_flag = "" if pre_by_id is not None else " [No pre-query snapshot; existence-only check, weaker guarantee.]"
    search_term = extract_keyword(gt_answer)

    if mode == "delete":
        matching_post = [n for n in notes if search_term and search_term in n.title.lower()]
        if pre_by_id is None:
            verified = len(matching_post) == 0
            rating = 5 if verified else 0
            analysis = (
                f"Delete verification: {len(notes)} notes remain. "
                f"Searched for '{search_term}' — {'not found (deleted successfully)' if verified else 'still found (delete failed)'}."
                f"{pre_flag}"
            )
        else:
            existed_before = any(search_term and search_term in (v.get("title") or "").lower() for v in pre_by_id.values())
            if not existed_before:
                verified, rating = False, 0
                analysis = (
                    f"Cannot confirm delete: no note matching '{search_term}' existed before this query "
                    f"({len(pre_by_id)} notes pre-existed). Nothing to delete, so a clean post-state is inconclusive, not a pass."
                )
            else:
                verified = len(matching_post) == 0
                rating = 5 if verified else 0
                analysis = (
                    f"Delete verification: matching note existed pre-query, {len(notes)} notes remain post-query. "
                    f"Searched for '{search_term}' — {'not found (deleted successfully)' if verified else 'still found (delete failed)'}."
                )
    elif mode == "modify":
        # For modify: check if an existing note's content was changed (appended to)
        # since pre-state.
        candidates = notes if pre_by_id is None else new_or_changed(notes, pre_by_id, ("title", "content"))
        matching = [n for n in candidates if search_term and search_term in n.title.lower()]

        if matching:
            note = matching[0]
            content_match = content_overlaps(gt_answer, note.content)

            # For modify, also check if content was APPENDED
            content_appended = False
            if pre_by_id is not None:
                pre_note = pre_by_id.get(note.id)
                if pre_note:
                    pre_content = (pre_note.get("content") or "").lower().strip()
                    post_content = (note.content or "").lower().strip()
                    if pre_content and pre_content in post_content and len(post_content) > len(pre_content):
                        content_appended = True
                    gt_lower = gt_answer.lower()
                    new_text = extract_content_from_gt(gt_answer)
                    if new_text and new_text in post_content:
                        content_appended = True

            verified = content_match or content_appended
            rating = 5 if verified else 3
            append_info = f" Content appended: {content_appended}." if pre_by_id is not None else ""
            analysis = (
                f"Modified note '{note.title}' found. "
                f"Content match: {content_match}.{append_info} "
                f"Content: '{note.content[:200]}'.{pre_flag}"
            )
        else:
            verified = False
            rating = 0
            analysis = (
                f"No modified note found matching '{search_term}' since the query began "
                f"({len(notes)} notes total"
                f"{'' if pre_by_id is None else f', {len(pre_by_id)} pre-existed'}).{pre_flag}"
            )
    else:
        # For create: only consider notes that are NEW or CHANGED since pre_state
        candidates = notes if pre_by_id is None else new_or_changed(notes, pre_by_id, ("title", "content"))
        matching = [n for n in candidates if search_term and search_term in n.title.lower()]

        if matching:
            note = matching[0]
            content_match = content_overlaps(gt_answer, note.content)
            verified = content_match
            rating = 5 if verified else 3
            analysis = (
                f"New/changed note '{note.title}' found. "
                f"Content match: {content_match}. "
                f"Content: '{note.content[:200]}'.{pre_flag}"
            )
        else:
            verified = False
            rating = 0
            analysis = (
                f"No new/changed note found matching '{search_term}' since the query began "
                f"({len(notes)} notes total"
                f"{'' if pre_by_id is None else f', {len(pre_by_id)} pre-existed'}).{pre_flag}"
            )

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)
