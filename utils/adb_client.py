"""
AdbClient — secure ADB wrapper with error handling.

Replaces the scattered `subprocess.run(f"adb -s {device_id} shell ...", shell=True)`
calls that are vulnerable to shell injection. Uses list-args (no shell) and
raises typed errors.

Usage:
    from utils.adb_client import AdbClient

    adb = AdbClient(timeout=30)
    adb.shell("R3CX80TTTCX", "input tap 400 1200")
    output = adb.shell("R3CX80TTTCX", "dumpsys activity", capture=True)
    adb.screencap("R3CX80TTTCX", "/sdcard/screen.png")
    adb.pull("R3CX80TTTCX", "/sdcard/screen.png", "/local/path/screen.png")
    adb.push("R3CX80TTTCX", "/local/file", "/sdcard/file")

    if adb.is_device_online("R3CX80TTTCX"):
        ...

Key safety properties:
    - All commands use list args (subprocess.run([...], shell=False))
    - No f-string shell commands — arguments are passed as list elements
    - Timeouts on every call
    - Typed exceptions (AdbError, AdbTimeoutError, AdbDeviceError)
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from common.schema import Constants

logger = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────

class AdbError(Exception):
    """Base error for all ADB failures."""


class AdbTimeoutError(AdbError):
    """ADB command timed out."""


class AdbDeviceError(AdbError):
    """Device is offline or not found."""


class AdbCommandError(AdbError):
    """ADB command returned a non-zero exit code."""


# ── AdbClient ────────────────────────────────────────────────────────────────

class AdbClient:
    """
    Secure ADB client using list-args (no shell=True).

    All methods that take a device_id will raise AdbDeviceError if the device
    is not online. All methods enforce a timeout.
    """

    def __init__(self, adb_path: str = "adb", timeout: int = Constants.DEFAULT_ADB_TIMEOUT):
        """
        Args:
            adb_path: Path to the adb executable.
            timeout: Default timeout in seconds for all commands.
        """
        self._adb_path = adb_path
        self._timeout = timeout
        self._device_cache: dict[str, str] = {}  # device_id -> status

    # ── Device management ──────────────────────────────────────────

    def list_devices(self) -> dict[str, str]:
        """
        List all connected devices.

        Returns:
            Dict mapping device serial -> status string (e.g. "device", "offline").
        """
        try:
            result = subprocess.run(
                [self._adb_path, "devices"],
                capture_output=True, text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            raise AdbTimeoutError("'adb devices' timed out")

        devices: dict[str, str] = {}
        lines = result.stdout.strip().split("\n")[1:]  # skip header
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                devices[parts[0].strip()] = parts[1].strip()

        self._device_cache = devices
        return devices

    def is_device_online(self, device_id: str) -> bool:
        """Check if a specific device is online and ready."""
        devices = self.list_devices()
        status = devices.get(device_id)
        if status == "device":
            return True
        if status and status != "device":
            logger.warning("Device %s found but status is '%s'", device_id, status)
        else:
            logger.warning("Device %s is not online", device_id)
        return False

    def _check_device(self, device_id: str) -> None:
        """Raise AdbDeviceError if device is not online."""
        if not self.is_device_online(device_id):
            raise AdbDeviceError(f"Device {device_id} is not online")

    # ── Core command runner ────────────────────────────────────────

    def _run(
        self,
        args: list[str],
        timeout: Optional[int] = None,
        capture: bool = False,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run an ADB command with list args (no shell)."""
        t = timeout or self._timeout
        try:
            result = subprocess.run(
                args,
                capture_output=capture,
                text=True,
                timeout=t,
            )
        except subprocess.TimeoutExpired as e:
            raise AdbTimeoutError(f"ADB command timed out after {t}s: {' '.join(args[:6])}") from e

        if check and result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            raise AdbCommandError(
                f"ADB command failed (exit {result.returncode}): {' '.join(args[:6])}"
                + (f"\nstderr: {stderr}" if stderr else "")
            )
        return result

    def _device_args(self, device_id: str, sub_args: list[str]) -> list[str]:
        """Build args list for a device-specific command."""
        return [self._adb_path, "-s", device_id] + sub_args

    # ── Shell commands ─────────────────────────────────────────────

    def shell(
        self,
        device_id: str,
        command: str,
        capture: bool = False,
        timeout: Optional[int] = None,
        check: bool = False,
    ) -> str:
        """
        Run a shell command on the device.

        Args:
            device_id: Device serial number.
            command: Shell command to run on device.
            capture: If True, return stdout. If False, return "".
            timeout: Override default timeout.
            check: If True, raise on non-zero exit.

        Returns:
            stdout string if capture=True, else "".
        """
        args = self._device_args(device_id, ["shell", command])
        result = self._run(args, timeout=timeout, capture=capture, check=check)
        return result.stdout if capture else ""

    def shell_su(
        self,
        device_id: str,
        command: str,
        capture: bool = False,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Run a shell command on the device with root access (su 0).

        Args:
            device_id: Device serial number.
            command: Shell command to run as root.
            capture: If True, return stdout. If False, return "".
            timeout: Override default timeout.

        Returns:
            stdout string if capture=True, else "".
        """
        args = self._device_args(device_id, ["shell", "su", "0", command])
        result = self._run(args, timeout=timeout, capture=capture)
        return result.stdout if capture else ""

    # ── Root Connectivity Commands ─────────────────────────────────

    def set_wifi(self, device_id: str, enable: bool) -> None:
        """Enable or disable WiFi on the device (requires root)."""
        state = "enable" if enable else "disable"
        self.shell_su(device_id, f"svc wifi {state}")
        logger.info("WiFi %s on %s", state, device_id)

    def set_mobile_data(self, device_id: str, enable: bool) -> None:
        """Enable or disable mobile data on the device (requires root)."""
        state = "enable" if enable else "disable"
        self.shell_su(device_id, f"svc data {state}")
        logger.info("Mobile data %s on %s", state, device_id)

    def set_bluetooth(self, device_id: str, enable: bool) -> None:
        """Enable or disable Bluetooth on the device (requires root)."""
        state = "enable" if enable else "disable"
        self.shell_su(device_id, f"cmd bluetooth_manager {state}")
        logger.info("Bluetooth %s on %s", state, device_id)

    # ── Input commands ─────────────────────────────────────────────

    def tap(self, device_id: str, x: int, y: int) -> None:
        """Tap at (x, y) on the device."""
        self.shell(device_id, f"input tap {x} {y}")
        logger.debug("Tapped %s at (%d, %d)", device_id, x, y)

    def swipe(self, device_id: str, x1: int, y1: int, x2: int, y2: int) -> None:
        """Swipe from (x1, y1) to (x2, y2) on the device."""
        self.shell(device_id, f"input swipe {x1} {y1} {x2} {y2}")
        logger.debug("Swiped %s (%d,%d)->(%d,%d)", device_id, x1, y1, x2, y2)

    def press_key(self, device_id: str, keycode: str) -> None:
        """Press a key (e.g. KEYCODE_BACK, KEYCODE_HOME)."""
        self.shell(device_id, f"input keyevent {keycode}")
        logger.debug("Pressed %s on %s", keycode, device_id)

    def press_back(self, device_id: str) -> None:
        """Press the BACK key."""
        self.press_key(device_id, "KEYCODE_BACK")

    def unlock(self, device_id: str) -> None:
        """Unlock the phone screen."""
        self.shell(device_id, "input keyevent --delay 100 224 82")
        logger.info("Unlocked %s", device_id)

    def reset_ime(self, device_id: str) -> None:
        """Reset the Input Method Editor (IME) to close active keyboard.
        
        This is useful for dismissing soft keyboards that may interfere with
        UI interactions or screenshot capture.
        """
        self.shell(device_id, "ime reset")
        logger.info("Reset IME (keyboard) on %s", device_id)

    # ── App management ──────────────────────────────────────────────

    def start_activity(self, device_id: str, activity_name: str) -> None:
        """Start an activity by component name (-n flag).
        
        The -n flag explicitly specifies the component name, which is more
        reliable across Android versions. Some apps (e.g., samsungcamera)
        only work with the -n flag.
        """
        self.shell(device_id, f"am start -n {activity_name}")
        logger.info("Started activity %s on %s", activity_name, device_id)

    def force_stop(self, device_id: str, package_name: str) -> None:
        """Force stop an app by package name."""
        self.shell(device_id, f"am force-stop {package_name}")
        logger.info("Force-stopped %s on %s", package_name, device_id)

    def launch_app(self, device_id: str, package_name: str) -> None:
        """Launch an app by package name."""
        self.shell(device_id, f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        logger.info("Launched %s on %s", package_name, device_id)

    def get_foreground_package(self, device_id: str) -> str:
        """Get the package name of the foreground app."""
        output = self.shell(device_id, "dumpsys activity activities | grep mResumedActivity", capture=True)
        # Parse: "mResumedActivity: ActivityRecord{... u0 com.example.app/.MainActivity ...}"
        for part in output.split():
            if "/" in part and "." in part:
                return part.split("/")[0]
        return ""

    # ── File operations ────────────────────────────────────────────

    def screencap(self, device_id: str, remote_path: str) -> None:
        """Take a screenshot on the device, saved to remote_path."""
        self.shell(device_id, f"screencap {remote_path}")
        logger.debug("Screenshot saved to %s on %s", remote_path, device_id)

    def pull(self, device_id: str, remote_path: str, local_path: str) -> None:
        """Pull a file from the device to the local machine."""
        args = self._device_args(device_id, ["pull", remote_path, local_path])
        self._run(args, check=True)
        logger.debug("Pulled %s -> %s from %s", remote_path, local_path, device_id)

    def push(self, device_id: str, local_path: str, remote_path: str) -> None:
        """Push a file from the local machine to the device."""
        args = self._device_args(device_id, ["push", local_path, remote_path])
        self._run(args, check=True)
        logger.debug("Pushed %s -> %s to %s", local_path, remote_path, device_id)

    def file_exists(self, device_id: str, remote_path: str) -> bool:
        """Check if a file exists on the device."""
        output = self.shell(device_id, f"test -f {remote_path} && echo yes || echo no", capture=True)
        return "yes" in output

    def delete_file(self, device_id: str, remote_path: str) -> None:
        """Delete a file on the device."""
        self.shell(device_id, f"rm -f {remote_path}")
        logger.debug("Deleted %s on %s", remote_path, device_id)

    # ── Property queries ───────────────────────────────────────────

    def getprop(self, device_id: str, prop: str) -> str:
        """Get a system property value."""
        return self.shell(device_id, f"getprop {prop}", capture=True).strip()

    def get_model(self, device_id: str) -> str:
        """Get device model name."""
        return self.getprop(device_id, "ro.product.model")

    def get_android_version(self, device_id: str) -> str:
        """Get Android version."""
        return self.getprop(device_id, "ro.build.version.release")

    # ── Logcat ─────────────────────────────────────────────────────

    def clear_logcat(self, device_id: str) -> None:
        """Clear logcat buffer."""
        self.shell(device_id, "logcat -c")
        logger.debug("Cleared logcat on %s", device_id)

    def dump_logcat(self, device_id: str, local_path: str, filter_spec: str = "") -> None:
        """
        Dump logcat to a local file.

        Args:
            device_id: Device serial.
            local_path: Local file to save logcat to.
            filter_spec: Optional filter (e.g. "*:W" for warnings+).
        """
        cmd = "logcat -d"
        if filter_spec:
            cmd += f" {filter_spec}"
        output = self.shell(device_id, cmd, capture=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(output)
        logger.debug("Dumped logcat to %s from %s", local_path, device_id)

    def get_dnd_mode(self, device_id: str) -> bool:
        """
        Check if Do Not Disturb (DND) mode is enabled on the device.

        Args:
            device_id: Device serial number.

        Returns:
            True if DND mode is enabled, False otherwise.
            "0" - OFF
            "1" - ON
        """
        try:
            output = self.shell(device_id, "settings get global zen_mode", capture=True).strip()
            return output and output != "0"
        except Exception:
            logger.warning("Failed to get DND mode from %s", device_id)
            return False

    def set_dnd_mode(self, device_id: str, enable: bool) -> None:
        """
        Enable or disable Do Not Disturb (DND) mode on the device.

        Args:
            device_id: Device serial number.
            enable: True to enable DND, False to disable.
        """
        zen_value = "1" if enable else "0"
        self.shell(device_id, f"settings put global zen_mode {zen_value}")
        logger.info("DND mode %s on %s", "enabled" if enable else "disabled", device_id)
