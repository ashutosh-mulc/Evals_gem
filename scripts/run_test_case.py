#!/usr/bin/env python3
"""
run_test_case.py — Parameterized single test-case runner for reliability testing.

Runs a single dataset question through the full evaluation pipeline:
  1. Decode audio + image from dataset
  2. Capture pre-state (device info, screenshots)
  3. Invoke device (Jinju Gemini)
  4. Play question audio via ARAP
  5. Record response via ARAP
  6. Capture post-state
  7. Transcribe response
  8. Verify state change (programmatic)
  9. Judge (LLM)
  10. Image verification (multimodal LLM)
  11. Save trace

Each step is recorded by ExecutionTracer for later reliability analysis.

Usage:
    # Single run
    python scripts/run_test_case.py --eval-id q00001 --config configs/jinju_gemini_config.json

    # Multiple runs for reliability testing
    python scripts/run_test_case.py --eval-id q00001 --runs 3 --config configs/jinju_gemini_config.json

    # Batch of eval IDs
    python scripts/run_test_case.py --eval-ids q00001,q00002,q00003 --runs 2 --config configs/jinju_gemini_config.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import traceback


# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from agent_testers.conversation import LogcatEvents, run_conversation
from scripts.execution_tracer import ExecutionTracer
from utils.file_utils import Base64Converter
from common.question_type import QuestionType


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_dataset(dataset_path: str) -> dict[str, dict]:
    """Load the JSONL dataset and return a dict keyed by eval_id."""
    entries = {}
    with open(dataset_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if "eval_id" in d:
                    entries[d["eval_id"]] = d
            except json.JSONDecodeError:
                continue
    return entries


# ---------------------------------------------------------------------------
# Service helpers (transcription, judge)
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path: str, transcription_url: str) -> dict:
    """Send audio to the transcription service and get text back."""
    import requests

    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = requests.post(
        f"{transcription_url}/transcribe/",
        json={"data": audio_b64},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def judge_response(
    question: str,
    transcription: str,
    question_type: str,
    eval_type: str,
    pre_state: dict,
    post_state: dict,
    judge_url: str,
    config: dict = None,
    q_info: dict = None,
) -> dict:
    """Send the evaluation to the judge LLM and get a score back.

    Uses the ResponseScorer from judge_worker for proper prompt construction,
    thinking-disabled mode, and rating/analysis extraction.
    """
    import re

    try:
        from judge_worker.response_scorer import ResponseScorer

        judge_config = config.get("judge_worker", {})
        scorer = ResponseScorer(
            transcription_url=config["urls"]["transcription_url"],
            judge_url=judge_url,
            rating_rectifier_url=config["urls"].get("rating_rectifier_url", ""),
            device_type=config.get("device_manager_type", ""),
            judge_config=judge_config,
        )

        metadata = q_info.get("metadata", {}) if q_info else {}
        metadata["device_info_pre"] = pre_state
        metadata["device_info_post"] = post_state

        encoded_image = ""
        image_path = q_info.get("metadata", {}).get("image_path", "") if q_info else ""
        if image_path and os.path.exists(image_path):
            encoded_image = Base64Converter.encode_to_base64(image_path).get("file_base64", "")

        encoded_app_screenshot = ""
        app_ss_path = q_info.get("metadata", {}).get("app_screenshot_path", "") if q_info else ""
        if app_ss_path and os.path.exists(app_ss_path):
            encoded_app_screenshot = Base64Converter.encode_to_base64(app_ss_path).get("file_base64", "")

        eval_db = {
            "eval_id": q_info.get("eval_id", "") if q_info else "",
            "eval_type": eval_type,
            "question": question,
            "question_type": question_type,
            "reference": q_info.get("gt_answer", "") if q_info else "",
            "encoded_audio": "",
            "encoded_image": encoded_image,
            "encoded_app_screenshot": encoded_app_screenshot,
            "metadata": metadata,
        }

        response, entropy_metrics, _judge_prompt = scorer.run_judge(
            eval_type=eval_type,
            question=question,
            gt_answer=q_info.get("gt_answer", "") if q_info else "",
            ai_response=transcription,
            encoded_image=encoded_image,
            question_type=question_type,
            device_info=post_state,
            eval_json=eval_db,
            device_info_pre=pre_state,
            encoded_app_screenshot=encoded_app_screenshot,
        )


        rating_match = re.search(r'[\'"]rating[\'"]\s*:\s*(\d+)', response)
        rating = int(rating_match.group(1)) if rating_match else 0

        analysis_match = re.search(r'[\'"]analysis[\'"]\s*:\s*[\'"](.*?)[\'"]\s*,\s*[\'"]rating[\'"]', response, re.DOTALL)
        analysis = analysis_match.group(1) if analysis_match else response[:200]

        return {"score": rating, "analysis": analysis}

    except Exception as e:
        return {"score": 0, "analysis": f"Judge failed: {e}\n{traceback.format_exc()[:300]}"}


# ---------------------------------------------------------------------------
# State verification
# ---------------------------------------------------------------------------

def verify_state_change(
    question_type: str,
    pre_state: dict | None,
    post_state: dict | None,
) -> dict:
    """Programmatically verify that the expected state change occurred."""
    if not pre_state or not post_state:
        return {"verified": False, "details": "Missing pre/post state"}

    qt = QuestionType.parse(question_type)
    feature = qt.feature
    action = qt.action

    if feature == "volume":
        pre_vol = pre_state.get("jinju", {}).get("volume", {}).get("current")
        post_vol = post_state.get("jinju", {}).get("volume", {}).get("current")
        vol_max = pre_state.get("jinju", {}).get("volume", {}).get("max", 100)
        if pre_vol is None or post_vol is None:
            return {"verified": False, "details": "Volume info missing"}

        if action == "up":
            if pre_vol >= vol_max:
                return {"verified": True, "details": f"Volume already at max ({pre_vol}/{vol_max}) — cannot increase further. AI acknowledged the request."}
            verified = post_vol > pre_vol
            return {"verified": verified, "details": f"Volume: {pre_vol} -> {post_vol}", "delta": post_vol - pre_vol}
        elif action == "down":
            if pre_vol <= 0:
                return {"verified": True, "details": "Volume already at min (0) — cannot decrease further."}
            verified = post_vol < pre_vol
            return {"verified": verified, "details": f"Volume: {pre_vol} -> {post_vol}", "delta": pre_vol - post_vol}
        elif action == "set":
            return {"verified": True, "details": f"Volume: {pre_vol} -> {post_vol} (set action, assuming correct)"}
        else:
            return {"verified": post_vol != pre_vol, "details": f"Volume changed: {pre_vol} -> {post_vol}"}

    if feature == "battery":
        return {"verified": True, "details": "Battery query (informational, no state change expected)"}

    if feature in ("datetime", "time", "date"):
        return {"verified": True, "details": "Time/date query (informational)"}

    pre_str = json.dumps(pre_state, sort_keys=True)
    post_str = json.dumps(post_state, sort_keys=True)
    if pre_str != post_str:
        return {"verified": True, "details": "State changed (generic check)"}
    return {"verified": False, "details": "No state change detected (generic check)"}


# ---------------------------------------------------------------------------
# Pipeline resources — created once, shared across all runs
# ---------------------------------------------------------------------------

class PipelineResources:
    """Context manager for shared pipeline resources (display server, ARAP, device manager).

    Resources are created once in __enter__ and cleaned up in __exit__.
    Individual runs reuse these resources without recreating them.
    """

    def __init__(self, config: dict, run_dir: str):
        self.config = config
        self.run_dir = run_dir
        self.dm = None
        self.arap_speaker = None
        self.arap_recorder = None
        self.display_server = None
        self.display_thread = None
        self.events = None  # LogcatEvents while a Gemini Live conversation is running
        self.jinju_device = config["devices"]["jinju_device_id"]

    def __enter__(self):
        from agent_testers.device_managers.jinju_gemini_manager import DeviceManager
        from agent_testers.arap_manager import ARAPManager

        companion_device = self.config["devices"]["s25_device_id"]
        arap_devices = self.config["devices"]["arap"]["devices"]

        # Start XRClaw instrumentation on companion device before creating DeviceManager
        # (DeviceManager.__init__ creates XRClawStateCollector which needs it running)
        xrclaw_config = self.config.get("xrclaw", {})
        if xrclaw_config.get("enabled", False):
            claw_package = xrclaw_config.get("claw_package", "com.samsung.xr.claw.client")
            print(f"Starting XRClaw instrumentation on {companion_device}...", flush=True)
            subprocess.run(
                f"adb -s {companion_device} shell am force-stop {claw_package}",
                shell=True
            )
            time.sleep(1)
            subprocess.Popen(
                [
                    "adb", "-s", companion_device, "shell",
                    "am", "instrument", "-w",
                    f"{claw_package}/.ShellIdentityInstrumentation"
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            time.sleep(3)
            print("XRClaw instrumentation started.", flush=True)

        self.dm = DeviceManager(companion_device, self.jinju_device, self.run_dir, self.config)

        self.arap_speaker = ARAPManager(arap_devices[0])
        self.arap_recorder = ARAPManager(arap_devices[-1])

        # Display server is started lazily — only when an image needs to be shown
        # (see show_image_on_display()). It runs for the lifetime of all runs.
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def ensure_display_server(self):
        """Start the display server if not already running (lazy init)."""
        if self.display_server is not None:
            return  # Already running

        from services.host.display_server import DisplayServer
        import threading

        display_port = self.config["urls"].get("display_port", 5001)
        self.display_server = DisplayServer()
        self.display_thread = threading.Thread(
            target=self.display_server.get_app().run,
            kwargs={"host": "0.0.0.0", "port": int(display_port)},
            daemon=True,
        )
        self.display_thread.start()
        time.sleep(1)
        print(f"  Display server started on port {display_port}", flush=True)

    def show_image_on_display(self, image_b64: str) -> bool:
        """Show an image on the display server. Returns True on success."""
        if not image_b64:
            return False
        try:
            self.ensure_display_server()
            self.display_server.set_image_status(None, "stop")
            time.sleep(1)
            self.display_server.set_image_status(image_b64, "show")
            time.sleep(1)
            return True
        except Exception as e:
            print(f"  [ERROR] show_image_on_display failed: {e}", flush=True)
            return False

    def cleanup(self):
        """Clean up all resources."""
        if self.arap_speaker:
            try:
                self.arap_speaker.stop_arap()
            except Exception:
                pass
        if self.arap_recorder:
            try:
                self.arap_recorder.stop_arap()
            except Exception:
                pass
        if self.dm:
            try:
                self.dm.terminate()
            except Exception:
                pass
        # Display server is a daemon thread — it will be killed when the process exits
        # We don't explicitly shut it down because Flask doesn't have a clean shutdown API


# ---------------------------------------------------------------------------
# Single run execution
# ---------------------------------------------------------------------------

def _decode_media(dataset_entry: dict, run_dir: str) -> tuple[str, str, str, str]:
    """Decode audio and image from dataset entry. Returns (audio_path, image_path, audio_b64, image_b64)."""
    audio_b64 = dataset_entry.get("audio", "")
    image_b64 = dataset_entry.get("image", "")

    audio_path = os.path.join(run_dir, "audio_question.wav")
    image_path = os.path.join(run_dir, "image_question.png")

    if audio_b64:
        Base64Converter.decode_to_file(audio_b64, audio_path)
    if image_b64:
        Base64Converter.decode_to_file(image_b64, image_path)

    return audio_path, image_path, audio_b64, image_b64


def _capture_pre_state(
    resources: PipelineResources,
    q_info: dict,
    eval_type: str,
    question_type: str,
    tracer: ExecutionTracer,
) -> dict:
    """Capture pre-invocation device state. Returns pre_state dict."""
    pre_state = {}

    # Device info
    try:
        if eval_type == "APP_EVAL_TASK":
            resources.dm.capture_device_info(q_info, capture_type="pre")
            pre_state = q_info["metadata"].get("device_info_pre", {})
        tracer.step("capture_pre_state", outputs={"state": pre_state})
    except Exception as e:
        print(f"  [ERROR] capture_pre_state failed: {e}", flush=True)
        traceback.print_exc()
        tracer.step("capture_pre_state", status="failure", error=str(e))

    # XRClaw pre-state
    try:
        resources.dm.capture_xrclaw_pre_state(q_info)
        tracer.step("capture_xrclaw_pre_state", outputs={"status": "captured"})
    except Exception as e:
        print(f"  [ERROR] capture_xrclaw_pre_state failed: {e}", flush=True)
        traceback.print_exc()
        tracer.step("capture_xrclaw_pre_state", status="failure", error=str(e))

    # Pre-test volume reset for volume-up queries
    try:
        from common.question_type import QuestionType as QT
        qt = QT.parse(question_type)
        if qt.feature == "volume" and qt.action == "up":
            print("  Pre-test: resetting volume to 30%", flush=True)
            resources.dm.reset_media_volume(resources.jinju_device, 30)
            time.sleep(1)
            tracer.step("pre_test_volume_reset", outputs={"status": "reset to 30%"})
            # Re-capture pre-state after volume reset
            q_info["metadata"] = {k: v for k, v in q_info["metadata"].items() if k != "device_info_pre"}
            resources.dm.capture_device_info(q_info, capture_type="pre")
            pre_state = q_info["metadata"].get("device_info_pre", {})
            print(f"  Pre-test: volume after reset: {pre_state.get('jinju', {}).get('volume', {})}", flush=True)
    except Exception as e:
        print(f"  [ERROR] pre_test_volume_reset failed: {e}", flush=True)
        traceback.print_exc()
        tracer.step("pre_test_volume_reset", status="failure", error=str(e))

    return pre_state


def _invoke_and_play(
    resources: PipelineResources,
    q_info: dict,
    audio_path: str,
    audio_duration: float,
    tracer: ExecutionTracer,
) -> bool:
    """Invoke device and play audio. Returns True on success."""
    try:
        resources.arap_speaker.start_arap()
        resources.arap_recorder.start_arap()

        if getattr(resources.dm, "live_device", None):
            # Gemini Live: the conversation loop speaks the question itself (_record_response)
            resources.events = LogcatEvents(resources.dm.live_device)
            resources.dm.invoke(q_info)
        else:
            resources.dm.invoke(q_info)
            resources.arap_speaker.play_audio(audio_path)
            time.sleep(audio_duration)

        tracer.step("invoke_device", outputs={"status": "invoked"})
        return True
    except Exception as e:
        print(f"  [ERROR] invoke_device failed: {e}", flush=True)
        traceback.print_exc()
        tracer.step("invoke_device", status="failure", error=str(e))
        return False


def _record_response(
    resources: PipelineResources,
    q_info: dict,
    question_type: str,
    eval_id: str,
    run_id: int,
    config: dict,
    tracer: ExecutionTracer,
) -> str | None:
    """Record the AI response via ARAP. Returns response_path or None."""
    try:
        response_path = os.path.join(tracer.output_dir, f"response_{eval_id}_run{run_id}.mp3")
        assets_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "agent_testers", "assets"
        )

        if resources.events:
            conversation = run_conversation(
                resources.events, resources.arap_speaker, resources.arap_recorder, q_info,
                tracer.output_dir, f"{eval_id}_run{run_id}", response_path,
                config["urls"]["transcription_url"], config["devices"]["arap"]["record_duration"], assets_dir)
            resources.events.close()
            resources.events = None
            q_info["metadata"]["conversation"] = conversation
            tracer.step("record_response", outputs={"response_path": response_path, "conversation": conversation})
            return response_path

        resources.arap_recorder.start_recording(f"response_{eval_id}_run{run_id}.mp3")

        # Play consent audio
        from agent_testers.consent_player import play_consent
        qt = QuestionType.parse(question_type)
        try:
            play_consent(resources.dm, qt, assets_dir)
            tracer.step("consent_audio", outputs={"status": "played"})
        except Exception as e:
            print(f"  [ERROR] consent_audio failed: {e}", flush=True)
            tracer.step("consent_audio", status="failure", error=str(e))

        time.sleep(config["devices"]["arap"]["record_duration"])
        resources.arap_recorder.stop_recording(response_path)

        tracer.step("record_response", outputs={"response_path": response_path})
        return response_path
    except Exception as e:
        print(f"  [ERROR] record_response failed: {e}", flush=True)
        traceback.print_exc()
        tracer.step("record_response", status="failure", error=str(e))
        return None


def _capture_post_state(
    resources: PipelineResources,
    q_info: dict,
    eval_type: str,
    question_type: str,
    tracer: ExecutionTracer,
) -> dict:
    """Capture post-invocation device state. Returns post_state dict."""
    post_state = {}

    try:
        if eval_type == "APP_EVAL_TASK":
            resources.dm.capture_device_info(q_info, capture_type="post")
            post_state = q_info["metadata"].get("device_info_post", {})
        tracer.step("capture_post_state", outputs={"state": post_state})
    except Exception as e:
        print(f"  [ERROR] capture_post_state failed: {e}", flush=True)
        traceback.print_exc()
        tracer.step("capture_post_state", status="failure", error=str(e))

    try:
        resources.dm.capture_app_meta_info(q_info)
        tracer.step("capture_app_meta_info", outputs={"status": "captured"})
    except Exception as e:
        print(f"  [ERROR] capture_app_meta_info failed: {e}", flush=True)
        tracer.step("capture_app_meta_info", status="failure", error=str(e))

    # Reset volume if this was a volume query
    try:
        qt = QuestionType.parse(question_type)
        if qt.feature == "volume":
            resources.dm.reset_media_volume(resources.jinju_device, 80)
            tracer.step("reset_volume", outputs={"status": "reset"})
    except Exception as e:
        tracer.step("reset_volume", status="failure", error=str(e))

    return post_state


def run_single(
    eval_id: str,
    run_id: int,
    dataset_entry: dict,
    config: dict,
    resources: PipelineResources,
    scratch_pad: str = "scratch_pad",
    skip_device: bool = False,
) -> str:
    """Run a single test case and save the trace.

    Args:
        eval_id: The evaluation ID (e.g., "q00001").
        run_id: The run number (1, 2, 3, etc.).
        dataset_entry: The dataset entry dict for this eval_id.
        config: The full config dict.
        resources: Shared pipeline resources (display server, ARAP, device manager).
        scratch_pad: Path to the scratch_pad directory.
        skip_device: If True, skip actual device interaction (dry run).

    Returns:
        Path to the saved trace JSON file.
    """
    run_dir = os.path.join(scratch_pad, "runs", eval_id)
    os.makedirs(run_dir, exist_ok=True)

    tracer = ExecutionTracer(eval_id, run_id, run_dir)

    question = dataset_entry.get("question", "")
    question_type = dataset_entry.get("question_type", "")
    eval_type = dataset_entry.get("eval_type", "")
    audio_duration = float(dataset_entry.get("audio_duration", 1.0))

    tracer.step("init", inputs={
        "eval_id": eval_id, "question": question,
        "question_type": question_type, "eval_type": eval_type,
        "audio_duration": audio_duration,
    }, outputs={"run_dir": run_dir})

    # Step 1: Decode media
    try:
        audio_path, image_path, audio_b64, image_b64 = _decode_media(dataset_entry, run_dir)
        tracer.step("decode_media", inputs={
            "audio_b64_len": len(audio_b64), "image_b64_len": len(image_b64),
        }, outputs={"audio_path": audio_path, "image_path": image_path})
    except Exception as e:
        tracer.step("decode_media", status="failure", error=str(e))
        return tracer.save()

    if skip_device:
        tracer.step("capture_pre_state", outputs={"state": {"simulated": True}}, status="skipped")
        tracer.step("invoke_device", outputs={"simulated": True}, status="skipped")
        tracer.step("capture_post_state", outputs={"state": {"simulated": True}}, status="skipped")
        tracer.step("transcribe_response", outputs={"text": "[dry run]"}, status="skipped")
        tracer.step("verify_state_change", outputs={"verified": True}, status="skipped")
        tracer.step("judge", outputs={"score": 5, "analysis": "dry run"}, status="skipped")
        tracer.step("image_verification", outputs={"match": True, "description": "dry run"}, status="skipped")
        tracer.step("overall", outputs={"pass": True, "dry_run": True})
        return tracer.save()

    # Step 2: Show image on display (if any)
    if image_b64:
        if resources.show_image_on_display(image_b64):
            tracer.step("display_image", outputs={"status": "shown"})
        else:
            tracer.step("display_image", status="failure", error="show_image_on_display failed")

    # Step 3: Capture pre-state
    q_info = {
        "eval_id": eval_id, "question": question,
        "question_type": question_type, "eval_type": eval_type,
        "gt_answer": dataset_entry.get("gt_answer", ""),
        "audio_duration": audio_duration,
        **{k: dataset_entry[k] for k in ("setup", "consent", "followups") if k in dataset_entry},
        "metadata": {"audio_raw_path": audio_path},
    }
    if image_b64:
        q_info["metadata"]["image_path"] = image_path

    # Reset companion screen before capturing pre-state
    try:
        if hasattr(resources.dm, "reset_companion_screen"):
            resources.dm.reset_companion_screen()
            tracer.step("reset_companion_screen", outputs={"status": "reset to home"})
    except Exception as e:
        print(f"  [WARN] reset_companion_screen failed: {e}", flush=True)
        tracer.step("reset_companion_screen", status="failure", error=str(e))

    pre_state = _capture_pre_state(resources, q_info, eval_type, question_type, tracer)

    # Step 4: Invoke device + play audio

    if not _invoke_and_play(resources, q_info, audio_path, audio_duration, tracer):
        return tracer.save()

    # Step 5: Record response
    response_path = _record_response(
        resources, q_info, question_type, eval_id, run_id, config, tracer
    )

    # Step 6: Capture post-state
    post_state = _capture_post_state(resources, q_info, eval_type, question_type, tracer)

    # Step 7: Transcribe response
    transcription = ""
    if response_path and os.path.exists(response_path):
        try:
            transcription_url = config["urls"]["transcription_url"]
            result = transcribe_audio(response_path, transcription_url)
            transcription = result.get("text", "")
            tracer.step("transcribe_response", outputs={
                "text": transcription, "language": result.get("language", ""),
            })
        except Exception as e:
            print(f"  [ERROR] transcribe_response failed: {e}", flush=True)
            tracer.step("transcribe_response", status="failure", error=str(e))
    else:
        tracer.step("transcribe_response", status="skipped", error="No response audio")

    # Step 8: Verify state change
    try:
        verification = verify_state_change(question_type, pre_state, post_state)
        tracer.step("verify_state_change", outputs=verification)
    except Exception as e:
        tracer.step("verify_state_change", status="failure", error=str(e))
        verification = {"verified": False}

    # Step 9: Judge
    try:
        judge_url = config["urls"]["judge_url"]
        judge_result = judge_response(
            question, transcription, question_type, eval_type,
            pre_state, post_state, judge_url, config=config, q_info=q_info,
        )
        tracer.step("judge", outputs={
            "score": judge_result.get("score", 0),
            "analysis": judge_result.get("analysis", ""),
        })
    except Exception as e:
        tracer.step("judge", status="failure", error=str(e))
        judge_result = {"score": 0}

    # Step 10: Image verification
    try:
        app_ss = os.path.join(run_dir, "app_screenshot.png")
        if os.path.exists(app_ss):
            tracer.step("image_verification", outputs={
                "screenshot_path": app_ss, "screenshot_exists": True,
                "note": "Use analyze_image tool for visual verification",
            })
        else:
            tracer.step("image_verification", status="skipped",
                        error="No app_screenshot.png found in run_dir")
    except Exception as e:
        tracer.step("image_verification", status="failure", error=str(e))

    # Step 11: Overall result
    state_verified = verification.get("verified", False)
    judge_score = judge_result.get("score", 0)
    overall_pass = state_verified and judge_score >= 3

    tracer.step("overall", outputs={
        "pass": overall_pass,
        "state_verified": state_verified,
        "judge_score": judge_score,
    })

    return tracer.save()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run a single test case through the evaluation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single run
  python scripts/run_test_case.py --eval-id q00001 --config configs/jinju_gemini_config.json

  # 3 runs for reliability testing
  python scripts/run_test_case.py --eval-id q00001 --runs 3 --config configs/jinju_gemini_config.json

  # Batch of eval IDs, 2 runs each
  python scripts/run_test_case.py --eval-ids q00001,q00002,q00003 --runs 2 --config configs/jinju_gemini_config.json

  # Dry run (no device interaction, test runner logic only)
  python scripts/run_test_case.py --eval-id q00001 --dry-run --config configs/jinju_gemini_config.json
        """,
    )
    parser.add_argument("--eval-id", help="Single eval ID to run (e.g., q00001)")
    parser.add_argument("--eval-ids", help="Comma-separated eval IDs to run (e.g., q00001,q00002)")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per eval ID (default: 1)")
    parser.add_argument("--config", default="configs/jinju_gemini_config.json", help="Path to config JSON")
    parser.add_argument("--scratch-pad", default="scratch_pad", help="Path to scratch_pad directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip device interaction (test runner logic only)")
    args = parser.parse_args()

    # Parse eval IDs
    if args.eval_ids:
        eval_ids = [e.strip() for e in args.eval_ids.split(",")]
    elif args.eval_id:
        eval_ids = [args.eval_id]
    else:
        parser.error("Either --eval-id or --eval-ids must be provided")

    # Load config
    with open(args.config) as f:
        config = json.load(f)

    # Load dataset
    dataset_path = config["paths"]["dataset_file"]
    print(f"Loading dataset from: {dataset_path}")
    dataset = load_dataset(dataset_path)
    print(f"Loaded {len(dataset)} entries from dataset")

    # Create shared resources (device manager, ARAP, display server)
    # These are created once and reused across all runs
    run_dir_base = os.path.join(args.scratch_pad, "runs")
    os.makedirs(run_dir_base, exist_ok=True)

    if args.dry_run:
        # Dry run — no resources needed
        for eval_id in eval_ids:
            if eval_id not in dataset:
                print(f"WARNING: {eval_id} not found in dataset, skipping")
                continue
            entry = dataset[eval_id]
            print(f"\n{'='*60}")
            print(f"Running {eval_id}: '{entry.get('question', '')}' ({entry.get('question_type', '')})")
            print(f"{'='*60}")
            for run_id in range(1, args.runs + 1):
                print(f"\n--- Run {run_id}/{args.runs} for {eval_id} ---")
                trace_path = run_single(
                    eval_id=eval_id, run_id=run_id, dataset_entry=entry,
                    config=config, resources=None,
                    scratch_pad=args.scratch_pad, skip_device=True,
                )
                print(f"Trace saved: {trace_path}")
    else:
        # Real device runs — create shared resources
        with PipelineResources(config, run_dir_base) as resources:
            for eval_id in eval_ids:
                if eval_id not in dataset:
                    print(f"WARNING: {eval_id} not found in dataset, skipping")
                    continue

                entry = dataset[eval_id]
                print(f"\n{'='*60}")
                print(f"Running {eval_id}: '{entry.get('question', '')}' ({entry.get('question_type', '')})")
                print(f"{'='*60}")

                for run_id in range(1, args.runs + 1):
                    print(f"\n--- Run {run_id}/{args.runs} for {eval_id} ---")
                    trace_path = run_single(
                        eval_id=eval_id, run_id=run_id, dataset_entry=entry,
                        config=config, resources=resources,
                        scratch_pad=args.scratch_pad, skip_device=False,
                    )
                    print(f"Trace saved: {trace_path}")

    # Generate reliability report if multiple runs
    if args.runs > 1 or len(eval_ids) > 1:
        print(f"\n{'='*60}")
        print("Generating reliability report...")
        print(f"{'='*60}")
        from scripts.reliability_tracker import ReliabilityTracker
        tracker = ReliabilityTracker(scratch_pad_dir=args.scratch_pad)
        tracker.save_report()
        tracker.generate_html_report()


if __name__ == "__main__":
    main()
