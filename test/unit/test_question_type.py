"""
Tests for common/question_type.py — QuestionType parsing.

Tests 4-part format, 5-part compound features, device queries,
and edge cases (too short, empty).
"""

import pytest

from common.question_type import QuestionType


# ── 4-part format ──────────────────────────────────────────────────

def test_four_part_samsung_notes():
    qt = QuestionType.parse("online_samsung_notes_create")
    assert qt.connectivity == "online"
    assert qt.group == "samsung"
    assert qt.feature == "notes"
    assert qt.action == "create"


def test_four_part_device_volume():
    qt = QuestionType.parse("online_device_volume_up")
    assert qt.group == "device"
    assert qt.feature == "volume"
    assert qt.action == "up"
    assert qt.is_device_query is True


def test_four_part_device_battery():
    qt = QuestionType.parse("online_device_battery_glasses")
    assert qt.group == "device"
    assert qt.feature == "battery"
    assert qt.action == "glasses"


# ── 5-part compound features ───────────────────────────────────────

def test_compound_clock_timer():
    qt = QuestionType.parse("online_samsung_clock_timer_create")
    assert qt.feature == "clock_timer"
    assert qt.action == "create"
    assert qt.is_compound_feature is True


def test_compound_clock_alarm():
    qt = QuestionType.parse("online_samsung_clock_alarm_create")
    assert qt.feature == "clock_alarm"
    assert qt.action == "create"
    assert qt.is_compound_feature is True


def test_compound_clock_stopwatch():
    qt = QuestionType.parse("online_samsung_clock_stopwatch_start")
    assert qt.feature == "clock_stopwatch"
    assert qt.action == "start"


# ── Edge cases ─────────────────────────────────────────────────────

def test_too_short():
    qt = QuestionType.parse("abc")
    assert qt.connectivity == "abc"
    assert qt.group == ""
    assert qt.feature == ""
    assert qt.action == ""
    assert qt.app_key is None


def test_empty_string():
    qt = QuestionType.parse("")
    assert qt.connectivity == ""
    assert qt.group == ""
    assert qt.app_key is None


def test_none_string():
    qt = QuestionType.parse(None)
    assert qt.raw == ""
    assert qt.connectivity == ""


# ── Properties ─────────────────────────────────────────────────────

def test_is_device_query_true():
    qt = QuestionType.parse("online_device_volume_up")
    assert qt.is_device_query is True


def test_is_device_query_false():
    qt = QuestionType.parse("online_samsung_notes_create")
    assert qt.is_device_query is False


def test_is_compound_feature_true():
    qt = QuestionType.parse("online_samsung_clock_timer_create")
    assert qt.is_compound_feature is True


def test_is_compound_feature_false():
    qt = QuestionType.parse("online_samsung_notes_create")
    assert qt.is_compound_feature is False


# ── App key resolution ─────────────────────────────────────────────

def test_app_key_resolved_for_notes():
    qt = QuestionType.parse("online_samsung_notes_create")
    assert qt.app_key is not None
    assert "note" in qt.app_key.lower()


def test_app_key_resolved_for_device():
    qt = QuestionType.parse("online_device_volume_up")
    assert qt.app_key is not None
    assert "device" in qt.app_key.lower()


# ── Consumers that used to parse the string themselves ─────────────
# Each of these once had its own split("_") parser; this table pins what
# they must keep returning now that they all go through QuestionType.

@pytest.mark.parametrize("question_type, handler_key, task_key, filter_feature", [
    ("online_samsung_notes_create", ("samsungnote", "create"), "create", "unknown"),
    ("online_samsung_clock_timer_create", ("clocktimer", "create"), "create", "unknown"),
    ("online_samsung_clock_launch", ("clockalarm", "launch"), "launch", "unknown"),
    ("online_samsung_message_thread_read", ("message", "thread"), "thread_read", "unknown"),
    ("online_device_volume_up", ("device", "up"), "up", "volume"),
    ("online_device_datetime_time", ("device", "time"), "time", "datetime_time"),
    ("online_device_mediacontrol_like", ("device", "like"), "like", "mediacontrol_like_dislike"),
    ("online_device_camera_click", ("device", "click"), "click", "camera"),
])
def test_consumer_views(question_type, handler_key, task_key, filter_feature):
    from judge_worker.deterministic_judge import _handler_key
    from judge_worker.device_info_filter import _get_feature

    qt = QuestionType.parse(question_type)
    assert _handler_key(question_type) == handler_key
    assert qt.action_with_suffix == task_key
    assert _get_feature(question_type) == filter_feature


@pytest.mark.parametrize("question_type, target", [
    ("online_device_battery_glasses", "jinju"),
    ("online_device_battery_phone", "companion"),
    ("online_device_battery_companion", "companion"),
])
def test_battery_target(question_type, target):
    from judge_worker.device_info_filter import _resolve_battery_target
    assert _resolve_battery_target(question_type) == target
