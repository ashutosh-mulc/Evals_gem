"""
Preconditions for Samsung Camera evaluations.

For the ``exit`` action, the Camera app must be in the foreground (manually
launched) before the agent is asked to close it.  Without this precondition the
"Close camera" query is meaningless — there is nothing to close.

For the ``launch`` action: force-stop the Camera app first to ensure a clean
state (the agent should be the one to open it).

For the ``check`` action: no precondition is needed — the screenshot mechanism
in config.py captures the camera state for the agent to inspect.

For all other actions (click, videostart, videostop): no precondition is
needed — the agent's own launch flow or the test harness will open the camera.
"""

from __future__ import annotations

import logging
import subprocess

from ..precondition_helpers import report

logger = logging.getLogger(__name__)

PACKAGE_NAME = "com.sec.android.app.camera"


def _launch_camera(device: str = "") -> bool:
    """Launch the Camera app via ADB am start.

    Returns True if the command succeeded, False otherwise.
    """
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    cmd += [
        "shell", "am", "start",
        "-n", f"{PACKAGE_NAME}/.Camera",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=10, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            logger.warning("ADB am start failed for camera: %s", result.stderr)
            return False
        return True
    except Exception as e:
        logger.warning("ADB am start error for camera: %s", e)
        return False


def _force_stop_camera(device: str = "") -> bool:
    """Force-stop the Camera app via ADB.

    Returns True if the command succeeded, False otherwise.
    """
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    cmd += ["shell", "am", "force-stop", PACKAGE_NAME]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=10, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            logger.warning("ADB force-stop failed for camera: %s", result.stderr)
            return False
        return True
    except Exception as e:
        logger.warning("ADB force-stop error for camera: %s", e)
        return False


def setup(dm, sc, qt, question, gt_answer):
    """Set up Samsung Camera preconditions.

    For exit: launch the Camera app so it is in the foreground before the
    agent is asked to close it.

    For launch: force-stop the Camera app to ensure a clean state.

    For all other actions: skip (no precondition needed).
    """
    action = qt.action

    # ── Exit: camera must be in foreground ──
    if action == "exit":
        device = (
            getattr(dm, "companion_device", None)
            or getattr(dm, "s25_device_id", None)
            or ""
        )
        success = _launch_camera(device)
        if success:
            logger.info("Precondition: launched Camera app before exit test")
            return report(
                set_items=["Launched Camera app (in foreground)"],
                checked=["Camera app is running in foreground"],
            )
        else:
            return report(
                passed=False,
                failed=["Failed to launch Camera app before exit test"],
            )

    # ── Launch: force-stop camera for clean state ──
    if action == "launch":
        device = (
            getattr(dm, "companion_device", None)
            or getattr(dm, "s25_device_id", None)
            or ""
        )
        _force_stop_camera(device)
        logger.info("Precondition: force-stopped Camera app before launch test")
        return report(
            set_items=["Force-stopped Camera app (clean state)"],
            checked=["Camera app is not running"],
        )

    # ── Other actions: no precondition needed ──
    return report(skipped=f"No precondition needed for action='{action}'")


def verify(dm, sc, qt, question, gt_answer):
    """Verify that the precondition state is correct.

    For exit: verify the Camera app is running (in foreground).
    For launch: verify the Camera app is NOT running.
    For other actions: always pass.
    """
    action = qt.action

    if action == "exit":
        # Verify camera is running — we just launched it in setup()
        from ..judge_helpers import _is_package_running, get_flag
        device = (
            getattr(dm, "companion_device", None)
            or getattr(dm, "s25_device_id", None)
            or ""
        )
        is_running = _is_package_running(PACKAGE_NAME, device)
        if is_running:
            return {"passed": True, "details": "Camera app is running (in foreground)"}
        return {"passed": False, "details": "Camera app is not running"}

    if action == "launch":
        from ..judge_helpers import _is_package_running
        device = (
            getattr(dm, "companion_device", None)
            or getattr(dm, "s25_device_id", None)
            or ""
        )
        is_running = _is_package_running(PACKAGE_NAME, device)
        if not is_running:
            return {"passed": True, "details": "Camera app is not running (clean state)"}
        return {"passed": False, "details": "Camera app is still running"}

    return {"passed": True, "details": f"No precondition for action='{action}'"}
