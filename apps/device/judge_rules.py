"""
Device-specific judge rules.

Handlers used only by apps/device/ for time, date, battery, volume, DND, and media control.
These live separately from judge_helpers.py to keep device-specific logic isolated.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

from ..judge_helpers import get_device_state, get_flag, parse_question_type


# =============================================================================
# Time and date handlers (from judge_worker/handlers/datetime_handler.py)
# =============================================================================

def handle_time(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate time query: parse TTS with dateparser, compare vs device time.
    
    IMPORTANT: dateparser import is lazy to avoid 390ms import cost on every apps/ import.
    """
    from dateparser.search import search_dates
    
    post_state = get_device_state(metadata, "post")

    time_info = post_state.get("time", {})
    actual_time_str = time_info.get("datetime_str", "")
    actual_epoch_ms = time_info.get("epoch_ms")

    if actual_epoch_ms:
        actual_dt = datetime.fromtimestamp(actual_epoch_ms / 1000)
    elif actual_time_str:
        results = search_dates(
            actual_time_str, settings={"RELATIVE_BASE": datetime.now()}
        )
        actual_dt = results[0][1] if results else None
    else:
        return 2, "No device time available for grounding"

    if not actual_dt:
        return 2, f"Time query: could not parse device time from '{actual_time_str}'. No valid grounding data available. Rating: 2."

    results = search_dates(ai_response, settings={"RELATIVE_BASE": actual_dt})
    if not results:
        return 0, f"Time query: could not parse any time from TTS response '{ai_response}'. Device time was {actual_dt}. Rating: 0 — no time mentioned in response."

    best_dt = None
    best_diff = float("inf")
    for _, parsed_dt in results:
        if parsed_dt.tzinfo:
            parsed_dt = parsed_dt.replace(tzinfo=None)
        diff = abs((parsed_dt - actual_dt).total_seconds())
        if diff < best_diff:
            best_diff = diff
            best_dt = parsed_dt

    if best_diff <= 120:
        return 5, f"Time query. Device time: {actual_dt.strftime('%H:%M:%S')}. Parsed from TTS: {best_dt.strftime('%H:%M:%S')}. Difference: {best_diff:.0f}s (within ±120s tolerance). Rating: 5."
    elif best_diff <= 300:
        return 3, f"Time query. Device time: {actual_dt.strftime('%H:%M:%S')}. Parsed from TTS: {best_dt.strftime('%H:%M:%S')}. Difference: {best_diff:.0f}s (within ±300s tolerance but exceeds ±120s). Rating: 3."
    elif best_diff <= 3600:
        return 2, f"Time query. Device time: {actual_dt.strftime('%H:%M:%S')}. Parsed from TTS: {best_dt.strftime('%H:%M:%S')}. Difference: {best_diff:.0f}s (off by more than 5 minutes). Rating: 2."
    else:
        return 1, f"Time query. Device time: {actual_dt.strftime('%H:%M:%S')}. Parsed from TTS: {best_dt.strftime('%H:%M:%S')}. Difference: {best_diff:.0f}s (completely wrong — off by more than 1 hour). Rating: 1."


