"""
Preconditions for Samsung Clock Alarm evaluations.

For delete/modify/disable/read/stop actions, an alarm must pre-exist.
This module creates it via XRClaw before the agent is invoked.
"""

from __future__ import annotations

import logging

from ..precondition_helpers import extract_time_from_gt, extract_time_from_question, report, clear_clock_state

logger = logging.getLogger(__name__)

_NEEDS_EXISTING_ALARM = {"delete", "modify", "disable", "read", "stop"}

# Default alarm time if none can be extracted from gt_answer
_DEFAULT_ALARM_TIME = "07:00"


def setup(dm, sc, qt, question, gt_answer):
    action = qt.action
    xrclaw_dm = getattr(sc, "_dm", None) or dm

    # ── Launch: clear all clock state for a clean slate ──
    if action == "launch":
        try:
            cleared = clear_clock_state(xrclaw_dm)
            logger.info("Precondition: cleared %d alarm(s), stopwatch_reset=%s",
                         cleared["alarms"], cleared["stopwatch_reset"])
            return report(
                set_items=[f"Cleared {cleared['alarms']} existing alarm(s), reset stopwatch"],
                checked=["Clock state is clean"],
            )
        except Exception as e:
            logger.error("Precondition: failed to clear clock state: %s", e)
            return report(passed=False, failed=[f"Failed to clear clock state: {e}"])

    if action not in _NEEDS_EXISTING_ALARM:
        return report(skipped=f"No precondition needed for action='{action}'")


    # Extract time from question first (gt_answer is often empty in the dataset),
    # then fall back to gt_answer, then default.
    time_str = (
        extract_time_from_question(question, action)
        or extract_time_from_gt(gt_answer)
        or _DEFAULT_ALARM_TIME
    )

    xrclaw_dm = getattr(sc, "_dm", None) or dm
    try:
        # Clear any stale alarms from previous queries so the agent sees exactly
        # the alarm we create.
        cleared = clear_clock_state(xrclaw_dm)
        xrclaw_dm.alarms.create_alarm(time_str, label="Test Alarm")
        logger.info("Precondition: cleared %d alarm(s), created alarm at %s",
                     cleared["alarms"], time_str)
        return report(
            set_items=[f"Cleared {cleared['alarms']} stale alarm(s), created alarm at {time_str}"],
            checked=[f"Alarm at {time_str} exists on device"],
        )
    except Exception as e:
        return report(passed=False, failed=[f"Failed to create alarm: {e}"])


def verify(dm, sc, qt, question, gt_answer):
    action = qt.action
    if action not in _NEEDS_EXISTING_ALARM:
        return {"passed": True, "details": f"No precondition for action='{action}'"}

    xrclaw_dm = getattr(sc, "_dm", None) or dm
    alarms = xrclaw_dm.alarms.find_alarms()
    if alarms:
        return {"passed": True, "details": f"{len(alarms)} alarm(s) exist"}
    return {"passed": False, "details": "No alarms found"}
