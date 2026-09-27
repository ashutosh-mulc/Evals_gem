"""
Tests for deterministic judge handlers.

Tests can_handle() from DeterministicJudge, and handler functions from
apps.device.judge_rules and apps.judge_helpers.
"""

import pytest

from judge_worker.deterministic_judge import DeterministicJudge
from apps.device.judge_rules import handle_battery, handle_volume, handle_dnd, handle_mediacontrol
from apps.judge_helpers import handle_camera, handle_video, handle_app_state


def _build_metadata(
    jinju_battery_level=75,
    jinju_volume_current=7,
    jinju_volume_muted=False,
    pre_jinju_volume_current=None,
    pre_jinju_volume_muted=None,
    companion_media_playing=False,
    companion_media_position_ms=0,
    pre_companion_media_playing=None,
    pre_companion_media_position_ms=None,
    companion_dnd=False,
    pre_companion_dnd=None,
    jinju_image_captured=False,
    jinju_video_captured=False,
    app_state=None,
    question_type="online_device_battery_glasses",
    jinju_all_streams=None,
    pre_jinju_all_streams=None,
    companion_all_streams=None,
    pre_companion_all_streams=None,
):
    """Build metadata dict in the format DeterministicJudge expects.

    Media state and DND state live in the companion sub-device (not jinju), per
    _get_device_state() which routes mediacontrol and _dnd_ queries to companion.
    """
    # Build all_streams for jinju (default: MUSIC stream matching top-level)
    if jinju_all_streams is None:
        jinju_all_streams = {
            "STREAM_MUSIC": {"streamVolume": jinju_volume_current, "muted": jinju_volume_muted, "min": 0, "max": 15},
        }

    jinju_post = {
        "battery": {"level": jinju_battery_level, "status": "Discharging", "charging": False},
        "time": {"datetime_str": "Mon Aug 25 13:00:00 IST 2026", "timezone": "IST", "epoch_ms": 1756110000000},
        "date": {"day": 25, "month": "Aug", "year": 2026, "day_of_week": "Mon"},
        "volume": {"muted": jinju_volume_muted, "min": 0, "max": 15, "current": jinju_volume_current, "all_streams": jinju_all_streams},
    }
    companion_post = {
        "media": {
            "active": companion_media_playing,
            "playing": companion_media_playing,
            "state": "Playing" if companion_media_playing else "Paused",
            "position_ms": companion_media_position_ms,
        },
        "dnd_mode": "true" if companion_dnd else "false",
    }
    if companion_all_streams is not None:
        companion_post["volume"] = {"muted": False, "min": 0, "max": 15, "current": 7, "all_streams": companion_all_streams}

    jinju_pre = dict(jinju_post)
    companion_pre = dict(companion_post)
    if pre_jinju_volume_current is not None:
        pre_streams = pre_jinju_all_streams or {
            "STREAM_MUSIC": {"streamVolume": pre_jinju_volume_current, "muted": pre_jinju_volume_muted or False, "min": 0, "max": 15},
        }
        jinju_pre["volume"] = {"muted": pre_jinju_volume_muted or False, "min": 0, "max": 15, "current": pre_jinju_volume_current, "all_streams": pre_streams}
    if pre_companion_media_playing is not None:
        companion_pre["media"] = {
            "active": pre_companion_media_playing,
            "playing": pre_companion_media_playing,
            "state": "Playing" if pre_companion_media_playing else "Paused",
            "position_ms": pre_companion_media_position_ms or 0,
        }
    if pre_companion_dnd is not None:
        companion_pre["dnd_mode"] = "true" if pre_companion_dnd else "false"
    if pre_companion_all_streams is not None:
        companion_pre["volume"] = {"muted": False, "min": 0, "max": 15, "current": 7, "all_streams": pre_companion_all_streams}

    metadata = {
        "question_type": question_type,
        "device_info_pre": {"jinju": jinju_pre, "companion": companion_pre},
        "device_info_post": {"jinju": jinju_post, "companion": companion_post},
    }
    # Build app_state with log_analysis (unified state channel)
    if app_state is None:
        app_state = {}
    log_analysis = {}
    if jinju_image_captured:
        log_analysis["jinju_image_captured"] = True
    if jinju_video_captured:
        log_analysis["jinju_video_captured"] = True
    if log_analysis:
        app_state["log_analysis"] = log_analysis
    if app_state:
        metadata["app_state"] = app_state
    return metadata



# ── can_handle ────────────────────────────────────────────────────

def test_can_handle_device_time():
    # Compound feature: online_device_datetime_time → app="device", task="time"
    assert DeterministicJudge.can_handle("online_device_datetime_time") is True



def test_can_handle_samsung_notes_create():
    assert DeterministicJudge.can_handle("online_samsung_notes_create") is True


