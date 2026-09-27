"""
State collector for all device-level queries.

Handles: volume, datetime, battery, dnd, mediacontrol, notification, device_info.

Accessors:
    - volume       → device_info
    - mediacontrol  → media
    - notification  → notifications
    - datetime/battery/dnd → device_info (fetch only, evaluation by judge)
    - device_info   → device_info (fetch only, evaluation by judge)

App keys registered:
    - "device"              → device_info queries (time, date, battery, volume, dnd)
    - "device_mediacontrol" → media control queries (play, pause, skip, etc.)
    - "notification"        → notification read/dismiss queries
"""

from __future__ import annotations

from ..helpers import extract_keyword, pre_items_by_id, result

APP_KEYS = ("device", "device_mediacontrol", "notification")


# ── capture_pre ───────────────────────────────────────────────────

def capture_pre(dm, app_key: str = "") -> dict:
    """Snapshot current device state before the agent acts.

    Args:
        dm: XRClaw DeviceManager instance.
        app_key: "device", "device_mediacontrol", or "notification".
    """
    if app_key == "device_mediacontrol":
        return dm.media.get_state().to_dict()
    if app_key == "notification":
        notifications = dm.notifications.get_notifications()
        return {"notifications": [n.to_dict() for n in notifications], "count": len(notifications)}
    # "device" — fetch full device info for pre/post diffing
    try:
        return dm.device_info.get_all().to_dict()
    except Exception:
        return {}


# ── verify ────────────────────────────────────────────────────────

def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify device state after the agent has acted.

    Args:
        dm: XRClaw DeviceManager instance.
        app_key: "device", "device_mediacontrol", or "notification".
        mode: The action (up, down, play, read, etc.)
        question: The user question text.
        gt_answer: The ground-truth answer.
        pre_state: Pre-query snapshot (if captured).
    """
    if app_key == "device_mediacontrol":
        return _verify_media(dm, app_key, mode, question, gt_answer, pre_state)
    if app_key == "notification":
        return _verify_notifications(dm, app_key, mode, question, gt_answer, pre_state)
    # "device" — fetch state only, evaluation by DeterministicJudge
    return _verify_device_info(dm, app_key, mode, question, gt_answer, pre_state)


# ── Media control verification ─────────────────────────────────────

def _verify_media(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Collect device media playback state via pre/post seek position diffing.

    This collector is for device_mediacontrol queries (system-level play/pause/skip control),
    which can be verified deterministically using seek position changes.
    """
    state = dm.media.get_state()
    actual_state = state.to_dict()

    gt_lower = gt_answer.lower()

    # ── Pre-state change detection ──
    pre_flag = ""
    pre_playing = None
    pre_position = None
    if pre_state:
        pre_playing = bool(pre_state.get("is_playing", False))
        pre_position = pre_state.get("position_ms")
    else:
        pre_flag = " [No pre-query snapshot; existence-only check, weaker guarantee.]"

    post_position = state.position_ms
    post_playing = state.is_playing

    # ── State collection logic by command ──
    if "play" in gt_lower:
        if pre_state:
            verified = post_playing and not pre_playing
            rating = 5 if verified else (1 if post_playing else 0)
            analysis = (
                f"Play command: is_playing changed from {pre_playing} → {post_playing}. "
                f"Position: {post_position}ms.{'' if verified else ' Already playing pre-query — inconclusive.'}"
            )
        else:
            verified = post_playing
            rating = 5 if verified else 0
            analysis = f"Media playing: {post_playing}. Position: {post_position}ms.{pre_flag}"

    elif "pause" in gt_lower:
        if pre_state:
            verified = not post_playing and pre_playing
            rating = 5 if verified else 0
            analysis = (
                f"Pause command: is_playing changed from {pre_playing} → {post_playing}. "
                f"Position: {post_position}ms.{'' if verified else ' Was not playing pre-query — inconclusive.'}"
            )
        else:
            verified = not post_playing
            rating = 5 if verified else 0
            analysis = f"Media paused: {not post_playing}. Position: {post_position}ms.{pre_flag}"

    elif "skip" in gt_lower or "next" in gt_lower:
        if pre_state:
            pos_reset = (post_position is not None and post_position < 5000)
            pos_advanced = (
                post_position is not None and pre_position is not None
                and (post_position - pre_position) > 30000
            )
            verified = (pos_reset or pos_advanced) and post_playing
            rating = 5 if verified else (4 if post_playing else 0)
            analysis = (
                f"Skip/Next command: position {pre_position}ms → {post_position}ms, "
                f"playing={post_playing}. "
                f"{f'Position reset (<5s). ' if pos_reset else ''}"
                f"{f'Position advanced >30s. ' if pos_advanced else ''}"
                f"{'' if verified else 'Playing but position unclear — partial credit.'}"
            )
        else:
            verified = post_playing
            rating = 5 if verified else 0
            analysis = f"Media playing after skip: {post_playing}. Position: {post_position}ms.{pre_flag}"

    elif "replay" in gt_lower or "previous" in gt_lower or "rewind" in gt_lower:
        if pre_state:
            pos_moved_back = (
                post_position is not None and pre_position is not None
                and post_position < pre_position
            )
            verified = pos_moved_back and post_playing
            rating = 5 if verified else (4 if post_playing else 0)
            analysis = (
                f"Replay/Previous command: position {pre_position}ms → {post_position}ms, "
                f"playing={post_playing}. "
                f"{f'Position moved backward. ' if pos_moved_back else ''}"
                f"{'' if verified else 'Playing but position unclear — partial credit.'}"
            )
        else:
            verified = post_playing
            rating = 5 if verified else 0
            analysis = f"Media playing after replay: {post_playing}. Position: {post_position}ms.{pre_flag}"

    else:
        # Generic media state check
        if pre_state:
            verified = post_playing
            rating = 5 if verified else 0
        else:
            verified = post_playing
            rating = 5 if verified else 0
        analysis = (
            f"Media state: playing={post_playing}, position={post_position}ms, "
            f"app={state.app_name}.{pre_flag}"
        )

    return result(app_key, verified, rating, analysis, actual_state, gt_answer)


