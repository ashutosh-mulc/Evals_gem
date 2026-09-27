"""
State collector for Samsung Clock Timer.

Uses the dm.timers accessor (TimerApp) to read real timer state from
the device via App Functions broadcast.  Each timer provides: id, label,
timer_state (STARTED/PAUSED/etc), is_firing, original_duration_millis,
duration_millis, remaining_duration_millis, expire_time_epoch_millis.

Supports modes: launch, create, read, modify, pause, restart, stop, delete.

When pre_state is available, requires a state transition (e.g.
0 timers -> 1 running timer for create) instead of a bare existence check.
"""

from __future__ import annotations

from ..helpers import PRE_FLAG, result, verify_launch

APP_KEYS = ("clocktimer",)
PACKAGE_NAME = "com.sec.android.app.clockpackage"


def _format_duration(millis: int) -> str:
    """Format milliseconds as a human-readable duration string."""
    if not millis:
        return "0ms"
    seconds = millis // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _format_timers(timers: list) -> str:
    """Format a list of TimerItem dicts for the analysis text."""
    if not timers:
        return "No timers found."
    parts = []
    for i, t in enumerate(timers):
        label = t.get("label", "")
        state = t.get("timer_state", "unknown")
        orig_dur = t.get("original_duration_millis", 0)
        remaining = t.get("remaining_duration_millis", 0)
        parts.append(
            f"Timer[{i}]: label='{label}', state={state}, "
            f"original_duration={_format_duration(orig_dur)}, "
            f"remaining={_format_duration(remaining)}"
        )
    return "; ".join(parts)


def capture_pre(dm) -> dict:
    """Snapshot current timer state before the agent acts."""
    return dm.timers.get_state().to_dict()


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Samsung Clock Timer state after the agent has acted."""
    app_name = app_key

    # ── Launch mode: verify Clock app is in foreground ──
    if mode == "launch":
        return verify_launch(dm, app_name, PACKAGE_NAME, "Clock", gt_answer)

    timer_state = dm.timers.get_state()
    actual_state = timer_state.to_dict()
    timers = actual_state.get("timers", [])
    count = actual_state.get("count", 0)
    running_count = actual_state.get("running_count", 0)

    # ── Parse pre-state ──
    pre_timers = []
    pre_count = 0
    pre_running = 0
    if pre_state:
        pre_timers = pre_state.get("timers", [])
        pre_count = pre_state.get("count", 0)
        pre_running = pre_state.get("running_count", 0)
    pre_flag = "" if pre_state else PRE_FLAG

    timers_desc = _format_timers(timers)
    pre_timers_desc = _format_timers(pre_timers) if pre_state else "(no pre-state)"

    # ── Read mode: return full timer state for LLM judge comparison ──
    if mode == "read":
        verified = True
        rating = 5
        analysis = (
            f"Read verification: {count} timer(s) found. {timers_desc}. "
            f"AI's spoken response should be compared against this state by the LLM judge."
        )
        res = result(app_name, verified, rating, analysis, actual_state, gt_answer)
        res["method"] = "xrclaw_read"
        return res

    # ── Route on app_mode ──
    if mode in ("start", "create"):
        if pre_state:
            verified = count > pre_count and running_count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer created: {count} timer(s) (was {pre_count} pre-query), "
                f"{running_count} running. {timers_desc}. "
                f"Pre-state: {pre_timers_desc}."
                f"{'' if verified else ' Timer count did not increase or no running timer.'}"
            )
        else:
            verified = count > 0 and running_count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer created: {count} timer(s), {running_count} running. "
                f"{timers_desc}.{pre_flag}"
            )

    elif mode in ("stop", "pause"):
        if pre_state:
            verified = running_count == 0 and pre_running > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer paused/stopped: running={running_count} "
                f"(was {pre_running} running pre-query). {timers_desc}."
                f"{'' if verified else ' Timer still running or was not running pre-query.'}"
            )
        else:
            verified = running_count == 0 and count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer paused/stopped: {count} timer(s), {running_count} running. "
                f"{timers_desc}.{pre_flag}"
            )

    elif mode == "restart":
        if pre_state:
            verified = running_count > 0 and pre_running == 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer restarted: running={running_count} "
                f"(was {pre_running} running pre-query). {timers_desc}."
                f"{'' if verified else ' Timer not running or was already running pre-query.'}"
            )
        else:
            verified = running_count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer running after restart: {running_count} running. "
                f"{timers_desc}.{pre_flag}"
            )

    elif mode == "reset":
        if pre_state:
            verified = count == 0 and pre_count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer reset/deleted: {count} timer(s) (was {pre_count} pre-query). "
                f"{timers_desc}."
                f"{'' if verified else ' Timers still exist or were none pre-query.'}"
            )
        else:
            verified = count == 0
            rating = 5 if verified else 0
            analysis = f"Timer reset: {count} timer(s).{pre_flag}"

    elif mode == "lap":
        if pre_state:
            verified = running_count > 0 and pre_running > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer lap: running={running_count} (was {pre_running} pre-query). "
                f"{timers_desc}."
                f"{'' if verified else ' Timer not running.'}"
            )
        else:
            verified = running_count > 0
            rating = 5 if verified else 0
            analysis = f"Timer running after lap: {running_count} running.{pre_flag}"

    elif mode == "delete":
        if pre_state:
            verified = count < pre_count
            rating = 5 if verified else 0
            analysis = (
                f"Timer deleted: {count} timer(s) (was {pre_count} pre-query). "
                f"{timers_desc}."
                f"{'' if verified else ' Timer count did not decrease.'}"
            )
        else:
            verified = count == 0
            rating = 5 if verified else 0
            analysis = f"Timer deleted: {count} timer(s).{pre_flag}"

    elif mode == "modify":
        if pre_state:
            pre_dur = (
                pre_timers[0].get("original_duration_millis", 0)
                if pre_timers else 0
            )
            post_dur = (
                timers[0].get("original_duration_millis", 0)
                if timers else 0
            )
            verified = (
                count > 0
                and pre_dur > 0
                and post_dur > 0
                and post_dur != pre_dur
            )
            rating = 5 if verified else 0
            analysis = (
                f"Timer modified: {count} timer(s). "
                f"Duration: {_format_duration(post_dur)} "
                f"(was {_format_duration(pre_dur)} pre-query). "
                f"{timers_desc}."
                f"{'' if verified else ' Duration did not change or no timer found.'}"
            )
        else:
            verified = count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer modified: {count} timer(s). {timers_desc}.{pre_flag}"
            )

    else:
        if pre_state:
            verified = count > pre_count
            rating = 5 if verified else 0
            analysis = (
                f"Timer state: {count} timer(s) (was {pre_count} pre-query), "
                f"{running_count} running. {timers_desc}."
                f"{'' if verified else ' Timer count did not increase.'}"
            )
        else:
            verified = count > 0
            rating = 5 if verified else 0
            analysis = (
                f"Timer state: {count} timer(s), {running_count} running. "
                f"{timers_desc}.{pre_flag}"
            )

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)
