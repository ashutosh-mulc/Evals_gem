"""
Shared judge helpers for app state evaluation.

These handlers are used by multiple apps and live under apps/ to enable
direct imports from app judge.py files, removing the string indirection.
"""

from __future__ import annotations

import json
import subprocess
import logging
from typing import Tuple

from apps.helpers import VERIFIED_METHODS
from common.question_type import QuestionType

logger = logging.getLogger(__name__)


# =============================================================================
# Common helpers (from judge_worker/handlers/_common.py)
# =============================================================================

def get_device_state(metadata: dict, when: str = "post") -> dict:
    """Extract device state from metadata.

    For Jinju device queries, returns the jinju sub-dict.
    For companion battery/mediacontrol queries, returns the companion sub-dict.
    """
    if when == "pre":
        state = metadata.get("device_info_pre", {})
    else:
        state = metadata.get("device_info_post", {})

    qt = QuestionType.parse(metadata.get("question_type", ""))
    uses_companion = (qt.feature == "battery" and qt.action == "companion") or qt.feature in ("mediacontrol", "dnd")
    return state.get("companion" if uses_companion else "jinju", {})


def get_flag(metadata: dict, flag_name: str) -> bool:
    """Read a boolean log-analysis flag (e.g. jinju_image_captured) from metadata."""
    app_state = metadata.get("app_state") or {}
    return bool((app_state.get("log_analysis") or {}).get(flag_name, False))


# =============================================================================
# App state handler (from judge_worker/handlers/app_state_handler.py)
# =============================================================================

def handle_app_state(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate app queries using state collector results from metadata.

    The state collector on the agent tester side queries the actual app
    database (notes, reminders, calendar, clock, etc.) via the plugin
    interface and stores the result in metadata["app_state"].

    This handler reads that pre-computed state and produces a rating.
    If app_state is missing or indicates an error, returns a low
    rating so the caller can fall back to VLM.
    """
    app_state = metadata.get("app_state", {})

    if not app_state:
        return 0, "App state query: no app_state found in metadata. Criteria: state collector must have captured app state. Cannot evaluate deterministically — falling back to VLM. Rating: 0."

    method = app_state.get("method", "")
    if method not in VERIFIED_METHODS:
        if method == "xrclaw_unavailable":
            return 0, f"App state query: state collector reports '{app_state.get('analysis', 'App state unavailable')}'. Criteria: state collector must verify app state. Cannot verify deterministically — falling back to VLM with gt_answer grounding. Rating: 0."
        return 0, f"App state query: state collector method is '{method}' (not a successful verification). Criteria: method must be one of {sorted(VERIFIED_METHODS)}. Falling back to VLM. Rating: 0."

    rating = app_state.get("rating", 0)
    analysis = app_state.get("analysis", "No state collector analysis available.")
    verified = app_state.get("verified", False)
    app_name = app_state.get("app_name", "unknown")
    actual_state = app_state.get("actual_state", {})
    expected = app_state.get("expected", "")

    full_analysis = (
        f"App state query for '{app_name}'. State collector verification: {'PASSED' if verified else 'FAILED'}. "
        f"Criteria: {analysis} "
        f"Expected: '{expected}'. "
        f"Actual state: {json.dumps(actual_state, ensure_ascii=False)[:500]}. "
        f"Rating: {rating}."
    )

    return rating, full_analysis


# =============================================================================
# Launch handler (from judge_worker/handlers/launch_handler.py)
# =============================================================================

def _is_package_running(package: str, device: str = "") -> bool:
    """Check if a package's process is running via ADB."""
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    cmd += ["shell", "ps -A"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=10, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            logger.warning("ADB ps -A failed: %s", result.stderr)
            return False
        return package in result.stdout
    except Exception as e:
        logger.warning("ADB is_package_running error for %s: %s", package, e)
        return False


def _check_running(action: str, expect_running: bool, metadata: dict) -> Tuple[int, str]:
    """Shared logic for handle_launch (expect_running=True) and handle_exit
    (expect_running=False): resolve the app's package from question_type, check
    via ADB whether its process is running, and rate against what's expected."""
    from apps import get_package_name

    app = QuestionType.parse(metadata.get("question_type", "")).app_key
    requirement = "must be running" if expect_running else "must NOT be running"

    # Get package name from registry (single source of truth)
    package = get_package_name(app)
    if not package:
        return 2, f"App {action} query for '{app}'. No package name found in APP_CONFIGS. Criteria: app process {requirement}. Cannot verify — unknown app. Rating: 2."

    device = (
        metadata.get("companion_device")
        or metadata.get("s25_device_id")
        or ""
    )

    is_running = _is_package_running(package, device)
    if is_running:
        state = "IS running" if expect_running else "IS still running"
    else:
        state = "is NOT running"

    rating = 5 if is_running == expect_running else 1
    return rating, (
        f"App {action} query for '{app}'. Package: {package}. "
        f"ADB ps -A check: process {state} on device {device or 'default'}. "
        f"Criteria: app process {requirement}. Rating: {rating}."
    )


def handle_launch(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate app launch query: check if the app's package is running."""
    return _check_running("launch", True, metadata)


def handle_exit(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate app exit query: check if the app's package is NOT running.

    This is the inverse of handle_launch — a successful exit means the app
    process is no longer running.
    """
    return _check_running("exit", False, metadata)


# =============================================================================
# Camera/Video handlers (from judge_worker/handlers/camera_handler.py)
# =============================================================================

def handle_camera(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate camera query: check jinju_image_captured flag."""
    image_captured = get_flag(metadata, "jinju_image_captured")

    if image_captured:
        return 5, f"Camera query. jinju_image_captured=True — photo file was saved to disk. This is definitive proof of capture success. Criteria: photo must be captured. Rating: 5."
    else:
        return 1, f"Camera query. jinju_image_captured=False — no photo file was saved. Criteria: photo must be captured. Rating: 1."


def handle_video(question: str, ai_response: str, metadata: dict) -> Tuple[int, str]:
    """Evaluate video query: check jinju_video_captured flag."""
    video_captured = get_flag(metadata, "jinju_video_captured")

    if video_captured:
        return 5, f"Video query. jinju_video_captured=True — video file was saved to disk. This is definitive proof of recording success. Criteria: video must be captured. Rating: 5."
    else:
        return 1, f"Video query. jinju_video_captured=False — no video file was saved. Criteria: video must be captured. Rating: 1."
