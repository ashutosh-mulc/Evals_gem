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
from typing import Any

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
        """Force-stop the app before a launch query so an already-running app can't pass."""
        from apps import get_package_name

        package_name = get_package_name(app_key)
        device_id = getattr(self.dm, "companion_device", None)
        if not package_name or not device_id:
            logger.warning(f"Skipping launch force-stop for app_key='{app_key}' (package={package_name}, device={device_id})")
            return

        try:
            self.dm._adb.force_stop(device_id, package_name)
            logger.info(f"Force-stopped {package_name} for launch precondition (app_key={app_key})")
        except Exception as e:
            logger.warning(f"Failed to force-stop {package_name}: {e}")
