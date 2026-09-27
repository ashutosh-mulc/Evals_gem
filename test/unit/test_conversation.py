"""Event-driven Gemini Live conversation loop (agent_testers/conversation.py).

A fake agent reacts to each utterance by pushing scripted #CM# events, so the real
LogcatEvents.wait_for / run_conversation logic runs without a device.
"""

import base64
import io
import os
import queue
import time
import wave

import pytest

from agent_testers import conversation as conv


def _wav(path, seconds=0.01):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\0\0" * int(16000 * seconds))
    return path


ANSWER = ["user_turn", "agent_start", "agent_end", "idle"]


class FakeAgent:
    """Speaker fake: each utterance triggers the next scripted list of agent events."""

    def __init__(self, events, reactions):
        self.events, self.reactions, self.played = events, list(reactions), []

    def play_audio(self, path):
        self.played.append(os.path.basename(path))
        for key in (self.reactions.pop(0) if self.reactions else []):
            self.events._q.put((time.monotonic(), key))


class FakeRecorder:
    def __init__(self):
        self.started = []

    def start_recording(self, name):
        self.started.append(name)

    def stop_recording(self, path):
        with open(path, "wb") as f:
            f.write(b"agent audio")


@pytest.fixture
def run(tmp_path, monkeypatch):
    for name, value in dict(MIC_READY_S=0.05, FIRST_RESPONSE_S=0.2, IDLE_S=0.1, SETTLE_S=0.05).items():
        monkeypatch.setattr(conv, name, value)
    assets = tmp_path / "assets"; assets.mkdir()
    _wav(str(assets / "Yes.wav")); _wav(str(assets / "No.wav"))
    concats = []
    monkeypatch.setattr(conv, "concat_audio", lambda paths, out: concats.append(list(paths)))

    def _run(reactions, texts=(), **row):
        events = object.__new__(conv.LogcatEvents)
        events._q = queue.Queue()
        events._q.put((time.monotonic(), "mic_ready"))
        heard = list(texts)
        asked = []
        monkeypatch.setattr(conv, "transcribe_live", lambda path, url: asked.append(path) or heard.pop(0))
        agent, recorder = FakeAgent(events, reactions), FakeRecorder()
        q_info = {"question": "Delete the 6PM alarm", "audio_duration": 0,
                  "metadata": {"audio_raw_path": _wav(str(tmp_path / "q.wav"))}, **row}
        result = conv.run_conversation(events, agent, recorder, q_info, str(tmp_path), "q1",
                                       str(tmp_path / "response_q1.mp3"), "http://asr", 0.2, str(assets))
        return result, agent.played, recorder.started, asked, concats

    return _run


def test_single_turn_ends_when_agent_does_not_ask(run):
    result, played, started, asked, _ = run([ANSWER], ["Your 6 PM alarm is deleted."])
    assert result["end_reason"] == "agent_done"
    assert played == ["q.wav"] and started == ["response_q1_t1.mp3"]
    assert result["turns"][0]["agent_text"] == "Your 6 PM alarm is deleted."


def test_confirmation_question_gets_consent_then_ends(run):
    result, played, started, _, concats = run([ANSWER, ANSWER], ["Should I send it to Maria?", "Sent."])
    assert played == ["q.wav", "Yes.wav"]
    assert [t["user"] for t in result["turns"]] == ["Delete the 6PM alarm", "yes"]
    assert result["end_reason"] == "agent_done"
    assert len(concats[-1]) == 2  # both agent turns go to the judge


def test_consent_no_is_played(run):
    _, played, *_ = run([ANSWER, ANSWER], ["Do you want me to delete it?", "Okay, I won't."], consent="no")
    assert played == ["q.wav", "No.wav"]


def test_null_consent_without_followups_skips_asr(run):
    result, _, _, asked, _ = run([ANSWER], [], consent=None)
    assert result["end_reason"] == "no_reply_possible" and asked == []


def test_no_agent_response_waits_once(run):
    t = time.monotonic()
    result, *_ = run([["user_turn"]])
    assert result["end_reason"] == "no_response"
    assert time.monotonic() - t < 1  # FIRST_RESPONSE_S (0.2) once, not doubled


def test_multi_part_answer_stays_one_turn(run):
    two_parts = ["agent_start", "agent_end", "idle", "agent_start", "agent_end", "idle"]
    result, _, started, *_ = run([two_parts], ["Setting it. Done, alarm set."])
    assert started == ["response_q1_t1.mp3"] and len(result["turns"]) == 1


def test_max_user_turns_enforced(run):
    keeps_asking = ["Do you want me to continue?"] * 5
    result, played, *_ = run([ANSWER] * 5, keeps_asking)
    assert result["end_reason"] == "max_turns"
    assert played == ["q.wav", "Yes.wav", "Yes.wav"]  # 3 user turns total


def test_scripted_followup_played_and_text_only_followups_ignored(run):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0" * 160)
    followups = [{"text": "not rendered yet"}, {"text": "Make it 7 PM", "audio": base64.b64encode(buf.getvalue()).decode()}]
    result, played, *_ = run([ANSWER, ANSWER], ["Alarm set for 6 PM.", "Changed to 7 PM."], followups=followups)
    assert played == ["q.wav", "followup_q1_t2.wav"]
    assert result["turns"][1]["user"] == "Make it 7 PM"


def test_session_end_stops_the_loop(run):
    result, *_ = run([["agent_start", "session_end"]])
    assert result["end_reason"] == "session_ended"


def test_rules():
    assert conv.next_user_turn("Shall I go ahead and send it?", "yes", [])["wav"] == "Yes.wav"
    assert conv.next_user_turn("Which Anne do you mean?", "yes", []) is None  # clarification, not consent
    assert conv.next_user_turn("Should I send it?", None, []) is None


def test_concat_audio_really_joins(tmp_path):
    parts = [_wav(str(tmp_path / f"t{i}.wav"), 0.5) for i in (1, 2)]
    out = str(tmp_path / "out.wav")
    conv.concat_audio(parts, out)
    with wave.open(out) as w:
        assert abs(w.getnframes() / w.getframerate() - 1.0) < 0.1
