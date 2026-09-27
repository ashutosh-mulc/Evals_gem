#!/usr/bin/env python3
"""Check Android device information via ADB using a DeviceInfo class."""
import subprocess
import re
import sys


# =============================================================================
# Device Command Registry
# =============================================================================
# Maps device command types to their actions and target devices
# Used for DEVICE_<STATE>_<COMMAND_TYPE> question types

DEVICE_COMMAND_TYPES = {
    "camera": {"action": "capture_image", "device": "jinju", "description": "Capture an image"},
    "video": {"action": "capture_video", "device": "jinju", "description": "Record a video"},
    "volume": {"action": "get_volume", "device": "jinju", "description": "Get/set volume level"},
    "mediacontrol": {"action": "get_media", "device": "companion", "description": "Media playback control"},
    "dnd": {"action": "get_dnd_mode", "device": "companion", "description": "Do Not Disturb mode"},
    "battery": {"action": "get_battery", "device": "jinju", "description": "Battery status"},
    "time": {"action": "get_time", "device": "jinju", "description": "Device time"},
    "date": {"action": "get_date", "device": "jinju", "description": "Device date"},
    "notification": {"action": "capture_notifications_screenshot", "device": "companion", "description": "Capture notification panel screenshot"},

}

DEVICE_STATES = ["online", "offline", "disconnected"]


def _parse_stream_into(stream_name, lines, result):
    """Parse a single STREAM section's lines into result['all_streams'][stream_name]."""
    volume_text = '\n'.join(lines)

    stream_info = {"streamVolume": None, "muted": None, "min": None, "max": None}

    sv_match = re.search(r'streamVolume:\s*(\d+)', volume_text)
    if sv_match:
        stream_info["streamVolume"] = int(sv_match.group(1))

    muted_match = re.search(r'Muted:\s*(true|false)', volume_text, re.IGNORECASE)
    if muted_match:
        stream_info["muted"] = muted_match.group(1).lower() == 'true'

    min_match = re.search(r'Min:\s*(\d+)', volume_text)
    if min_match:
        stream_info["min"] = int(min_match.group(1))

    max_match = re.search(r'Max:\s*(\d+)', volume_text)
    if max_match:
        stream_info["max"] = int(max_match.group(1))

    result["all_streams"][stream_name] = stream_info


