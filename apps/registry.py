"""
App plugin registry — auto-discovers all apps/ subdirectories and builds
the global registries that the framework consumes.

Each app directory under ``apps/`` contains:
    config.py            — required: APP_KEY, GROUP, FEATURE (or FEATURES), PACKAGE_NAME, ACTIVITY_NAME, ACTIONS
    state_collector.py   — optional: APP_KEYS, capture_pre(dm), verify(dm, ...)
    judge.py             — optional: HANDLERS {(app_key, action): handler}
    prompt.json          — optional: VLM judge prompts
    consent.py           — optional: CONSENT_RULES
    precondition.py      — optional: setup(...)

Apps without a state collector or judge handler fall back to the VLM judge.

The registry auto-discovers all subdirectories and merges their data into:
    APP_CONFIGS          — {group: {feature: {package_name, activity_name, actions}}}
    APP_KEY_MAP          — {(group, feature) → app_key}
    STATE_COLLECTORS     — {app_key → module with capture_pre/verify}
    JUDGE_HANDLERS       — {(app_key, action) → handler function}
    JUDGE_PROMPTS        — {app_key → prompt string/dict}
    CONSENT_RULES        — {(feature, action) → [(wav, pause, wait), ...]}
    PRECONDITIONS        — {app_key → module with setup}
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)

# ── Auto-discovery ───────────────────────────────────────────────

_THIS_DIR = Path(__file__).parent

# All app subdirectories (skip files, __pycache__, etc.)
_APP_DIRS = sorted(
    d.name for d in _THIS_DIR.iterdir()
    if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
)

# ── Global registries (built by auto-discovery) ───────────────────

APP_CONFIGS: Dict[str, Dict[str, dict]] = {}
APP_KEY_MAP: Dict[Tuple[str, str], str] = {}
_APP_KEY_TO_CONFIG: Dict[str, Tuple[str, str]] = {}  # {app_key → (group, feature)} for O(1) lookup
STATE_COLLECTORS: Dict[str, Any] = {}       # {app_key → module with capture_pre/verify}
JUDGE_HANDLERS: Dict[Tuple[str, str], Callable[[str, str, dict], Tuple[int, str]]] = {}  # {(app_key, action) → handler function}
JUDGE_PROMPTS: Dict[str, Any] = {}           # {app_key → prompt string/dict}
CONSENT_RULES: Dict[Tuple[str, str], List[Tuple[str, int, int]]] = {}
PRECONDITIONS: Dict[str, Any] = {}           # {app_key → module with setup/verify}


def _discover_apps():
    """Import each app's submodules and merge into the global registries."""
    for app_dir in _APP_DIRS:
        pkg = f"apps.{app_dir}"

        # ── config.py (required) ──
        try:
            cfg = importlib.import_module(f".config", package=pkg)
        except ImportError:
            logger.debug("App %s has no config.py — skipping", app_dir)
            continue

        app_key = getattr(cfg, "APP_KEY", "")
        group = getattr(cfg, "GROUP", "")

        if not app_key or not group:
            logger.warning("App %s missing APP_KEY/GROUP — skipping", app_dir)
            continue

        # ── Handle both single-feature and multi-feature apps ──
        # Single-feature apps export FEATURE (str) + flat ACTIONS {action: steps}
        # Multi-feature apps (e.g. device) export FEATURES (tuple) + nested ACTIONS {feature: {action: steps}}
        features = getattr(cfg, "FEATURES", None)
        if features:
            # Multi-feature app: register each feature separately
            actions_dict = getattr(cfg, "ACTIONS", {})
            for feat in features:
                APP_KEY_MAP[(group, feat)] = app_key
                _APP_KEY_TO_CONFIG[app_key] = (group, feat)  # Last feature wins for multi-feature apps
                APP_CONFIGS.setdefault(group, {})[feat] = {
                    "package_name": getattr(cfg, "PACKAGE_NAME", ""),
                    "activity_name": getattr(cfg, "ACTIVITY_NAME", ""),
                    "actions": actions_dict.get(feat, {}),
                }
        else:
            # Single-feature app
            feature = getattr(cfg, "FEATURE", "")
            APP_KEY_MAP[(group, feature)] = app_key
            _APP_KEY_TO_CONFIG[app_key] = (group, feature)
            APP_CONFIGS.setdefault(group, {})[feature] = {
                "package_name": getattr(cfg, "PACKAGE_NAME", ""),
                "activity_name": getattr(cfg, "ACTIVITY_NAME", ""),
                "actions": getattr(cfg, "ACTIONS", {}),
            }

        # ── state_collector.py (optional) ──
        try:
            sc_mod = importlib.import_module(f".state_collector", package=pkg)
            for ak in getattr(sc_mod, "APP_KEYS", (app_key,)):
                STATE_COLLECTORS[ak] = sc_mod
        except ImportError:
            pass

        # ── judge.py (optional) ──
        try:
            judge_mod = importlib.import_module(f".judge", package=pkg)
            handlers = getattr(judge_mod, "HANDLERS", {})
            for key, fn in handlers.items():
                if not callable(fn):
                    raise TypeError(
                        f"apps.{app_dir}.judge.HANDLERS[{key!r}] must be a function, got {fn!r}. "
                        f"Import the handler and reference it directly."
                    )
                JUDGE_HANDLERS[key] = fn
        except ImportError:
            pass

        # ── prompt.json (optional) ──
        prompt_path = _THIS_DIR / app_dir / "prompt.json"
        if prompt_path.exists():
            JUDGE_PROMPTS[app_key] = json.loads(prompt_path.read_text(encoding="utf-8"))

        # ── consent.py (optional) ──

        try:
            consent_mod = importlib.import_module(f".consent", package=pkg)
            rules = getattr(consent_mod, "CONSENT_RULES", {})
            for key, wavs in rules.items():
                CONSENT_RULES[key] = wavs
        except ImportError:
            pass

        # ── precondition.py (optional) ──
        try:
            precond_mod = importlib.import_module(f".precondition", package=pkg)
            PRECONDITIONS[app_key] = precond_mod
        except ImportError:
            pass

    logger.info(
        "App registry: %d apps discovered, %d state collectors, %d judge handlers, %d prompts, %d consent rules, %d preconditions",
        len(APP_KEY_MAP), len(STATE_COLLECTORS), len(JUDGE_HANDLERS),
        len(JUDGE_PROMPTS), len(CONSENT_RULES), len(PRECONDITIONS),
    )


