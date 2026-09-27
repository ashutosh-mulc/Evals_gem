"""
Config schema — Pydantic models for MAIRE configuration validation.

Validates the JSON config at startup so errors are caught early with readable
messages instead of cryptic KeyError/AttributeError at runtime.

Usage:
    from common.schema import AppConfig

    config = AppConfig.from_json_file("configs/jinju_gemini_config.json")
    # All fields validated; access via config.paths.dataset_file, etc.

The JSON files on disk remain unchanged — this is a read-side validation layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


# ── Named constants (extracted from magic numbers scattered in code) ──────────

class Constants:
    """Magic numbers that were previously hardcoded across the codebase."""

    # AgentTester: cooldown after every N test cases
    COOLDOWN_EVERY_N: int = 50
    COOLDOWN_SECONDS: int = 300

    # Judge worker: LLM generation limits
    JUDGE_MAX_TOKENS_VLLM: int = 18192
    JUDGE_MAX_TOKENS_NON_VLLM: int = 20000
    JUDGE_TOP_LOGPROBS: int = 5
    JUDGE_TOP_K: int = 20
    JUDGE_TOP_P: float = 0.95
    JUDGE_PRESENCE_PENALTY_VLLM: float = 1.5
    JUDGE_FREQUENCY_PENALTY_NON_VLLM: float = 0.7
    JUDGE_PRESENCE_PENALTY_NON_VLLM: float = 0.1

    # Message service
    DEFAULT_WAIT_TIME: int = 5

    # ADB
    DEFAULT_ADB_TIMEOUT: int = 30  # seconds

    # ARAP
    MIN_ARAP_DEVICES: int = 1
    MAX_ARAP_DEVICES: int = 2

    HEIRARCHY_QTYPES: list = [
        "online_device_volume_up",
        "online_device_volume_down",
        "online_device_volume_set",
        "online_device_volume_uprelative",
        "online_device_volume_downrelative",
        "online_device_volume_mute",
        "online_device_volume_unmute",
        "online_device_datetime_time",
        "online_device_datetime_date",
        "online_device_battery_glasses",
        "online_device_battery_companion",
        "online_device_dnd_on",
        "online_device_dnd_off",
        "online_device_notification_read",
        "online_device_notification_notread",
        "online_device_notification_auto",
        "online_samsung_camera_click",
        "online_samsung_camera_videostart",
        "online_samsung_camera_videostop",
        "online_device_mediacontrol_play",
        "online_device_mediacontrol_pause",
        "online_device_mediacontrol_resume",
        "online_device_mediacontrol_replay",
        "online_device_mediacontrol_previous",
        "online_device_mediacontrol_skip",
        "online_samsung_call_launch",
        "online_samsung_call_send",
        "online_samsung_call_send",
        "online_samsung_call_disambiguation",
        "online_samsung_call_notsend",
        "online_samsung_call_videostart",
        "online_samsung_message_launch",
        "online_samsung_message_read",
        "online_samsung_message_send",
        "online_samsung_message_draft",
        "online_samsung_message_disambiguation",
        "online_samsung_message_notsend",
        "online_samsung_calendar_launch",
        "online_samsung_calendar_read",
        "online_samsung_calendar_create",
        "online_samsung_calendar_modify",
        "online_samsung_calendar_delete",
        "online_samsung_reminder_launch",
        "online_samsung_reminder_create",
        "online_samsung_reminder_modify",
        "online_samsung_reminder_delete",
        "online_samsung_reminder_read",
        "online_samsung_reminder_noread",
        "online_samsung_notes_launch",
        "online_samsung_notes_create",
        "online_samsung_notes_visualcreate",
        "online_samsung_notes_modify",
        "online_samsung_notes_delete",
        "online_samsung_notes_read",
        "online_samsung_voicerecorder_launch",
        "online_samsung_clock_launch",
        "online_samsung_clock_timer_create",
        "online_samsung_clock_timer_read",
        "online_samsung_clock_timer_modify",
        "online_samsung_clock_timer_pause",
        "online_samsung_clock_timer_restart",
        "online_samsung_clock_timer_stop",
        "online_samsung_clock_alarm_create",
        "online_samsung_clock_alarm_read",
        "online_samsung_clock_alarm_modify",
        "online_samsung_clock_alarm_stop",
        "online_samsung_clock_alarm_disable",
        "online_samsung_clock_alarm_delete",
        "online_samsung_clock_stopwatch_start",
        "online_samsung_clock_stopwatch_lap",
        "online_samsung_clock_stopwatch_stop",
        "online_samsung_clock_stopwatch_reset",
        "online_google_translate_launch",
        "online_google_translate_start",
        "online_google_calendar_read",
        "online_google_calendar_create",
        "online_google_calendar_modify",
        "online_google_calendar_delete",
        "online_google_tasks_launch",
        "online_google_tasks_create",
        "online_google_tasks_modify",
        "online_google_tasks_delete",
        "online_google_tasks_modify",
        "online_google_keep_launch",
        "online_google_keep_create",
        "online_google_keep_visualcreate",
        "online_google_keep_modify",
        "online_google_keep_delete",
        "online_google_keep_read",
        "online_google_mail_launch",
        "online_google_mail_search",
        "online_google_mail_thread_read",
        "online_google_maps_launch",
        "online_google_maps_query",
        "online_google_maps_eta",
        "online_google_maps_startnavigate",
        "online_google_maps_stopnavigate",
        "online_google_maps_addstop",
        "online_google_maps_querynavigate",
        "online_google_youtubemusic_launch",
        "online_google_youtubemusic_play",
        "online_google_youtubemusic_playlistcreate",
        "online_google_youtubemusic_playlistplay",
        "online_google_youtubemusic_podcastnext",
        "online_thirdparty_whatsapp_launch",
        "online_thirdparty_whatsapp_call",
        "online_thirdparty_whatsapp_messagesend",
        "online_thirdparty_whatsapp_messagereply",
        "online_thirdparty_whatsapp_disambiguation",
        "online_thirdparty_spotify_launch",
        "online_thirdparty_spotify_play",
        "online_thirdparty_spotify_playlistplay",
        "online_thirdparty_spotify_podcastnext",
        "offline_device_datetime_time",
        "offline_device_datetime_date",
        "offline_device_battery_glasses",
        "offline_device_battery_companion",
        "offline_device_volume_up",
        "offline_device_volume_down",
        "offline_device_volume_set",
        "offline_device_mediacontrol_play",
        "offline_device_mediacontrol_pause",
        "offline_device_mediacontrol_resume",
        "offline_device_mediacontrol_replay",
        "offline_device_mediacontrol_previous",
        "offline_device_mediacontrol_skip",
        "offline_samsung_camera_click",
        "offline_samsung_camera_videostart",
        "offline_samsung_camera_videostop",
        "offline_device_dnd_on",
        "offline_device_dnd_off",
        "disconnected_device_datetime_time",
        "disconnected_device_datetime_date",
        "disconnected_device_battery_glasses",
        "disconnected_device_battery_glasses",
        "disconnected_device_volume_up",
        "disconnected_device_volume_down",
        "disconnected_device_volume_set",
        "disconnected_samsung_camera_click",
        "disconnected_samsung_camera_videostart",
        "disconnected_samsung_camera_videostop"
    ],



# ── Sub-models ───────────────────────────────────────────────────────────────

class LoggerConfig(BaseModel):
    dump_device_logs: bool = False
    logger_level: str = ""

    @field_validator("logger_level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        allowed = {"", "debug", "info", "warning", "error", "critical"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"logger_level must be one of {allowed}, got '{v}'")
        return v_lower


class PowerMeasurementConfig(BaseModel):
    enabled: bool = False
    script_path: str = "scripts/power_measure_jinju.sh"
    samples: int = 100000
    interval: int = 2


class PathsConfig(BaseModel):
    dataset_file: str = ""
    root_folder: str = ""
    queue_file: str = ""
    queue_backup_folder: str = ""
    backup_folder_path: str = ""


class ArapConfig(BaseModel):
    use_robohead: bool = False
    robopod_url: str = ""
    record_duration: int = 0
    devices: list[str] = Field(default_factory=list)


class DevicesConfig(BaseModel):
    s25_device_id: str = ""
    jinju_device_id: str = ""
    arap: ArapConfig = Field(default_factory=ArapConfig)


class UrlsConfig(BaseModel):
    transcription_url: str = ""
    judge_url: str = ""
    rating_rectifier_url: str = ""
    display_port: int = 0


class MessageServiceConfig(BaseModel):
    wait_time: int = Constants.DEFAULT_WAIT_TIME


class JudgeWorkerConfig(BaseModel):
    vllm_api: bool = False
    qa_prompt_version: list[str] = Field(default_factory=list)
    vqa_prompt_version: list[str] = Field(default_factory=list)
    hqa_prompt_version: list[str] = Field(default_factory=list)
    appEval_prompt_version: list[str] = Field(default_factory=list)


class XRClawConfig(BaseModel):
    enabled: bool = False
    python_automation_path: str = ""
    claw_package: str = "com.samsung.xr.claw.client"


class XRBoardConfig(BaseModel):
    generate_reports: bool = False
    upload_files: bool = False
    user_id: str = ""
    companion_pair: str = ""
    kpi_type: str = ""
    dataset_name: str = ""
    judge_name: str = ""


class AutomatorConfig(BaseModel):
    num_evaluations: int = 0
    postprocess_only: bool = False
    generate_reports: bool = False
    xr_board: XRBoardConfig = Field(default_factory=XRBoardConfig)


# ── Top-level config ─────────────────────────────────────────────────────────

class AppConfig(BaseModel):
    """Top-level validated configuration for MAIRE."""

    device_manager_type: str = ""
    dataset_start_index: int = 0
    dataset_end_index: int = 10000
    reevaluation_question_indices: list = []
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
    power_measurement: PowerMeasurementConfig = Field(default_factory=PowerMeasurementConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    devices: DevicesConfig = Field(default_factory=DevicesConfig)
    urls: UrlsConfig = Field(default_factory=UrlsConfig)
    message_service: MessageServiceConfig = Field(default_factory=MessageServiceConfig)
    judge_worker: JudgeWorkerConfig = Field(default_factory=JudgeWorkerConfig)
    xrclaw: XRClawConfig = Field(default_factory=XRClawConfig)
    automator: AutomatorConfig = Field(default_factory=AutomatorConfig)

    @field_validator("dataset_start_index", "dataset_end_index")
    @classmethod
    def non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Index must be non-negative, got {v}")
        return v

    def validate_indices(self) -> None:
        """Call after construction to verify start <= end."""
        if self.dataset_start_index > self.dataset_end_index:
            raise ValueError(
                f"dataset_start_index ({self.dataset_start_index}) must be <= "
                f"dataset_end_index ({self.dataset_end_index})"
            )

    def validate_arap_devices(self) -> None:
        """Verify ARAP device count is within bounds when not using robohead."""
        if not self.devices.arap.use_robohead:
            n = len(self.devices.arap.devices)
            if n < Constants.MIN_ARAP_DEVICES or n > Constants.MAX_ARAP_DEVICES:
                raise ValueError(
                    f"ARAP devices count must be between {Constants.MIN_ARAP_DEVICES} "
                    f"and {Constants.MAX_ARAP_DEVICES}, got {n}"
                )

    def validate_runtime(self) -> "AppConfig":
        """Run all runtime validations. Returns self for chaining."""
        self.validate_indices()
        self.validate_arap_devices()
        return self

    # ── Factory methods ──────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Create from a raw dict (e.g. json.load output)."""
        return cls.model_validate(data)

    @classmethod
    def from_json_file(cls, path: str) -> "AppConfig":
        """Load and validate a JSON config file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        """Serialize back to a plain dict (for JSON output)."""
        return self.model_dump()

    def to_json_file(self, path: str) -> None:
        """Write config to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4)


