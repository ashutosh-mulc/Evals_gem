"""
AppPlugin — the contract each app directory must follow.

Each app directory under ``apps/`` (top-level package) contains up to 6 files:

    __init__.py          Exports metadata (APP_KEY, GROUP, FEATURE, SKIP).
    config.py            package_name, activity_name, ACTIONS dict (task lists).
    state_collector.py   capture_pre(dm) + verify(dm, ...) — or stub.
    judge.py             HANDLERS dict + handler functions — or empty.
    prompt.json          LLM judge prompt (string, dict for mode-keyed, list, or callable) — or omitted.
    consent.py           CONSENT_RULES dict — or empty {}.

The registry in ``apps/registry.py`` auto-discovers all app directories and
builds the global registries that the framework consumes. App contributors
should not need to understand the registry mechanics — just provide the
files above, and the registry handles the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class AppPlugin:
    """Metadata describing a single app plugin.

    This is populated by the registry during auto-discovery. Each field
    corresponds to a module-level constant in the app's subdirectory.
    """

    app_key: str
    group: str
    feature: str
    skip: bool = False

    # Config
    package_name: str = ""
    activity_name: str = ""
    actions: Dict[str, List] = field(default_factory=dict)

    # State collector module (has capture_pre + verify functions)
    state_collector_module: Optional[Any] = None

    # Judge handlers: {(app_key, action) → handler_fn}
    judge_handlers: Dict[Tuple[str, str], str] = field(default_factory=dict)

    # LLM judge prompt
    prompt: Optional[str] = None

    # Consent rules: {(feature, action) → [(wav, pause, wait), ...]}
    consent_rules: Dict[Tuple[str, str], List[Tuple[str, int, int]]] = field(default_factory=dict)
