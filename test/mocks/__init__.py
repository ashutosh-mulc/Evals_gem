"""
Test mocks for MAIRE — drop-in replacements for real services.

Modules:
    mock_xrclaw — MockXRClawDeviceManager (mirrors XRClaw's DeviceManager)
    mock_arap   — MockARAPManager (mirrors ARAPManager/RobopodManager)
    mock_transcription — MockTranscriptionServer (mirrors Whisper server)
    mock_judge  — MockJudgeServer (mirrors VLM judge server)
"""

from test.mocks.mock_xrclaw import MockXRClawDeviceManager
from test.mocks.mock_arap import MockARAPManager
from test.mocks.mock_transcription import MockTranscriptionServer
from test.mocks.mock_judge import MockJudgeServer

__all__ = [
    "MockXRClawDeviceManager",
    "MockARAPManager",
    "MockTranscriptionServer",
    "MockJudgeServer",
]
