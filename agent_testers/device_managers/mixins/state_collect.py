"""
StateCollectMixin — pre/post app state capture through ``self.state_collector``.

``self.state_collector`` is a StateCollector instance, or None when state
collection is disabled (DeviceManagerTemplate defaults it to None).
"""

from __future__ import annotations

import logging

from common.question_type import QuestionType

logger = logging.getLogger(__name__)


class StateCollectMixin:
    """Mixin for state collector initialization and pre/post state capture."""

    def _init_state_collector(self, collector_config: dict, adb_device: str):
        """Build the XRClaw state collector from the config's "xrclaw" section, or None."""
        if not collector_config or not collector_config.get("enabled", False):
            return None

        try:
            from agent_testers.device_managers.xrclaw_state_collector import XRClawStateCollector
            collector = XRClawStateCollector(
                python_automation_path=collector_config.get("python_automation_path", ""),
                adb_device=adb_device,
                adb_path="adb",
            )
            logger.info("State collector initialized for device %s", adb_device)
            return collector
        except Exception as e:
            logger.warning("Failed to initialize state collector: %s", e)
            return None

    def _collector_question_type(self, q_info: dict) -> QuestionType | None:
        """Parsed question type if the state collector supports its app, else None."""
        if self.state_collector is None:
            return None
        qt = QuestionType.parse(q_info.get("question_type", ""))
        if not qt.app_key or qt.app_key not in self.state_collector.get_supported_apps():
            return None
        return qt

    def capture_pre_state(self, q_info: dict) -> None:
        """Snapshot the app's state BEFORE the agent acts, for pre/post diffing."""
        qt = self._collector_question_type(q_info)
        if qt is None or qt.action == "launch":
            return
        if qt.app_key == "device":
            # Of the device features only media control is diffed against a pre-state.
            if qt.feature != "mediacontrol":
                return
            app = "device_mediacontrol"
        else:
            app = qt.app_key
        q_info["metadata"]["app_state_pre"] = self.state_collector.capture_pre_state(app)

    def _collect_state(self, q_info: dict) -> None:
        """Run state collector verification AFTER the agent acts and store it in metadata.

        Device queries go to metadata["device_info_state"], app queries to metadata["app_state"].
        """
        qt = self._collector_question_type(q_info)
        if qt is None:
            return

        meta = q_info["metadata"]
        question = q_info.get("question", "")
        gt_answer = q_info.get("gt_answer", "")
        pre_state = meta.get("app_state_pre")

        if qt.app_key == "device":
            result = self.state_collector.collect_device_state(qt.raw, question, gt_answer, pre_state)
            meta["device_info_state"] = result
        else:
            result = self.state_collector.collect_app_state(qt.app_key, qt.action, question, gt_answer, pre_state)
            meta["app_state"] = result

        logger.info("State collector %s (%s): verified=%s, rating=%s",
                    qt.app_key, qt.action, result.get("verified"), result.get("rating"))
