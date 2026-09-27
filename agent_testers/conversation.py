"""
Event-driven conversation loop for Gemini Live agents.

Turn boundaries come from the Gemini app's own unredacted ``#CM#`` logcat lines on the
device running Gemini Live. The agent's words come from per-turn recordings sent to the
transcription service's ``/transcribe_live/`` endpoint. Replies are rules plus dataset fields:

    "consent":   "yes" | "no" | null   answer to "should I send it?"-style questions
                                       (default "yes"; null = the agent asking is the expected end)
    "followups": [{"text": ..., "audio": <b64 wav>}]   scripted later user turns

Phase 0 probe (prints live turn events while you talk to the agent by hand):
    python -m agent_testers.conversation --device <serial of the device running Gemini Live>
"""

from __future__ import annotations

import base64
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import wave

import requests

logger = logging.getLogger(__name__)

# Unredacted Gemini app log lines (tags are obfuscated, so match the message).
# Calibration knob: a Gemini build that renames these needs only this dict edited.
EVENTS = {
    "session_start": "#CM# ConversationModeControllerImplV3 session started",
    "mic_ready":     "#CM# Encoder: encoding PCM audio to Opus",
    "idle":          "#CM# State is idle, starting inactivity timeout",
    "user_turn":     "#CM# Creating new turn",
    "agent_start":   "#CM# First audio chunk received",
    # Playback finished. NOT "Received silence. Finishing playback" (server end-of-stream, ~3s early).
    "agent_end":     "#CM# Setting received milestones as reached.",
    "session_end":   "#CM# Logging session stop",
}

MAX_USER_TURNS = 3
MIC_READY_S = 5
FIRST_RESPONSE_S = 20
IDLE_S = 3
SETTLE_S = 0.8        # calibrate in Phase 0: gap before the 2nd part of a tool-call answer
SESSION_END_S = 5

CONFIRM = re.compile(
    r"\b(should i|shall i|do you want|want me to|go ahead|confirm|are you sure|is that (right|correct))\b",
    re.IGNORECASE,
)


