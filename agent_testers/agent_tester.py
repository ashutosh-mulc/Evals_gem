"""
Agent Tester — Executes evaluation queries on AI agent devices.

This module is the client worker that:
  1. Receives questions from the metric_coordinator via FIFO
  2. Decodes question data (images, audio)
  3. Sets up preconditions (app state, device settings)
  4. Invokes the AI agent via device-specific manager
  5. Plays query audio via ARAP (Audio Recording and Playback)
  6. Records agent's spoken response
  7. Captures post-execution state (device info, app state, screenshots)
  8. Returns results to coordinator for judging

Process Role:
    Runs in a screen session as a CLIENT, communicating with the
    metric_coordinator (HOST) via named pipes in /tmp.

Device Manager Pattern:
    Supports multiple device configurations via pluggable DeviceManager
    classes (see agent_testers.device_managers.DEVICE_MANAGERS).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import sys
import threading
import time

from agent_testers.arap_manager import ARAPManager
from agent_testers.consent_player import play_consent
from agent_testers.device_managers import DEVICE_MANAGERS
from agent_testers.conversation import SESSION_END_S, LogcatEvents, run_conversation
from agent_testers.preconditions import PreconditionManager
from agent_testers.robopod_manager import RobopodManager
from common.logging_config import setup_logging
from common.message import Message
from common.question_type import QuestionType
from services.host.display_server import DisplayServer
from utils.file_utils import Base64Converter, JSONFileManager
from utils.message_transport import MessagePipes



class AgentTester:
    """
    Executes evaluation queries on AI agent devices.

    Responsibilities:
      - Initialize device-specific DeviceManager (jinju, s25, meta, etc.)
      - Configure ARAP (local via ADB or remote via Robopod)
      - Set up XRClaw state collector for app verification
      - Receive questions from coordinator via FIFO message transport
      - Execute queries: display image, play audio, invoke agent, record response
      - Capture pre/post device state and app state for verification
      - Return encoded results (audio, image, metadata) to coordinator
    """
    def __init__(self, config_path: str) -> None:
        """Initialize AgentTester with configuration.

        Args:
            config_path: Path to evaluation config JSON.

        Sets up:
          - DeviceManager (type from config: jinju-gemini, s25-gemini-live, etc.)
          - XRClaw state collector (if enabled)
          - PreconditionManager for app state setup
          - ARAP (speaker/recorder) — local ADB or remote Robopod
          - MessagePipes for coordinator communication
          - DisplayServer for showing Jinju screen images
        """
        self.config = JSONFileManager.load_file(config_path)

        self.tc_excecuted = 0
        self.stop_process = False

        device_manager_module = importlib.import_module(DEVICE_MANAGERS[self.config["device_manager_type"]])
        DeviceManager = device_manager_module.DeviceManager

        #define DeviceManager args
        dm_args = []
        for device_name in DeviceManager.get_device_names():
            dm_args.append(self.config["devices"][device_name])
        
        # Handle logger config
        self.dump_logs = self.config["logger"]["dump_device_logs"] #boolean
        self.log_root = self.config["paths"]["root_folder"]
        self.log_folders = {"fixed": os.path.join(self.log_root, "assets"), "tmp": os.path.join(self.log_root, "tmp")}
        for log_folder_type in self.log_folders:
            os.makedirs(self.log_folders[log_folder_type], exist_ok = True)
        dm_args.append(self.log_folders["tmp"])
        dm_args.append(self.config)  # pass full config; each device manager extracts what it needs
        setup_logging(self.config["logger"]["logger_level"], os.path.join(self.log_root, "agent_tester.log"))

        self.device_manager = DeviceManager(*dm_args)

        # Initialize XRClaw verifier if configured
        # The verifier runs on the companion device (the phone running the apps).
        # For S25 setups, this is the s25_device_id. For Jinju, it's the companion (s25_device_id).
        xrclaw_config = self.config.get("xrclaw", {})
        if xrclaw_config.get("enabled", False):
            # Determine which device runs the apps (companion phone)
            xrclaw_device = self.config["devices"].get("s25_device_id", "")
            if xrclaw_device:
                self.device_manager.state_collector = self.device_manager._init_state_collector(
                    xrclaw_config, xrclaw_device
                )
                # Backward compat: keep xrclaw_collector as an alias
                self.device_manager.xrclaw_collector = self.device_manager.state_collector

            else:
                print("Warning: XRClaw enabled but no s25_device_id found in config for XRClaw target device")

        # Initialize precondition manager for app evaluations
        self.precondition_manager = PreconditionManager(
            self.device_manager,
            getattr(self.device_manager, "state_collector", None),
        )

        # set arap configs

        self.use_robohead = self.config["devices"]["arap"]["use_robohead"]

        self.arap_record_duration = self.config["devices"]["arap"]["record_duration"]
        if not self.use_robohead:
            arap_devices = self.config["devices"]["arap"]["devices"]
            assert len(arap_devices) > 0 and len(arap_devices) < 3, "Too less or too many arap devices!"

            self.arap_speaker = ARAPManager(arap_devices[0])
            self.arap_recorder = ARAPManager(arap_devices[-1])
        else:
            robopod_url = self.config["devices"]["arap"]["robopod_url"]
            if not robopod_url:
                raise KeyError("robopod_url cannot be empty if you need to use robopod")
            self.arap_speaker = self.arap_recorder = RobopodManager(robopod_url)
            self.arap_speaker.start_arap()
        self.device_manager.arap_speaker = self.arap_speaker 
        #setup the message service
        self.message_service = MessagePipes(read_path = "/tmp/coordinator_to_agent_tester",
                                            write_path = "/tmp/agent_tester_to_coordinator",
                                            write_first = True
                                            )       
        self.message_service_config = { 
                                    "wait_time": self.config["message_service"]["wait_time"]
                                    }


        #host the display service
        display_port = self.config["urls"]["display_port"]
        self.display_server = DisplayServer()
        logging.info(f"DISPLAY SERVER hosted on port: {display_port}")
        self.display_server_thread = threading.Thread(target = self.display_server.get_app().run, kwargs = {"host": "0.0.0.0", "port": int(display_port)}, daemon = True)
    
    def display_image(self, encoded_image: str) -> None:
        """Display a base64-encoded image on the external monitor.

        Shows the Jinju glasses screen image on an external display for
        real-time monitoring. The image is sent to the DisplayServer which
        serves it via HTTP to a browser-based viewer.

        Args:
            encoded_image: Base64-encoded PNG image data.

        Note:
            TODO: Currently stops previous image before showing new one.
            Consider optimizing to avoid flicker.
        """
        #TODO: Stop showing the previous image and start showing the current image
        logging.info("Waiting for image to be updated on display monitor!")
        self.display_server.set_image_status(None, "stop")
        time.sleep(1)
        self.display_server.set_image_status(encoded_image, "show")
        time.sleep(1)
    
    def send_message(self, payload: dict, current_status: str):
        """Send a request message to the coordinator and wait for response.

        Uses FIFO-based message transport (MessagePipes) to communicate with
        the metric_coordinator. Messages are JSON-encoded with metadata including
        eval_id, message type, status, and payload.

        Args:
            payload: Dict containing evaluation data (or empty for status updates).
            current_status: Current worker status (READY, WAIT, WORK, STOP).

        Returns:
            Tuple of (response_payload, response_status) from coordinator.

        Raises:
            Message validation errors if response is malformed or timeout occurs.
        """
        msg = Message(
            eval_id = payload["eval_id"] if payload else "",
            msg_type = "REQUEST",
            status = current_status,
            payload = json.dumps(payload) if payload else "",
            sender = "agent_tester"
        )

        msg_bytes = json.dumps(msg.get_json()).encode()
        logging.debug(f"Sent request: {msg_bytes}")
        response_bytes = self.message_service.request(payload = msg_bytes, timeout = 10)
        logging.debug(f"Received response: {response_bytes}")
        
        response = json.loads(response_bytes.decode())
        Message.check_response(msg.msg_id, "coordinator", response)

        return response["payload"], response["status"]      
        
    
    def create_payload(self, itr_info: dict) -> dict:
        """Create the evaluation payload to send to the judge worker.

        Encodes audio, Jinju screen image, and optional app screenshot
        (from companion device) to base64 for transmission to the judge.

        Args:
            itr_info: Dict containing evaluation metadata including paths
                     to recorded audio, captured images, and screenshots.

        Returns:
            Payload dict with:
              - eval_id, eval_type, question, question_type, reference
              - encoded_audio: Base64-encoded agent response audio
              - encoded_image: Base64-encoded Jinju screen image
              - encoded_app_screenshot: Base64-encoded phone screenshot (if available)
              - metadata: Full metadata dict for verification

        Note:
            Returns minimal payload with empty encodings if decode failed
            (question should be skipped).
        """
        # Skipped question (base64 decode failed) — return minimal payload
        if not itr_info["metadata"].get("response_path") or not itr_info["metadata"].get("image_path"):
            return {
                "eval_id": itr_info["eval_id"],
                "eval_type": itr_info["eval_type"],
                "question": itr_info["question"],
                "question_type": itr_info["question_type"],
                "reference": itr_info.get("gt_answer", ""),
                "encoded_audio": "",
                "encoded_image": "",
                "encoded_app_screenshot": "",
                "metadata": itr_info["metadata"]
            }

        encoded_audio = Base64Converter.encode_to_base64(itr_info["metadata"]["response_path"])

        # Always encode the Jinju screen image (what the AI saw)
        encoded_image = Base64Converter.encode_to_base64(itr_info["metadata"]["image_path"])

        # If an app screenshot (S25 companion device) was captured, encode it separately
        # so the judge can see both the Jinju screen and the app state on the phone.
        encoded_app_screenshot = ""
        app_screenshot_path = itr_info["metadata"].get("app_screenshot_path")
        if app_screenshot_path and os.path.exists(app_screenshot_path):
            encoded_app_screenshot = Base64Converter.encode_to_base64(app_screenshot_path)["file_base64"]

        payload = {
            "eval_id": itr_info["eval_id"],
            "eval_type": itr_info["eval_type"],
            "question": itr_info["question"],
            "question_type": itr_info["question_type"],
            "reference": itr_info["gt_answer"],
            "encoded_audio": encoded_audio["file_base64"],
            "encoded_image": encoded_image["file_base64"],
            "encoded_app_screenshot": encoded_app_screenshot,
            "metadata": itr_info["metadata"]
        }
        
        return payload


    def execute(self, question_info: str) -> dict:
        """Execute a single evaluation query.

        Full execution pipeline for one question:
          1. Start ARAP (Audio Recording and Playback) services
          2. Decode question data (image, audio) from base64
          3. Display Jinju screen image on external monitor
          4. Capture PRE-state (device info, XRClaw app state)
          5. Set up preconditions (app state, device settings)
          6. Invoke AI agent via DeviceManager
          7. Play query audio through ARAP speaker
          8. Play consent/affirmation audio (if required by app rules)
          9. Record agent's spoken response via ARAP recorder
          10. Capture POST-state (device info, app meta, logs)
          11. Reset media volume (for volume queries)
          12. Return enriched question_info with all metadata

        Args:
            question_info: JSON string containing:
                - eval_id, eval_type, question, question_type
                - image: Base64-encoded Jinju screen
                - audio: Base64-encoded query audio
                - audio_duration: Duration in seconds
                - gt_answer: Ground truth answer

        Returns:
            Enriched question_info dict with metadata including:
                - image_path, audio_raw_path, response_path
                - device_info_pre/post, app_state
                - extra_logs (logcat, screenshots)
                - precondition_report, jinju_image_captured flag
        """
        
        ## Start Arap services
        self.arap_speaker.start_arap()
        self.arap_recorder.start_arap()

        ## Decode question data
        
        question_info = json.loads(question_info)
        question_info["metadata"] = {}

        eval_id = question_info["eval_id"].replace('q', '')

        # Create per-query subfolder: assets/q{eval_id}/
        query_dir = os.path.join(self.log_folders["fixed"], f"q{eval_id}")
        os.makedirs(query_dir, exist_ok=True)

        encoded_image = question_info["image"]
        question_info["metadata"]["image_path"] = os.path.join(query_dir, f"image_{eval_id}.png")
        try:
            Base64Converter.decode_to_file(encoded_image, question_info["metadata"]["image_path"])
        except Exception as e:
            print(f"Warning: Failed to decode image for {eval_id}: {e} — skipping this question.")
            question_info["metadata"]["image_path"] = None
            question_info["metadata"]["audio_raw_path"] = None
            question_info["metadata"]["response_path"] = None
            return question_info

        encoded_audio = question_info["audio"]
        audio_duration = float(question_info["audio_duration"])
        question_info["metadata"]["audio_raw_path"] = os.path.join(query_dir, f"audio_{eval_id}.wav")
        Base64Converter.decode_to_file(encoded_audio, question_info["metadata"]["audio_raw_path"])
        
        response_filename = f"response_{eval_id}.mp3"            
        response_path = os.path.join(query_dir, response_filename)
        
        qt = QuestionType.parse(question_info.get("question_type", ""))

        
        ## TODO: For app evaluation we can remove the blank images from the dataset
        ## WIll save 2-3 seconds if no image has to be set on display server
        if question_info["metadata"].get("image_path"):
            self.display_image(encoded_image)
            
        # Set current question type on device manager for query-type-driven logcat profile selection
        self.device_manager.current_question_type = question_info.get("question_type", "")

        time.sleep(2)
        if self.dump_logs:
            self.device_manager.logger()

       
        ## FOR APP EVAL TASK:
        # - First reset the global device state
        # - Apply app specific conditions
        # - Capture PRE-state before task execution 

        if question_info["eval_type"] == "APP_EVAL_TASK":
            global_reset_report = self.device_manager.reset_device_to_default_state()
            question_info["metadata"]["global_reset_report"] = global_reset_report

            self.device_manager.capture_device_info(question_info, capture_type="pre")

            print(f"Device info pre captured: {list(question_info['metadata'].get('device_info_pre', {}).keys())}")


            # ── Set up preconditions before invoking the agent ──────
            # This creates required device state (e.g., a note to delete,
            # media playing to pause, known volume level for up/down tests)
            # so the agent has something to act on.
            precond_report = self.precondition_manager.setup(question_info)
            if not precond_report["passed"]:
                print(f"WARNING: Precondition failed for {question_info.get('eval_id')}: "
                                    f"{precond_report.get('failed', [])}")
                # Declared state we couldn't build: don't score the agent on a broken setup.
                if question_info.get("setup"):
                    question_info["metadata"]["skip"] = True
                    question_info["metadata"]["skip_reason"] = f"precondition_failed: {precond_report['failed']}"
            elif precond_report.get("set"):
                print(f"Preconditions set: {precond_report['set']}")


            # Snapshot XRClaw app state (notes/reminders/calendar/alarms lists) pre-invoke
            # so verification can diff pre vs post instead of a stale-match-prone
            # existence check. See DeviceManagerTemplate.capture_xrclaw_pre_state.
                      
            self.device_manager.capture_xrclaw_pre_state(question_info) 
            question_info["metadata"]["precondition_report"] = precond_report

            # Capture PRE-state screenshot AFTER preconditions, BEFORE Gemini invoke
            self.device_manager.capture_pre_state_meta_info(question_info)

        ## Setup companion device connectivity based on question type (offline/disconnected/online)
        ## before invoking the agent, to reduce delay inside invoke().
        self.device_manager.set_connectivity(qt.connectivity)

        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        live_device = getattr(self.device_manager, "live_device", None)
        events = None

        if question_info["metadata"].get("skip"):
            response_path = None  # judge_worker short-circuits on metadata["skip"]
        elif live_device:
            # Gemini Live: react to the agent's own turn events instead of fixed sleeps.
            events = LogcatEvents(live_device)  # before invoke, so no event is missed
            self.device_manager.invoke(question_info)
            question_info["metadata"]["conversation"] = run_conversation(
                events, self.arap_speaker, self.arap_recorder, question_info, query_dir, eval_id,
                response_path, self.config["urls"]["transcription_url"], self.arap_record_duration, assets_dir)
        else:
            ## Inovokes execution of agent tester for the given question
            self.device_manager.invoke(question_info)

            self.arap_speaker.play_audio(question_info["metadata"]["audio_raw_path"])
            time.sleep(audio_duration) # Wait for the question audio duration

            self.arap_recorder.start_recording(response_filename)

            # ── Play consent/affirmation audio ────────────────────────
            # Delegates to consent_player which reads CONSENT_RULES from the
            # app registry. Adding a new consent case = one dict entry in the
            # app's consent.py, not an if/elif chain here.
            play_consent(self.device_manager, qt, assets_dir)

            time.sleep(self.arap_record_duration)
            self.arap_recorder.stop_recording(response_path)
        question_info["metadata"]["response_path"] = response_path

        if question_info["eval_type"] == "APP_EVAL_TASK":
            try:
                self.device_manager.capture_post_state_meta_info(question_info)
            except Exception as e:
                print(f"Warning: capture_post_state_meta_info failed: {e}")
                import traceback; traceback.print_exc()


        if self.dump_logs:
            extra_logs = self.device_manager.logger()
            if extra_logs:
                # Merge extra_logs into app_state.log_analysis (unified state channel)
                app_state = question_info["metadata"].get("app_state", {})
                if not isinstance(app_state, dict):
                    app_state = {}
                app_state["log_analysis"] = extra_logs
                question_info["metadata"]["app_state"] = app_state
                # Keep extra_logs for backward compat (report generator, dashboard)
                question_info["metadata"]["extra_logs"] = extra_logs
            
            # Move all files from tmp/ to per-query subfolder: assets/q{eval_id}/
            # Files are renamed with an eval_id suffix (e.g., jinju_log.txt →
            # q00001/jinju_log_q00001.txt) so every artifact keeps the eval id
            # in its filename. Files that already carry the eval_id (e.g.
            # device_info_pre_q00001.json) are not suffixed again.
            from pathlib import Path
            tmp_dir = Path(self.log_folders["tmp"])
            query_dst = Path(query_dir)
            
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    src_path = Path(root) / file
                    # Calculate relative path from tmp_dir to preserve directory structure
                    rel_path = src_path.relative_to(tmp_dir)
                   
                    # Create destination directory structure within query folder
                    dst_dir = query_dst / rel_path.parent
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    # Suffix filename with eval_id (skip if already present)
                    file_stem, file_ext = os.path.splitext(file)
                    if eval_id not in file_stem:
                        file_stem = f"{file_stem}_{eval_id}"
                    dst_path = dst_dir / f"{file_stem}{file_ext}"
                    # Move file
                    shutil.move(str(src_path), str(dst_path))
                    # Store metadata path - use relative path components for key
                    # Key is derived from the ORIGINAL stem (without eval_id) so
                    # downstream consumers (e.g. jinju_log_path) stay stable
                    # e.g., "screenshot.png" -> "screenshot_path"
                    orig_stem, _ = os.path.splitext(file)
                    path_key_parts = list(rel_path.parent.parts) + [orig_stem]
                    metadata_key = "_".join(path_key_parts) + "_path"
                    question_info["metadata"][metadata_key] = str(dst_path)

        time.sleep(5)

        self.arap_speaker.stop_arap()
        self.arap_recorder.stop_arap()
        time.sleep(2)
        
        self.device_manager.terminate()
        if events:
            question_info["metadata"]["conversation"]["session_closed"] = bool(
                events.wait_for({"session_end"}, SESSION_END_S))
            events.close()

        if self.tc_excecuted % 50 == 49 and self.tc_excecuted > 0:
            time.sleep(300)
        self.tc_excecuted += 1

        return question_info
    
    def client_server(self):
        """Main client-server loop for coordinator communication.

        Runs a state machine that:
          - READY: Announces readiness, waits for work
          - WAIT: Pauses between queries (configurable wait_time)
          - WORK: Executes query via execute(), sends payload to coordinator
          - STOP: Exits the loop and terminates

        The loop continues until receiving a STOP status from the coordinator.
        Each WORK cycle executes one evaluation query and returns results.
        """
        self.device_manager.terminate()
        self.display_server_thread.start()  # start the display server
        time.sleep(1)

        current_status = "READY"
        question = ""

        while not self.stop_process:
            payload = {}

            match(current_status):
                case "READY":
                    logging.info("Agent tester is ready!")

                case "WAIT":
                    time.sleep(self.message_service_config["wait_time"])

                case "WORK":
                    evaluation_info = self.execute(question)
                    payload = self.create_payload(evaluation_info)
                    logging.info("------Submitting for Evaluation-------")

                case "STOP":
                    self.stop_process = False
                    break

                case _:
                    raise NotImplementedError

            question, current_status = self.send_message(payload, current_status)


if __name__ == "__main__":
    config_path = "configs/config_template.json"
    if len(sys.argv) > 1:
       print(f"Config path set to {sys.argv[1]}")
       config_path = sys.argv[1]
    if os.environ.get("PIPELINE_TRACE"):
        from utils.trace_injection import install_tracing
        install_tracing(config_path)
    agent_tester = AgentTester(config_path)
    agent_tester.client_server()