# ── Notifications verification ────────────────────────────────────

def _verify_notifications(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Collect state for a "read notification" (or dismiss/clear) task.

    Unlike notes/reminders/calendar, the target notification is injected by the
    test harness BEFORE the query (via NotificationsApp.post_notification), not
    created by the agent — the agent's job is to read it aloud, not mutate state.
    So for mode="read" this checks EXISTENCE with matching content in the
    current (post-query) notification list, not a pre/post transition.

    For mode="dismiss"/"clear", it checks the opposite: the matching
    notification existed pre-query and is gone post-query (agent dismissed it).
    """
    notifications = dm.notifications.get_notifications()
    actual_state = {
        "notifications": [n.to_dict() for n in notifications],
        "count": len(notifications),
    }

    search_term = extract_keyword(gt_answer)
    gt_lower = gt_answer.lower()

    def matches(n):
        title = (n.title or "").lower()
        text = (n.text or "").lower()
        return (search_term and search_term in title) or (search_term and search_term in text) or \
               (n.title and n.title.lower() in gt_lower) or (n.text and n.text.lower() in gt_lower)

    matching_post = [n for n in notifications if matches(n)]

    if mode in ("dismiss", "clear", "delete"):
        pre_by_id = pre_items_by_id(pre_state, "notifications")
        if pre_by_id is None:
            verified = len(matching_post) == 0
            rating = 5 if verified else 0
            analysis = (
                f"Dismiss verification: {len(notifications)} notifications remain. "
                f"Searched for '{search_term}' — "
                f"{'not found (dismissed)' if verified else 'still found (not dismissed)'}. "
                f"[No pre-query snapshot; existence-only check, weaker guarantee.]"
            )
        else:
            existed_before = any(
                search_term and (search_term in (v.get("title") or "").lower() or search_term in (v.get("text") or "").lower())
                for v in pre_by_id.values()
            )
            if not existed_before:
                verified, rating = False, 0
                analysis = (
                    f"Cannot confirm dismiss: no notification matching '{search_term}' existed "
                    f"before this query ({len(pre_by_id)} notifications pre-existed)."
                )
            else:
                verified = len(matching_post) == 0
                rating = 5 if verified else 0
                analysis = (
                    f"Dismiss verification: matching notification existed pre-query, "
                    f"{len(notifications)} remain post-query. Searched for '{search_term}' — "
                    f"{'not found (dismissed)' if verified else 'still found (not dismissed)'}."
                )
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)

    # Default / "read" mode: confirm the expected notification exists with matching content.
    if matching_post:
        n = matching_post[0]
        verified = True
        rating = 5
        analysis = (
            f"Notification found: title='{n.title}', text='{n.text}', "
            f"package={n.package}. Matches expected content '{search_term}'."
        )
    else:
        verified = False
        rating = 0
        analysis = (
            f"No notification found matching '{search_term}' "
            f"({len(notifications)} notifications currently active)."
        )
    return result(app_key, verified, rating, analysis, actual_state, gt_answer)


# ── Device info (fetch only — evaluation by DeterministicJudge) ───

def _verify_device_info(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Fetch device info state (battery, time, volume, DND, media) via XRClaw.

    Only fetches state — evaluation is done by DeterministicJudge in the
    judge_worker process.
    """
    try:
        device_state = dm.device_info.get_all()
        state_dict = device_state.to_dict()
    except Exception as e:
        return {
            "method": "xrclaw_error",
            "app_name": app_key,
            "verified": False,
            "rating": 0,
            "analysis": f"Device info fetch failed: {e}",
            "actual_state": {},
            "expected": gt_answer,
        }

    return {
        "method": "xrclaw",
        "app_name": app_key,
        "verified": False,  # not evaluated here
        "rating": 0,  # not evaluated here
        "analysis": "Device state fetched via XRClaw — evaluation deferred to DeterministicJudge.",
        "actual_state": state_dict,
        "expected": gt_answer,
    }
