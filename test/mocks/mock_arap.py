"""
MockARAPManager — mock for ARAPManager/RobopodManager.

Records all play/record calls for assertion and writes dummy audio files
so file operations in AgentTester.execute() don't fail.
"""

from __future__ import annotations

import os


class MockARAPManager:
    """Mock for ARAPManager and RobopodManager.

    Records all play/record calls so tests can assert on them.
    Writes dummy audio files so file operations don't fail.
    """

    def __init__(self):
        self.played_files: list[str] = []
        self.recorded_files: list[str] = []
        self._recording = False
        self._started = False
        self._current_recording_name: str = ""

    def start_arap(self):
        """Start the ARAP service."""
        self._started = True

    def stop_arap(self):
        """Stop the ARAP service."""
        self._started = False

    def play_audio(self, path: str):
        """Play an audio file. Records the call."""
        self.played_files.append(path)

    def start_recording(self, filename: str):
        """Start recording audio. Records the call."""
        self._recording = True
        self._current_recording_name = filename

    def stop_recording(self, output_path: str):
        """Stop recording and save to output_path.

        Writes a dummy audio file so file operations don't fail.
        """
        self._recording = False
        self.recorded_files.append(output_path)

        # Write a dummy file so Base64Converter.encode_to_base64 doesn't fail
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"\x00" * 100)

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_recording(self) -> bool:
        return self._recording

    def reset(self):
        """Clear all recorded calls."""
        self.played_files = []
        self.recorded_files = []
        self._recording = False
        self._started = False
        self._current_recording_name = ""
