""" XRClaw State Collector — programmatic verification of APP_EVAL_TASK using XRClaw.

This module wraps the XRClaw Python Automation framework's `DeviceManager` to
query the actual app databases on the companion device and verify whether the
AI agent's action succeeded — without taking screenshots or calling an LLM judge.

The XRClaw DeviceManager provides programmatic access to:
  - Samsung Notes      (dm.notes)
  - Samsung Reminders   (dm.reminders)
  - Samsung Calendar    (dm.calendar)
  - Samsung Messages    (dm.messages)
  - Samsung Stopwatch   (dm.stopwatch)
  - Google Maps         (dm.maps)
  - Live Translation    (dm.translation)
  - Notifications       (dm.notifications)

Usage:
    collector = XRClawStateCollector(
        python_automation_path="/path/to/XRClaw/python_automation",
        adb_device="R5CR30XXXXX",
    )
    result = collector.collect_app_state(
        app_name="samsungnote",
        app_mode="create",
        question="Create a note titled Shopping List with milk and eggs",
        gt_answer="A note titled 'Shopping List' with content 'milk and eggs'",
    )
    # result = {
    #     "method": "xrclaw",
    #     "app_name": "samsungnote",
    #     "verified": True,
    #     "rating": 5,
    #     "analysis": "Note 'Shopping List' found with matching content.",
    #     "actual_state": {...},
    #     "expected": "A note titled 'Shopping List' with content 'milk and eggs'",
    # }
"""

import sys
import os
import logging

from agent_testers.device_managers.state_collector import StateCollector
from apps import STATE_COLLECTORS, supported_apps as _registry_supported_apps
from apps.helpers import unsupported_result, error_result

logger = logging.getLogger(__name__)


