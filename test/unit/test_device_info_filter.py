"""
Unit tests for judge_worker.device_info_filter.filter_device_info()

Tests that the filter correctly extracts only the relevant device state fields
for a given question_type, and outputs them in compact XML format.
"""

import json

import pytest

from judge_worker.device_info_filter import filter_device_info


# ── Fixtures ────────────────────────────────────────────────────────

SAMPLE_DEVICE_INFO = {
    "jinju": {
        "battery": {
            "level": 100,
            "status": "Full",
            "charging": True,
        },
        "time": {
            "datetime_str": "Thu Aug 27 21:21:14 IST 2026",
            "timezone": "IST",
            "epoch_ms": 1787845874408,
        },
        "date": {
            "day": 27,
            "month": "Aug",
            "year": 2026,
            "day_of_week": "Thu",
        },
        "volume": {
            "muted": False,
            "min": 0,
            "max": 100,
            "current": 29,
            "all_streams": {
                "STREAM_MUSIC": {"streamVolume": 29, "muted": False, "min": 0, "max": 100},
                "STREAM_RING": {"streamVolume": 5, "muted": False, "min": 0, "max": 7},
                "STREAM_ALARM": {"streamVolume": 3, "muted": False, "min": 0, "max": 15},
            },
        },
    },
    "companion": {
        "dnd_mode": "false",
        "battery": {
            "level": 85,
            "status": "Discharging",
            "charging": False,
        },
        "media": {
            "active": True,
            "playing": False,
            "state": "Paused",
            "package": "com.google.android.apps.youtube.music",
            "title": "Far Away Across The Sea",
            "artist": "Sierra Ferrell",
            "album": "Long Time Coming",
            "position_ms": 65849,
            "speed": 1.0,
            "last_audio_package": "com.google.android.googlequicksearchbox",
        },
    },
    "captured_at_epoch": 1787827252994,
}


# ── Volume queries ──────────────────────────────────────────────────