# Run discovery on import
_discover_apps()


# ── Public query functions ───────────────────────────────────────

def supported_apps() -> set:
    """Return the set of app_keys that have a state collector."""
    return set(STATE_COLLECTORS.keys())


def get_state_collector(app_key: str):
    """Return the state collector module for an app_key, or None."""
    return STATE_COLLECTORS.get(app_key)


def get_judge_handler(app_key: str, action: str) -> Optional[Callable[[str, str, dict], Tuple[int, str]]]:
    """Return the handler function for (app_key, action), or None."""
    return JUDGE_HANDLERS.get((app_key, action))


def get_prompt(app_key: str) -> Optional[str | dict | list]:
    """Return the LLM judge prompt for an app_key, or None.

    Returns a string (legacy/simple prompts), dict (mode-keyed prompts),
    list (array prompts), or callable (device lambda), depending on the
    app's prompt.json structure.
    """
    return JUDGE_PROMPTS.get(app_key)


def get_consent_rules(feature: str, action: str) -> List[Tuple[str, int, int]]:
    """Return consent audio rules for (feature, action), or empty list."""
    return CONSENT_RULES.get((feature, action), [])


# ── Convenience helpers (folded in from agent_testers/device_managers/app_config.py) ──

def get_task_list(question_type: str) -> list | None:
    """Look up the task list for a 4-part question_type.

    Args:
        question_type: e.g. "online_samsung_notes_create"

    Returns:
        Task list (list of step lists) or None if not found.
    """
    # Deferred import to avoid circular: apps.registry ↔ common.question_type
    from common.question_type import QuestionType
    qt = QuestionType.parse(question_type)
    if not qt.group:
        return None

    group_config = APP_CONFIGS.get(qt.group)
    if not group_config:
        return None

    # Try direct feature lookup
    feature_config = group_config.get(qt.feature)
    if feature_config:
        actions = feature_config.get("actions", {})
        # Try single action
        if qt.action in actions:
            return actions[qt.action]
        # Try compound action: action + "_" + next part (e.g. "thread_read")
        parts = question_type.lower().split("_")
        if len(parts) >= 5:
            compound_action = f"{parts[3]}_{parts[4]}"
            if compound_action in actions:
                return actions[compound_action]

    return None


def get_app_info(question_type: str) -> dict | None:
    """Get package_name and activity_name for a question_type.

    Returns:
        {"package_name": ..., "activity_name": ...} or None.
    """
    from common.question_type import QuestionType
    qt = QuestionType.parse(question_type)
    if not qt.group:
        return None

    group_config = APP_CONFIGS.get(qt.group)
    if not group_config:
        return None

    feature_config = group_config.get(qt.feature)
    if feature_config:
        return {
            "package_name": feature_config.get("package_name", ""),
            "activity_name": feature_config.get("activity_name", ""),
        }

    return None


def get_app_key(question_type: str) -> str | None:
    """Map a 4-part question_type to the canonical app key.

    e.g. "online_samsung_notes_create" → "samsungnote"
         "online_samsung_clock_timer_create" → "clocktimer"

    Returns None if the app is not in APP_KEY_MAP.
    """
    from common.question_type import QuestionType
    qt = QuestionType.parse(question_type)
    return qt.app_key


def get_package_name(app_key: str) -> str | None:
    """Return the package name for an app_key, or None if unknown.

    Args:
        app_key: e.g. "samsungnote", "googlecalendar", "clockalarm"

    Returns:
        Package name like "com.samsung.android.app.notes" or None if not found.
    """
    group_feature = _APP_KEY_TO_CONFIG.get(app_key)
    if not group_feature:
        return None

    group, feature = group_feature
    feature_cfg = APP_CONFIGS.get(group, {}).get(feature)
    if feature_cfg:
        return feature_cfg.get("package_name", "")
    return None


# ── Backward-compatible aliases ───────────────────────────────────
XRCLAW_APP_KEY_MAP = APP_KEY_MAP
get_xrclaw_app_key = get_app_key