def test_can_handle_nonexistent():
    assert DeterministicJudge.can_handle("nonexistent_type") is False


# ── Battery handler ───────────────────────────────────────────────

def test_battery_correct():
    metadata = _build_metadata(jinju_battery_level=75, question_type="online_device_battery_glasses")
    rating, analysis = handle_battery("What's my battery?", "Your battery is at 75 percent", metadata)
    assert rating == 5


def test_battery_wrong():
    metadata = _build_metadata(jinju_battery_level=75, question_type="online_device_battery_glasses")
    rating, analysis = handle_battery("What's my battery?", "Battery is at 20 percent", metadata)
    assert rating == 1


def test_battery_no_percentage():
    metadata = _build_metadata(jinju_battery_level=75, question_type="online_device_battery_glasses")
    rating, analysis = handle_battery("What's my battery?", "I don't know", metadata)
    assert rating == 0


# ── Volume handler ─────────────────────────────────────────────────

def test_volume_up_success():
    metadata = _build_metadata(
        jinju_volume_current=7, pre_jinju_volume_current=5,
        question_type="online_device_volume_up",
    )
    rating, analysis = handle_volume("Turn up the volume", "Volume increased", metadata)
    assert rating == 5


def test_volume_up_unchanged():
    metadata = _build_metadata(
        jinju_volume_current=7, pre_jinju_volume_current=7,
        question_type="online_device_volume_up",
    )
    rating, analysis = handle_volume("Turn up the volume", "Volume increased", metadata)
    assert rating == 2


def test_volume_down_success():
    metadata = _build_metadata(
        jinju_volume_current=5, pre_jinju_volume_current=7,
        question_type="online_device_volume_down",
    )
    rating, analysis = handle_volume("Turn down the volume", "Volume decreased", metadata)
    assert rating == 5


def test_volume_mute_success():
    metadata = _build_metadata(
        jinju_volume_muted=True, pre_jinju_volume_muted=False,
        pre_jinju_volume_current=5,
        question_type="online_device_volume_mute",
    )
    rating, analysis = handle_volume("Mute the volume", "Muted", metadata)
    assert rating == 5


def test_volume_unmute_success():
    metadata = _build_metadata(
        jinju_volume_muted=False, pre_jinju_volume_muted=True,
        pre_jinju_volume_current=0,
        question_type="online_device_volume_unmute",
    )
    rating, analysis = handle_volume("Unmute the volume", "Unmuted", metadata)
    assert rating == 5


def test_volume_up_multistream_any_pass():
    """Multi-stream: MUSIC unchanged but ALARM increased → overall pass."""
    pre_streams = {
        "STREAM_MUSIC": {"streamVolume": 5, "muted": False, "min": 0, "max": 15},
        "STREAM_ALARM": {"streamVolume": 3, "muted": False, "min": 0, "max": 15},
    }
    post_streams = {
        "STREAM_MUSIC": {"streamVolume": 5, "muted": False, "min": 0, "max": 15},
        "STREAM_ALARM": {"streamVolume": 8, "muted": False, "min": 0, "max": 15},
    }
    metadata = _build_metadata(
        question_type="online_device_volume_up",
        jinju_all_streams=post_streams,
        pre_jinju_all_streams=pre_streams,
        pre_jinju_volume_current=5,
    )
    rating, analysis = handle_volume("Turn up the volume", "Volume increased", metadata)
    assert rating == 5


def test_volume_down_multistream_companion_pass():
    """Companion device stream decreased → overall pass even if jinju unchanged."""
    pre_streams = {
        "STREAM_MUSIC": {"streamVolume": 10, "muted": False, "min": 0, "max": 15},
    }
    post_streams = {
        "STREAM_MUSIC": {"streamVolume": 10, "muted": False, "min": 0, "max": 15},
    }
    pre_comp_streams = {
        "STREAM_MUSIC": {"streamVolume": 80, "muted": False, "min": 0, "max": 100},
    }
    post_comp_streams = {
        "STREAM_MUSIC": {"streamVolume": 50, "muted": False, "min": 0, "max": 100},
    }
    metadata = _build_metadata(
        question_type="online_device_volume_down",
        jinju_all_streams=post_streams,
        pre_jinju_all_streams=pre_streams,
        pre_jinju_volume_current=10,
        companion_all_streams=post_comp_streams,
        pre_companion_all_streams=pre_comp_streams,
    )
    rating, analysis = handle_volume("Turn down the volume", "Volume decreased", metadata)
    assert rating == 5


def test_volume_set_multistream():
    """Set to 50% — MUSIC at 7/15 should match (threshold=1)."""
    post_streams = {
        "STREAM_MUSIC": {"streamVolume": 7, "muted": False, "min": 0, "max": 15},
    }
    metadata = _build_metadata(
        question_type="online_device_volume_set",
        jinju_all_streams=post_streams,
        jinju_volume_current=7,
    )
    rating, analysis = handle_volume("Set volume to 50%", "Volume set", metadata)
    assert rating == 5


