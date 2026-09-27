"""
Question loader — decodes and validates question data.

Extracts the base64 decode + skip-guard logic from agent_tester.execute()
so that execute() reads as a sequence of named steps.

Usage:
    from agent_testers.question_loader import load_question
    q_info, ok = load_question(raw_question)
    if not ok:
        return  # skip this question
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def load_question(raw_question: str) -> Tuple[Optional[dict], bool]:
    """Decode a raw question string and check if it should be skipped.

    Args:
        raw_question: Base64-encoded or JSON string containing question data.

    Returns:
        (question_info, ok) where:
            - question_info: decoded dict or None on failure
            - ok: True if the question should be processed, False if it should be skipped
    """
    if not raw_question:
        return None, False

    # ── Decode ──
    q_info = None
    try:
        # Try base64 decode first
        try:
            decoded = base64.b64decode(raw_question).decode("utf-8")
            q_info = json.loads(decoded)
        except Exception:
            # Fall back to plain JSON
            q_info = json.loads(raw_question)
    except Exception as e:
        logger.error("Failed to decode question: %s", e)
        return None, False

    if not q_info:
        return None, False

    # ── Validate ──
    question_type = q_info.get("question_type", "")
    if not question_type:
        logger.warning("Question has no question_type — skipping")
        return q_info, False

    return q_info, True
