"""
Preconditions for Samsung Clock Timer evaluations.

For modify/pause/restart/stop/read actions, a timer must pre-exist.
This module creates a real timer via the XRClaw TimerApp before the 
agent is invoked.
"""

from __future__ import annotations

import logging

from ..precondition_helpers import (
    parse_duration_to_seconds,
    report,
    clear_clock_state,
)

logger = logging.getLogger(__name__)

_NEEDS_EXISTING_TIMER = {"modify", "pause", "restart", "stop", "read", "delete"}

_DEFAULT_TIMER_DURATION = "5 minutes"


def setup(dm, sc, qt, question, gt_answer):
    action = qt.action
    xrclaw_dm = getattr(sc, "_dm", None) or dm

    # ── Launch: clear all clock state for a clean slate ──
    if action == "launch":
        try:
            cleared = clear_clock_state(xrclaw_dm)
            logger.info(
                "Precondition: cleared %d alarm(s), %d timer(s), stopwatch_reset=%s",
                cleared["alarms"], cleared["timers"], cleared["stopwatch_reset"],
            )
            return report(
                set_items=[
                    f"Cleared {cleared['alarms']} alarm(s), "
                    f"{cleared['timers']} timer(s), reset stopwatch",
                ],
                checked=["Clock state is clean"],
            )
        except Exception as e:
            logger.error("Precondition: failed to clear clock state: %s", e)
            return report(passed=False, failed=[f"Failed to clear clock state: {e}"])

    if action not in _NEEDS_EXISTING_TIMER:
        return report(skipped=f"No precondition needed for action='{action}'")

    # Always use the default duration for the pre-existing timer.
    # For modify: the agent will change this to the target duration from the question.
    # For other actions: the exact duration doesn't matter, just needs a running timer.
    duration_str = _DEFAULT_TIMER_DURATION
    duration_seconds = parse_duration_to_seconds(duration_str)

    try:
        # Clear any stale timers from previous queries.
        cleared = clear_clock_state(xrclaw_dm)
        xrclaw_dm.timers.create_timer(duration_seconds, label="Timer")
        logger.info("Precondition: cleared %d timer(s), created timer (%s = %ds)",
                     cleared["timers"], duration_str, duration_seconds)
        return report(
            set_items=[f"Cleared {cleared['timers']} stale timer(s), created timer ({duration_str})"],
            checked=[f"Timer exists on device"],
        )
    except Exception as e:
        return report(passed=False, failed=[f"Failed to create timer: {e}"])


