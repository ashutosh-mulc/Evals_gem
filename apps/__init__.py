"""
App plugin package — thin re-export of the registry module.

All discovery logic, registry dicts, query helpers, and convenience
functions live in ``apps.registry``.  This file re-exports them so that
``from apps import APP_CONFIGS`` continues to work unchanged.
"""

from apps.registry import (
    APP_CONFIGS,
    APP_KEY_MAP,
    STATE_COLLECTORS,
    JUDGE_HANDLERS,
    JUDGE_PROMPTS,
    CONSENT_RULES,
    PRECONDITIONS,
    supported_apps,
    get_state_collector,
    get_judge_handler,
    get_prompt,
    get_consent_rules,
    get_task_list,
    get_app_info,
    get_app_key,
    get_package_name,
)

__all__ = [
    "APP_CONFIGS",
    "APP_KEY_MAP",
    "STATE_COLLECTORS",
    "JUDGE_HANDLERS",
    "JUDGE_PROMPTS",
    "CONSENT_RULES",
    "PRECONDITIONS",
    "supported_apps",
    "get_state_collector",
    "get_judge_handler",
    "get_prompt",
    "get_consent_rules",
    "get_task_list",
    "get_app_info",
    "get_app_key",
    "get_package_name",
]
