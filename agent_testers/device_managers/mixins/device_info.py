"""
DeviceInfoMixin — device info capture (battery, time, volume, DND, media).

Extracted from JinjuGeminiManager so that device info capture logic is
reusable across managers that need pre/post state snapshots.

Requires the host class to provide:
    - self.jinju_device: ADB serial of the Jinju glasses
    - self.companion_device: ADB serial of the companion phone
    - self.log_folder: Path to the log dump folder
    - self.xrclaw_collector: StateCollector instance or None (backward-compat alias)
"""

from __future__ import annotations

import os
import json
import time
import subprocess
import logging

logger = logging.getLogger(__name__)


class DeviceInfoMixin:
    """Mixin for capturing device info (battery, time, volume, DND, media).

    Host class must provide:
        - self.jinju_device
        - self.companion_device
        - self.log_folder
        - self.xrclaw_collector (or self.state_collector)
    """

    def capture_device_info(self, q_info, capture_type="post", device_state=None):
        """Capture device state at query time for APP_EVAL_TASK.

        When XRClaw is available, uses XRClaw's DeviceInfoApp (secure ADB,
        list-args, no shell=True) instead of the standalone DeviceInfo class.
        Falls back to DeviceInfo when XRClaw is not enabled.

        Args:
            q_info: The evaluation info dictionary
            capture_type: "pre" for before task execution, "post" for after (default: "post")
            device_state: Optional device state context (e.g., "online", "offline") for device queries
        """
        from utils.adb_client import AdbClient

        adb = AdbClient()
        assert adb.is_device_online(self.jinju_device), \
            f"Device {self.jinju_device} NOT online!"
        assert adb.is_device_online(self.companion_device), \
            f"Device {self.companion_device} NOT online!"

        # --- Use XRClaw DeviceInfoApp if available ---
        collector = getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)
        if collector is not None and getattr(collector, "_dm", None) is not None:
            device_info = self._capture_device_info_xrclaw()
        else:
            device_info = self._capture_device_info_legacy()

        # Store in metadata based on capture type
        metadata_key = f"device_info_{capture_type}"
        q_info["metadata"][metadata_key] = device_info

        # Save to file for logging
        device_info_path = os.path.join(
            self.log_folder,
            f"device_info_{capture_type}_{q_info['eval_id']}.json"
        )
        with open(device_info_path, 'w') as f:
            json.dump(device_info, f, indent=2)
        q_info["metadata"][f"{metadata_key}_path"] = device_info_path

    def _capture_device_info_xrclaw(self) -> dict:
        """Capture device info using XRClaw DeviceInfoApp (secure ADB).

        Jinju-side info (battery, time, date, volume) is fetched via the legacy
        DeviceInfo class because the XRClaw DeviceManager is connected to the
        companion device, not the Jinju glasses.
        Companion-side info (DND, media) uses XRClaw.
        """
        from agent_testers.device_managers.device_config import DeviceInfo

        # Jinju device info via legacy DeviceInfo (correct device)
        jinju_di = DeviceInfo(device=self.jinju_device)
        battery_info = jinju_di.get_battery()
        time_info = jinju_di.get_time()
        volume_info = jinju_di.get_volume()

        # Parse date from datetime string
        date_info = self._parse_date_from_time(time_info)

        jinju_device_info = self._build_jinju_device_info(battery_info, time_info, date_info, volume_info)

        # Companion device info (DND, media, battery) via XRClaw + DeviceInfo
        from python_automation import DeviceManager as XRClawDM
        companion_dm = XRClawDM(adb_path="adb", device=self.companion_device)
        dnd = companion_dm.device_info.get_dnd_mode()
        media = companion_dm.device_info.get_media()

        companion_di = DeviceInfo(device=self.companion_device)
        companion_battery = companion_di.get_battery()
        companion_volume = companion_di.get_volume()

        companion_device_info = self._build_companion_device_info(
            companion_battery, dnd.enabled, media, companion_volume
        )

        return {
            "jinju": jinju_device_info,
            "companion": companion_device_info,
            "captured_at_epoch": int(time.time() * 1000)
        }

    def _capture_device_info_legacy(self) -> dict:
        """Capture device info using the legacy DeviceInfo class (fallback)."""
        from agent_testers.device_managers.device_config import DeviceInfo

        # --- Jinju Device Info ---
        device_info_util = DeviceInfo(device=self.jinju_device)

        battery_info = device_info_util.get_battery()
        time_info = device_info_util.get_time()
        volume_info = device_info_util.get_volume()

        # Parse date from datetime string
        date_info = self._parse_date_from_time(time_info)

        jinju_device_info = self._build_jinju_device_info(battery_info, time_info, date_info, volume_info)

        # --- Companion Device Info (DND Mode and Media State) ---
        from utils.adb_client import AdbClient
        adb = AdbClient()
        dnd_enabled = adb.get_dnd_mode(self.companion_device)
        dnd_mode = "true" if dnd_enabled else "false"

        # --- Companion Device Info (Media State + Battery) ---
        companion_info_util = DeviceInfo(device=self.companion_device)
        media_info = companion_info_util.get_media()
        companion_battery = companion_info_util.get_battery()
        companion_volume = companion_info_util.get_volume()

        companion_device_info = self._build_companion_device_info(
            companion_battery, dnd_mode == "true", media_info, companion_volume
        )

        # --- Combine into single device_info object ---
        return {
            "jinju": jinju_device_info,
            "companion": companion_device_info,
            "captured_at_epoch": int(time.time() * 1000)
        }

    # ── Shared helpers ──────────────────────────────────────────────

    @staticmethod
    def _parse_date_from_time(time_info: dict) -> dict:
        """Parse date components from a time info dict."""
        date_info = {}
        if time_info.get("datetime_str"):
            from datetime import datetime
            try:
                dt = datetime.strptime(time_info["datetime_str"], "%a %b %d %H:%M:%S %Z %Y")
                date_info = {
                    "day": dt.day,
                    "month": dt.strftime("%b"),
                    "year": dt.year,
                    "day_of_week": dt.strftime("%a")
                }
            except Exception:
                pass
        return date_info

    @staticmethod
    def _build_jinju_device_info(battery_info, time_info, date_info, volume_info) -> dict:
        """Build the jinju device info dict from raw component dicts."""
        return {
            "battery": {
                "level": battery_info.get("level"),
                "status": battery_info.get("status"),
                "charging": battery_info.get("charging")
            },
            "time": {
                "datetime_str": time_info.get("datetime_str"),
                "timezone": time_info.get("timezone"),
                "epoch_ms": time_info.get("epoch_ms")
            },
            "date": date_info,
            "volume": {
                "muted": volume_info.get("muted"),
                "min": volume_info.get("min"),
                "max": volume_info.get("max"),
                "current": volume_info.get("current"),
                "all_streams": volume_info.get("all_streams", {}),
            }
        }

    @staticmethod
    def _build_companion_device_info(companion_battery, dnd_enabled, media_info, volume_info=None) -> dict:
        """Build the companion device info dict from raw component data.

        Args:
            companion_battery: Battery info dict from DeviceInfo.get_battery()
            dnd_enabled: bool — whether DND is on
            media_info: Media info dict (from XRClaw or DeviceInfo.get_media())
            volume_info: Optional volume info dict from DeviceInfo.get_volume()
        """
        vol_dict = {}
        if volume_info:
            vol_dict = {
                "muted": volume_info.get("muted"),
                "min": volume_info.get("min"),
                "max": volume_info.get("max"),
                "current": volume_info.get("current"),
                "all_streams": volume_info.get("all_streams", {}),
            }
        return {
            "dnd_mode": "true" if dnd_enabled else "false",
            "battery": {
                "level": companion_battery.get("level"),
                "status": companion_battery.get("status"),
                "charging": companion_battery.get("charging"),
            },
            "volume": vol_dict,
            "media": {
                "active": media_info.get("active"),
                "playing": media_info.get("playing"),
                "state": media_info.get("state"),
                "package": media_info.get("package"),
                "title": media_info.get("title"),
                "artist": media_info.get("artist"),
                "album": media_info.get("album"),
                "position_ms": media_info.get("position_ms"),
                "speed": media_info.get("speed"),
                "last_audio_package": media_info.get("last_audio_package"),
            },
        }
