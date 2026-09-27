"""
PreconditionManager — sets up and verifies device state before app evaluations.

Many app evaluation tasks require specific device state to exist BEFORE the AI
agent is invoked. For example:
  - "Delete a note titled Shopping List" requires the note to pre-exist
  - "Pause the music" requires media to be actively playing
  - "Turn volume up" requires volume at a known starting level

This module provides a central PreconditionManager that dispatches to per-app
precondition modules (discovered via the app registry) to set up and verify
the required state.

Usage:
    mgr = PreconditionManager(device_manager, state_collector)
    report = mgr.setup(q_info)
    # report = {"passed": True, "set": [...], "checked": [...], "failed": []}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from common.question_type import QuestionType

logger = logging.getLogger(__name__)


class PreconditionManager:
    """Central manager for setting up and verifying evaluation preconditions.

    Args:
        device_manager: The DeviceManager instance (provides ADB, XRClaw access).
        state_collector: Optional StateCollector instance for XRClaw-backed queries.
    """

    def __init__(self, device_manager: Any, state_collector: Any = None):
        self.dm = device_manager
        self.sc = state_collector

    def setup(self, q_info: dict) -> dict:
        """Set up preconditions before the agent is invoked.

        Dispatches to the app-specific precondition module if one exists.
        Returns a report dict with:
            - passed: bool — whether all preconditions were set successfully
            - set: list of str — descriptions of what was set
            - checked: list of str — descriptions of what was verified
            - failed: list of str — descriptions of what failed
            - skipped: str or None — reason if preconditions were skipped
        """
        q_type = q_info.get("question_type", "")
        qt = QuestionType.parse(q_type)

        # No question type or not an app eval — skip
        if not qt.group or not qt.feature:
            return self._skip("No question_type or unparseable")

        # For launch actions: force-stop the app first to ensure clean state
        if qt.action == "launch" and qt.app_key:
            self._force_stop_app_for_launch(qt.app_key)

        # Rows that declare their state get it built exactly; the rest keep the per-app module.
        if q_info.get("setup"):
            from apps.setup_state import apply_setup
            return apply_setup(getattr(self.sc, "_dm", None) or self.dm, q_info["setup"])

        # DND (zen mode) state is managed by connectivity setup, not here.
        app_report = self._dispatch_app_precondition(qt, q_info)
        return app_report

    def _dispatch_app_precondition(self, qt: QuestionType, q_info: dict) -> dict:
        """Run the app-specific precondition module, if one is registered."""
        from apps import PRECONDITIONS
        precond_mod = PRECONDITIONS.get(qt.app_key)
        if precond_mod is None:
            return self._skip(f"No precondition module for app_key='{qt.app_key}'")

        setup_fn = getattr(precond_mod, "setup", None)
        if setup_fn is None:
            return self._skip(f"No setup() in precondition module for '{qt.app_key}'")

        question = q_info.get("question", "")
        gt_answer = q_info.get("gt_answer", "")

        try:
            report = setup_fn(
                dm=self.dm,
                sc=self.sc,
                qt=qt,
                question=question,
                gt_answer=gt_answer,
            )
            report = self._normalize_report(report)
            logger.info(
                "Precondition setup for %s: passed=%s, set=%d, failed=%d",
                qt.app_key, report["passed"], len(report["set"]), len(report["failed"]),
            )
            return report
        except Exception as e:
            logger.error("Precondition setup failed for %s: %s", qt.app_key, e, exc_info=True)
            return self._fail(f"Precondition setup raised: {e}")

    def verify(self, q_info: dict) -> dict:
        """Verify that preconditions are met before proceeding.

        Returns:
            {"passed": bool, "details": str}
        """
        q_type = q_info.get("question_type", "")
        qt = QuestionType.parse(q_type)

        if not qt.group or not qt.feature:
            return {"passed": True, "details": "No precondition needed (no app_key)"}

        from apps import PRECONDITIONS
        precond_mod = PRECONDITIONS.get(qt.app_key)
        if precond_mod is None:
            return {"passed": True, "details": f"No precondition module for '{qt.app_key}'"}

        verify_fn = getattr(precond_mod, "verify", None)
        if verify_fn is None:
            return {"passed": True, "details": f"No verify() in precondition module for '{qt.app_key}'"}

        question = q_info.get("question", "")
        gt_answer = q_info.get("gt_answer", "")

        try:
            return verify_fn(
                dm=self.dm,
                sc=self.sc,
                qt=qt,
                question=question,
                gt_answer=gt_answer,
            )
        except Exception as e:
            logger.error("Precondition verify failed for %s: %s", qt.app_key, e, exc_info=True)
            return {"passed": False, "details": f"Precondition verify raised: {e}"}

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _normalize_report(report: dict) -> dict:
        """Ensure report has all expected keys with defaults."""
        return {
            "passed": report.get("passed", True),
            "set": report.get("set", []),
            "checked": report.get("checked", []),
            "failed": report.get("failed", []),
            "skipped": report.get("skipped", None),
        }

    @staticmethod
    def _skip(reason: str) -> dict:
        return {"passed": True, "set": [], "checked": [], "failed": [], "skipped": reason}

    @staticmethod
    def _fail(reason: str) -> dict:
        return {"passed": False, "set": [], "checked": [], "failed": [reason], "skipped": None}

    def _force_stop_app_for_launch(self, app_key: str) -> None:
        """Force-stop an app before launch to ensure clean state.
        
        Prevents false positives when the app is already running in background.
        
        Args:
            app_key: The app key (e.g., 'samsungcalendar', 'samsungnotes')
        """
        from apps import APP_CONFIGS
        from utils.adb_client import AdbClient
        
        # Find package_name from app_key by searching all groups
        package_name = None
        for group_config in APP_CONFIGS.values():
            for feature_name, feature_config in group_config.items():
                if isinstance(feature_config, dict) and feature_config.get("app_key") == app_key:
                    package_name = feature_config.get("package_name")
                    break
            if package_name:
                break
        
        if not package_name:
            logger.warning(f"Could not find package_name for app_key='{app_key}'")
            return
        
        # Get device_id from device manager
        device_id = getattr(self.dm, "companion_device", None)
        if not device_id:
            logger.warning(f"No companion_device available for force-stop of {package_name}")
            return
        
        try:
            adb = AdbClient()
            adb.force_stop(device_id, package_name)
            logger.info(f"Force-stopped {package_name} for launch precondition (app_key={app_key})")
        except Exception as e:
            logger.warning(f"Failed to force-stop {package_name}: {e}")
