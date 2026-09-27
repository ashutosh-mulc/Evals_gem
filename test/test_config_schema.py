"""
Tests for config/schema.py — Pydantic config validation.

Tests that:
- Valid configs load correctly
- Invalid configs raise clear errors
- Default values are sensible
- Runtime validations (indices, ARAP devices) work
- Round-trip (load -> dump -> load) preserves data
"""

import json
import os
import tempfile
import pytest

from common.schema import AppConfig, Constants


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_config_dict():
    """A minimal valid config dict matching the template."""
    return {
        "device_manager_type": "jinju-gemini",
        "dataset_start_index": 0,
        "dataset_end_index": 100,
        "logger": {
            "dump_device_logs": True,
            "logger_level": "debug",
        },
        "paths": {
            "dataset_file": "/data/dataset.jsonl",
            "root_folder": "/data/results",
            "queue_file": "/tmp/queue.db",
            "queue_backup_folder": "/tmp/backup",
            "backup_folder_path": "/tmp/backup_storage/",
        },
        "devices": {
            "s25_device_id": "R3CX80TTTCX",
            "jinju_device_id": "4103d783bb2a9c00",
            "arap": {
                "use_robohead": True,
                "robopod_url": "http://localhost:8000",
                "record_duration": 30,
                "devices": ["R3CY40XBDZM"],
            },
        },
        "urls": {
            "transcription_url": "http://localhost:8080",
            "judge_url": "http://localhost:8282/v1",
            "rating_rectifier_url": "",
            "display_port": 5050,
        },
        "message_service": {"wait_time": 5},
        "judge_worker": {
            "vllm_api": True,
            "qa_prompt_version": ["1.0"],
            "vqa_prompt_version": ["2.0"],
            "hqa_prompt_version": ["1.0"],
            "appEval_prompt_version": ["1.0"],
        },
        "xrclaw": {
            "enabled": False,
            "python_automation_path": "",
        },
        "automator": {
            "num_evaluations": 3,
            "postprocess_only": False,
            "generate_reports": True,
            "xr_board": {
                "generate_reports": False,
                "upload_files": False,
                "user_id": "test_user",
                "companion_pair": "jinju/gemini-live-s25",
                "kpi_type": "kpi",
                "dataset_name": "test_dataset",
                "judge_name": "test_judge",
            },
        },
    }


# ── Basic loading tests ──────────────────────────────────────────────────────

class TestAppConfigLoading:
    def test_load_valid_config(self, valid_config_dict):
        config = AppConfig.from_dict(valid_config_dict)
        assert config.device_manager_type == "jinju-gemini"
        assert config.dataset_start_index == 0
        assert config.dataset_end_index == 100

    def test_load_from_json_file(self, valid_config_dict, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(valid_config_dict))
        config = AppConfig.from_json_file(str(config_path))
        assert config.device_manager_type == "jinju-gemini"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            AppConfig.from_json_file("/nonexistent/path/config.json")

    def test_defaults_applied(self):
        """Minimal dict should get all defaults."""
        config = AppConfig.from_dict({})
        assert config.device_manager_type == ""
        assert config.dataset_start_index == 0
        assert config.dataset_end_index == 10000
        assert config.logger.dump_device_logs is False
        assert config.logger.logger_level == ""
        assert config.message_service.wait_time == Constants.DEFAULT_WAIT_TIME
        assert config.xrclaw.enabled is False
        assert config.automator.num_evaluations == 0

    def test_nested_defaults(self):
        """Nested objects get their defaults."""
        config = AppConfig.from_dict({"devices": {}})
        assert config.devices.s25_device_id == ""
        assert config.devices.jinju_device_id == ""
        assert config.devices.arap.use_robohead is False
        assert config.devices.arap.devices == []

    def test_extra_fields_ignored(self):
        """Unknown fields should be ignored (not raise)."""
        config = AppConfig.from_dict({"unknown_field": 42, "device_manager_type": "test"})
        assert config.device_manager_type == "test"


