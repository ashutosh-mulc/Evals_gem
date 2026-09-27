"""
State collector for Google Maps.

Accessor: maps

Migrated from xrclaw_state_collector.py _collect_maps_state.
Routes on app_mode (the action from question_type) rather than keyword-matching
gt_answer. Handles all Maps sub-features:
  - launch:         verify Maps is in foreground
  - query:          place info — VLM fallback with gt_answer
  - eta:            ETA query — VLM fallback with gt_answer
  - startnavigate:  start turn-by-turn navigation (state transition)
  - stopnavigate:   stop navigation (state transition)
  - addstop:        add a stop/waypoint (stop count change)
  - querynavigate:  query during navigation — VLM fallback with gt_answer
"""

from __future__ import annotations

from ..helpers import PRE_FLAG, result, verify_launch, xrclaw_unavailable_result

APP_KEYS = ("googlemaps",)


def capture_pre(dm) -> dict:
    """Snapshot current maps state before the agent acts."""
    return dm.maps.get_state().to_dict()


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Google Maps state for all query modes.

    For query, eta, and querynavigate modes, when Maps is NOT open (the
    agent answered from LLM knowledge), returns method="xrclaw_unavailable"
    so the deterministic judge returns 0 and the caller falls back to the
    VLM judge which uses gt_answer as ground truth.
    """
    maps = dm.maps

    # ── launch mode: verify Maps app is in foreground ──
    if mode == "launch":
        return verify_launch(dm, app_key, "com.google.android.apps.maps", "Maps", gt_answer)

    # ── Get current navigation state ──
    state = maps.get_state()
    actual_state = state.to_dict()

    # ── Pre-state extraction ──
    pre_flag = ""
    pre_is_navigating = None
    pre_is_running = None
    pre_stops = None
    if pre_state:
        pre_is_navigating = bool(pre_state.get("is_navigating"))
        pre_is_running = bool(pre_state.get("is_running"))
        pre_stops = pre_state.get("stops", [])
    else:
        pre_flag = PRE_FLAG

    # ── query mode: place info (hours, rating, distance) ──
    # Always handled by VLM with gt_answer as ground truth.
    if mode == "query":
        actual_state = {"is_running": state.is_running, "is_navigating": state.is_navigating}
        analysis = (
            f"Maps query: Handled by VLM with gt_answer as ground truth. "
            f"Maps running={state.is_running}. Cannot verify place details programmatically."
        )
        return xrclaw_unavailable_result(app_key, analysis, actual_state, gt_answer)

    # ── eta mode: "What's my ETA?" ──
    # Always handled by VLM with gt_answer as ground truth.
    if mode == "eta":
        actual_state = {"is_running": state.is_running, "is_navigating": state.is_navigating}
        analysis = (
            f"Maps eta: Handled by VLM with gt_answer as ground truth. "
            f"Maps running={state.is_running}, navigating={state.is_navigating}."
        )
        return xrclaw_unavailable_result(app_key, analysis, actual_state, gt_answer)

    # ── startnavigate mode: start turn-by-turn navigation ──
    if mode == "startnavigate":
        if pre_state:
            # Require transition: not navigating before → navigating after
            verified = state.is_navigating and not pre_is_navigating
            rating = 5 if verified else 0
            analysis = (
                f"Maps startnavigate: running={state.is_running}, navigating={state.is_navigating} "
                f"(was navigating={pre_is_navigating} pre-query). "
                f"Direction: {state.direction}, ETA: {state.eta}."
                f"{'' if verified else ' Already navigating pre-query — inconclusive, not a pass.'}"
            )
        else:
            verified = state.is_navigating
            rating = 5 if verified else 0
            analysis = (
                f"Maps startnavigate: running={state.is_running}, navigating={state.is_navigating}. "
                f"Direction: {state.direction}, ETA: {state.eta}.{pre_flag}"
            )
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)

    # ── stopnavigate mode: stop navigation ──
    if mode == "stopnavigate":
        if pre_state:
            # Require transition: navigating before → not navigating after
            verified = (not state.is_navigating) and pre_is_navigating
            rating = 5 if verified else 0
            analysis = (
                f"Maps stopnavigate: navigating={state.is_navigating} "
                f"(was navigating={pre_is_navigating} pre-query). "
                f"Running={state.is_running}."
                f"{'' if verified else ' Was not navigating pre-query or still navigating — inconclusive.'}"
            )
        else:
            verified = not state.is_navigating
            rating = 5 if verified else 0
            analysis = (
                f"Maps stopnavigate: navigating={state.is_navigating}, running={state.is_running}.{pre_flag}"
            )
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)

    # ── addstop mode: add a stop/waypoint to route ──
    if mode == "addstop":
        post_stops = maps.get_stops() or []
        actual_state = {
            "is_running": state.is_running,
            "is_navigating": state.is_navigating,
            "stops": post_stops,
            "destination": state.direction,
            "eta": state.eta,
        }
        if pre_state:
            pre_stop_count = len(pre_stops) if pre_stops else 0
            post_stop_count = len(post_stops)
            verified = post_stop_count > pre_stop_count
            rating = 5 if verified else 0
            analysis = (
                f"Maps addstop: stops changed from {pre_stop_count} → {post_stop_count}. "
                f"Stops: {post_stops}. "
                f"Navigation: {state.is_navigating}, ETA: {state.eta}."
                f"{'' if verified else ' Stop count did not increase — add stop may have failed.'}"
            )
        else:
            verified = len(post_stops) > 0
            rating = 5 if verified else 0
            analysis = (
                f"Maps addstop: {len(post_stops)} stops on route. Stops: {post_stops}. "
                f"Navigation: {state.is_navigating}, ETA: {state.eta}.{pre_flag}"
            )
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)

    # ── querynavigate mode: query during navigation (next turn, ETA) ──
    # Always handled by VLM with gt_answer as ground truth.
    if mode == "querynavigate":
        actual_state = {"is_running": state.is_running, "is_navigating": state.is_navigating}
        analysis = (
            f"Maps querynavigate: Handled by VLM with gt_answer as ground truth. "
            f"Maps running={state.is_running}, navigating={state.is_navigating}."
        )
        return xrclaw_unavailable_result(app_key, analysis, actual_state, gt_answer)

    # ── Fallback: generic state check ──
    if pre_state:
        verified = state.is_running and not pre_is_running
        rating = 5 if verified else 0
        analysis = (
            f"Maps state: running={state.is_running} (was {pre_is_running} pre-query), "
            f"navigating={state.is_navigating}."
            f"{'' if verified else ' Already running pre-query — inconclusive, not a pass.'}"
        )
    else:
        verified = state.is_running
        rating = 5 if verified else 0
        analysis = f"Maps state: running={state.is_running}, navigating={state.is_navigating}.{pre_flag}"

    return result(app_key, verified, rating, analysis, actual_state, gt_answer)