class DeviceInfo:
    """
    Query information from an Android device connected via ADB.

    This class wraps ADB shell commands to retrieve battery status, system time,
    and other device properties. It supports multiple connected devices by
    specifying a device serial number.

    Attributes:
        device (str or None): The serial number of the target device. If None,
            ADB uses the first (or only) connected device.
        _timeout (int): Timeout in seconds for ADB commands.

    Example:
        >>> info = DeviceInfo("R3CY504QDGE")
        >>> battery = info.get_battery()
        >>> print(f"Battery: {battery['level']}%")
        Battery: 100%
        >>> dev_time = info.get_time()
        >>> print(f"Device time: {dev_time['datetime_str']}")
        Device time: Fri Jul 17 15:04:30 IST 2026
    """

    # Status code -> human-readable name mapping (Android BatteryManager constants)
    _STATUS_MAP = {
        1: "Unknown",
        2: "Charging",
        3: "Discharging",
        4: "Not Charging",
        5: "Full",
    }

    # Health code -> human-readable name mapping (Android BatteryManager constants)
    _HEALTH_MAP = {
        1: "Unknown",
        2: "Good",
        3: "Overheat",
        4: "Dead",
        5: "Over Voltage",
        6: "Unspecified Failure",
        7: "Cold",
    }

    # PlaybackState code -> name (android.media.session.PlaybackState)
    _PLAYBACK_STATE_MAP = {
        0: "None", 1: "Stopped", 2: "Paused", 3: "Playing",
        4: "Fast Forwarding", 5: "Rewinding", 6: "Buffering",
        7: "Error", 8: "Connecting", 9: "Skipping to Previous",
        10: "Skipping to Next", 11: "Skipping to Queue Item",
    }

    def __init__(self, device=None, timeout=10):
        """
        Initialize the DeviceInfo instance.

        Args:
            device (str, optional): Serial number of the target device. If None,
                ADB will use the first connected device. Use `list_devices()` to
                discover available serial numbers.
            timeout (int): Timeout in seconds for each ADB command. Default is 10.
        """
        self.device = device
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_adb(self, *shell_args):
        """
        Run an ADB shell command and return the stdout output.

        Args:
            *shell_args: Arguments to pass to `adb shell`. For example,
                `_run_adb("dumpsys", "battery")` runs `adb shell dumpsys battery`.

        Returns:
            str: The stdout output from the command.

        Raises:
            FileNotFoundError: If adb is not in PATH.
            subprocess.TimeoutExpired: If the command times out.
            RuntimeError: If the command returns a non-zero exit code.
        """
        cmd = ["adb"]
        if self.device:
            cmd.extend(["-s", self.device])
        cmd.extend(["shell", *shell_args])

        output = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )

        if output.returncode != 0:
            raise RuntimeError(
                f"ADB command failed: {' '.join(cmd)}\n{output.stderr.strip()}"
            )

        return output.stdout

    @staticmethod
    def _parse_field(text, field_name, cast=int):
        """
        Extract a named field from ADB dumpsys-style output.

        Args:
            text (str): The full text output to search.
            field_name (str): The field name to look for (e.g., "level", "status").
            cast (callable): Type to cast the matched value to. Default is int.

        Returns:
            The casted value, or None if the field is not found.
        """
        match = re.search(
            rf"^\s*{re.escape(field_name)}:\s*(.+)$", text, re.MULTILINE
        )
        if match:
            try:
                return cast(match.group(1).strip())
            except (ValueError, TypeError):
                return None
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_battery(self):
        """
        Get battery information from the device.

        Runs `adb shell dumpsys battery` and parses the output.

        Returns:
            dict: A dictionary with the following keys:
                - level (int): Battery percentage (0-100), or None.
                - status (str): Charging status (e.g., "Charging", "Full").
                - charging (bool): True if charging or full.
                - temperature (float): Temperature in Celsius, or None.
                - voltage (int): Voltage in mV, or None.
                - health (str): Battery health (e.g., "Good"), or None.
                - technology (str): Battery technology (e.g., "Li-ion"), or None.
                - error (str): Error message, or None if successful.
        """
        result = {
            "level": None,
            "status": None,
            "charging": False,
            "temperature": None,
            "voltage": None,
            "health": None,
            "technology": None,
            "error": None,
        }

        try:
            text = self._run_adb("dumpsys", "battery")
        except FileNotFoundError:
            result["error"] = "ADB not found. Ensure adb is installed and in your PATH."
            return result
        except subprocess.TimeoutExpired:
            result["error"] = "ADB command timed out. Is the device responding?"
            return result
        except RuntimeError as e:
            result["error"] = str(e)
            return result

        # Parse level
        result["level"] = self._parse_field(text, "level")

        # Parse status
        status_code = self._parse_field(text, "status")
        if status_code is not None:
            result["status"] = self._STATUS_MAP.get(
                status_code, f"Unknown ({status_code})"
            )
            result["charging"] = status_code in (2, 5)

        # Parse temperature (stored in tenths of a degree)
        temp_raw = self._parse_field(text, "temperature")
        if temp_raw is not None:
            result["temperature"] = temp_raw / 10.0

        # Parse voltage
        result["voltage"] = self._parse_field(text, "voltage")

        # Parse health
        health_code = self._parse_field(text, "health")
        if health_code is not None:
            result["health"] = self._HEALTH_MAP.get(
                health_code, f"Unknown ({health_code})"
            )

        # Parse technology (string field)
        result["technology"] = self._parse_field(text, "technology", cast=str)

        if result["level"] is None:
            result["error"] = "Could not parse battery level from ADB output."

        return result

    def get_time(self):
        """
        Get the current date and time from the device.

        Runs `adb shell date` to get the human-readable time, and
        `adb shell date +%s%3N` to get the Unix epoch in milliseconds.

        Returns:
            dict: A dictionary with the following keys:
                - datetime_str (str): Human-readable date-time from the device.
                - timezone (str): Timezone abbreviation (e.g., "IST"), or None.
                - epoch_ms (int): Unix epoch time in milliseconds, or None.
                - error (str): Error message, or None if successful.
        """
        result = {
            "datetime_str": None,
            "timezone": None,
            "epoch_ms": None,
            "error": None,
        }

        try:
            raw = self._run_adb("date").strip()
        except FileNotFoundError:
            result["error"] = "ADB not found. Ensure adb is installed and in your PATH."
            return result
        except subprocess.TimeoutExpired:
            result["error"] = "ADB command timed out. Is the device responding?"
            return result
        except RuntimeError as e:
            result["error"] = str(e)
            return result

        result["datetime_str"] = raw

        # Extract timezone from date output
        # e.g., "Fri Jul 17 15:04:30 IST 2026" -> "IST"
        tz_match = re.search(r"\d{2}:\d{2}:\d{2}\s+(\S+)\s+\d{4}", raw)
        if tz_match:
            result["timezone"] = tz_match.group(1)

        # Get epoch time in milliseconds
        try:
            epoch_str = self._run_adb("date", "+%s%3N").strip()
            if epoch_str.isdigit():
                result["epoch_ms"] = int(epoch_str)
        except (subprocess.TimeoutExpired, RuntimeError, ValueError):
            pass  # Non-critical, leave as None

        return result

    def get_property(self, prop_name):
        """
        Get a system property from the device via `adb shell getprop`.

        Args:
            prop_name (str): The property name (e.g., "ro.product.model",
                "ro.build.version.release").

        Returns:
            str: The property value, or None if not found / on error.
        """
        try:
            value = self._run_adb("getprop", prop_name).strip()
            return value if value else None
        except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError):
            return None

    def get_volume(self):
        """
        Get volume information from the device — all audio streams.

        Runs `adb shell dumpsys audio` and parses every STREAM_* volume group.
        Returns MUSIC stream values in top-level fields (backward compat) plus
        an `all_streams` dict with every stream's streamVolume/muted/min/max.

        Returns:
            dict: A dictionary with the following keys:
                - muted (bool): MUSIC stream muted state (backward compat)
                - min (int): MUSIC stream min (backward compat)
                - max (int): MUSIC stream max (backward compat)
                - current (int): MUSIC streamVolume (backward compat)
                - all_streams (dict): {stream_name: {streamVolume, muted, min, max}}
                - error (str): Error message, or None if successful
        """
        result = {
            "muted": None,
            "min": None,
            "max": None,
            "current": None,
            "all_streams": {},
            "error": None,
        }

        try:
            text = self._run_adb("dumpsys", "audio")
        except FileNotFoundError:
            result["error"] = "ADB not found. Ensure adb is installed and in your PATH."
            return result
        except subprocess.TimeoutExpired:
            result["error"] = "ADB command timed out. Is the device responding?"
            return result
        except RuntimeError as e:
            result["error"] = str(e)
            return result

        # Parse ALL STREAM_* sections from dumpsys audio
        lines = text.split('\n')
        current_stream = None
        stream_lines = []

        for line in lines:
            # Detect start of a STREAM section: "- STREAM_MUSIC:"
            stream_match = re.match(r'\s*-\s+(STREAM_\w+):', line)
            if stream_match:
                # Save previous stream if any
                if current_stream is not None:
                    _parse_stream_into(current_stream, stream_lines, result)
                current_stream = stream_match.group(1)
                stream_lines = []
            elif current_stream is not None:
                # Stop if we hit a non-stream section (e.g., "- VOLUME GROUP")
                if line.strip().startswith('- ') and not re.match(r'\s*-\s+STREAM_\w+:', line):
                    _parse_stream_into(current_stream, stream_lines, result)
                    current_stream = None
                    stream_lines = []
                    continue
                stream_lines.append(line)

        # Don't forget the last stream
        if current_stream is not None:
            _parse_stream_into(current_stream, stream_lines, result)

        if not result["all_streams"]:
            result["error"] = "Could not parse any STREAM_* volume groups from dumpsys audio."
            return result

        # Backward compat: populate top-level fields from MUSIC stream
        music = result["all_streams"].get("STREAM_MUSIC", {})
        result["muted"] = music.get("muted")
        result["min"] = music.get("min")
        result["max"] = music.get("max")
        result["current"] = music.get("streamVolume")

        return result

    def get_media(self):
        """
        Get current media session state via `adb shell dumpsys media_session`.

        Returns:
            dict: A dictionary with the following keys:
                - active (bool): Whether there is an active media session
                - playing (bool): Whether media is currently playing
                - package (str): Package name of the active media session
                - state (str): Human-readable playback state (e.g., "Playing", "Paused")
                - state_code (int): Raw playback state code
                - title (str): Media title, or None
                - artist (str): Media artist, or None
                - album (str): Media album, or None
                - position_ms (int): Current playback position in milliseconds, or None
                - speed (float): Playback speed, or None
                - last_audio_package (str): Last package that played audio, or None
                - error (str): Error message, or None if successful
        """
        result = {
            "active": False,
            "playing": False,
            "package": None,
            "state": None,
            "state_code": None,
            "title": None,
            "artist": None,
            "album": None,
            "position_ms": None,
            "speed": None,
            "last_audio_package": None,
            "error": None,
        }
        
        try:
            text = self._run_adb("dumpsys", "media_session")
        except FileNotFoundError:
            result["error"] = "ADB not found. Ensure adb is installed and in your PATH."
            return result
        except subprocess.TimeoutExpired:
            result["error"] = "ADB command timed out. Is the device responding?"
            return result
        except RuntimeError as e:
            result["error"] = str(e)
            return result

        # Get last played audio package (even if session is gone)
        m = re.search(
            r"Audio playback \(lastly played comes first\)\s*\n\s*uid=\d+\s+packages=(\S+)",
            text
        )
        if m:
            result["last_audio_package"] = m.group(1)

        session = self._select_active_session(text)
        if session:
            result.update(session)
            result["active"] = True
            result["playing"] = (session["state_code"] == 3)
        return result

    @classmethod
    def _select_active_session(cls, text):
        """
        Parse the 'Sessions Stack' block from dumpsys media_session output.
        Prefer a session in PLAYING state.

        Args:
            text (str): The full dumpsys media_session output.

        Returns:
            dict or None: Session info dict if found, None otherwise.
        """
        # Scope to the sessions stack so the telecom global session and
        # the events log (which also contains 'pkg=') are excluded.
        stack = re.search(
            r"Sessions Stack - have (\d+) sessions:(.*?)(?=\nisAppCastingOn|\Z)",
            text, re.DOTALL
        )
        if not stack or int(stack.group(1)) == 0:
            return None
        body = stack.group(2)

        marks = list(re.finditer(r"^\s*package=(\S+)\s*$", body, re.MULTILINE))
        sessions = []
        for i, mk in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
            block = body[mk.start():end]
            pkg = mk.group(1)

            state_code = state_name = position = speed = None
            sm = re.search(
                r"state=PlaybackState\s*\{\s*state=([A-Z_]+)\((\d+)\)"
                r"(?:,\s*position=(-?\d+))?(?:.*?speed=(-?[\d.]+))?",
                block, re.DOTALL
            )
            if sm:
                state_name, state_code = sm.group(1), int(sm.group(2))
                position = int(sm.group(3)) if sm.group(3) else None
                speed = float(sm.group(4)) if sm.group(4) else None

            title = artist = album = None
            dm = re.search(r"^\s*metadata:\s*(.*)$", block, re.MULTILINE)
            if dm and dm.group(1).strip() != "null":
                desc = re.search(r"description=(.*)", dm.group(1))
                if desc:
                    parts = [p.strip() for p in desc.group(1).split(",")]
                    vals = [p if p and p != "null" else None for p in parts[:3]]
                    vals += [None] * (3 - len(vals))
                    title, artist, album = vals

            sessions.append({
                "package": pkg,
                "state_code": state_code,
                "state": cls._PLAYBACK_STATE_MAP.get(state_code, state_name),
                "title": title,
                "artist": artist,
                "album": album,
                "position_ms": position,
                "speed": speed,
            })

        if not sessions:
            return None
        # Actively playing wins
        for s in sessions:
            if s["state_code"] == 3:
                return s
        # Else first with a real state
        for s in sessions:
            if s["state_code"] is not None:
                return s
        return sessions[0]

    def get_model_info(self):
        """
        Get basic device model information.

        Returns:
            dict: A dictionary with model, brand, manufacturer, Android version,
                and SDK level.
        """
        return {
            "model": self.get_property("ro.product.model"),
            "brand": self.get_property("ro.product.brand"),
            "manufacturer": self.get_property("ro.product.manufacturer"),
            "android_version": self.get_property("ro.build.version.release"),
            "sdk_level": self.get_property("ro.build.version.sdk"),
            "device_serial": self.device,
        }

    def print_report(self):
        """Print device state in the exact format passed to the Judge VLM.

        This mirrors the structure built by capture_device_info() in
        jinju_gemini_manager.py so you can see exactly what the judge receives.
        Assumes a single device (no jinju/companion split).
        """
        import json
        from datetime import datetime

        # --- Gather raw data ---
        battery = self.get_battery()
        dev_time = self.get_time()
        volume = self.get_volume()
        media = self.get_media()

        # Parse date from datetime string (same logic as capture_device_info)
        date_info = {}
        if dev_time.get("datetime_str"):
            try:
                dt = datetime.strptime(dev_time["datetime_str"], "%a %b %d %H:%M:%S %Z %Y")
                date_info = {
                    "day": dt.day,
                    "month": dt.strftime("%b"),
                    "year": dt.year,
                    "day_of_week": dt.strftime("%a"),
                }
            except Exception:
                pass

        # --- Build the same dict structure the judge sees ---
        device_info = {
            "battery": {
                "level": battery.get("level"),
                "status": battery.get("status"),
                "charging": battery.get("charging"),
            },
            "time": {
                "datetime_str": dev_time.get("datetime_str"),
                "timezone": dev_time.get("timezone"),
                "epoch_ms": dev_time.get("epoch_ms"),
            },
            "date": date_info,
            "volume": {
                "muted": volume.get("muted"),
                "min": volume.get("min"),
                "max": volume.get("max"),
                "current": volume.get("current"),
            },
            "dnd_mode": "false",  # single device assumption
            "media": {
                "active": media.get("active"),
                "playing": media.get("playing"),
                "state": media.get("state"),
                "package": media.get("package"),
                "title": media.get("title"),
                "artist": media.get("artist"),
                "album": media.get("album"),
                "position_ms": media.get("position_ms"),
                "speed": media.get("speed"),
                "last_audio_package": media.get("last_audio_package"),
            },
        }

        # --- Print in the exact JSON format the judge VLM receives ---
        print(f"\n{'='*60}")
        print("=== DEVICE STATE (as passed to Judge VLM) ===")
        print(f"{'='*60}")
        print(json.dumps(device_info, indent=2))
        print(f"{'='*60}\n")


# ------------------------------------------------------------------
# Module-level utility functions
# ------------------------------------------------------------------

def list_devices():
    """
    List all connected Android devices.

    Returns:
        list: A list of device serial numbers. Empty if no devices connected.
    """
    try:
        output = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    devices = []
    for line in output.stdout.strip().split("\n")[1:]:
        parts = line.strip().split("\t")
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])

    return devices


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main():
    """Main entry point - check battery, time, and model for all connected devices."""
    devices = list_devices()

    if not devices:
        print("No devices connected. Connect a device via USB or wireless ADB.")
        sys.exit(1)

    for serial in devices:
        print(f"\n{'=' * 50}")
        print(f"Device: {serial}")
        print(f"{'=' * 50}")

        info = DeviceInfo(device=serial)
        info.print_report()

    print()


if __name__ == "__main__":
    main()