def handle_date(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate date query: parse TTS with dateparser, compare vs device date.
    
    IMPORTANT: dateparser import is lazy to avoid 390ms import cost on every apps/ import.
    """
    from dateparser.search import search_dates
    
    post_state = get_device_state(metadata, "post")
    date_info = post_state.get("date", {})

    actual_day = date_info.get("day")
    actual_month = date_info.get("month", "")
    actual_year = date_info.get("year")

    if not actual_day:
        time_info = post_state.get("time", {})
        actual_time_str = time_info.get("datetime_str", "")
        results = search_dates(actual_time_str)
        if results:
            actual_dt = results[0][1]
            actual_day = actual_dt.day
            actual_month = actual_dt.strftime("%b")
            actual_year = actual_dt.year

    if not actual_day:
        return 2, f"Date query: no device date available for grounding. Rating: 2."

    results = search_dates(ai_response)
    if not results:
        return 0, f"Date query: could not parse any date from TTS response '{ai_response}'. Expected date: {actual_year}-{actual_month}-{actual_day}. Rating: 0 — no date mentioned in response."

    best_dt = None
    best_diff = float("inf")
    for _, parsed_dt in results:
        if parsed_dt.tzinfo:
            parsed_dt = parsed_dt.replace(tzinfo=None)
        if parsed_dt.day == actual_day:
            diff = 0 if (parsed_dt.year == actual_year) else 365
            if diff < best_diff:
                best_diff = diff
                best_dt = parsed_dt

    if best_dt and best_dt.day == actual_day:
        if best_dt.year == actual_year:
            return 5, f"Date query. Device date: {actual_year}-{actual_month}-{actual_day}. Parsed from TTS: {best_dt.strftime('%Y-%m-%d')}. Day and year match exactly. Rating: 5."
        else:
            return 4, f"Date query. Device date: {actual_year}-{actual_month}-{actual_day}. Parsed from TTS: {best_dt.strftime('%Y-%m-%d')}. Day matches but year is wrong. Rating: 4."
    else:
        parsed_str = best_dt.strftime("%Y-%m-%d") if best_dt else "none"
        return 1, f"Date query. Device date: {actual_year}-{actual_month}-{actual_day}. Parsed from TTS: {parsed_str}. Day does not match. Rating: 1."


# =============================================================================
# Battery handler (from judge_worker/handlers/battery_handler.py)
# =============================================================================

def handle_battery(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate battery query: parse % from TTS, compare vs device battery."""
    question_type = metadata.get("question_type", "").lower()
    raw_state = metadata.get("device_info_post", {})

    if "companion" in question_type:
        battery = raw_state.get("companion", {}).get("battery", {})
    else:
        battery = raw_state.get("jinju", {}).get("battery", {})

    actual_level = battery.get("level")

    if actual_level is None:
        return 2, f"Battery query: no battery info available in device state for grounding. Rating: 2."

    match = re.search(r"(\d+)\s*%?", ai_response)
    if not match:
        return 0, f"Battery query: could not parse battery percentage from TTS response '{ai_response}'. Device battery level: {actual_level}%. Rating: 0 — no percentage mentioned in response."

    predicted_level = int(match.group(1))
    level_diff = abs(predicted_level - actual_level)

    if level_diff <= 2:
        return 5, f"Battery query. Device battery level: {actual_level}%. Parsed from TTS: {predicted_level}%. Difference: {level_diff}% (within ±2% tolerance). Rating: 5."
    elif level_diff <= 5:
        return 3, f"Battery query. Device battery level: {actual_level}%. Parsed from TTS: {predicted_level}%. Difference: {level_diff}% (within ±5% tolerance but exceeds ±2%). Rating: 3."
    elif level_diff <= 10:
        return 2, f"Battery query. Device battery level: {actual_level}%. Parsed from TTS: {predicted_level}%. Difference: {level_diff}% (off by more than 5%). Rating: 2."
    else:
        return 1, f"Battery query. Device battery level: {actual_level}%. Parsed from TTS: {predicted_level}%. Difference: {level_diff}% (completely wrong — off by more than 10%). Rating: 1."


# =============================================================================
# Volume handler (from judge_worker/handlers/volume_handler.py)
# =============================================================================

def _compute_threshold(stream_info: dict) -> int:
    """Compute adaptive threshold based on stream's min/max range.

    For range 0-15: threshold = 1
    For range 0-100: threshold = 10
    Formula: max(1, (max - min) // 10)
    """
    smin = stream_info.get("min")
    smax = stream_info.get("max")
    if smin is None or smax is None:
        return 1
    return max(1, (smax - smin) // 10)


def handle_volume(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate volume query: compare pre/post volume across ALL streams.

    Collects all volume streams from both jinju and companion device states.
    For up/down: passes if ANY stream changed by at least the adaptive threshold.
    For set: passes if ANY stream is within threshold of the target.
    For mute/unmute: passes if ANY stream's muted flag transitioned correctly.
    For read: uses MUSIC streamVolume from jinju (backward compat).
    """
    question_type = metadata.get("question_type", "").lower()
    _, action = parse_question_type(question_type)

    pre_full = metadata.get("device_info_pre", {})
    post_full = metadata.get("device_info_post", {})

    # Collect all streams from both jinju and companion, both pre and post
    all_streams_data = []  # list of (stream_name, pre_info, post_info, source)

    for source in ("jinju", "companion"):
        pre_vol = pre_full.get(source, {}).get("volume", {})
        post_vol = post_full.get(source, {}).get("volume", {})

        pre_streams = pre_vol.get("all_streams", {})
        post_streams = post_vol.get("all_streams", {})

        # If all_streams is empty (old format), fall back to top-level fields as MUSIC
        if not pre_streams and pre_vol.get("current") is not None:
            pre_streams = {"STREAM_MUSIC": {
                "streamVolume": pre_vol.get("current"),
                "muted": pre_vol.get("muted"),
                "min": pre_vol.get("min"),
                "max": pre_vol.get("max"),
            }}
        if not post_streams and post_vol.get("current") is not None:
            post_streams = {"STREAM_MUSIC": {
                "streamVolume": post_vol.get("current"),
                "muted": post_vol.get("muted"),
                "min": post_vol.get("min"),
                "max": post_vol.get("max"),
            }}

        all_stream_names = set(pre_streams.keys()) | set(post_streams.keys())
        for sname in all_stream_names:
            pre_info = pre_streams.get(sname, {})
            post_info = post_streams.get(sname, {})
            all_streams_data.append((sname, pre_info, post_info, source))

    is_up = action in ("up", "uprelative")
    is_down = action in ("down", "downrelative")
    is_set = action == "set"

    # ── UP / DOWN ──────────────────────────────────────────────────
    if is_up or is_down:
        any_pass = False
        details = []
        has_data = False

        for sname, pre_info, post_info, source in all_streams_data:
            pre_vol_val = pre_info.get("streamVolume")
            post_vol_val = post_info.get("streamVolume")

            if pre_vol_val is None or post_vol_val is None:
                continue

            has_data = True
            threshold = _compute_threshold(pre_info)
            delta = post_vol_val - pre_vol_val

            # Only mention streams that actually changed
            if delta == 0:
                continue

            if is_up and delta >= threshold:
                any_pass = True
                details.append(f"{source}.{sname}: {pre_vol_val}→{post_vol_val} (Δ=+{delta}, threshold={threshold}) ✓")
            elif is_down and delta <= -threshold:
                any_pass = True
                details.append(f"{source}.{sname}: {pre_vol_val}→{post_vol_val} (Δ={delta}, threshold={threshold}) ✓")
            else:
                details.append(f"{source}.{sname}: {pre_vol_val}→{post_vol_val} (Δ={delta:+d}, threshold={threshold}) ✗")

        if any_pass:
            return 5, f"Volume {'increase' if is_up else 'decrease'} query. At least one stream changed significantly. {'; '.join(details)}. Rating: 5."
        elif details:
            return 2, f"Volume {'increase' if is_up else 'decrease'} query. No stream changed by threshold amount. {'; '.join(details)}. Rating: 2."
        elif has_data:
            return 2, f"Volume {'increase' if is_up else 'decrease'} query. No stream changed at all between pre and post. Rating: 2."
        else:
            return 3, f"Volume {'increase' if is_up else 'decrease'} query. No pre/post stream data available to verify change. Rating: 3."
    # ── SET ───────────────────────────────────────────────────────
    elif is_set:
        match = re.search(r"(\d+)\s*%?", question.lower())
        if not match:
            return 3, f"Volume set query. Could not parse target percentage from question. Rating: 3."

        target_pct = int(match.group(1))
        any_pass = False
        details = []
        closest = None  # (abs_diff, detail_str) for the nearest stream

        for sname, pre_info, post_info, source in all_streams_data:
            post_vol_val = post_info.get("streamVolume")
            smax = post_info.get("max") or 15
            smin = post_info.get("min") or 0
            target_level = int(target_pct / 100 * (smax - smin)) + smin
            threshold = _compute_threshold(post_info)

            if post_vol_val is None:
                continue

            diff = abs(post_vol_val - target_level)
            detail_str = f"{source}.{sname}: {post_vol_val} (target={target_level}, threshold={threshold})"

            if diff <= threshold:
                any_pass = True
                details.append(f"{detail_str} ✓")
            else:
                # Track the closest non-matching stream for context
                if closest is None or diff < closest[0]:
                    closest = (diff, f"{detail_str} ✗")

        if any_pass:
            return 5, f"Volume set query. Target: {target_pct}%. At least one stream matches. {'; '.join(details)}. Rating: 5."
        elif closest:
            return 2, f"Volume set query. Target: {target_pct}%. No stream matches target. Closest: {closest[1]}. Rating: 2."
        else:
            return 2, f"Volume set query. Target: {target_pct}%. No stream data available. Rating: 2."

    # ── MUTE / UNMUTE ────────────────────────────────────────────
    elif action in ("mute", "unmute"):
        any_pass = False
        details = []

        for sname, pre_info, post_info, source in all_streams_data:
            pre_muted = pre_info.get("muted", False)
            post_muted = post_info.get("muted", False)

            # Only mention streams where muted state actually changed
            if pre_muted == post_muted:
                continue

            if action == "mute":
                if post_muted and not pre_muted:
                    any_pass = True
                    details.append(f"{source}.{sname}: muted {pre_muted}→{post_muted} ✓")
                else:
                    details.append(f"{source}.{sname}: muted {pre_muted}→{post_muted} ✗")
            else:  # unmute
                if not post_muted and pre_muted:
                    any_pass = True
                    details.append(f"{source}.{sname}: muted {pre_muted}→{post_muted} ✓")
                else:
                    details.append(f"{source}.{sname}: muted {pre_muted}→{post_muted} ✗")

        if any_pass:
            return 5, f"Volume {action} query. At least one stream transitioned correctly. {'; '.join(details)}. Rating: 5."
        elif details:
            return 0, f"Volume {action} query. No stream transitioned correctly. {'; '.join(details)}. Rating: 0."
        else:
            return 0, f"Volume {action} query. No stream's muted state changed between pre and post. Rating: 0."

    # ── READ (default) ───────────────────────────────────────────
    else:
        # Use MUSIC streamVolume from jinju for read queries
        jinju_post = post_full.get("jinju", {})
        post_vol = jinju_post.get("volume", {})
        post_streams = post_vol.get("all_streams", {})
        music = post_streams.get("STREAM_MUSIC", {})
        post_level = music.get("streamVolume", post_vol.get("current"))
        actual_muted = music.get("muted", post_vol.get("muted", False))

        if post_level is None:
            return 0, f"Volume read query: no volume info available in device state for grounding. Rating: 0."

        if actual_muted or post_level == 0:
            if any(w in ai_response.lower() for w in ["mute", "silent"]):
                return 5, f"Volume read query. Device is muted (level={post_level}, muted={actual_muted}). TTS correctly reported as muted/silent. Rating: 5."
            return 2, f"Volume read query. Device is muted (level={post_level}, muted={actual_muted}). TTS did NOT mention mute/silent state. Rating: 2."

        match = re.search(r"(\d+)", ai_response)
        if not match:
            return 0, f"Volume read query. Could not parse volume level from TTS: '{ai_response}'. Actual volume: {post_level}. Rating: 0."

        predicted_level = int(match.group(1))
        level_diff = abs(predicted_level - post_level)

        if level_diff <= 2:
            return 5, f"Volume read query. Device volume: {post_level}. Parsed from TTS: {predicted_level}. Difference: {level_diff} (within ±2 tolerance). Rating: 5."
        elif level_diff <= 5:
            return 3, f"Volume read query. Device volume: {post_level}. Parsed from TTS: {predicted_level}. Difference: {level_diff} (within ±5 tolerance but exceeds ±2). Rating: 3."
        else:
            return 1, f"Volume read query. Device volume: {post_level}. Parsed from TTS: {predicted_level}. Difference: {level_diff} (completely wrong — off by more than 5). Rating: 1."


# =============================================================================
# DND handler (from judge_worker/handlers/dnd_handler.py)
# =============================================================================

def handle_dnd(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate DND query: parse on/off from TTS, compare vs device DND state."""
    question_type = metadata.get("question_type", "").lower()
    _, action = parse_question_type(question_type)

    pre_state = get_device_state(metadata, "pre")
    post_state = get_device_state(metadata, "post")

    pre_dnd = pre_state.get("dnd_mode", "false").lower() == "true"
    post_dnd = post_state.get("dnd_mode", "false").lower() == "true"

    if action == "on":
        if post_dnd and not pre_dnd:
            return 5, f"DND turn-on query. Pre-state: {pre_dnd}, Post-state: {post_dnd}. DND successfully turned on (False → True). Criteria: DND must be on. Rating: 5."
        elif post_dnd:
            return 5, f"DND turn-on query. Post-state: {post_dnd}. DND is on but was already on. Rating: 5."
        else:
            return 0, f"DND turn-on query. Pre-state: {pre_dnd}, Post-state: {post_dnd}. DND failed to turn on. Criteria: DND must be on. Rating: 0."
    elif action == "off":
        if not post_dnd and pre_dnd:
            return 5, f"DND turn-off query. Pre-state: {pre_dnd}, Post-state: {post_dnd}. DND successfully turned off (True → False). Criteria: DND must be off. Rating: 5."
        elif not post_dnd:
            return 5, f"DND turn-off query. Post-state: {post_dnd}. DND is off but was already off. Rating: 5."
        else:
            return 0, f"DND turn-off query. Pre-state: {pre_dnd}, Post-state: {post_dnd}. DND failed to turn off. Criteria: DND must be off. Rating: 0."
    else:
        tts_lower = ai_response.lower()
        on_words = ["on", "enabled", "active", "yes"]
        off_words = ["off", "disabled", "inactive", "no"]

        predicted_dnd = None
        if any(w in tts_lower for w in on_words):
            predicted_dnd = True
        elif any(w in tts_lower for w in off_words):
            predicted_dnd = False

        if predicted_dnd is None:
            return 0, f"DND read query. Could not parse DND status from TTS: '{ai_response}'. Actual DND state: {post_dnd}. Rating: 0."

        if predicted_dnd == post_dnd:
            return 5, f"DND read query. Device DND: {post_dnd}. Parsed from TTS: {predicted_dnd}. Status matches. Rating: 5."
        else:
            return 1, f"DND read query. Device DND: {post_dnd}. Parsed from TTS: {predicted_dnd}. Status does not match. Rating: 1."


# =============================================================================
# Media control handler (from judge_worker/handlers/media_handler.py)
# =============================================================================

def handle_mediacontrol(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate media control query using pre/post device media state."""
    question_type = metadata.get("question_type", "").lower()
    _, action = parse_question_type(question_type)

    pre_state = get_device_state(metadata, "pre")
    post_state = get_device_state(metadata, "post")

    post_media = post_state.get("media", {})
    actual_playing = post_media.get("playing", False)
    actual_active = post_media.get("active", False)
    actual_state = post_state.get("state", "")
    actual_title = post_media.get("title", "")
    actual_artist = post_media.get("artist", "")
    actual_position = post_media.get("position_ms")

    pre_flag = ""
    pre_playing = None
    pre_position = None
    capture_delay_ms = 0
    
    if pre_state:
        pre_media = pre_state.get("media", pre_state)
        pre_playing = bool(pre_media.get("playing", pre_media.get("is_playing", False)))
        pre_position = pre_media.get("position_ms")
        
        # Calculate capture delay for seek queries
        pre_epoch = metadata.get("device_info_pre", {}).get("captured_at_epoch", 0)
        post_epoch = metadata.get("device_info_post", {}).get("captured_at_epoch", 0)
        if pre_epoch and post_epoch:
            capture_delay_ms = post_epoch - pre_epoch
    else:
        pre_flag = " [No pre-query snapshot; existence-only check, weaker guarantee.]"

    # Handle seek actions (seekforward, seekback, skip by X seconds)
    if action in ("seekforward", "seekback", "seek") or "seek" in question_type:
        # Parse seek amount from question (e.g., "skip forward 10 seconds" → 10000ms)
        import re
        seek_match = re.search(r'(\d+)\s*(?:second|sec|s)', question.lower())
        if seek_match and pre_position is not None and actual_position is not None:
            seek_amount_ms = int(seek_match.group(1)) * 1000
            actual_delta = actual_position - pre_position
            
            # For seek forward: expected = seek_amount + capture_delay (natural playback)
            # For seek back: expected = -seek_amount + capture_delay
            if "back" in question.lower() or "backward" in question.lower() or "rewind" in question.lower():
                expected_delta = -seek_amount_ms + capture_delay_ms
            else:
                expected_delta = seek_amount_ms + capture_delay_ms
            
            # Allow ±3s tolerance for capture delay estimation
            if abs(actual_delta - expected_delta) <= 3000 and actual_playing:
                return 5, f"Media seek query. Pre-position: {pre_position}ms, Post-position: {actual_position}ms, Capture delay: {capture_delay_ms}ms. Expected delta: {expected_delta}ms, Actual delta: {actual_delta}ms. Within tolerance — seek verified. Rating: 5."
            elif actual_playing and abs(actual_delta - expected_delta) <= 5000:
                return 4, f"Media seek query. Pre-position: {pre_position}ms, Post-position: {actual_position}ms, Capture delay: {capture_delay_ms}ms. Expected delta: {expected_delta}ms, Actual delta: {actual_delta}ms. Slightly outside tolerance but close. Rating: 4."
            else:
                return 1, f"Media seek query. Pre-position: {pre_position}ms, Post-position: {actual_position}ms, Capture delay: {capture_delay_ms}ms. Expected delta: {expected_delta}ms, Actual delta: {actual_delta}ms. Position does not match expected seek. Rating: 1."
        elif actual_playing:
            return 4, f"Media seek query. Could not parse seek amount from question, but media is playing. Rating: 4."
        else:
            return 1, f"Media seek query. Media not playing. Rating: 1."

    if action == "pause":
        if pre_state:
            verified = (not actual_playing) and pre_playing
            rating = 5 if verified else 1
            analysis = (
                f"Media pause query. Pre-state: playing={pre_playing}, Post-state: playing={actual_playing}. Position: {actual_position}ms. "
                f"Criteria: playing must change from True to False. "
                f"{'Transition verified — media successfully paused. ' if verified else 'Was not playing pre-query — inconclusive. '}"
                f"Rating: {rating}."
            )
        else:
            verified = not actual_playing
            rating = 5 if verified else 1
            analysis = (
                f"Media pause query. Post-state: playing={actual_playing}, active={actual_active}. State: {actual_state}. Title: '{actual_title}'. "
                f"Criteria: media must be paused (playing=False). "
                f"{'No pre-state — existence-only check. ' if pre_flag else ''}"
                f"Rating: {rating}.{pre_flag}"
            )
    elif action == "skip":
        if pre_state:
            pos_reset = actual_position is not None and actual_position < 5000
            pos_advanced = (
                actual_position is not None and pre_position is not None
                and (actual_position - pre_position) > 30000
            )
            verified = (pos_reset or pos_advanced) and actual_playing
            rating = 5 if verified else (4 if actual_playing else 0)
            analysis = (
                f"Media skip/next query. Pre-position: {pre_position}ms, Post-position: {actual_position}ms, playing={actual_playing}. "
                f"Criteria: position must reset (<5s) or advance >30s, and media must be playing. "
                f"{'Position reset (<5s). ' if pos_reset else ''}{'Position advanced >30s. ' if pos_advanced else ''}"
                f"{'Track change verified. ' if verified else 'Playing but position unclear — partial credit. '}"
                f"Rating: {rating}."
            )
        else:
            verified = actual_active and actual_playing
            rating = 5 if verified else (4 if actual_active else 1)
            analysis = (
                f"Media skip/next query. Post-state: active={actual_active}, playing={actual_playing}. Title: '{actual_title}'. "
                f"Criteria: media must be active and playing (track change cannot be verified without pre-state). "
                f"Rating: {rating}.{pre_flag}"
            )
    elif action in ("replay", "previous"):
        if pre_state:
            pos_moved_back = (
                actual_position is not None and pre_position is not None
                and actual_position < pre_position
            )
            verified = pos_moved_back and actual_playing
            rating = 5 if verified else (4 if actual_playing else 0)
            analysis = (
                f"Media replay/previous query. Pre-position: {pre_position}ms, Post-position: {actual_position}ms, playing={actual_playing}. "
                f"Criteria: position must move backward and media must be playing. "
                f"{'Position moved backward — replay verified. ' if pos_moved_back else 'Position did not move backward. '}"
                f"{'Playing but position unclear — partial credit. ' if not verified and actual_playing else ''}"
                f"Rating: {rating}."
            )
        else:
            verified = actual_active and actual_playing
            rating = 5 if verified else (4 if actual_active else 1)
            analysis = (
                f"Media replay/previous query. Post-state: active={actual_active}, playing={actual_playing}. Title: '{actual_title}'. "
                f"Criteria: media must be active and playing (position change cannot be verified without pre-state). "
                f"Rating: {rating}.{pre_flag}"
            )
    elif action in ("resume", "play"):
        if pre_state:
            verified = actual_playing and not pre_playing
            rating = 5 if verified else (1 if actual_playing else 0)
            analysis = (
                f"Media play/resume query. Pre-state: playing={pre_playing}, Post-state: playing={actual_playing}. Position: {actual_position}ms. "
                f"Criteria: playing must change from False to True. "
                f"{'Transition verified — media successfully started. ' if verified else 'Already playing pre-query — inconclusive. '}"
                f"Rating: {rating}."
            )
        else:
            verified = actual_playing
            rating = 5 if verified else (2 if actual_active else 1)
            analysis = (
                f"Media play/resume query. Post-state: playing={actual_playing}, active={actual_active}. State: {actual_state}. Title: '{actual_title}'. "
                f"Criteria: media must be playing (playing=True). "
                f"Rating: {rating}.{pre_flag}"
            )
    elif actual_title or actual_artist:
        rating = 4
        analysis = (
            f"Media read query. Title: '{actual_title}', Artist: '{actual_artist}'. Playing: {actual_playing}. "
            f"Criteria: media metadata must be available. "
            f"Rating: {rating}."
        )
    else:
        rating = 1
        analysis = (
            f"Media control query: could not determine expected media action from question. "
            f"Post-state: active={actual_active}, playing={actual_playing}, state={actual_state}. "
            f"Criteria: unable to determine action. Rating: {rating}."
        )

    return rating, analysis


# =============================================================================
# Media like/dislike handler (log analysis based)
# =============================================================================

def handle_media_like_dislike(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate media like/dislike query using log analysis results.

    Uses the 'liked' and 'disliked' flags from app_state.log_analysis.
    These flags are set when "Undo like" or "Undo dislike" patterns are detected
    in device logs by the LogcatAnalyzer.
    """
    question_type = metadata.get("question_type", "").lower()
    _, action = parse_question_type(question_type)

    # Get like/dislike flags from app_state.log_analysis (via get_flag helper)
    liked = get_flag(metadata, "liked")
    disliked = get_flag(metadata, "disliked")

    if action == "like":
        if liked:
            return 5, f"Media like query. Log analysis detected 'Undo like' action. Song was successfully liked. Rating: 5."
        else:
            return 1, f"Media like query. Log analysis did NOT detect 'Undo like' action. Like action not verified. Rating: 1."
    elif action == "dislike":
        if disliked:
            return 5, f"Media dislike query. Log analysis detected 'Undo dislike' action. Song was successfully disliked. Rating: 5."
        else:
            return 1, f"Media dislike query. Log analysis did NOT detect 'Undo dislike' action. Dislike action not verified. Rating: 1."
    else:
        return 2, f"Media like/dislike query. Unknown action '{action}'. Rating: 2."

