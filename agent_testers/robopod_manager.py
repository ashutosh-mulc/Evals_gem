"""
Robopod Manager — Remote ARAP control via HTTP API.

Alternative to ARAPManager that controls audio I/O through a remote
Robotester server instead of direct ADB. Used when audio hardware
is connected to a separate machine.

The Robopod server exposes endpoints for:
  - /health_check — Server health
  - /start_recording — Begin audio capture
  - /stop_recording — End capture and download file
  - /upload_and_play — Upload audio and play through speaker
"""

import requests
import os
import time


class RobopodManager:
    """
    Controls ARAP remotely via HTTP API (Robotester server).

    Provides the same interface as ARAPManager but communicates
    with a remote server instead of using ADB directly.

    Args:
        url: Base URL of the Robopod server (e.g., "http://robotester:8000").
    """
    def __init__(self, url: str):
        """Initialize RobopodManager with server URL.

        Args:
            url: Base URL of the Robopod/Robotester HTTP server.
        """
        self.base_url = url

    def start_arap(self):
        """Check server health (no-op for remote server)."""
        r = requests.get(f"{self.base_url}/health_check", timeout=5)
        r.raise_for_status()

    def start_recording(self, response_file: str):
        """Start remote audio recording.

        Args:
            response_file: Filename for the recording (not used remotely).
        """
        print("----Recording Started----")
        r = requests.post(f"{self.base_url}/start_recording", timeout=5)
        r.raise_for_status()
        print("Start:", r.json())

    def stop_recording(self, response_path: str):
        """Stop remote recording and download the file.

        Args:
            response_path: Local destination path for the downloaded audio.
        """
        print("----Recording Stopped----")
        r = requests.post(
            f"{self.base_url}/stop_recording",
            json={"filename": os.path.basename(response_path)},
            stream=True,
            timeout=5
        )
        r.raise_for_status()

        with open(response_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"Downloaded recording to {response_path}")

    def play_audio(self, audio_path: str):
        """Upload and play audio on remote server.

        Args:
            audio_path: Local path to the audio file to upload and play.
        """
        print("----Playing Query----")
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            resp = requests.post(f"{self.base_url}/upload_and_play", files=files, timeout=5)
            print("Upload and Play:", resp.json())

    def stop_arap(self):
        """No-op for remote server (no process to stop)."""
        pass
