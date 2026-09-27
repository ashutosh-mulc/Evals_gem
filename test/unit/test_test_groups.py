"""
Unit tests for common.test_groups — test group registry and dataset filtering.

Tests that:
1. All test groups have required fields
2. Group patterns match question_types in the dataset
3. get_group_for_question_type() resolves correctly
4. filter_dataset_by_group() filters correctly
5. list_groups() returns sorted names
6. Config "test_groups" field is parsed correctly
"""

import json

import pytest

from common.test_groups import (
    TestGroup,
    TEST_GROUPS,
    get_group_for_question_type,
    filter_dataset_by_group,
    list_groups,
    resolve_config_groups,
)


# ── Registry structure ─────────────────────────────────────────────

class TestRegistryStructure:
    def test_registry_nonempty(self):
        assert len(TEST_GROUPS) > 0

    def test_all_groups_have_required_fields(self):
        for name, group in TEST_GROUPS.items():
            assert group.name == name, f"Group key '{name}' doesn't match group.name '{group.name}'"
            assert group.description, f"Group '{name}' has empty description"
            assert group.patterns, f"Group '{name}' has no patterns"
            assert isinstance(group.patterns, list), f"Group '{name}' patterns is not a list"
            assert group.app_keys, f"Group '{name}' has no app_keys"

    def test_no_duplicate_group_names(self):
        names = [g.name for g in TEST_GROUPS.values()]
        assert len(names) == len(set(names))

    def test_list_groups_returns_sorted(self):
        names = list_groups()
        assert names == sorted(names)

    def test_list_groups_returns_list(self):
        assert isinstance(list_groups(), list)


# ── Group resolution ───────────────────────────────────────────────

class TestGroupResolution:
    def test_volume_question_resolves_to_volume_group(self):
        assert get_group_for_question_type("online_device_volume_up") == "volume"

    def test_camera_question_resolves_to_camera_group(self):
        assert get_group_for_question_type("online_device_camera_click") == "camera"

    def test_mediacontrol_resolves_to_music_group(self):
        assert get_group_for_question_type("online_device_mediacontrol_play") == "music"

    def test_notification_resolves_to_notifications_group(self):
        assert get_group_for_question_type("online_device_notification_read") == "notifications"

    def test_datetime_time_resolves_to_datetime_group(self):
        assert get_group_for_question_type("online_device_datetime_time") == "datetime"

    def test_battery_resolves_to_battery_group(self):
        assert get_group_for_question_type("online_device_battery_glasses") == "battery"

    def test_dnd_resolves_to_dnd_group(self):
        assert get_group_for_question_type("online_device_dnd_on") == "dnd"

    def test_samsung_notes_resolves_to_notes_group(self):
        assert get_group_for_question_type("online_samsung_notes_create") == "notes"

    def test_samsung_reminders_resolves_to_reminders_group(self):
        assert get_group_for_question_type("online_samsung_reminders_create") == "reminders"

    def test_google_maps_resolves_to_maps_group(self):
        assert get_group_for_question_type("online_google_maps_search") == "maps"

    def test_clock_launch_resolves_to_clock_group(self):
        assert get_group_for_question_type("online_samsung_clock_launch") == "clock"

    def test_clock_alarm_resolves_to_clock_group(self):
        assert get_group_for_question_type("online_samsung_clock_alarm_create") == "clock"

    def test_clock_timer_resolves_to_clock_group(self):
        assert get_group_for_question_type("online_samsung_clock_timer_create") == "clock"

    def test_clock_stopwatch_resolves_to_clock_group(self):
        assert get_group_for_question_type("online_samsung_clock_stopwatch_start") == "clock"

    def test_unknown_question_type_returns_none(self):
        assert get_group_for_question_type("some_unknown_type") is None

    def test_empty_question_type_returns_none(self):
        assert get_group_for_question_type("") is None


# ── Dataset filtering ──────────────────────────────────────────────

SAMPLE_DATASET = [
    {"eval_id": "q00001", "question_type": "online_device_volume_up", "question": "Turn up the volume"},
    {"eval_id": "q00002", "question_type": "online_device_volume_down", "question": "Turn down the volume"},
    {"eval_id": "q00003", "question_type": "online_device_camera_click", "question": "Take a photo"},
    {"eval_id": "q00004", "question_type": "online_device_mediacontrol_play", "question": "Play music"},
    {"eval_id": "q00005", "question_type": "online_samsung_notes_create", "question": "Create a note"},
    {"eval_id": "q00006", "question_type": "online_device_notification_read", "question": "Read my notifications"},
    {"eval_id": "q00007", "question_type": "online_device_datetime_time", "question": "What time is it?"},
    {"eval_id": "q00008", "question_type": "online_device_battery_glasses", "question": "What's the battery?"},
    {"eval_id": "q00009", "question_type": "online_samsung_clock_launch", "question": "Open the clock app"},
    {"eval_id": "q00010", "question_type": "online_samsung_clock_alarm_create", "question": "Set an alarm"},
]


class TestDatasetFiltering:
    def test_filter_by_volume_group(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "volume")
        ids = [e["eval_id"] for e in filtered]
        assert "q00001" in ids
        assert "q00002" in ids
        assert "q00003" not in ids

    def test_filter_by_camera_group(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "camera")
        ids = [e["eval_id"] for e in filtered]
        assert "q00003" in ids
        assert len(filtered) == 1

    def test_filter_by_music_group(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "music")
        ids = [e["eval_id"] for e in filtered]
        assert "q00004" in ids

    def test_filter_by_notes_group(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "notes")
        ids = [e["eval_id"] for e in filtered]
        assert "q00005" in ids

    def test_filter_by_multiple_groups(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, ["volume", "camera"])
        ids = [e["eval_id"] for e in filtered]
        assert "q00001" in ids
        assert "q00002" in ids
        assert "q00003" in ids
        assert "q00004" not in ids

    def test_filter_by_clock_group_includes_launch(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "clock")
        ids = [e["eval_id"] for e in filtered]
        assert "q00009" in ids  # clock_launch
        assert "q00010" in ids  # clock_alarm_create

    def test_filter_unknown_group_returns_empty(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "nonexistent")
        assert filtered == []

    def test_filter_preserves_entry_structure(self):
        filtered = filter_dataset_by_group(SAMPLE_DATASET, "volume")
        assert all("eval_id" in e and "question_type" in e for e in filtered)


# ── Config resolution ──────────────────────────────────────────────

class TestConfigResolution:
    def test_resolve_single_group_string(self):
        config = {"test_groups": "volume"}
        groups = resolve_config_groups(config)
        assert groups == ["volume"]

    def test_resolve_multiple_groups_list(self):
        config = {"test_groups": ["volume", "camera", "music"]}
        groups = resolve_config_groups(config)
        assert groups == ["volume", "camera", "music"]

    def test_resolve_comma_separated_string(self):
        config = {"test_groups": "volume,camera,music"}
        groups = resolve_config_groups(config)
        assert groups == ["volume", "camera", "music"]

    def test_resolve_no_test_groups_key_returns_none(self):
        config = {}
        groups = resolve_config_groups(config)
        assert groups is None

    def test_resolve_empty_string_returns_none(self):
        config = {"test_groups": ""}
        groups = resolve_config_groups(config)
        assert groups is None

    def test_resolve_all_keyword_returns_all(self):
        config = {"test_groups": "all"}
        groups = resolve_config_groups(config)
        assert groups is None  # "all" means no filtering

    def test_resolve_validates_group_names(self):
        config = {"test_groups": "volume,nonexistent"}
        with pytest.raises(ValueError, match="Unknown test group"):
            resolve_config_groups(config)
