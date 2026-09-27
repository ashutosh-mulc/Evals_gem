"""
Deterministic Judge — evaluates queries without LLM by comparing
parsed TTS responses against grounding information (app state from
state collector, device logs, screenshots, flags).

Architecture:
    - DeterministicJudge: Main entry point. Routes question_type → handler.
    - Handler registry: Lives in apps/JUDGE_HANDLERS — maps (app, task) → handler function.
    - Handlers live in apps/judge_helpers.py (shared) and apps/device/judge_rules.py (device-only).

Fallback policy:
    1. If question_type not in registry → return None (caller falls back to VLM)
    2. If handler raises exception → return None (caller falls back to VLM)
    3. If handler returns rating <= BAD_RATING_THRESHOLD → caller can optionally
       re-evaluate with VLM (configurable)

To add a new app/type:
    1. Add the handler to your app's judge.py HANDLERS dict
    2. Done — no changes needed to this file.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Tuple

from apps import JUDGE_HANDLERS, get_app_key
from apps.judge_helpers import parse_question_type, get_device_state, get_flag

logger = logging.getLogger(__name__)

# Rating threshold below which caller should fall back to VLM
BAD_RATING_THRESHOLD = 3


class DeterministicJudge:
    """
    General-purpose deterministic judge.

    Routes queries to handlers based on question_type.
    Each handler:
      1. Parses the TTS response into structured data
      2. Extracts grounding info from metadata (device state, XRClaw, flags)
      3. Compares parsed vs grounding → (rating, analysis)

    Returns (response_json, entropy_metrics) or None if unsupported.
    """

    BAD_RATING_THRESHOLD = 3

    # ── Handler registry (directly from apps.JUDGE_HANDLERS) ──────────
    HANDLER_REGISTRY = JUDGE_HANDLERS

    # ── Public API ─────────────────────────────────────────────────

    @classmethod
    def can_handle(cls, question_type: str) -> bool:
        """Check if this question_type can be evaluated deterministically."""
        app, task = cls._parse_question_type(question_type)
        return (app, task) in cls.HANDLER_REGISTRY

    def evaluate(
        self,
        question_type: str,
        question: str,
        ai_response: str,
        metadata: dict,
    ) -> Optional[Tuple[str, dict]]:
        """Main entry point.

        Returns (response_json, entropy_metrics) if handled, None if unsupported.
        """
        app, task = self._parse_question_type(question_type)
        handler_fn = self.HANDLER_REGISTRY.get((app, task))

        if not handler_fn:
            return None

        if "question_type" not in metadata:
            metadata = {**metadata, "question_type": question_type}

        try:
            rating, analysis = handler_fn(question, ai_response, metadata)
        except Exception as e:
            logger.error(
                "Deterministic judge error for %s: %s",
                question_type, e, exc_info=True,
            )
            return None

        if rating <= self.BAD_RATING_THRESHOLD:
            logger.info(
                "Deterministic judge gave low rating %d for %s — caller may fall back to VLM",
                rating, question_type,
            )

        response = {
            "question": question,
            "analysis": f"[Deterministic Judge] {analysis}",
            "rating": rating,
        }
        response_json = json.dumps(response, ensure_ascii=False)

        entropy_metrics = {
            "entropy": 0.0,
            "surprisal": 0.0,
            "curvature": 0.0,
            "entropy_delta": 0.0,
        }

        return response_json, entropy_metrics

    # ── Question type parsing ──────────────────────────────────────

    @staticmethod
    def _parse_question_type(question_type: str) -> Tuple[str, str]:
        """Parse question_type into (app, task)."""
        return parse_question_type(question_type)

    # ── Static helpers kept for backward compat ───────────────────

    @staticmethod
    def _get_device_state(metadata: dict, when: str = "post") -> dict:
        return get_device_state(metadata, when)

    @staticmethod
    def _get_flag(metadata: dict, flag_name: str) -> bool:
        return get_flag(metadata, flag_name)
