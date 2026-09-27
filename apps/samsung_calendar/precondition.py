"""
Preconditions for Samsung Calendar evaluations.

For delete/modify/read actions, a calendar event with a matching title must
pre-exist. This module creates it via XRClaw before the agent is invoked.

For launch: all existing events are deleted via XRClaw so that no stale events
from previous runs remain on the device (holidays are also removed).
"""

from __future__ import annotations

import logging

from ..precondition_helpers import extract_title_from_gt, extract_content_from_gt, report

logger = logging.getLogger(__name__)

_NEEDS_EXISTING_EVENT = {"delete", "modify", "read"}


def setup(dm, sc, qt, question, gt_answer):
    action = qt.action

    # ── Launch: clear all events to ensure a clean state ──
    if action == "launch":
        xrclaw_dm = getattr(sc, "_dm", None) or dm
        try:
            cleared = xrclaw_dm.calendar.clear_all_events()
            logger.info("Precondition: cleared %d existing event(s) before launch", cleared)
            return report(
                set_items=[f"Cleared {cleared} existing event(s) before launch"],
                checked=["No stale events on device"],
            )
        except Exception as e:
            logger.error("Precondition: failed to clear events before launch: %s", e)
            return report(passed=False, failed=[f"Failed to clear events before launch: {e}"])

    if action not in _NEEDS_EXISTING_EVENT:
        return report(skipped=f"No precondition needed for action='{action}'")


    title = extract_title_from_gt(gt_answer)
    if not title:
        return report(
            passed=False,
            failed=[f"Could not extract event title from gt_answer: '{gt_answer}'"],
        )

    description = extract_content_from_gt(gt_answer)

    xrclaw_dm = getattr(sc, "_dm", None) or dm
    try:
        xrclaw_dm.calendar.create_event(title, description)
        logger.info("Precondition: created calendar event '%s'", title)
        return report(
            set_items=[f"Created event '{title}'"],
            checked=[f"Event '{title}' exists on device"],
        )
    except Exception as e:
        return report(passed=False, failed=[f"Failed to create event '{title}': {e}"])


def verify(dm, sc, qt, question, gt_answer):
    action = qt.action
    if action not in _NEEDS_EXISTING_EVENT:
        return {"passed": True, "details": f"No precondition for action='{action}'"}

    title = extract_title_from_gt(gt_answer)
    if not title:
        return {"passed": False, "details": "Could not extract event title"}

    xrclaw_dm = getattr(sc, "_dm", None) or dm
    events = xrclaw_dm.calendar.find_events(title)
    if events:
        return {"passed": True, "details": f"Event '{title}' exists"}
    return {"passed": False, "details": f"Event '{title}' not found"}
