"""
MockDeviceManager — feature-rich mock for integration testing.

Implements the DeviceManagerTemplate abstract interface with configurable
behavior. Records all calls for assertion. Can simulate device state
changes (volume up, DND on, etc.) for deterministic judge tests.

This mock wraps MockXRClawDeviceManager for app state and MockARAPManager
for audio playback/recording, providing a single object that can be passed
to AgentTester in place of a real DeviceManager.

Usage:
    from agent_testers.device_managers.mock_device_manager import DeviceManager
    from test.mocks.mock_xrclaw import MockXRClawDeviceManager

    dm = DeviceManager(log_dump_folder="/tmp/test_logs")
    dm.state_collector = MyStateCollector(mock_xrclaw_dm)
    dm.invoke(q_info)
    result = dm.capture_app_meta_info(q_info)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from agent_testers.device_managers.device_manager import DeviceManagerTemplate

logger = logging.getLogger(__name__)


class DeviceManager(DeviceManagerTemplate):
    """Feature-rich mock DeviceManager for integration testing.

    Implements all abstract methods from DeviceManagerTemplate with
    configurable behavior. All calls are recorded in ``call_log`` for
    assertion. Device state changes can be simulated for deterministic tests.

    Attributes:
        call_log: List of (method_name, args) tuples for all method calls.
        arap_speaker: MockARAPManager for audio playback.
        arap_recorder: MockARAPManager for audio recording.
        state_collector: Optional state collector instance.
        jinju_device: Mock device serial string.
    """

    @staticmethod
    def get_device_names():
        """Return empty list — no real devices."""
        return []

    def __init__(self, log_dump_folder: str = "", config: dict = None):
        self.log_folder = log_dump_folder
        self.config = config or {}
        self.call_log: list[tuple] = []

        # Device state storage (mirrors what real managers capture)
        self._device_state: dict = {
            "jinju": {},
            "companion": {},
        }
        self._foreground_app: Optional[str] = None

        # Mock ARAP managers (real managers set these in __init__)
        from test.mocks.mock_arap import MockARAPManager
        self.arap_speaker = MockARAPManager()
        self.arap_recorder = MockARAPManager()

        # State collector (set by the test or framework)
        self.state_collector = None

        # Device serials
        self.jinju_device = "mock_jinju_device"
        self.s25_device = "mock_s25_device"
        self.companion_device = "mock_companion_device"

        # Configurable responses
        self._invoke_result = None
        self._app_meta_info = {}

        # Ensure log folder exists
        if log_dump_folder:
            os.makedirs(log_dump_folder, exist_ok=True)

    def _log_call(self, method: str, *args):
        """Record a method call for later assertion."""
        self.call_log.append((method, args))

    # ── Abstract method implementations ─────────────────────────────

    def invoke(self, q_info: dict):
        """Mock invoke — records the call and optionally plays audio."""
        self._log_call("invoke", q_info)
        # In real managers, this plays the question audio and records the response.
        # For testing, we just record the call.

    def terminate(self):
        """Mock terminate — records the call."""
        self._log_call("terminate")
        self._foreground_app = None

    def reset_companion_screen(self):
        """Mock reset_companion_screen — records the call and clears foreground app."""
        self._log_call("reset_companion_screen")
        self._foreground_app = None


    def logger(self) -> dict:
        """Mock logger — returns empty dict."""
        self._log_call("logger")
        return {}

    def capture_app_meta_info(self, q_info: dict) -> dict:
        """Mock capture_app_meta_info — returns configurable app metadata.

        In real managers, this captures screenshots, device info, and app state
        after the agent responds. For testing, we return configurable data.
        """
        self._log_call("capture_app_meta_info", q_info)
        return dict(self._app_meta_info)

    # ── Device info capture (override from template) ────────────────

    def capture_device_info(self, q_info, capture_type="post", device_state=None):
        """Mock capture_device_info — returns configurable device state.

        Args:
            q_info: Question info dict.
            capture_type: "pre" or "post".
            device_state: Optional pre-configured device state.

        Returns:
            Dict with "jinju" and "companion" sub-dicts containing device info.
        """
        self._log_call("capture_device_info", q_info, capture_type)
        if device_state:
            return device_state
        return {
            "jinju": dict(self._device_state.get("jinju", {})),
            "companion": dict(self._device_state.get("companion", {})),
        }

    # ── State collection (override from template) ───────────────────

    def _init_state_collector(self, collector_config: dict, adb_device: str):
        """Initialize the state collector with a mock XRClaw DeviceManager."""
        self._log_call("_init_state_collector", collector_config, adb_device)
        return self.state_collector

    def capture_pre_state(self, q_info: dict) -> None:
        """Mock capture_pre_state — delegates to state_collector if set."""
        self._log_call("capture_pre_state", q_info)
        if self.state_collector:
            app_key = q_info.get("app_key", "")
            if app_key and hasattr(self.state_collector, "capture_pre_state"):
                try:
                    pre = self.state_collector.capture_pre_state(app_key)
                    q_info.setdefault("pre_state", {})[app_key] = pre
                except Exception as e:
                    logger.warning("Mock capture_pre_state failed: %s", e)

    def _collect_state(self, collector, q_info: dict) -> bool:
        """Mock _collect_state — delegates to state_collector if set."""
        self._log_call("_collect_state", collector, q_info)
        if collector and hasattr(collector, "collect_app_state"):
            app_key = q_info.get("app_key", "")
            app_mode = q_info.get("app_mode", "")
            question = q_info.get("question", "")
            gt_answer = q_info.get("gt_answer", "")
            pre_state = q_info.get("pre_state", {}).get(app_key)
            try:
                result = collector.collect_app_state(
                    app_key, app_mode, question, gt_answer, pre_state
                )
                q_info.setdefault("app_state", {})
                q_info["app_state"] = result
                return True
            except Exception as e:
                logger.warning("Mock _collect_state failed: %s", e)
        return False

    # ── Device command execution (override from template) ───────────

    def _execute_device_command(self, q_info, command_type, device_state):
        """Mock _execute_device_command — records the call."""
        self._log_call("_execute_device_command", q_info, command_type, device_state)

    # ── App task execution (override from template) ─────────────────

    def _execute_app_tasks(self, app_name: str, app_config: dict, app_eval_mode: str):
        """Mock _execute_app_tasks — records the call."""
        self._log_call("_execute_app_tasks", app_name, app_config, app_eval_mode)

    def _pull_screenshot(self, remote_path="/sdcard/Pictures/screen.png"):
        """Mock _pull_screenshot — records the call."""
        self._log_call("_pull_screenshot", remote_path)

    def _clear_screenshot(self, remote_path="/sdcard/Pictures/screen.png"):
        """Mock _clear_screenshot — records the call."""
        self._log_call("_clear_screenshot", remote_path)

    def _capture_calendar_day_view(self, q_info, app_name):
        """Mock _capture_calendar_day_view — records the call."""
        self._log_call("_capture_calendar_day_view", q_info, app_name)

    # ── Volume reset (override from template) ───────────────────────

    def reset_media_volume(self, device_id: str, volume: int) -> None:
        """Mock reset_media_volume — records the call."""
        self._log_call("reset_media_volume", device_id, volume)

    # ── Test configuration helpers ───────────────────────────────────

    def set_device_state(self, device: str = "jinju", **kwargs):
        """Set device state fields for a specific device.

        Args:
            device: "jinju" or "companion".
            **kwargs: State fields (battery, time, volume, dnd_mode, media, etc.)
        """
        self._device_state.setdefault(device, {}).update(kwargs)

    def set_jinju_state(self, **kwargs):
        """Set jinju (glasses) device state."""
        self.set_device_state("jinju", **kwargs)

    def set_companion_state(self, **kwargs):
        """Set companion (phone) device state."""
        self.set_device_state("companion", **kwargs)

    def set_app_meta_info(self, **kwargs):
        """Set the app metadata that capture_app_meta_info will return."""
        self._app_meta_info.update(kwargs)

    def set_foreground_app(self, package: str):
        """Set the current foreground app package."""
        self._foreground_app = package

    def get_foreground_app(self) -> Optional[str]:
        """Get the current foreground app package."""
        return self._foreground_app

    def is_app_running(self, package: str) -> bool:
        """Check if an app is running (in foreground)."""
        return package == self._foreground_app

    def force_stop_app(self, package: str) -> None:
        """Force stop an app (removes from foreground)."""
        if package == self._foreground_app:
            self._foreground_app = None

    def launch_app(self, package: str) -> None:
        """Launch an app (sets as foreground)."""
        self._foreground_app = package

    def reset(self):
        """Clear all recorded calls and state."""
        self.call_log = []
        self._device_state = {"jinju": {}, "companion": {}}
        self._foreground_app = None
        self._app_meta_info = {}
        self.arap_speaker.reset()
        self.arap_recorder.reset()

    # ── Convenience: build device info dict matching DeterministicJudge format ──

    @staticmethod
    def build_device_info(
        battery_level: int = 75,
        battery_status: str = "Discharging",
        charging: bool = False,
        time_str: str = "Mon Aug 25 13:00:00 IST 2026",
        timezone: str = "IST",
        epoch_ms: int = 1756110000000,
        volume_current: int = 7,
        volume_max: int = 15,
        volume_muted: bool = False,
        dnd_enabled: bool = False,
        media_playing: bool = False,
        media_title: str = "",
        media_artist: str = "",
        media_package: str = "",
        media_position_ms: int = 0,
    ) -> dict:
        """Build a device info dict in the format DeterministicJudge expects.

        This matches the structure produced by XRClaw's DeviceInfoState.to_dict().
        """
        return {
            "battery": {
                "level": battery_level,
                "status": battery_status,
                "charging": charging,
            },
            "time": {
                "datetime_str": time_str,
                "timezone": timezone,
                "epoch_ms": epoch_ms,
            },
            "date": {
                "day": 25,
                "month": "Aug",
                "year": 2026,
                "day_of_week": "Mon",
            },
            "volume": {
                "muted": volume_muted,
                "min": 0,
                "max": volume_max,
                "current": volume_current,
            },
            "dnd_mode": "true" if dnd_enabled else "false",
            "media": {
                "active": media_playing or bool(media_title),
                "playing": media_playing,
                "state": "Playing" if media_playing else "Paused",
                "package": media_package,
                "title": media_title,
                "artist": media_artist,
                "position_ms": media_position_ms,
            },
        }
