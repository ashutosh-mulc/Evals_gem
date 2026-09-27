"""
State collector for Google Translate (Live Translation).

Extracted from XRClawStateCollector._collect_translation_state().

Collects live translation state by parsing ADB logcat.

This method reads the logcat (which was cleared before the query and
captured during the query) and checks:
  1. Translation intent was triggered (TranslateLanguage command)
  2. Google Translate app was launched
  3. Target language matches the expected language (if specified)
  4. Translation service connected
  5. Gemini conversation mode reached LISTENING state

The target language is extracted from the logcat (from the translation
app's actual state), NOT from the user's query.
"""

from __future__ import annotations

from ..helpers import result

APP_KEYS = ("googletranslate",)
PACKAGE_NAME = "com.google.android.apps.translate"


def capture_pre(dm) -> dict:
    """No pre-state snapshot for translation.

    Translation verification is done entirely via logcat parsing in verify().
    """
    return {}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Google Translate state after the agent has acted."""
    app_name = app_key

    # Read translation state from logcat
    state = dm.translation.get_state()
    actual_state = state.to_dict()

    gt_lower = gt_answer.lower().strip()
    expects_specific_language = gt_lower not in ("", "default", "any", "auto")

    # Determine expected language
    expected_lang_name = None
    expected_lang_code = None
    if expects_specific_language:
        for lang_name, lang_code in dm.translation.LANGUAGE_CODE_MAP.items():
            if lang_name == gt_lower or lang_code == gt_lower:
                expected_lang_name = lang_name
                expected_lang_code = lang_code
                break
        if expected_lang_name is None:
            expected_lang_name = gt_lower
            expected_lang_code = dm.translation.LANGUAGE_CODE_MAP.get(gt_lower)

    # ── Scoring logic ──
    rating = 0
    analysis_parts = []

    # Check 1: Translation intent triggered
    if not state.translation_triggered:
        analysis_parts.append("Translation intent was NOT triggered (no TranslateLanguage command in logcat).")
        return result(app_name, False, 0, ". ".join(analysis_parts), actual_state, gt_answer)

    analysis_parts.append("Translation intent triggered.")
    rating = 1

    # Check 2: Google Translate app launched
    if not state.translate_app_launched:
        analysis_parts.append("Google Translate app was NOT launched.")
        return result(app_name, False, rating, ". ".join(analysis_parts), actual_state, gt_answer)

    analysis_parts.append("Google Translate app launched.")
    rating = 2

    # Check 3: Language match (if a specific language was expected)
    if expects_specific_language:
        actual_name = state.target_language_name
        actual_code = state.target_language_code

        lang_matches = False
        if actual_name and actual_code:
            if actual_name == expected_lang_name or actual_name == gt_lower:
                lang_matches = True
            elif expected_lang_code and actual_code == expected_lang_code:
                lang_matches = True
            elif actual_code == gt_lower:
                lang_matches = True

        if not lang_matches:
            analysis_parts.append(
                f"Language mismatch: expected '{expected_lang_name}' ({expected_lang_code}), "
                f"but got '{actual_name}' ({actual_code})."
            )
            return result(app_name, False, rating, ". ".join(analysis_parts), actual_state, gt_answer)

        analysis_parts.append(f"Target language matches: {actual_name} ({actual_code}).")
        rating = 3
    else:
        analysis_parts.append("No specific language expected (default translation).")
        rating = 3

    # Check 4: Translation service connected
    if not state.translation_service_connected:
        analysis_parts.append("Translation service was NOT connected.")
        return result(app_name, False, rating, ". ".join(analysis_parts), actual_state, gt_answer)

    analysis_parts.append("Translation service connected.")
    rating = 4

    # Check 5: Gemini conversation mode reached LISTENING state
    if state.gemini_client_states:
        reached_listening = "LISTENING" in state.gemini_client_states
        if reached_listening:
            analysis_parts.append(
                f"Gemini conversation mode active (states: {state.gemini_client_states})."
            )
            rating = 5
        else:
            analysis_parts.append(
                f"Gemini conversation states: {state.gemini_client_states} (LISTENING not reached)."
            )
    else:
        # Check language pair changed as fallback
        if state.language_pair_changed:
            analysis_parts.append("Language pair change notification received.")
            rating = 5
        else:
            analysis_parts.append("No Gemini conversation states or language pair notification found.")

    verified = rating >= 4
    return result(app_name, verified, rating, ". ".join(analysis_parts), actual_state, gt_answer)
