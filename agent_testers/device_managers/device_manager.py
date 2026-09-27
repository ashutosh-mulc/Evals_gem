"""
DeviceManagerTemplate — abstract base class for all device managers.

Abstract methods + low-level ADB helpers (_click/_swipe/_back/_speak). Higher-level
functionality lives in the mixins under ``device_managers/mixins/`` and is opted
into per manager, e.g.:

    class DeviceManager(AppTasksMixin, StateCollectMixin, DeviceManagerTemplate)

The no-op stubs at the bottom cover the methods ``agent_tester.execute()`` calls
unconditionally, for managers that don't include the corresponding mixin.
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

    def reset_device_to_default_state(self) -> dict:
        """Reset the device to a known baseline before every APP_EVAL_TASK.

        No-op here; managers that drive a companion device (Jinju) override it.
        Returns {"set": [...], "failed": [...]}.
        """
        return {"set": [], "failed": []}

    # ── No-op stubs, overridden by the mixins ─────────────────────

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

    def capture_device_info(self, q_info, capture_type="post", device_state=None):
        """No-op. Override via DeviceInfoMixin."""
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

