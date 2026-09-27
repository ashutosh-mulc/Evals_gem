"""
StateCollectMixin — state collector integration.

Extracted from DeviceManagerTemplate so that managers that don't use
state collection (dummy, claude, gpt, meta) don't inherit it.

Requires the host class to have a `state_collector` (or `xrclaw_collector`)
attribute, or None if not using state collection.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class StateCollectMixin:
    """Mixin for state collector initialization and pre/post state capture.

    Host class should set:
        - self.state_collector: StateCollector instance or None
        - self.xrclaw_collector: backward-compat alias (optional)
    """

    def _init_state_collector(self, collector_config: dict, adb_device: str):
        """Initialize the state collector plugin if enabled in config.

        Args:
            collector_config: The "xrclaw" section from the config JSON.
            adb_device: ADB serial of the companion device running the apps.

        Returns:
            StateCollector instance if enabled, None otherwise.
        """
        if not collector_config or not collector_config.get("enabled", False):
            return None

        try:
            from agent_testers.device_managers.xrclaw_state_collector import XRClawStateCollector
            collector = XRClawStateCollector(
                python_automation_path=collector_config.get("python_automation_path", ""),
                adb_device=adb_device,
                adb_path="adb",
                claw_package=collector_config.get("claw_package", "com.samsung.xr.claw.client"),
            )
            logger.info("State collector initialized for device %s", adb_device)
            print(f"State collector initialized for device {adb_device}")
            return collector
        except Exception as e:
            logger.warning("Failed to initialize state collector: %s", e)
            print(f"Warning: Failed to initialize state collector: {e}")
            return None

    # ── Backward-compatible alias ──────────────────────────────────
    _init_xrclaw_collector = _init_state_collector

    def capture_pre_state(self, q_info: dict) -> None:
        """Snapshot the app's state-queryable data BEFORE the agent acts.

        See DeviceManagerTemplate.capture_pre_state() for full docs.
        """
        
        ## Find if a valid collector is available. If not, do nothing. ──
        collector = getattr(self, "state_collector", None)
        if collector is None:
            collector = getattr(self, "xrclaw_collector", None)
        if collector is None:
            return

        q_type = q_info.get("question_type", "")
        if not q_type or "_" not in q_type:
            return

        from common.question_type import QuestionType
        qt = QuestionType.parse(q_type)
        app_name = qt.app_key
        if not app_name:
            return

        supported_apps = collector.get_supported_apps()
        if app_name not in supported_apps:
            return

        ## Isn't this invalidatin the second last line ? 
        ## "pre_state_app = "device_mediacontrol" if "mediacontrol" in q_type.lower() else app_name"
        ## TODO: Figure out why we skipped medicontrol 
        if app_name == "device" and "mediacontrol" not in q_type.lower():
            return

        if qt.action == "launch":
            return

        pre_state_app = "device_mediacontrol" if "mediacontrol" in q_type.lower() else app_name
        q_info["metadata"]["app_state_pre"] = collector.capture_pre_state(pre_state_app)

    # ── Backward-compatible alias ──────────────────────────────────
    capture_xrclaw_pre_state = capture_pre_state

    def _collect_state(self, collector, q_info: dict) -> bool:
        """Run state collector verification for an APP_EVAL_TASK.

        See DeviceManagerTemplate._collect_state() for full docs.
        """
        if collector is None:
            return False

        q_type = q_info.get("question_type", "")
        if not q_type or "_" not in q_type:
            return False

        from common.question_type import QuestionType
        qt = QuestionType.parse(q_type)
        app_name = qt.app_key
        if not app_name:
            return False

        app_mode = qt.action

        supported_apps = collector.get_supported_apps()
        if app_name not in supported_apps:
            return False

        gt_answer = q_info.get("gt_answer", "")
        question = q_info.get("question", "")

        pre_state = q_info["metadata"].get("app_state_pre",
                                           q_info["metadata"].get("xrclaw_state_pre"))

        if app_name == "device":
            print(f"----State collector verifying device query ({q_type})----")
            result = collector.collect_device_state(
                question_type=q_type,
                question=question,
                gt_answer=gt_answer,
                pre_state=pre_state,
            )
            q_info["metadata"]["device_info_state"] = result
            print(f"Device info result: verified={result.get('verified')}, rating={result.get('rating')}")
            logger.info("Device info verification for %s: verified=%s, rating=%d",
                         result.get('query_type'), result.get('verified'), result.get('rating'))
            return result.get("method") == "device_info"

        print(f"----State collector verifying {app_name} ({app_mode})----")
        result = collector.collect_app_state(
            app_name=app_name,
            app_mode=app_mode,
            question=question,
            gt_answer=gt_answer,
            pre_state=pre_state,
        )

        q_info["metadata"]["app_state"] = result
        q_info["metadata"]["xrclaw_state"] = result  # backward compat
        print(f"State collector result: verified={result['verified']}, rating={result['rating']}")
        logger.info("State collector verification for %s: verified=%s, rating=%d",
                     app_name, result['verified'], result['rating'])

        return result.get("method") in ("xrclaw", "xrclaw_read", "state_collector", "state_collector_read")

    # ── Backward-compatible alias ──────────────────────────────────
    _xrclaw_collect_state = _collect_state
