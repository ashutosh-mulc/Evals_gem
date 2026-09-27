"""
AppMetaInfoMixin — pre/post app state capture and routing.

Extracted from JinjuGeminiManager so that the capture_app_meta_info() routing
logic (device vs app, camera, XRClaw, screenshot fallback) is reusable
across managers.

Requires the host class to provide:
    - self.companion_device: ADB serial of the companion phone
    - self.log_folder: Path to the log dump folder
    - self.xrclaw_collector (or self.state_collector): StateCollector or None
    - self._xrclaw_collect_state() / _collect_state(): From StateCollectMixin
    - self._pull_screenshot(): From AppTasksMixin
    - self._capture_calendar_day_view(): From CalendarMixin
    - self._execute_app_tasks(): From AppTasksMixin
    - self.capture_device_info(): From DeviceInfoMixin
    - self._execute_device_command(): From DeviceCommandMixin
"""

from __future__ import annotations

import os
import logging
import traceback

logger = logging.getLogger(__name__)


class AppMetaInfoMixin:
    """Mixin for pre/post app state capture and routing.

    Host class must provide:
        - self.companion_device
        - self.log_folder
        - self.xrclaw_collector (or self.state_collector)
        - self._collect_state() (from StateCollectMixin)
        - self._pull_screenshot() (from AppTasksMixin)
        - self._capture_calendar_day_view() (from CalendarMixin)
        - self._execute_app_tasks() (from AppTasksMixin)
        - self.capture_device_info() (from DeviceInfoMixin)
        - self._execute_device_command() (from DeviceCommandMixin)
    """

    def _save_screenshot_to_state_dir(self, q_info: dict, state_type: str) -> str:
        """Move app_screenshot.png to state-specific directory in per-query assets folder.
        
        Saves directly to {log_root}/assets/q{eval_id}/screenshots/ instead of
        {log_folder}/tmp/assets/ to avoid cleanup issues and ensure files persist
        for report generation.
        
        Args:
            q_info: The evaluation info dictionary
            state_type: "pre_state" or "post_state"
        
        Returns:
            New path to screenshot, or empty string if not found
        """
        app_screenshot = os.path.join(self.log_folder, "app_screenshot.png")
        if not os.path.exists(app_screenshot):
            return ""
        
        # Get final assets folder (not tmp!)
        # log_root is the parent of log_folder (e.g., log_folder = {root}/tmp, log_root = {root})
        log_root = os.path.dirname(self.log_folder)
        final_assets = os.path.join(log_root, "assets")
        
        # Create screenshots directory in per-query assets folder
        eval_id = q_info["eval_id"].replace('q', '')
        screenshots_dir = os.path.join(
            final_assets, f"q{eval_id}", "screenshots"
        )
        os.makedirs(screenshots_dir, exist_ok=True)
        
        # Move to new location (keep eval_id in the filename)
        new_path = os.path.join(
            screenshots_dir, f"{state_type}_{eval_id}.png"
        )
        os.rename(app_screenshot, new_path)
        return new_path

    def capture_pre_state_meta_info(self, q_info):
        """Capture app state BEFORE Gemini invoke (after preconditions).
        
        Executes app tasks from config.py and captures screenshot for
        human interpretability (pre-state baseline).
        
        Args:
            q_info: The evaluation info dictionary
        """
        from utils.adb_client import AdbClient
        from common.question_type import QuestionType
        from apps import APP_CONFIGS

        adb = AdbClient()
        assert adb.is_device_online(self.companion_device), \
            f"Device {self.companion_device} NOT online!"

        q_type = q_info["question_type"]
        qt = QuestionType.parse(q_type)
        app_eval_mode = qt.action


        # Execute app tasks and capture screenshot
        group_config = APP_CONFIGS.get(qt.group, {})
        feature_config = group_config.get(qt.feature)
        if feature_config:
            app_config = {
                "package_name": feature_config.get("package_name", ""),
                "activity_name": feature_config.get("activity_name", ""),
                "tasks": feature_config.get("actions", {}),
            }
            self._execute_app_tasks(qt.app_key, app_config, app_eval_mode)

        # Save to pre_state_screenshots
        new_path = self._save_screenshot_to_state_dir(q_info, "pre_state")
        if new_path:
            q_info["metadata"]["pre_state_screenshots"] = [new_path]

    def capture_post_state_meta_info(self, q_info):
        """Capture app state AFTER Gemini invoke (for VLM judge).
        
        Executes app tasks from config.py and captures screenshot
        for judge verification.
        
        Args:
            q_info: The evaluation info dictionary
        """
        from utils.adb_client import AdbClient
        from common.question_type import QuestionType
        from apps import APP_CONFIGS

        adb = AdbClient()
        assert adb.is_device_online(self.companion_device), \
            f"Device {self.companion_device} NOT online!"

        q_type = q_info["question_type"]
        qt = QuestionType.parse(q_type)
        app_eval_mode = qt.action

        # Handle device queries
        if qt.group == "device":
            device_state = qt.connectivity
            command_type = qt.feature
            
            # Capture device info with state context
            try:
                self.capture_device_info(q_info, capture_type="post", device_state=device_state)
            except Exception as e:
                print(f"Warning: capture_device_info(post) failed for device query: {e}")
                traceback.print_exc()
            
            # Execute device-specific command
            try:
                self._execute_device_command(q_info, command_type, device_state)
            except Exception as e:
                print(f"Warning: _execute_device_command failed: {e}")
                traceback.print_exc()
            
            # XRClaw verification
            collect_fn = getattr(self, "_collect_state", None)
            collector = getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)
            if collect_fn and collector:
                collect_fn(collector, q_info)

            # Execute app tasks from config.py (open_activity + screenshot) for
            # device queries so the post-state screenshot shows the relevant UI
            # (e.g., volume slider) for judge verification.
            group_config = APP_CONFIGS.get(qt.group, {})
            feature_config = group_config.get(qt.feature)
            if feature_config:
                app_config = {
                    "package_name": feature_config.get("package_name", ""),
                    "activity_name": feature_config.get("activity_name", ""),
                    "tasks": feature_config.get("actions", {}),
                }
                self._execute_app_tasks(qt.app_key, app_config, app_eval_mode)
            else:
                print(f"App '{qt.group}/{qt.feature}' not found in APP_CONFIGS! Taking fallback screenshot.")
                self._pull_screenshot("/sdcard/Pictures/app_screenshot.png")

            # Save to post_state_screenshots
            new_path = self._save_screenshot_to_state_dir(q_info, "post_state")
            if new_path:
                q_info["metadata"]["post_state_screenshots"] = [new_path]
            return

        # Camera queries: capture flags come from the logcat/photo pull in logger()
        # and land in app_state.log_analysis.
        if qt.feature == "camera":
            return

        # Capture device info for all APP_EVAL_TASK
        self.capture_device_info(q_info)

        # XRClaw verification (if available)
        collect_fn = getattr(self, "_collect_state", None)
        collector = getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)
        if collect_fn and collector:
            collect_fn(collector, q_info)
            print(f"----XRClaw verification completed for {qt.app_key}----")

        # Execute app tasks and capture screenshot
        group_config = APP_CONFIGS.get(qt.group, {})
        feature_config = group_config.get(qt.feature)
        if feature_config:
            app_config = {
                "package_name": feature_config.get("package_name", ""),
                "activity_name": feature_config.get("activity_name", ""),
                "tasks": feature_config.get("actions", {}),
            }
            self._execute_app_tasks(qt.app_key, app_config, app_eval_mode)
        else:
            print(f"App '{qt.group}/{qt.feature}' not found in APP_CONFIGS! Taking fallback screenshot.")
            self._pull_screenshot("/sdcard/Pictures/app_screenshot.png")

        # Save to post_state_screenshots
        new_path = self._save_screenshot_to_state_dir(q_info, "post_state")
        if new_path:
            q_info["metadata"]["post_state_screenshots"] = [new_path]