class XRClawStateCollector(StateCollector):
    """
    Collects app state for APP_EVAL_TASK by querying actual app state via XRClaw.

    This class wraps XRClaw's DeviceManager and provides app-specific verification
    logic. It does NOT take screenshots or call any LLM — it directly queries
    the app databases/content providers on the device.

    Implements the StateCollector plugin interface so the core framework can
    interact with it generically (without importing XRClaw-specific types).
    """


    def __init__(
        self,
        python_automation_path: str,
        adb_device: str,
        adb_path: str = "adb",
    ):
        """
        Initialize the XRClaw state collector.

        Args:
            python_automation_path: Path to the XRClaw `python_automation` directory.
            adb_device: ADB serial of the companion device running the apps.
            adb_path: Path to the ADB executable (default: "adb").
        """
        self.adb_device = adb_device
        self.adb_path = adb_path
        self._dm = None

        if not python_automation_path or not os.path.isdir(python_automation_path):
            raise ValueError(
                f"XRClaw python_automation_path does not exist: '{python_automation_path}'. "
                "Set 'xrclaw.python_automation_path' in your config to the XRClaw python_automation directory."
            )

        # Add the parent of python_automation_path to sys.path so that
        # `from python_automation import DeviceManager` works.
        parent_dir = os.path.dirname(python_automation_path)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        from python_automation import DeviceManager

        self._dm = DeviceManager(adb_path=adb_path, device=adb_device)
        logger.info(
            "XRClaw DeviceManager initialized: device=%s, adb=%s", adb_device, adb_path
        )
        print(f"XRClaw DeviceManager initialized: device={adb_device}, adb={adb_path}")

    # ── Public API ──────────────────────────────────────────────────

    def get_supported_apps(self) -> set[str]:
        """Return the set of app keys that this collector can verify."""
        return _registry_supported_apps()

    def capture_pre_state(self, app_name: str) -> dict:
        """
        Snapshot the app's current state BEFORE the agent acts.

        Uses registry dispatch to the app-specific state collector module.

        Args:
            app_name: Lowercase app name (e.g., "samsungnote").

        Returns:
            Dict with the pre-state snapshot, or empty dict if unsupported.
        """
        mod = STATE_COLLECTORS.get(app_name)
        if mod and hasattr(mod, "capture_pre"):
            try:
                return mod.capture_pre(self._dm)
            except Exception as e:
                logger.warning("Failed to capture pre-state for %s: %s", app_name, e)
                return {}
        return {}

    def collect_app_state(
        self,
        app_name: str,
        app_mode: str,
        question: str,
        gt_answer: str,
        pre_state: dict = None,
    ) -> dict:
        """
        Collect app state for an APP_EVAL_TASK by querying the actual app state via XRClaw.

        Uses registry dispatch to the app-specific state collector module.

        Args:
            app_name: Lowercase app name from question_type (e.g., "samsungnote").
            app_mode: Task mode from question_type (e.g., "create", "modify", "delete").
            question: The original user question/query.
            gt_answer: The expected ground-truth answer.
            pre_state: Optional pre-state snapshot (from capture_pre_state) for
                       apps that accumulate state (notes, reminders, etc.).

        Returns:
            Result dict with keys:
                - method: "xrclaw" on success, "xrclaw_error" on failure
                - app_name: The app that was verified
                - verified: bool
                - rating: int (0-5)
                - analysis: str
                - actual_state: dict (the actual app state that was queried)
                - expected: str (the gt_answer)
        """
        mod = STATE_COLLECTORS.get(app_name)
        if mod and hasattr(mod, "verify"):
            try:
                return mod.verify(self._dm, app_name, app_mode, question, gt_answer, pre_state)
            except Exception as e:
                logger.error("XRClaw verification error for %s: %s", app_name, e, exc_info=True)
                return error_result(app_name, gt_answer, str(e))
        return unsupported_result(app_name, gt_answer)

    def collect_device_state(
        self,
        question_type: str,
        question: str,
        gt_answer: str,
        pre_state: dict = None,
    ) -> dict:
        """
        Collect device state for a DEVICE_* query by querying device state via XRClaw.

        This is a separate entry point from collect_app_state() because device queries
        have a different question_type format (DEVICE_<STATE>_<COMMAND_TYPE>)
        and don't follow the app_name/mode pattern.

        Args:
            question_type: The question type string (e.g., "DEVICE_ONLINE_BATTERY").
            question: The original user question.
            gt_answer: The expected ground-truth answer.

        Returns:
            Result dict with keys:
                - method: "device_info" on success, "device_info_error" on failure
                - query_type: The extracted query type (battery, time, etc.)
                - verified: bool
                - rating: int (0-5)
                - analysis: str
                - actual_state: dict
                - expected: str (the gt_answer)
        """
        try:
            # Query device state via XRClaw DeviceInfoApp — fetch only, no evaluation.
            # Evaluation is done by DeterministicJudge in the judge_worker process.
            device_state = self._dm.device_info.get_all()
            state_dict = device_state.to_dict()

            # Store raw state — the deterministic judge will compare it against
            # the TTS response and gt_answer.
            return {
                "method": "device_info",
                "query_type": self._extract_query_type(question_type),
                "verified": False,  # not evaluated here
                "rating": 0,  # not evaluated here
                "analysis": "Device state fetched via XRClaw — evaluation deferred to DeterministicJudge.",
                "actual_state": state_dict,
                "expected": gt_answer,
            }
        except Exception as e:
            logger.error("Device info fetch error for %s: %s", question_type, e, exc_info=True)
            return {
                "method": "device_info_error",
                "query_type": self._extract_query_type(question_type),
                "verified": False,
                "rating": 0,
                "analysis": f"Device info fetch failed: {e}",
                "actual_state": {},
                "expected": gt_answer,
            }


    @staticmethod
    def _extract_query_type(question_type: str) -> str:
        """Extract query type from question_type string (e.g., 'device_online_battery' → 'battery')."""
        parts = question_type.lower().split('_')
        return parts[-1] if len(parts) >= 3 else question_type
