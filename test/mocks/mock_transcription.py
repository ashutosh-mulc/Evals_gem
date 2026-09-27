"""
MockTranscriptionServer — mock for the Whisper transcription service.

Returns canned transcriptions for testing the pipeline without a real
Whisper server. Can be configured to return specific transcriptions per
audio file or a default response.
"""

from __future__ import annotations


class MockTranscriptionServer:
    """Mock transcription server that returns canned responses.

    Usage:
        server = MockTranscriptionServer()
        server.set_response("test.wav", "Your battery is at 75 percent")
        text = server.transcribe("test.wav")
        assert text == "Your battery is at 75 percent"
    """

    def __init__(self, default_response: str = "This is a mock transcription."):
        self._responses: dict[str, str] = {}
        self._default_response = default_response
        self.call_log: list[str] = []

    def set_response(self, audio_path: str, text: str):
        """Set the transcription response for a specific audio file."""
        self._responses[audio_path] = text

    def set_default_response(self, text: str):
        """Set the default transcription response."""
        self._default_response = text

    def transcribe(self, audio_path: str) -> str:
        """Return the canned transcription for the given audio file."""
        self.call_log.append(audio_path)
        return self._responses.get(audio_path, self._default_response)

    def reset(self):
        """Clear all configured responses and call log."""
        self._responses = {}
        self.call_log = []
        self._default_response = "This is a mock transcription."
