"""AgentTester._decode_inputs / _move_tmp_artifacts (agent_testers/agent_tester.py).

These are the two steps of execute() that do pure file I/O with no device/ADB
dependency, extracted so the 230-line execute() reads as named steps. Everything
else in execute() drives real hardware (ARAP, ADB, device managers) and has no
test harness in this repo, so it stays inline and untested here as before.
"""

import base64
import os

import pytest

from agent_testers.agent_tester import AgentTester


class _Bare(AgentTester):
    """AgentTester with only the attributes _decode_inputs/_move_tmp_artifacts read."""

    def __init__(self, tmp_path):
        self.log_folders = {"fixed": str(tmp_path / "assets"), "tmp": str(tmp_path / "tmp")}
        os.makedirs(self.log_folders["fixed"])


@pytest.fixture
def tester(tmp_path):
    return _Bare(tmp_path)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class TestDecodeInputs:
    def test_happy_path(self, tester):
        q_info = {
            "eval_id": "q00042",
            "question_type": "online_samsung_notes_create",
            "image": _b64(b"fake-image-bytes"),
            "audio": _b64(b"fake-audio-bytes"),
            "audio_duration": "3.5",
            "metadata": {},
        }
        result = tester._decode_inputs(q_info)
        assert result is not None
        query_dir, eval_id, encoded_image, audio_duration, response_filename, response_path, qt = result

        assert eval_id == "00042"
        assert query_dir == os.path.join(tester.log_folders["fixed"], "q00042")
        assert audio_duration == 3.5
        assert response_filename == "response_00042.mp3"
        assert response_path == os.path.join(query_dir, "response_00042.mp3")
        assert qt.app_key == "samsungnote"
        assert open(q_info["metadata"]["image_path"], "rb").read() == b"fake-image-bytes"
        assert open(q_info["metadata"]["audio_raw_path"], "rb").read() == b"fake-audio-bytes"

    def test_bad_image_base64_skips_question(self, tester):
        q_info = {
            "eval_id": "q00099",
            "question_type": "online_x_y_z",
            "image": "!!!not base64!!!",
            "audio": _b64(b"x"),
            "audio_duration": "1.0",
            "metadata": {},
        }
        result = tester._decode_inputs(q_info)
        assert result is None
        assert q_info["metadata"]["image_path"] is None
        assert q_info["metadata"]["audio_raw_path"] is None
        assert q_info["metadata"]["response_path"] is None


class TestMoveTmpArtifacts:
    def test_moves_and_suffixes_files(self, tester):
        tmp_dir = tester.log_folders["tmp"]
        os.makedirs(os.path.join(tmp_dir, "assets"))
        with open(os.path.join(tmp_dir, "jinju_log.txt"), "w") as f:
            f.write("log")
        # Already carries the eval_id -> not suffixed again
        with open(os.path.join(tmp_dir, "device_info_pre_q00042.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(tmp_dir, "assets", "screenshot.png"), "w") as f:
            f.write("img")

        query_dir = os.path.join(tester.log_folders["fixed"], "q00042")
        os.makedirs(query_dir)
        updates = tester._move_tmp_artifacts(query_dir, "00042")

        assert updates["jinju_log_path"] == os.path.join(query_dir, "jinju_log_00042.txt")
        assert updates["device_info_pre_q00042_path"] == os.path.join(query_dir, "device_info_pre_q00042.json")
        assert updates["assets_screenshot_path"] == os.path.join(query_dir, "assets", "screenshot_00042.png")
        for path in updates.values():
            assert os.path.exists(path)
        assert not os.listdir(tmp_dir) or all(
            not os.listdir(os.path.join(tmp_dir, d)) for d in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, d))
        )  # everything moved out of tmp/