class TestVolumeFilter:
    def test_volume_up_returns_only_volume_pre_post(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_up")
        assert "<volume" in result
        assert "current=" in result
        # Should NOT contain battery, time, date, media, dnd
        assert "battery" not in result.lower()
        assert "datetime_str" not in result
        assert "media" not in result.lower()
        assert "dnd" not in result.lower()

    def test_volume_down_returns_only_volume(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "offline_device_volume_down")
        assert "<volume" in result
        assert "battery" not in result.lower()

    def test_volume_set_returns_only_volume(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_set")
        assert "<volume" in result

    def test_volume_uprelative_returns_only_volume(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_uprelative")
        assert "<volume" in result

    def test_volume_downrelative_returns_only_volume(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_downrelative")
        assert "<volume" in result

    def test_volume_mute_returns_only_volume(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_mute")
        assert "<volume" in result
        assert "muted=" in result

    def test_volume_unmute_returns_only_volume(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_unmute")
        assert "<volume" in result
        assert "muted=" in result

    def test_volume_includes_all_streams(self):
        """Volume XML should include <stream> child elements for all_streams."""
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_up")
        assert "<stream " in result
        assert "STREAM_MUSIC" in result
        assert "STREAM_RING" in result
        assert "streamVolume=" in result

    def test_volume_query_has_pre_and_post(self):
        """Volume needs pre+post comparison."""
        pre = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        pre["jinju"]["volume"]["current"] = 66
        post = SAMPLE_DEVICE_INFO

        result_pre = filter_device_info(pre, "online_device_volume_up")
        result_post = filter_device_info(post, "online_device_volume_up")
        assert "current=\"66\"" in result_pre
        assert "current=\"29\"" in result_post


# ── Time/Date queries ────────────────────────────────────────────────

class TestTimeDateFilter:
    def test_time_query_returns_only_time(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_datetime_time")
        assert "datetime_str=" in result
        assert "timezone=" in result
        assert "volume" not in result.lower()
        assert "battery" not in result.lower()
        assert "media" not in result.lower()

    def test_date_query_returns_only_date(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_datetime_date")
        assert "day=" in result
        assert "month=" in result
        assert "year=" in result
        assert "volume" not in result.lower()
        assert "battery" not in result.lower()

    def test_time_query_post_only(self):
        """Time queries only need post state (no pre comparison)."""
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_datetime_time")
        assert "<device_state>" in result
        assert "<device_state_pre>" not in result


# ── Battery queries ──────────────────────────────────────────────────

class TestBatteryFilter:
    def test_battery_glasses_returns_jinju_battery(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_battery_glasses")
        assert "level=" in result
        assert "100" in result  # jinju battery level
        assert "85" not in result  # companion battery level should NOT be present
        assert "volume" not in result.lower()
        assert "media" not in result.lower()

    def test_battery_companion_returns_companion_battery(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_battery_companion")
        assert "level=" in result
        assert "85" in result  # companion battery level
        assert "100" not in result  # jinju battery level should NOT be present
        assert "volume" not in result.lower()

    def test_battery_phone_returns_companion_battery(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_battery_phone")
        assert "level=" in result
        assert "85" in result


# ── DND queries ──────────────────────────────────────────────────────

class TestDNDFilter:
    def test_dnd_on_returns_dnd_pre_post(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_dnd_on")
        assert "dnd_mode" in result
        assert "false" in result  # current value
        assert "volume" not in result.lower()
        assert "battery" not in result.lower()
        assert "media" not in result.lower()

    def test_dnd_off_returns_dnd(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_dnd_off")
        assert "dnd_mode" in result


# ── Media control queries ────────────────────────────────────────────

class TestMediaControlFilter:
    @pytest.mark.parametrize("action", [
        "play", "pause", "resume", "replay", "previous", "skip",
        "like", "dislike", "seek", "seekrelative",
    ])
    def test_mediacontrol_returns_only_media(self, action):
        qt = f"online_device_mediacontrol_{action}"
        result = filter_device_info(SAMPLE_DEVICE_INFO, qt)
        assert "playing=" in result
        assert "state=" in result
        assert "title=" in result
        assert "artist=" in result
        assert "position_ms=" in result
        # Should NOT contain volume, battery, time, date, dnd
        assert "volume" not in result.lower()
        assert "battery" not in result.lower()
        assert "datetime_str" not in result
        assert "dnd_mode" not in result

    def test_mediacontrol_has_pre_and_post(self):
        """Media control needs pre+post comparison.

        filter_device_info is called once per snapshot (pre and post separately).
        Each call returns a <device_state> block. The caller (response_scorer)
        is responsible for labeling them as pre/post.
        """
        pre = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        pre["companion"]["media"]["playing"] = False
        post = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        post["companion"]["media"]["playing"] = True

        result_pre = filter_device_info(pre, "online_device_mediacontrol_play")
        result_post = filter_device_info(post, "online_device_mediacontrol_play")
        assert "<device_state>" in result_pre
        assert "<device_state>" in result_post
        assert "playing=\"false\"" in result_pre
        assert "playing=\"true\"" in result_post



# ── Notification / Camera / Video queries ───────────────────────────

class TestNoDeviceInfo:
    def test_notification_read_returns_empty(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_notification_read")
        assert result == ""

    def test_notification_notread_returns_empty(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_notification_notread")
        assert result == ""

    def test_notification_auto_returns_empty(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_notification_auto")
        assert result == ""

    def test_camera_returns_empty(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_camera_click")
        assert result == ""

    def test_video_returns_empty(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_video_videostart")
        assert result == ""


# ── Edge cases ──────────────────────────────────────────────────────

class TestEdgeCases:
    def test_none_device_info_returns_empty(self):
        result = filter_device_info(None, "online_device_volume_up")
        assert result == ""

    def test_empty_dict_returns_empty(self):
        result = filter_device_info({}, "online_device_volume_up")
        assert result == ""

    def test_unknown_feature_returns_full_json(self):
        """Unknown features fall back to full JSON for safety."""
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_unknown_feature")
        assert "jinju" in result
        assert "companion" in result
        assert "battery" in result

    def test_unknown_question_type_returns_full_json(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "some_random_type")
        assert "jinju" in result

    def test_missing_volume_field_returns_empty(self):
        """If device_info exists but volume field is missing, return empty."""
        info = {"jinju": {"battery": {"level": 50}}, "companion": {}}
        result = filter_device_info(info, "online_device_volume_up")
        assert result == ""

    def test_missing_media_field_returns_empty(self):
        info = {"jinju": {}, "companion": {"dnd_mode": "false"}}
        result = filter_device_info(info, "online_device_mediacontrol_play")
        assert result == ""


# ── Output format ───────────────────────────────────────────────────

class TestOutputFormat:
    def test_output_is_xml_not_json(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_up")
        assert "<device_state" in result
        assert "{" not in result  # No JSON braces

    def test_volume_output_has_attributes(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_volume_up")
        assert "muted=" in result
        assert "min=" in result
        assert "max=" in result
        assert "current=" in result

    def test_media_output_has_attributes(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_mediacontrol_play")
        assert "active=" in result
        assert "playing=" in result
        assert "state=" in result
        assert "package=" in result
        assert "title=" in result
        assert "artist=" in result
        assert "position_ms=" in result

    def test_battery_output_has_attributes(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_battery_glasses")
        assert "level=" in result
        assert "status=" in result
        assert "charging=" in result

    def test_time_output_has_attributes(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_datetime_time")
        assert "datetime_str=" in result
        assert "timezone=" in result

    def test_date_output_has_attributes(self):
        result = filter_device_info(SAMPLE_DEVICE_INFO, "online_device_datetime_date")
        assert "day=" in result
        assert "month=" in result
        assert "year=" in result
        assert "day_of_week=" in result
