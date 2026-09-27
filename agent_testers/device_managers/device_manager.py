"""
DeviceManagerTemplate — abstract base class for all device managers.

This is the slim core: abstract method declarations + low-level ADB helpers
(_click/_swipe/_back/_speak).  All higher-level functionality (app task
execution, state collection, calendar capture) lives in the mixin classes
under ``device_managers/mixins/`` and is opted into per-manager:

    class DeviceManager(AppTasksMixin, StateCollectMixin, CalendarMixin, DeviceManagerTemplate)

Managers that don't need app-level functionality (dummy, claude, gpt, meta)
inherit ``DeviceManagerTemplate`` directly and get no-op stubs for the
methods that ``agent_tester.execute()`` calls unconditionally.
"""

from abc import ABC, abstractmethod
import subprocess
import time
import re
import logging

logger = logging.getLogger(__name__)


class DeviceManagerTemplate(ABC):
    '''
    Base (template) class for device managers.

    Only one instance is created per evaluation run.  If stateful counters are
    needed (e.g. to toggle device on/off), implement them in the manager
    subclass — ``agent_tester.py`` should not be changed.
    '''

    # ── Abstract methods (every manager must implement) ────────────

    @staticmethod
    @abstractmethod
    def get_device_names():
        pass

    @abstractmethod
    def invoke(self, q_info: dict):
        pass

    @abstractmethod
    def terminate(self):
        pass

    @abstractmethod
    def logger(self) -> dict:
        pass

    # ── Low-level ADB helpers (shared by all managers) ─────────────

    def _get_screen_resolution(self, device_id: str) -> tuple:
        """Get screen resolution (width, height) via 'adb shell wm size'.

        Results are cached per device_id on the instance.
        """
        if not hasattr(self, '_screen_res_cache'):
            self._screen_res_cache = {}
        if device_id not in self._screen_res_cache:
            try:
                output = subprocess.run(
                    f"adb -s {device_id} shell wm size",
                    shell=True, capture_output=True, text=True, timeout=10
                ).stdout
                # Parse "Physical size: 1080x2520"
                m = re.search(r'(\d+)x(\d+)', output)
                if m:
                    self._screen_res_cache[device_id] = (int(m.group(1)), int(m.group(2)))
                else:
                    self._screen_res_cache[device_id] = (1080, 2520)  # fallback
            except Exception:
                self._screen_res_cache[device_id] = (1080, 2520)  # fallback
        return self._screen_res_cache[device_id]

    def _swipe_phone(self, device_id: str, x1, y1, x2, y2):
        """Swipe from (x1, y1) to (x2, y2).

        Accepts absolute pixels (int) or screen ratios (float in [0, 1]).
        Floats are scaled by the device's screen resolution at runtime.
        """
        if isinstance(x1, float) and 0.0 <= x1 <= 1.0:
            w, h = self._get_screen_resolution(device_id)
            x1, y1 = int(x1 * w), int(y1 * h)
            x2, y2 = int(x2 * w), int(y2 * h)
        command = f"adb -s {device_id} shell input swipe {x1} {y1} {x2} {y2}"
        print(f"Swiped on {device_id} at position ({x1}, {y1}) ({x2}, {y2})")
        subprocess.run(command, shell=True)

    def _click_phone(self, device_id: str, x, y):
        """Tap at (x, y).

        Accepts absolute pixels (int) or screen ratios (float in [0, 1]).
        Floats are scaled by the device's screen resolution at runtime.
        """
        if isinstance(x, float) and 0.0 <= x <= 1.0:
            w, h = self._get_screen_resolution(device_id)
            x, y = int(x * w), int(y * h)
        command = f"adb -s {device_id} shell input tap {x} {y}"
        print(f"Clicked on {device_id} at position ({x}, {y})")
        subprocess.run(command, shell=True)

    def _press_back(self, device_id: str):
        command = f"adb -s {device_id} shell input keyevent KEYCODE_BACK"
        print(f"Pressed BACK on {device_id}")
        subprocess.run(command, shell=True)

    def _speak(self, wav_file: str, pause_before: int = 0, wait_after: int = 0):
        time.sleep(pause_before)
        print(f"Playing wav file: {wav_file}")
        self.arap_speaker.play_audio(wav_file)
        time.sleep(wait_after)
        print("ARAP speaking user consent")

    def reset_media_volume(self, device_id: str, volume: int) -> None:
        """Reset media volume on a device. Override in subclass for device-specific impl."""
        pass

    def reset_device_to_default_state(self) -> dict:
        """Reset the device to a known baseline before every APP_EVAL_TASK.

        No-op here; managers that drive a companion device (Jinju) override it.
        Returns {"set": [...], "failed": [...]}.
        """
        return {"set": [], "failed": []}

    # ── No-op stubs for mixin methods ──────────────────────────────
    # These are overridden by AppTasksMixin / StateCollectMixin / CalendarMixin
    # in managers that opt into those mixins.  Managers that inherit
    # DeviceManagerTemplate directly (dummy, claude, gpt, meta) get these
    # no-ops so agent_tester.execute() can call them without crashing.

    def _get_companion_device(self) -> str:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _get_companion_device() "
            "or inherit AppTasksMixin"
        )

    def _init_state_collector(self, collector_config: dict, adb_device: str):
        """No-op: returns None. Override via StateCollectMixin."""
        return None

    # Backward-compatible alias
    _init_xrclaw_collector = _init_state_collector

    def capture_pre_state(self, q_info: dict) -> None:
        """No-op. Override via StateCollectMixin."""
        pass

    # Backward-compatible alias
    capture_xrclaw_pre_state = capture_pre_state

    def _collect_state(self, collector, q_info: dict) -> bool:
        """No-op: returns False. Override via StateCollectMixin."""
        return False

    # Backward-compatible alias
    _xrclaw_collect_state = _collect_state

    def _execute_app_tasks(self, app_name: str, app_config: dict, app_eval_mode: str):
        """No-op. Override via AppTasksMixin."""
        pass

    def _capture_calendar_day_view(self, q_info, app_name):
        """No-op. Override via CalendarMixin."""
        pass

    def _pull_screenshot(self, remote_path="/sdcard/Pictures/screen.png"):
        """No-op. Override via AppTasksMixin."""
        pass

    def _clear_screenshot(self, remote_path="/sdcard/Pictures/screen.png"):
        """No-op. Override via AppTasksMixin."""
        pass

    def capture_device_info(self, q_info, capture_type="post", device_state=None):
        """No-op. Override via DeviceInfoMixin."""
        pass

    def _execute_device_command(self, q_info, command_type, device_state):
        """No-op. Override via DeviceCommandMixin."""
        pass

    def capture_pre_state_meta_info(self, q_info: dict):
        """No-op. Override via AppMetaInfoMixin."""
        pass

    def capture_post_state_meta_info(self, q_info: dict):
        """No-op. Override via AppMetaInfoMixin."""
        pass

    def set_connectivity(self, connectivity: str) -> None:
        """Set companion-device connectivity mode before invoking the agent.

        Modes:
            - "offline":      paired but no internet (wifi off, mobile data off, bluetooth on)
            - "disconnected": not paired       (wifi on,  mobile data on,  bluetooth off)
            - "online":       paired + internet (wifi on,  mobile data on,  bluetooth on)

        Default is a no-op so agent_tester can call this unconditionally on any
        manager. Override in managers that control a companion device (e.g.
        JinjuGeminiManager) to apply the ADB state changes.
        """
        pass

