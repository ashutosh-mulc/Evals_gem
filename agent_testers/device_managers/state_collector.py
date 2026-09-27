"""
State Collector — plugin interface for programmatic app state collection.

This abstract base class defines the contract that any state collector plugin
must implement.  The core framework (DeviceManagerTemplate, DeterministicJudge,
ResponseScorer) interacts only with this interface; it does not import or know
about any specific plugin (e.g. XRClaw).

The XRClaw plugin (xrclaw_state_collector.py) is the first and currently only
implementation.  Future plugins (e.g. a UI-automation-based collector) can
implement this interface and be dropped in without core changes.

Usage from the core:
    collector = device_manager.state_collector  # StateCollector | None
    if collector is not None:
        pre = collector.capture_pre_state(app_key)
        result = collector.collect_app_state(app_key, mode, question, gt_answer, pre)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class StateCollector(ABC):
    """
    Plugin interface for programmatic app state collection.

    A state collector queries the actual app databases / content providers on
    the device.

    The collector runs on the **agent tester** process.  Results are stored in
    ``metadata["app_state"]`` and later read by the DeterministicJudge on the
    **judge worker** process.
    """

    @abstractmethod
    def capture_pre_state(self, app_key: str) -> dict:
        """Snapshot the app's current state BEFORE the agent acts.

        Used by collect_app_state() to diff pre vs post state, so we can
        distinguish "the agent just created this" from "this was already there."

        Args:
            app_key: Canonical app key (e.g. "samsungnote", "device").

        Returns:
            Dict with the pre-state snapshot, or empty dict if unsupported.
        """

    @abstractmethod
    def collect_app_state(
        self,
        app_key: str,
        app_mode: str,
        question: str,
        gt_answer: str,
        pre_state: Optional[dict] = None,
    ) -> dict:
        """Collect app state AFTER the agent acts and produce a verification result.

        Args:
            app_key: Canonical app key (e.g. "samsungnote").
            app_mode: Task mode from question_type (e.g. "create", "modify", "delete").
            question: The original user question/query.
            gt_answer: The expected ground-truth answer.
            pre_state: Optional pre-state snapshot from capture_pre_state().

        Returns:
            Result dict with keys:
                - method: str (e.g. "state_collector" on success,
                  "state_collector_error" on failure)
                - app_name: str
                - verified: bool
                - rating: int (0-5)
                - analysis: str
                - actual_state: dict
                - expected: str (the gt_answer)
        """

    @abstractmethod
    def collect_device_state(
        self,
        question_type: str,
        question: str,
        gt_answer: str,
        pre_state: Optional[dict] = None,
    ) -> dict:
        """Collect device state for a DEVICE_* query (battery, time, volume, etc.).

        This is a separate entry point from collect_app_state() because device
        queries have a different question_type format and don't follow the
        app_key/mode pattern.

        Args:
            question_type: The question type string (e.g. "device_online_battery").
            question: The original user question.
            gt_answer: The expected ground-truth answer.
            pre_state: Optional pre-state snapshot.

        Returns:
            Result dict (same structure as collect_app_state, with
            method="device_info" on success).
        """

    @abstractmethod
    def get_supported_apps(self) -> set[str]:
        """Return the set of app keys that this collector can verify.

        Used by the core to decide whether to attempt state collection or
        fall back to the screenshot+VLM path.
        """

