"""
Preconditions for Samsung Reminders evaluations.

For delete/modify/read/noread actions, a reminder with a matching title must
pre-exist. This module creates it via XRClaw before the agent is invoked.

For launch: all existing reminders are deleted via XRClaw so that no stale
reminders from previous runs remain on the device.
"""

from __future__ import annotations

import logging

from ..precondition_helpers import extract_title_from_gt, extract_description_from_gt, report

logger = logging.getLogger(__name__)

_NEEDS_EXISTING_REMINDER = {"delete", "modify", "read", "noread"}


def setup(dm, sc, qt, question, gt_answer):
    action = qt.action

    # ── Launch: clear all reminders to ensure a clean state ──
    if action == "launch":
        statecollector_dm = getattr(sc, "_dm", None) or dm
        try:
            cleared = statecollector_dm.reminders.clear_all_reminders()
            logger.info("Precondition: cleared %d existing reminder(s) before launch", cleared)
            return report(
                set_items=[f"Cleared {cleared} existing reminder(s) before launch"],
                checked=["No stale reminders on device"],
            )
        except Exception as e:
            logger.error("Precondition: failed to clear reminders before launch: %s", e)
            return report(passed=False, failed=[f"Failed to clear reminders before launch: {e}"])

    if action not in _NEEDS_EXISTING_REMINDER:
        return report(skipped=f"No precondition needed for action='{action}'")


    title = extract_title_from_gt(gt_answer)
    if not title:
        return report(
            passed=False,
            failed=[f"Could not extract reminder title from gt_answer: '{gt_answer}'"],
        )

    description = extract_description_from_gt(gt_answer)

    statecollector_dm = getattr(sc, "_dm", None) or dm
    try:
        statecollector_dm.reminders.create_reminder(title, description)
        logger.info("Precondition: created reminder '%s'", title)
        return report(
            set_items=[f"Created reminder '{title}' with description '{description}'"],
            checked=[f"Reminder '{title}' exists on device"],
        )
    except Exception as e:
        return report(passed=False, failed=[f"Failed to create reminder '{title}': {e}"])


