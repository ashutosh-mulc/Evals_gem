"""
State collector for Samsung Clock Stopwatch.

Extracted from XRClawStateCollector._collect_stopwatch_state() and the
stopwatch branch of capture_pre_state().

Supports modes: launch, start, lap, stop, reset.

When pre_state is available, requires a state transition (e.g.
not-running → running for start) instead of a bare existence check.
"""

from __future__ import annotations

from ..helpers import PRE_FLAG, result, verify_launch

APP_KEYS = ("clockstopwatch",)
PACKAGE_NAME = "com.sec.android.app.clockpackage"


def capture_pre(dm) -> dict:
    """Snapshot current stopwatch state before the agent acts."""
    return dm.stopwatch.get_state().to_dict()


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Samsung Clock Stopwatch state after the agent has acted."""
    app_name = app_key

    # ── Launch mode: verify Clock app is in foreground ──
    if mode == "launch":
        return verify_launch(dm, app_name, PACKAGE_NAME, "Clock", gt_answer)

    state = dm.stopwatch.get_state()
    actual_state = state.to_dict()

    # ── Pre-state change detection ──
    pre_flag = ""
    pre_is_running = None
    pre_elapsed = None
    if pre_state:
        pre_is_running = bool(pre_state.get("is_running"))
        pre_elapsed = pre_state.get("elapsed_ms", 0)
    else:
        pre_flag = PRE_FLAG

    # ── Read mode: return state for LLM judge comparison ──
    if mode == "read":
        verified = True
        rating = 5
        analysis = (
            f"Read verification: stopwatch state: running={state.is_running}, "
            f"elapsed={state.elapsed_ms}ms. "
            f"AI's spoken response should be compared against this state by the LLM judge."
        )
        res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
        res["method"] = "xrclaw_read"
        return res

    # ── Route on app_mode ──
    if mode in ("start", "create"):
        # start (stopwatch) / create (timer): not running → running
        if pre_state:
            verified = state.is_running and not pre_is_running
            rating = 5 if verified else 0
            analysis = (
                f"Stopwatch/timer started: running={state.is_running} (was {pre_is_running} pre-query). "
                f"Elapsed: {state.elapsed_ms}ms."
                f"{'' if verified else ' Already running pre-query — inconclusive, not a pass.'}"
            )
        else:
            verified = state.is_running
            rating = 5 if verified else 0
            analysis = f"Stopwatch/timer running: {state.is_running}. Elapsed: {state.elapsed_ms}ms.{pre_flag}"

    elif mode in ("stop", "pause"):
        # stop/pause: running → stopped (but elapsed > 0)
        if pre_state:
            verified = not state.is_running and pre_is_running and state.elapsed_ms > 0
            rating = 5 if verified else 0
            analysis = (
                f"Stopwatch/timer paused: {not state.is_running} (was running={pre_is_running} pre-query). "
                f"Elapsed: {state.elapsed_ms}ms."
                f"{'' if verified else ' Was not running pre-query — inconclusive, not a pass.'}"
            )
        else:
            verified = not state.is_running and state.elapsed_ms > 0
            rating = 5 if verified else 0
            analysis = f"Stopwatch/timer paused: {not state.is_running}. Elapsed: {state.elapsed_ms}ms.{pre_flag}"

    elif mode == "restart":
        # restart: stopped → running again
        if pre_state:
            verified = state.is_running and not pre_is_running
            rating = 5 if verified else 0
            analysis = (
                f"Stopwatch/timer restarted: running={state.is_running} (was {pre_is_running} pre-query). "
                f"Elapsed: {state.elapsed_ms}ms."
                f"{'' if verified else ' Already running pre-query — inconclusive, not a pass.'}"
            )
        else:
            verified = state.is_running
            rating = 5 if verified else 0
            analysis = f"Stopwatch/timer running after restart: {state.is_running}. Elapsed: {state.elapsed_ms}ms.{pre_flag}"

    elif mode == "reset":
        # reset: elapsed > 0 → 0, not running
        if pre_state:
            verified = not state.is_running and state.elapsed_ms == 0 and (pre_elapsed or 0) > 0
            rating = 5 if verified else 0
            analysis = (
                f"Stopwatch/timer reset: elapsed={state.elapsed_ms}ms (was {pre_elapsed}ms pre-query)."
                f"{'' if verified else ' Was already at 0 pre-query — inconclusive, not a pass.'}"
            )
        else:
            verified = not state.is_running and state.elapsed_ms == 0
            rating = 5 if verified else 0
            analysis = f"Stopwatch/timer reset: elapsed={state.elapsed_ms}ms, running={state.is_running}.{pre_flag}"

    elif mode == "lap":
        # lap: stopwatch should still be running (lap doesn't stop it)
        if pre_state:
            verified = state.is_running and pre_is_running
            rating = 5 if verified else 0
            analysis = (
                f"Stopwatch lap: running={state.is_running} (was {pre_is_running} pre-query). "
                f"Elapsed: {state.elapsed_ms}ms."
                f"{'' if verified else ' Stopwatch not running — lap failed.'}"
            )
        else:
            verified = state.is_running
            rating = 5 if verified else 0
            analysis = f"Stopwatch running after lap: {state.is_running}. Elapsed: {state.elapsed_ms}ms.{pre_flag}"

    elif mode in ("modify", "delete"):
        # modify: timer was modified — should be running with different elapsed
        # delete: timer was deleted/stopped — should not be running, elapsed 0
        if mode == "delete":
            if pre_state:
                verified = not state.is_running and state.elapsed_ms == 0 and (pre_elapsed or 0) > 0
                rating = 5 if verified else 0
                analysis = (
                    f"Timer deleted/stopped: running={state.is_running}, elapsed={state.elapsed_ms}ms "
                    f"(was running={pre_is_running}, elapsed={pre_elapsed}ms pre-query)."
                )
            else:
                verified = not state.is_running and state.elapsed_ms == 0
                rating = 5 if verified else 0
                analysis = f"Timer deleted/stopped: running={state.is_running}, elapsed={state.elapsed_ms}ms.{pre_flag}"
        else:  # modify
            if pre_state:
                verified = state.is_running
                rating = 5 if verified else 0
                analysis = (
                    f"Timer modified: running={state.is_running}, elapsed={state.elapsed_ms}ms "
                    f"(was running={pre_is_running}, elapsed={pre_elapsed}ms pre-query)."
                )
            else:
                verified = state.is_running
                rating = 5 if verified else 0
                analysis = f"Timer running after modify: {state.is_running}. Elapsed: {state.elapsed_ms}ms.{pre_flag}"

    else:
        # Unknown mode — generic state check
        if pre_state:
            verified = state.is_running and not pre_is_running
            rating = 5 if verified else 0
            analysis = (
                f"Stopwatch/timer state: running={state.is_running} (was {pre_is_running} pre-query), "
                f"elapsed={state.elapsed_ms}ms."
                f"{'' if verified else ' Already running pre-query — inconclusive, not a pass.'}"
            )
        else:
            verified = state.is_running
            rating = 5 if verified else 0
            analysis = f"Stopwatch/timer state: running={state.is_running}, elapsed={state.elapsed_ms}ms.{pre_flag}"

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)
