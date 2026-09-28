"""
Preconditions for Samsung Clock Stopwatch evaluations.

For lap/stop/reset actions, a running stopwatch must pre-exist.
This module starts the stopwatch via XRClaw before the agent is invoked.
"""

from __future__ import annotations

import logging

from ..precondition_helpers import report, clear_clock_state

logger = logging.getLogger(__name__)

# Actions that require a running stopwatch
_NEEDS_RUNNING_STOPWATCH = {"lap", "stop", "reset"}


def setup(dm, sc, qt, question, gt_answer):
    action = qt.action
    statecollector_dm = getattr(sc, "_dm", None) or dm

    # ── Launch: clear all clock state for a clean slate ──
    if action == "launch":
        try:
            cleared = clear_clock_state(statecollector_dm)
            logger.info("Precondition: cleared %d alarm(s), stopwatch_reset=%s",
                         cleared["alarms"], cleared["stopwatch_reset"])
            return report(
                set_items=[f"Cleared {cleared['alarms']} existing alarm(s), reset stopwatch"],
                checked=["Clock state is clean"],
            )
        except Exception as e:
            logger.error("Precondition: failed to clear clock state: %s", e)
            return report(passed=False, failed=[f"Failed to clear clock state: {e}"])

    if action not in _NEEDS_RUNNING_STOPWATCH:
        return report(skipped=f"No precondition needed for action='{action}'")


    statecollector_dm = getattr(sc, "_dm", None) or dm
    try:
        statecollector_dm.stopwatch.start_stopwatch()
        logger.info("Precondition: started stopwatch")
        return report(
            set_items=["Started stopwatch"],
            checked=["Stopwatch is running"],
        )
    except Exception as e:
        return report(passed=False, failed=[f"Failed to start stopwatch: {e}"])