class LogcatEvents:
    """Streams the Gemini Live device's logcat and queues (host_monotonic_time, event_key)."""

    def __init__(self, device_id: str):
        self._q: queue.Queue = queue.Queue()
        # Start from the device's "now" so events from an earlier session are never replayed.
        since = subprocess.run(["adb", "-s", device_id, "shell", "date", "+%s"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        self._proc = subprocess.Popen(
            ["adb", "-s", device_id, "logcat", "-T", f"{since}.000", "-e", "#CM#"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace",
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self._proc.stdout:
            for key, message in EVENTS.items():
                if message in line:
                    self._q.put((time.monotonic(), key))
                    break

    def wait_for(self, keys, timeout: float):
        """Return the first (key, t) with key in ``keys`` within ``timeout``, else None.
        Events not in ``keys`` are consumed and dropped."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                t, key = self._q.get(timeout=max(deadline - time.monotonic(), 0))
            except queue.Empty:
                return None
            if key in keys:
                return key, t

    def close(self):
        self._proc.terminate()


def next_user_turn(agent_text: str, consent, followups: list):
    """Rules only: answer a confirmation question with the row's consent, else the next
    scripted follow-up, else None (conversation over). Pops the used follow-up."""
    if consent in ("yes", "no") and CONFIRM.search(agent_text or ""):
        return {"text": consent, "wav": f"{consent.capitalize()}.wav"}
    return followups.pop(0) if followups else None


def transcribe_live(path: str, url: str, timeout: float = 10) -> str:
    """Agent text for turn decisions. Empty string on any failure, which ends the conversation safely."""
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        r = requests.post(f"{url.rstrip('/')}/transcribe_live/", json={"data": data}, timeout=timeout)
        r.raise_for_status()
        return r.json().get("text", "")
    except Exception as e:
        logger.warning("transcribe_live failed for %s: %s", path, e)
        return ""


def wav_seconds(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def concat_audio(paths: list, out_path: str) -> None:
    """Join per-turn recordings into the single response file the judge pipeline expects."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return
    if len(paths) == 1:
        shutil.copyfile(paths[0], out_path)
        return
    inputs = [arg for p in paths for arg in ("-i", p)]
    streams = "".join(f"[{i}:a]" for i in range(len(paths)))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex", f"{streams}concat=n={len(paths)}:v=0:a=1", out_path]
    try:
        ok = subprocess.run(cmd).returncode == 0
    except OSError:  # ffmpeg not installed
        ok = False
    if not ok:
        logger.error("ffmpeg concat failed; judge gets only the first turn: %s", paths[0])
        shutil.copyfile(paths[0], out_path)


def run_conversation(events, speaker, recorder, q_info: dict, query_dir: str, eval_id: str,
                     response_path: str, transcription_url: str, turn_max_s: float,
                     assets_dir: str) -> dict:
    """Speak the question, then react to the agent turn by turn (up to MAX_USER_TURNS).
    Writes the concatenated agent audio to ``response_path`` and returns the conversation record."""
    consent = q_info.get("consent", "yes")
    followups = [f for f in q_info.get("followups") or [] if f.get("audio")]  # text-only = not rendered yet
    utter_path = q_info["metadata"]["audio_raw_path"]
    utter_text = q_info.get("question", "")
    utter_s = float(q_info.get("audio_duration") or wav_seconds(utter_path))

    if not events.wait_for({"mic_ready"}, MIC_READY_S):
        logger.warning("[%s] mic_ready not seen within %ss, speaking anyway", eval_id, MIC_READY_S)

    t0 = time.monotonic()
    turns, turn_files, end_reason = [], [], None
    for n in range(1, MAX_USER_TURNS + 1):
        speaker.play_audio(utter_path)
        time.sleep(utter_s)  # our own audio: known length
        turn = {"user": utter_text}
        turns.append(turn)

        turn_file = f"response_{eval_id}_t{n}.mp3"
        turn_path = os.path.join(query_dir, turn_file)
        recorder.start_recording(turn_file)

        got = events.wait_for({"agent_start", "session_end"}, FIRST_RESPONSE_S)
        if not got or got[0] == "session_end":
            end_reason = "no_response" if not got else "session_ended"
        else:
            turn["t_agent_start"] = round(got[1] - t0, 2)
            # A tool-call answer can come in parts; a new agent_start right after idle continues the turn.
            while True:
                end = events.wait_for({"agent_end", "session_end"}, turn_max_s)
                if not end or end[0] == "session_end":
                    end_reason = "turn_timeout" if not end else "session_ended"
                    break
                turn["t_agent_end"] = round(end[1] - t0, 2)
                nxt = events.wait_for({"idle", "agent_start"}, IDLE_S)
                if nxt and nxt[0] == "idle":
                    nxt = events.wait_for({"agent_start"}, SETTLE_S)
                if not nxt:
                    break
        recorder.stop_recording(turn_path)
        turn_files.append(turn_path)
        if end_reason:
            break

        # ponytail: if the agent starts talking again after SETTLE_S while we decide, that audio
        # is not recorded; handle it here if Phase 0 shows late continuations.
        if consent is None and not followups:
            end_reason = "no_reply_possible"
            break
        turn["agent_text"] = transcribe_live(turn_path, transcription_url)
        reply = next_user_turn(turn["agent_text"], consent, followups)
        logger.info("[%s] turn %d agent=%r -> reply=%r", eval_id, n, turn["agent_text"], reply and reply["text"])
        if reply is None:
            end_reason = "agent_done"
            break
        if n == MAX_USER_TURNS:
            break
        utter_text = reply["text"]
        if "wav" in reply:
            utter_path = os.path.join(assets_dir, reply["wav"])
        else:
            utter_path = os.path.join(query_dir, f"followup_{eval_id}_t{n + 1}.wav")
            with open(utter_path, "wb") as f:
                f.write(base64.b64decode(reply["audio"]))
        utter_s = wav_seconds(utter_path)

    concat_audio(turn_files, response_path)
    return {"turns": turns, "end_reason": end_reason or "max_turns", "turn_files": turn_files}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Print Gemini Live turn events live (Phase 0 probe).")
    parser.add_argument("--device", required=True, help="serial of the device running Gemini Live")
    args = parser.parse_args()
    ev = LogcatEvents(args.device)
    start = time.monotonic()
    print("Streaming #CM# turn events. Talk to Gemini Live; Ctrl+C to stop.")
    try:
        while True:
            hit = ev.wait_for(set(EVENTS), 3600)
            if hit:
                print(f"{hit[1] - start:8.3f}s  {hit[0]}", flush=True)
    except KeyboardInterrupt:
        ev.close()