def test_volume_mute_multistream():
    """Mute: one stream transitions to muted → pass."""
    pre_streams = {
        "STREAM_MUSIC": {"streamVolume": 5, "muted": False, "min": 0, "max": 15},
        "STREAM_RING": {"streamVolume": 7, "muted": False, "min": 0, "max": 7},
    }
    post_streams = {
        "STREAM_MUSIC": {"streamVolume": 5, "muted": False, "min": 0, "max": 15},
        "STREAM_RING": {"streamVolume": 0, "muted": True, "min": 0, "max": 7},
    }
    metadata = _build_metadata(
        question_type="online_device_volume_mute",
        jinju_all_streams=post_streams,
        pre_jinju_all_streams=pre_streams,
        jinju_volume_current=5,
        pre_jinju_volume_current=5,
    )
    rating, analysis = handle_volume("Mute the volume", "Muted", metadata)
    assert rating == 5


# ── DND handler ───────────────────────────────────────────────────

def test_dnd_on_success():
    metadata = _build_metadata(
        companion_dnd=True, pre_companion_dnd=False,
        question_type="online_device_dnd_on",
    )
    rating, analysis = handle_dnd("Turn on DND", "DND is on", metadata)
    assert rating == 5


def test_dnd_off_success():
    metadata = _build_metadata(
        companion_dnd=False, pre_companion_dnd=True,
        question_type="online_device_dnd_off",
    )
    rating, analysis = handle_dnd("Turn off DND", "DND is off", metadata)
    assert rating == 5


def test_dnd_on_failed():
    metadata = _build_metadata(
        companion_dnd=False, pre_companion_dnd=False,
        question_type="online_device_dnd_on",
    )
    rating, analysis = handle_dnd("Turn on DND", "DND is on", metadata)
    assert rating == 0


# ── Camera handler ────────────────────────────────────────────────

def test_camera_captured():
    metadata = _build_metadata(jinju_image_captured=True, question_type="online_samsung_camera_click")
    rating, analysis = handle_camera("Take a photo", "Photo taken", metadata)
    assert rating == 5


def test_camera_not_captured():
    metadata = _build_metadata(jinju_image_captured=False, question_type="online_samsung_camera_click")
    rating, analysis = handle_camera("Take a photo", "Photo taken", metadata)
    assert rating == 1


# ── Video handler ─────────────────────────────────────────────────

def test_video_captured():
    metadata = _build_metadata(jinju_video_captured=True, question_type="online_samsung_camera_videostart")
    rating, analysis = handle_video("Start recording", "Recording started", metadata)
    assert rating == 5


def test_video_not_captured():
    metadata = _build_metadata(jinju_video_captured=False, question_type="online_samsung_camera_videostart")
    rating, analysis = handle_video("Start recording", "Recording started", metadata)
    assert rating == 1


# ── App state handler ─────────────────────────────────────────────

def test_app_state_verified():
    app_state = {
        "method": "xrclaw",
        "app_name": "samsungnote",
        "verified": True,
        "rating": 5,
        "analysis": "Note found with matching content.",
        "actual_state": {"notes": []},
        "expected": "A note titled 'Test'",
    }
    metadata = _build_metadata(app_state=app_state, question_type="online_samsung_notes_create")
    rating, analysis = handle_app_state("Create a note", "Note created", metadata)
    assert rating == 5


def test_app_state_missing():
    metadata = _build_metadata(app_state=None, question_type="online_samsung_notes_create")
    rating, analysis = handle_app_state("Create a note", "Note created", metadata)
    assert rating == 0


def test_app_state_error_method():
    app_state = {
        "method": "xrclaw_error",
        "app_name": "samsungnote",
        "verified": False,
        "rating": 0,
        "analysis": "Error",
        "actual_state": {},
        "expected": "test",
    }
    metadata = _build_metadata(app_state=app_state, question_type="online_samsung_notes_create")
    rating, analysis = handle_app_state("Create a note", "Note created", metadata)
    assert rating == 0


# ── Media control handler ─────────────────────────────────────────

def test_media_play_success():
    metadata = _build_metadata(
        companion_media_playing=True, pre_companion_media_playing=False,
        question_type="online_device_mediacontrol_play",
    )
    rating, analysis = handle_mediacontrol("Play music", "Playing", metadata)
    assert rating == 5


def test_media_pause_success():
    metadata = _build_metadata(
        companion_media_playing=False, pre_companion_media_playing=True,
        question_type="online_device_mediacontrol_pause",
    )
    rating, analysis = handle_mediacontrol("Pause music", "Paused", metadata)
    assert rating == 5

