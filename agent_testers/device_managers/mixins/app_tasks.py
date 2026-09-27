"""
AppTasksMixin — shared app interaction methods.

Extracted from DeviceManagerTemplate so that managers that don't use
app tasks (dummy, claude, gpt, meta) don't inherit them.

Requires the host class to implement _get_companion_device().
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class AppTasksMixin:
    """Mixin for app task execution and screenshot management.

    Host class must implement:
        - _get_companion_device() → str (ADB serial)
        - _click_phone(device_id, x, y)
        - _swipe_phone(device_id, x1, y1, x2, y2)
        - _press_back(device_id)
        - _speak(wav_file, pause, wait)
    """

    def _get_companion_device(self) -> str:
        """Return the ADB serial of the companion device where apps run."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _get_companion_device() "
            "to use shared app interaction methods"
        )

    def _run_app_tasks(self, group: str, feature: str, app_key: str, mode: str,
                        fallback_screenshot: bool = False, mode_fallback: str = None) -> bool:
        """Look up the (group, feature) app config and run its tasks for `mode`
        (or `mode_fallback` if `mode` has no task list — e.g. a multi-word action
        like "thread_read" registered under the full key).

        Returns True if a config was found and tasks were run. If not and
        fallback_screenshot is set, takes a generic screenshot instead (so the
        VLM judge still has something to look at) and returns False.
        """
        from apps import APP_CONFIGS

        feature_config = APP_CONFIGS.get(group, {}).get(feature)
        if not feature_config:
            if fallback_screenshot:
                print(f"App '{group}/{feature}' not found in APP_CONFIGS! Taking fallback screenshot.")
                self._pull_screenshot("/sdcard/Pictures/app_screenshot.png")
            return False

        actions = feature_config.get("actions", {})
        if mode not in actions and mode_fallback and mode_fallback in actions:
            mode = mode_fallback

        app_config = {
            "package_name": feature_config.get("package_name", ""),
            "activity_name": feature_config.get("activity_name", ""),
            "tasks": actions,
        }
        self._execute_app_tasks(app_key, app_config, mode)
        return True

    def _execute_app_tasks(self, app_name: str, app_config: dict, app_eval_mode: str):
        """Execute app-specific tasks defined in the app config.

        Args:
            app_name: Name of the app being executed
            app_config: Dictionary containing activity_name, package_name, and tasks
            app_eval_mode: Mode of evaluation (create, modify, delete)
        """
        device_id = self._get_companion_device()

        # Enforce mode-specific task selection
        if not isinstance(app_config['tasks'], dict):
            raise ValueError(f"App '{app_name}' tasks must be a dictionary with mode keys (create/modify/delete)")

        task_list = app_config['tasks'].get(app_eval_mode, [])
        if not task_list:
            print(f"Warning: No tasks defined for mode '{app_eval_mode}' in {app_name}")
        for task in task_list:
            print(f"Performing task: {task}")
            time.sleep(2)

            if task[0] == 'open_activity':
                # Launch activity by component name (-n) with optional flags/extras.
                # task = ['open_activity', 'com.example.app/.MainActivity']
                # task = ['open_activity', 'com.android.settings/.SubSettings --es :settings:show_fragment com.samsung.android.settings.asbase.audio.SecVolumeSettings']
                self._adb.start_activity(device_id, task[1])
                time.sleep(2)
            elif task[0] == 'open_intent_action':
                # Launch activity by intent action (-a).
                # task = ['open_intent_action', 'com.samsung.android.app.reminder.action.VIEW_TRASH']
                self._adb.shell(device_id, f"am start -a {task[1]}")
                time.sleep(2)
            elif task[0] == 'close_app':
                self._adb.force_stop(device_id, app_config['package_name'])
            elif task[0] == 'click_stop_notification':
                time.sleep(15)
                self._click_phone(device_id, task[1], task[2])
            elif task[0] == 'click':
                self._click_phone(device_id, task[1], task[2])
            elif task[0] == 'swipe':
                self._swipe_phone(device_id, task[1], task[2], task[3], task[4])
            elif task[0] == 'screenshot':
                remote_path = "/sdcard/Pictures/app_screenshot.png"
                self._pull_screenshot(remote_path)
            elif task[0] == 'back':
                self._press_back(device_id)
            elif task[0] == 'wait':
                time.sleep(task[1])
            elif task[0] == 'speak':
                self._speak(task[1], task[2], task[3])
            elif task[0] == 'open_gemini':
                command = f"adb -s {device_id} shell monkey -p com.google.android.apps.bard -v 1"
                subprocess.run(command, shell=True)
                time.sleep(2)
            elif task[0] == 'long_wait':
                time.sleep(10)
            elif task[0] == 'open_notification_panel':
                subprocess.run(f"adb -s {device_id} shell service call statusbar 1", shell=True)
                time.sleep(2)
            elif task[0] == 'close_notification_panel':
                subprocess.run(f"adb -s {device_id} shell service call statusbar 2", shell=True)
                time.sleep(1)
            elif task[0] == 'tap_resource_id':
                # Tap UI element by resource-id (screen-size independent)
                self._tap_by_resource_id(device_id, task[1])
            elif task[0] == 'tap_content_desc':
                # Tap UI element by content-desc, for elements with no unique
                # resource-id. task = ['tap_content_desc', desc] (exact match) or
                # ['tap_content_desc', desc, True] (prefix match, e.g. desc that
                # includes a variable item count like "Completed, 1 item").
                prefix_match = task[2] if len(task) > 2 else False
                self._tap_by_content_desc(device_id, task[1], prefix_match=prefix_match)
            elif task[0] == 'tap_text':
                # Tap UI element by text content (case-insensitive).
                # Useful for bottom navigation tabs that share the same resource-id
                # but have different text labels. task = ['tap_text', 'Library']
                self._tap_by_text(device_id, task[1])

    # ── UI-tree tap infrastructure (shared by all _tap_by_* finders) ────
    #
    # A "finder" is a callable `(root) -> (bounds, clickable)` — it knows
    # HOW to locate a node in a freshly-dumped UI tree; everything else
    # (dumping the tree, retrying, falling back to a clickable ancestor,
    # tapping the center) is common and lives in _tap_matching_element.
    # Add new _tap_by_* methods by writing a new finder, not by copying
    # the dump/retry/tap loop again.

    def _get_ui_tree(self, device_id: str) -> str:
        """Dump the on-device UI tree and return it as an XML string.

        Uses adb exec-out to reliably read the UI tree XML file.
        Falls back to pulling the file if exec-out fails.
        """
        dump_cmd = f"adb -s {device_id} shell uiautomator dump /sdcard/ui.xml"
        subprocess.run(dump_cmd, shell=True, capture_output=True)
        time.sleep(1)

        cat_cmd = f"adb -s {device_id} exec-out cat /sdcard/ui.xml"
        result = subprocess.run(cat_cmd, shell=True, capture_output=True, text=True)
        xml_content = result.stdout

        # Fallback: if exec-out returned very little content, try pulling the file
        if not xml_content or len(xml_content) < 100:
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w") as f:
                tmp_path = f.name
            pull_cmd = f"adb -s {device_id} pull /sdcard/ui.xml {tmp_path}"
            subprocess.run(pull_cmd, shell=True, capture_output=True)
            try:
                with open(tmp_path, "r", encoding="utf-8") as f:
                    xml_content = f.read()
            except Exception:
                xml_content = ""
            finally:
                os.unlink(tmp_path)

        return xml_content

    @staticmethod
    def _find_first(root, predicate):
        """Return (bounds, clickable) for the first node matching `predicate`, or (None, False)."""
        for elem in root.iter("node"):
            if predicate(elem):
                bounds_str = elem.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
                if m:
                    return tuple(map(int, m.groups())), elem.get("clickable", "false") == "true"
        return None, False

    @staticmethod
    def _find_clickable_parent(root, target_bounds):
        """Find the smallest clickable element that contains the target bounds."""
        if not target_bounds:
            return None
        tx1, ty1, tx2, ty2 = target_bounds
        best = None
        best_area = float('inf')

        for elem in root.iter("node"):
            if elem.get("clickable", "false") == "true":
                bounds_str = elem.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
                if m:
                    x1, y1, x2, y2 = map(int, m.groups())
                    if x1 <= tx1 and y1 <= ty1 and x2 >= tx2 and y2 >= ty2:
                        area = (x2 - x1) * (y2 - y1)
                        if area < best_area:
                            best_area = area
                            best = (x1, y1, x2, y2)
        return best

    @staticmethod
    def _tap_center(bounds):
        """Calculate center of bounds."""
        x1, y1, x2, y2 = bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    def _tap_matching_element(self, device_id: str, description: str, finder_fn, max_retries=3, retry_delay=1.0) -> bool:
        """Dump the UI tree, locate a node via `finder_fn(root) -> (bounds, clickable)`,
        and tap it — falling back to the smallest enclosing clickable ancestor if the
        matched node itself isn't clickable. Retries the whole dump+find on failure.
        """
        def find_and_tap(xml_content):
            if not xml_content:
                return False
            try:
                root = ET.fromstring(xml_content)
                bounds, clickable = finder_fn(root)
                if bounds is None:
                    return False

                if not clickable:
                    print("  Element not clickable, finding clickable parent...")
                    clickable_bounds = self._find_clickable_parent(root, bounds)
                    if clickable_bounds:
                        print(f"  Found clickable parent: [{clickable_bounds[0]},{clickable_bounds[1]}][{clickable_bounds[2]},{clickable_bounds[3]}]")
                        bounds = clickable_bounds

                cx, cy = self._tap_center(bounds)
                print(f"  Tapping at ({cx}, {cy})")
                self._click_phone(device_id, cx, cy)
                return True
            except ET.ParseError as e:
                print(f"  Failed to parse UI tree XML: {e}")
            return False

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                print(f"  Retry {attempt}/{max_retries}: Looking for {description}...")
                time.sleep(retry_delay)

            xml_content = self._get_ui_tree(device_id)
            if not xml_content:
                print(f"  Attempt {attempt}/{max_retries}: Failed to read UI tree XML from device")
                continue

            if find_and_tap(xml_content):
                return True

        print(f"  Element not found after {max_retries} attempts: {description}")
        return False

    def _tap_by_resource_id(self, device_id: str, resource_id: str, max_retries=3, retry_delay=1.0) -> bool:
        """Tap UI element by resource-id using UI tree (screen-size independent).

        Retries multiple times to handle slow-loading apps (e.g., YouTube Music).
        Falls back to a partial resource-id match (e.g. "mini_player" contains "mini")
        if no exact match is found, then to the smallest enclosing clickable ancestor
        if the matched element itself isn't clickable.

        Args:
            device_id: ADB device serial
            resource_id: Full resource-id (e.g., "com.google.android.apps.youtube.music:id/mini_player_metadata")
            max_retries: Maximum number of attempts (default: 3)
            retry_delay: Seconds between retries (default: 1.0)

        Returns:
            True if element found and tapped, False otherwise.
        """
        def finder(root):
            bounds, clickable = self._find_first(root, lambda e: e.get("resource-id", "") == resource_id)
            if bounds is not None:
                return bounds, clickable

            print(f"  Element {resource_id} not found directly")
            base_id = resource_id.split('/')[-1]
            bounds, clickable = self._find_first(root, lambda e: base_id in e.get("resource-id", ""))
            if bounds is not None:
                print(f"  Found similar match for base id '{base_id}'")
            return bounds, clickable

        return self._tap_matching_element(device_id, resource_id, finder, max_retries, retry_delay)

    def _tap_by_content_desc(self, device_id: str, content_desc: str, prefix_match: bool = False,
                              max_retries=3, retry_delay=1.0) -> bool:
        """Tap UI element by content-desc using UI tree (screen-size independent).

        Use this when an element has no unique resource-id — e.g. Samsung Reminder's
        category tiles all share resource-id "category_name" and are distinguished only
        by content-desc ("Completed, 1 item", "Today, 3 items", ...). Retries and the
        clickable-parent fallback behave the same as `_tap_by_resource_id`.

        Args:
            device_id: ADB device serial
            content_desc: content-desc to search for.
                - prefix_match=False (default): must match exactly (e.g. "Now Playing Bar")
                - prefix_match=True: matches any desc starting with this string
                  (e.g. "Completed" matches "Completed, 1 item", "Completed, 0 items")
            prefix_match: match by prefix instead of exact match (default: False)
            max_retries: Maximum number of attempts (default: 3)
            retry_delay: Seconds between retries (default: 1.0)

        Returns:
            True if element found and tapped, False otherwise.
        """
        def finder(root):
            if prefix_match:
                return self._find_first(root, lambda e: e.get("content-desc", "").startswith(content_desc))
            return self._find_first(root, lambda e: e.get("content-desc", "") == content_desc)

        description = f"content-desc~='{content_desc}'" if prefix_match else f"content-desc='{content_desc}'"
        return self._tap_matching_element(device_id, description, finder, max_retries, retry_delay)

    def _tap_by_text(self, device_id: str, text: str, 
                     max_retries=3, retry_delay=1.0) -> bool:
        """Tap UI element by text content (case-insensitive).
        
        Useful for bottom navigation tabs that share the same resource-id
        but have different text labels (e.g., YouTube Music's Library/Home/Explore tabs).
        
        Args:
            device_id: ADB device serial
            text: Text to match (case-insensitive)
            max_retries: Maximum number of attempts (default: 3)
            retry_delay: Seconds between retries (default: 1.0)
        
        Returns:
            True if element found and tapped, False otherwise.
        """
        def finder(root):
            return self._find_first(root, lambda e: e.get("text", "").strip().lower() == text.lower())
        
        return self._tap_matching_element(device_id, f"text='{text}'", finder, max_retries, retry_delay)

    def _pull_screenshot(self, remote_path="/sdcard/Pictures/screen.png"):

        """Take a screenshot on the companion device and pull it to the log folder.

        Deletes any stale local copy first to avoid attaching wrong eval's screenshot.
        """
        device_id = self._get_companion_device()
        local_basename = remote_path.rsplit('/', 1)[1]
        local_path = os.path.join(self.log_folder, local_basename)
        if os.path.exists(local_path):
            os.remove(local_path)

        # Create directory first (in case it doesn't exist)
        command = f"adb -s {device_id} shell mkdir -p /sdcard/Pictures"
        subprocess.run(command, shell=True)

        # Take screenshot
        command = f"adb -s {device_id} shell screencap {remote_path}"
        subprocess.run(command, shell=True)
        print(command)

        command = (
            f"adb -s {device_id} pull"
            f' {remote_path}'
            f" {self.log_folder}"
        )
        subprocess.run(command, shell=True)
        print(command)

        self._clear_screenshot(remote_path)

    def _clear_screenshot(self, remote_path="/sdcard/Pictures/screen.png"):
        """Remove a screenshot file from the companion device."""
        device_id = self._get_companion_device()
        command = (
            f"adb -s {device_id} shell rm"
            f' {remote_path}'
        )
        subprocess.run(command, shell=True)
        print(command)


