"""
Consent / affirmation audio player.

Plays pre-recorded WAV files to answer the agent's follow-up questions
(e.g. "Do you want to send this message?").  Rules are looked up from
the app registry's CONSENT_RULES, keyed by (feature, action).

## TODO:
Desing a smart voice agent for affirmation/consent

Usage:
    from agent_testers.consent_player import play_consent
    play_consent(device_manager, qt, assets_dir)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def play_consent(device_manager, qt, assets_dir: str) -> None:
    """Play consent audio for a question if rules exist.

    Args:
        device_manager: Device manager instance (must have _speak method).
        qt: QuestionType dataclass (from common.question_type).
        assets_dir: Path to the directory containing WAV files.
    """
    from apps import get_consent_rules

    rules = get_consent_rules(qt.feature, qt.action)
    if not rules:
        return

    for wav_file, pause, wait in rules:
        wav_path = os.path.join(assets_dir, wav_file)
        if not os.path.exists(wav_path):
            logger.warning("Consent audio not found: %s", wav_path)
            continue
        logger.info("Playing consent audio: %s (pause=%d, wait=%d)", wav_file, pause, wait)
        device_manager._speak(wav_path, pause, wait)
