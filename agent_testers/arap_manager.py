"""
ARAP Manager — Controls Audio Recording and Playback on Android devices.
ARAP (Audio Recording and Playback) is an Android app (com.ss.arap) that
provides audio I/O capabilities for evaluation. This manager wraps ADB
commands to control the ARAP app for:
  - Playing query audio through the device speaker
  - Recording the AI agent's spoken responses

Usage Modes:
  - Local: Direct ADB control via ARAPManager (this module)
  - Remote: HTTP API via RobopodManager (for Robotester hardware)

The ARAP app must be installed on devices used for audio I/O.
"""

import os, subprocess, time
from utils.adb_client import AdbClient

class ARAPManager:
    """
    Manages ARAP (Audio Recording and Playback) app via ADB.

    Responsibilities:
      - Start/stop ARAP app lifecycle
      - Play audio files through device speaker
      - Start/stop audio recording and pull recorded files

    Args:
        device_id: ADB device serial (e.g., "ABC123XYZ").
    """
    def __init__(self, device_id):
        """Initialize ARAPManager for a specific device.

        Args:
            device_id: ADB device serial identifier.
        """
        self.device = device_id
        self._adb = AdbClient()

    def _run_adb(self, command: str, timeout: int = 15) -> subprocess.CompletedProcess:
        """Execute an ADB shell command.

        Args:
            command: Full ADB command string (e.g., "adb -s device shell ...").
            timeout: Command timeout in seconds (default 15).

        Returns:
            subprocess.CompletedProcess with stdout/stderr captured.
        """
        result = subprocess.run(
            command, shell=True, capture_output=True, timeout=timeout, encoding="utf-8"
        )
        return result

    def start_arap(self):
        """Start the ARAP app with a clean restart.

        Ensures ARAP is running by:
          1. Verifying device is online
          2. Unlocking device screen
          3. Force-stopping any existing instance
          4. Starting MainActivity
          5. Verifying process is running via pidof

        Prints status and warnings to console.
        """
        assert self._adb.is_device_online(self.device), f"Device {self.device} NOT online!"
        self._adb.unlock(self.device)

        # Force-stop any existing ARAP instance first to ensure clean start
        print("----Force-stopping ARAP (clean restart)----")
        self._run_adb(f"adb -s {self.device} shell am force-stop com.ss.arap")
        time.sleep(1)

        print("----Starting ARAP----")
        result = self._run_adb(
            f"adb -s {self.device} shell am start -n com.ss.arap/com.ss.arap.MainActivity"
        )
        if result.returncode != 0:
            print(f"  WARNING: am start returned {result.returncode}: {result.stderr.strip()}")
        # Wait for ARAP to fully initialize
        time.sleep(3)

        # Verify ARAP is actually running
        pid_result = self._run_adb(f"adb -s {self.device} shell pidof com.ss.arap")
        arap_pid = pid_result.stdout.strip()
        if arap_pid:
            print(f"  ARAP running (pid={arap_pid})")
        else:
            print("  WARNING: ARAP did not start (no pid found)")

    def start_recording(self, response_file: str):
        """Start audio recording via ARAP.

        Sends a broadcast intent to ARAP to begin recording to the specified file.

        Args:
            response_file: Filename for the recording (e.g., "response_q001.mp3").
        """
        print("----Recording Started----")
        command = (
            f"adb -s {self.device} shell am broadcast -a com.ss.arap.START_RECORDING --es fileName"
            f' "{response_file}"'
        )
        result = self._run_adb(command)
        print(command)
        if result.returncode != 0:
            print(f"  WARNING: start_recording returned {result.returncode}: {result.stderr.strip()}")

    def stop_recording(self, response_path: str):
        """Stop audio recording and pull the file.

        Sends a broadcast intent to stop recording, then pulls the recorded
        file from the device to the specified local path.

        Args:
            response_path: Local destination path for the recorded file.
        """
        print("----Recording Stopped----")
        command = (
            f"adb -s {self.device} shell am broadcast -a com.ss.arap.STOP_RECORDING"
        )
        result = self._run_adb(command)
        if result.returncode != 0:
            print(f"  WARNING: stop_recording returned {result.returncode}: {result.stderr.strip()}")
        time.sleep(1)  # Give ARAP time to flush the recording file
        self.__pull_recording(response_path.split('/')[-1], response_path)

    def __pull_recording(self, response_file: str, response_path: str):
        """Pull a recorded audio file from the device.

        Args:
            response_file: Filename on device (e.g., "response_q001.mp3").
            response_path: Local destination path.
        """
        command = (
            f"adb -s {self.device} pull"
            f' "/storage/emulated/0/Android/data/com.ss.arap/files/{response_file}"'
            f" {response_path}"
        )
        print(command)
        result = self._run_adb(command, timeout=30)
        if result.returncode != 0:
            print(f"  WARNING: pull returned {result.returncode}: {result.stderr.strip()}")

    def __push_audio(self, audio_path: str) -> str:
        """Push an audio file to the device for playback.

        Uses a two-stage push:
          1. Push to /sdcard/ (accessible without root)
          2. Copy to ARAP's private /data/data/ directory

        Falls back to direct push if sdcard method fails.

        Args:
            audio_path: Local path to the audio file.

        Returns:
            Path to the audio file on the device (in ARAP's private storage).
        """
        # Push to /sdcard/ first (accessible via adb), then use ARAP's internal path
        # /data/data/ is private app storage and may not be writable via adb on newer Android
        ARAP_ROOT = "/data/data/com.ss.arap/files/"
        SDCARD_TMP = "/sdcard/arap_audio/"
        filename = audio_path.split('/')[-1]

        # Ensure temp dir exists
        self._run_adb(f"adb -s {self.device} shell mkdir -p {SDCARD_TMP}")

        # Push to sdcard first
        push_result = self._run_adb(
            f'adb -s {self.device} push "{audio_path}" {SDCARD_TMP}',
            timeout=30
        )
        if push_result.returncode != 0:
            print(f"  WARNING: push to sdcard failed: {push_result.stderr.strip()}")
            # Fallback: try direct push to app data
            fallback_result = self._run_adb(
                f'adb -s {self.device} push "{audio_path}" {ARAP_ROOT}',
                timeout=30
            )
            if fallback_result.returncode != 0:
                print(f"  WARNING: fallback push also failed: {fallback_result.stderr.strip()}")
            return os.path.join(ARAP_ROOT, filename)

        # Try to copy from sdcard to app data dir (may need root)
        cp_result = self._run_adb(
            f"adb -s {self.device} shell cp {SDCARD_TMP}{filename} {ARAP_ROOT}"
        )
        if cp_result.returncode != 0:
            # If cp fails (permissions), try run-as
            self._run_adb(
                f"adb -s {self.device} shell run-as com.ss.arap cp {SDCARD_TMP}{filename} {ARAP_ROOT}"
            )

        return os.path.join(ARAP_ROOT, filename)

    def play_audio(self, audio_path: str):
        """Play an audio file through the device speaker.

        Pushes the audio file to the device, then sends a broadcast intent
        to ARAP to play it.

        Args:
            audio_path: Local path to the audio file to play.
        """
        audio_path = self.__push_audio(audio_path)
        print("----Playing Query----")
        command = (
            f"adb -s {self.device} shell am broadcast -a com.ss.arap.PLAY_AUDIO --es filePath"
            f' "{audio_path}"'
        )
        result = self._run_adb(command)
        print(command)
        if result.returncode != 0:
            print(f"  WARNING: play_audio broadcast returned {result.returncode}: {result.stderr.strip()}")
        # Give ARAP time to actually start playing
        time.sleep(1)

    def stop_arap(self):
        """Stop the ARAP app (force stop)."""
        print("----Stopping ARAP----")
        command = f"adb -s {self.device} shell am force-stop com.ss.arap"
        result = self._run_adb(command)
        if result.returncode != 0:
            print(f"  WARNING: stop_arap returned {result.returncode}: {result.stderr.strip()}")

