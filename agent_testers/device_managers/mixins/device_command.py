"""
DeviceCommandMixin — device-level command execution (volume, camera, DND, etc.).

Extracted from JinjuGeminiManager so that device command logic is reusable
across managers that support device-level queries.

Requires the host class to provide:
    - self.jinju_device: ADB serial of the Jinju glasses
    - self.companion_device: ADB serial of the companion phone
    - self.log_folder: Path to the log dump folder
    - self._execute_app_tasks(): From AppTasksMixin
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


class DeviceCommandMixin:
    """Mixin for executing device-specific commands (volume, camera, DND, etc.).

    Host class must provide:
        - self.jinju_device
        - self.companion_device
        - self.log_folder
        - self._execute_app_tasks() (from AppTasksMixin)
    """

    def _execute_device_command(self, q_info, command_type, device_state):
        """Execute device-specific commands based on command type and device state.

        Args:
            q_info: The evaluation info dictionary
            command_type: Type of command (camera, volume, mediacontrol, dnd, battery, time, date)
            device_state: Device state (online, offline, disconnected)
        """
        from agent_testers.device_managers.device_config import DeviceInfo, DEVICE_COMMAND_TYPES
        from apps import APP_CONFIGS

        print(f"Executing device command: {command_type} (state: {device_state})")

        # Get command config from registry (convert to lowercase for lookup)
        command_config = DEVICE_COMMAND_TYPES.get(command_type.lower())
        if not command_config:
            print(f"Warning: Unknown device command type: {command_type}")
            q_info["metadata"]["device_command_result"] = {"error": f"Unknown command type: {command_type}"}
            return

        action = command_config["action"]
        target_device = command_config["device"]

        # Select the target device
        device_id = self.jinju_device if target_device == "jinju" else self.companion_device
        device_info_util = DeviceInfo(device=device_id)

        # Execute the action
        result = {"command_type": command_type, "device_state": device_state, "target_device": target_device}

        # Capture flags for camera/video are set by logger() into app_state.log_analysis.
        if action == "capture_image":
            result["action"] = "image_capture_initiated"

        elif action == "capture_video":
            result["action"] = "video_capture_initiated"

        elif action == "get_volume":
            volume_info = device_info_util.get_volume()
            result["volume"] = volume_info
            print(f"Volume info: {volume_info}")

        elif action == "get_media":
            media_info = device_info_util.get_media()
            result["media"] = media_info
            print(f"Media info: {media_info}")

        elif action == "get_dnd_mode":
            try:
                from utils.adb_client import AdbClient
                adb = AdbClient()
                dnd_enabled = adb.get_dnd_mode(self.companion_device)
                dnd_mode = "true" if dnd_enabled else "false"
                result["dnd_mode"] = dnd_mode
                print(f"DND mode: {dnd_mode}")
            except Exception as e:
                result["dnd_mode"] = "false"
                result["error"] = str(e)

        elif action == "get_battery":
            battery_info = device_info_util.get_battery()
            result["battery"] = battery_info
            print(f"Battery info: {battery_info}")

        elif action == "get_time":
            time_info = device_info_util.get_time()
            result["time"] = time_info
            print(f"Time info: {time_info}")

        elif action == "get_date":
            time_info = device_info_util.get_time()
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
            result["date"] = date_info
            print(f"Date info: {date_info}")

        elif action == "capture_notifications_screenshot":
            # Open notification shade, screenshot
            from common.question_type import QuestionType
            notif_actions = APP_CONFIGS.get("device", {}).get("notification", {}).get("actions", {})
            # Use the action from the question type (read/notread/auto) as the mode
            qt = QuestionType.parse(q_info.get("question_type", ""))
            mode = qt.action if qt.action in notif_actions else "read"
            self._run_app_tasks("device", "notification", "device", mode)
            # capture_post_state_meta_info moves this into post_state_screenshots
            if os.path.exists(os.path.join(self.log_folder, "app_screenshot.png")):
                result["action"] = "notification_screenshot_captured"
            else:
                result["error"] = "Failed to capture notification screenshot"
                print("Warning: Failed to capture notification panel screenshot!")

        else:
            result["error"] = f"Unknown action: {action}"

        # Store result in metadata
        q_info["metadata"]["device_command_result"] = result