# ── Validation tests ─────────────────────────────────────────────────────────

class TestAppConfigValidation:
    def test_negative_index_rejected(self):
        with pytest.raises(Exception):
            AppConfig.from_dict({"dataset_start_index": -1})

    def test_invalid_logger_level_rejected(self):
        with pytest.raises(Exception):
            AppConfig.from_dict({"logger": {"logger_level": "verbose"}})

    def test_empty_logger_level_allowed(self):
        config = AppConfig.from_dict({"logger": {"logger_level": ""}})
        assert config.logger.logger_level == ""

    def test_validate_indices_pass(self, valid_config_dict):
        config = AppConfig.from_dict(valid_config_dict)
        config.validate_indices()  # should not raise

    def test_validate_indices_fail(self):
        config = AppConfig.from_dict({"dataset_start_index": 10, "dataset_end_index": 5})
        with pytest.raises(ValueError, match="start_index.*end_index"):
            config.validate_indices()

    def test_validate_runtime_pass(self, valid_config_dict):
        config = AppConfig.from_dict(valid_config_dict)
        config.validate_runtime()  # should not raise

    def test_validate_arap_devices_robohead_ok(self):
        """When use_robohead=True, device count doesn't matter."""
        config = AppConfig.from_dict({
            "devices": {"arap": {"use_robohead": True, "devices": []}}
        })
        config.validate_arap_devices()  # should not raise

    def test_validate_arap_devices_no_devices_fails(self):
        config = AppConfig.from_dict({
            "devices": {"arap": {"use_robohead": False, "devices": []}}
        })
        with pytest.raises(ValueError, match="ARAP devices count"):
            config.validate_arap_devices()

    def test_validate_arap_devices_too_many_fails(self):
        config = AppConfig.from_dict({
            "devices": {"arap": {"use_robohead": False, "devices": ["a", "b", "c"]}}
        })
        with pytest.raises(ValueError, match="ARAP devices count"):
            config.validate_arap_devices()

    def test_validate_arap_devices_correct_count(self):
        config = AppConfig.from_dict({
            "devices": {"arap": {"use_robohead": False, "devices": ["a", "b"]}}
        })
        config.validate_arap_devices()  # should not raise


# ── Round-trip tests ─────────────────────────────────────────────────────────

class TestAppConfigRoundTrip:
    def test_round_trip_preserves_data(self, valid_config_dict, tmp_path):
        config = AppConfig.from_dict(valid_config_dict)
        out_path = tmp_path / "out.json"
        config.to_json_file(str(out_path))

        config2 = AppConfig.from_json_file(str(out_path))
        assert config2.device_manager_type == config.device_manager_type
        assert config2.devices.s25_device_id == config.devices.s25_device_id
        assert config2.judge_worker.vllm_api == config.judge_worker.vllm_api
        assert config2.automator.xr_board.user_id == config.automator.xr_board.user_id

    def test_to_dict_returns_plain_dict(self, valid_config_dict):
        config = AppConfig.from_dict(valid_config_dict)
        d = config.to_dict()
        assert isinstance(d, dict)
        assert d["device_manager_type"] == "jinju-gemini"
        assert isinstance(d["devices"], dict)
        assert isinstance(d["devices"]["arap"], dict)


# ── Constants tests ──────────────────────────────────────────────────────────

class TestConstants:
    def test_constants_exist(self):
        assert Constants.COOLDOWN_EVERY_N == 50
        assert Constants.COOLDOWN_SECONDS == 300
        assert Constants.JUDGE_MAX_TOKENS_VLLM == 18192
        assert Constants.DEFAULT_ADB_TIMEOUT == 30

    def test_arap_bounds(self):
        assert Constants.MIN_ARAP_DEVICES == 1
        assert Constants.MAX_ARAP_DEVICES == 2
