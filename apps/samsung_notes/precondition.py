"""
Preconditions for Samsung Notes evaluations.

For delete/modify/read actions, a note with a matching title must pre-exist
on the device. This module creates that note via XRClaw before the agent
is invoked.

For launch: all existing notes are deleted via XRClaw so that no stale notes
from previous runs remain on the device.

For create: no precondition is needed.
"""

from __future__ import annotations

import logging

from ..precondition_helpers import extract_title_from_gt, extract_description_from_gt, report

logger = logging.getLogger(__name__)

# Actions that require a pre-existing note
_NEEDS_EXISTING_NOTE = {"delete", "modify", "read"}


def setup(dm, sc, qt, question, gt_answer):
    """Set up Samsung Notes preconditions.

    For delete/modify/read: create a note with the title extracted from gt_answer.
    For launch: clear all notes so no stale notes remain from previous runs.
    For create: no precondition needed (skip).
    """
    action = qt.action

    # ── Launch: clear all notes to ensure a clean state ──
    if action == "launch":
        statecollector_dm = getattr(sc, "_dm", None) or dm
        try:
            cleared = statecollector_dm.notes.clear_all_notes()
            logger.info("Precondition: cleared %d existing note(s) before launch", cleared)
            return report(
                set_items=[f"Cleared {cleared} existing note(s) before launch"],
                checked=["No stale notes on device"],
            )
        except Exception as e:
            logger.error("Precondition: failed to clear notes before launch: %s", e)
            return report(passed=False, failed=[f"Failed to clear notes before launch: {e}"])

    if action not in _NEEDS_EXISTING_NOTE:
        return report(skipped=f"No precondition needed for action='{action}'")


    title = extract_title_from_gt(gt_answer)
    if not title:
        return report(
            passed=False,
            failed=[f"Could not extract note title from gt_answer: '{gt_answer}'"],
        )

    content = extract_description_from_gt(gt_answer)

    # Create the note via XRClaw (use dm directly or via state collector)
    statecollector_dm = getattr(sc, "_dm", None) or dm
    try:
        statecollector_dm.notes.create_note(title, content)
        logger.info("Precondition: created note '%s' with content '%s'", title, content)
        return report(
            set_items=[f"Created note '{title}' with content '{content}'"],
            checked=[f"Note '{title}' exists on device"],
        )
    except Exception as e:
        logger.error("Precondition: failed to create note '%s': %s", title, e)
        return report(passed=False, failed=[f"Failed to create note '{title}': {e}"])


