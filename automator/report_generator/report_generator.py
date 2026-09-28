import shutil, subprocess, sys, os, json
import numpy as np
from fireredvad import FireRedVad, FireRedVadConfig

from automator.report_generator.utils.render_summary import SummaryRenderer
from automator.report_generator.utils.render_report import render_part_html
from automator.report_generator.report_writer import VQASample, VQADatasetWriter, QueueDBReader, MediaEncoder
from utils.file_utils import JSONLFileManager
from apps.judge_helpers import get_flag
from common.question_type import QuestionType

class ReportGenerator:
    def __init__(self, input_db_path):
        self.out_path = input_db_path.rsplit("/", 1)[0]
        self.writer = VQADatasetWriter(version="1.0.0")
        
        db_reader = QueueDBReader(db_path=input_db_path)
        self.entries = db_reader.fetch_all()
        self.bad_counts = 0
        self.error_codes = {
            0: "no_error",
            1: "empty_response",
            2: "not_english",
            3: "judge_response_decode_error"
        }
        
        vad_config = FireRedVadConfig(use_gpu=False, smooth_window_size=5, speech_threshold=0.4, min_speech_frame=20, max_speech_frame=2000, min_silence_frame=20, merge_silence_frame=0, extend_speech_frame=0, chunk_max_frame=30000)
        self.fire_vad = FireRedVad.from_pretrained("data/models/fireredvad/pretrained_models/FireRedVAD/VAD", vad_config)

        os.makedirs("data/maire_tmp", exist_ok = True)

    def clip_response(self, audio_path, cleaned_audio_path):
        tmp_audio_path = "data/maire_tmp/tmp.wav"
        if os.path.exists(tmp_audio_path):
            os.remove(tmp_audio_path)
        if os.path.exists(cleaned_audio_path):
            os.remove(cleaned_audio_path)
            
        command = f"ffmpeg -y -i {audio_path} -ar 16000 -ac 1 -acodec pcm_s16le -f wav {tmp_audio_path}"
        conversion_status = os.system(command)
        result, probs = self.fire_vad.detect(tmp_audio_path)
        if result["timestamps"] == []:
            shutil.copy(audio_path, cleaned_audio_path)
            return None, None
        else:       
            start = result["timestamps"][0][0]; end = result["timestamps"][-1][-1]
            subprocess.call(['ffmpeg', '-y', '-i', audio_path, '-ss', str(start), '-t', str(end), cleaned_audio_path])
            return np.round(start, 3), np.round((end - start), 3)        
                
    def generate_json_report(self, append_to_existing: bool = False):
        """
        Generate JSON report from queue entries.

        Args:
            append_to_existing: If True, append new entries to existing vqa_report.jsonl.
                               The automator should have already removed entries for re-evaluated qids.
                               Raises error if any eval_id from queue already exists in report.
        """
        question_types = {}

        # Load existing entries if append mode is enabled
        existing_entries = []
        existing_header = None
        vqa_report_path = f"{self.out_path}/vqa_report.jsonl"

        if append_to_existing:
            if not os.path.exists(vqa_report_path):
                raise FileNotFoundError(f"vqa_report.jsonl not found at {vqa_report_path}. Cannot append to non-existing report.")
            existing_header, existing_entries = JSONLFileManager.load_file(vqa_report_path)
            print(f"Loading {len(existing_entries)} existing entries for appending")

        # Build set of existing eval_ids to check for duplicates
        existing_eval_ids = set(entry["eval_id"] for entry in existing_entries)

        # Collect new eval_ids from queue
        new_eval_ids = set()
        for row in self.entries:
            eval_json = json.loads(row["eval_json"])
            new_eval_ids.add(eval_json["eval_id"])

        # Check for duplicates - if any new eval_id exists in report, automator didn't clean up properly
        if append_to_existing:
            duplicates = existing_eval_ids.intersection(new_eval_ids)
            if duplicates:
                raise ValueError(f"Duplicate eval_ids found: {duplicates}. Automator should have removed these entries before re-evaluation.")

        for row in self.entries:
            eval_json = json.loads(row["eval_json"])
            result_json = json.loads(row['result_json'].split("<meta_start>")[1].replace("<meta_end>", ""))
            judge_response = row['result_json'].split("<meta_start>")[0]
            eval_id = eval_json["eval_id"]

            meta_info = {**eval_json["metadata"]}
            meta_info["error_type"] = self.error_codes[int(result_json["error_type"])]
            meta_info["entropy_metrics"] = result_json["entropy_metrics"]
            meta_info["judge_method"] = result_json.get("judge_method", "vlm")


            # Skip entries that were skipped by agent_tester (no response audio recorded)
            # or that crashed before response_path was set.
            if meta_info.get("skip") or not meta_info.get("response_path"):
                print(f"Skipping entry {eval_id}: no response_path (skipped={meta_info.get('skip', False)})")
                continue

            # Derive cleaned audio path from the response basename (robust for both
            # old "response.mp3" and new "response_{eval_id}.mp3" naming)
            response_dir = os.path.dirname(meta_info["response_path"])
            response_name = os.path.basename(meta_info["response_path"])
            cleaned_audio_path = os.path.join(
                response_dir, response_name.replace("response", "cleaned_response")
            )
            
            response_time, response_duration = self.clip_response(meta_info["response_path"], cleaned_audio_path)

            question_duration = MediaEncoder.get_audio_duration(meta_info["audio_raw_path"])
            meta_info["question_audio_duration"] = question_duration
            
            question = eval_json["question"]
            gt_answer = eval_json["reference"]            
            question_type = eval_json["question_type"]
            meta_info["question_type"] = question_type

            
            judgement = {"question" : eval_json["question"], 
                            "analysis": None , 
                            "rating" : None }

            ai_response = None
            if  meta_info["error_type"] == "no_error":
                if result_json["duration"] <= 0:
                    response_time = response_duration = None
                else:
                    response_time = response_time if(response_time) else result_json["response_time"]
                    response_duration = response_duration if(response_duration) else result_json["duration"]
                
                ai_response = result_json["answer"]

                if "<think>" in judge_response:
                    judge_string = judge_response.split("</think>")[-1].replace("```json", "").replace("```", "").split("<meta_start>")[0].strip()
                elif "◁/think▷" in judge_response:
                    judge_string = judge_response.split("◁/think▷")[-1].strip().replace("```", "").split("<meta_start>")[0].strip()
                else:
                    judge_string = judge_response.replace("```json", "").replace("```", "").split("<meta_start>")[0].strip()
                try:
                    judgement = json.loads(judge_string)
                    judgement["rating"] = int(judgement["rating"])
                    judgement["analysis"] = judgement["analysis"]
                except:
                    meta_info["error_type"] = "judge_response_decode_error"
                    self.bad_counts += 1
            else:
                response_time = response_duration = None

            # Extract grounding info for validation display in report
            grounding_info = self._extract_grounding_info(meta_info)

            self.writer.add_sample(VQASample(eval_id = eval_id, original_image_path = meta_info["image_path"], 
                screen_path = meta_info.get("device_view_image_path", ""), image_path = meta_info["image_path"], 
                audio_path = cleaned_audio_path, question = question, gt_answer = gt_answer, question_type = question_type, 
                ai_response = ai_response, rating = judgement["rating"], reason = judgement["analysis"], 
                response_time = response_time, response_duration = response_duration, eval_type = eval_json["eval_type"], error_type = meta_info["error_type"], 
                meta_info = meta_info, grounding_info = grounding_info, judge_method = meta_info["judge_method"]))


            
        self.writer.write(f"{self.out_path}/vqa_report.jsonl", append_to_existing=append_to_existing)
        
        
    
    
    def _extract_grounding_info(self, meta_info: dict) -> dict:
        """Extract grounding/validation info from meta_info for report display.

        Uses question_type to route only the relevant data:
        - device_* queries: only the relevant device feature (battery/volume/etc.)
        - app queries (samsung/google/thirdparty): only XRClaw app_state
        - camera queries: only capture flags
        - notification queries: XRClaw app_state (notifications list) + screenshot
        """
        grounding = {}

        qt = QuestionType.parse(meta_info.get("question_type", ""))
        group, feature, action = qt.group, qt.feature, qt.action

        # ── State collector result (for all app + notification queries) ──
        app_state = meta_info.get("app_state") or {}
        if app_state.get("method"):
            grounding["app_state"] = {
                "verified": app_state.get("verified"),
                "rating": app_state.get("rating"),
                "analysis": app_state.get("analysis"),
                "method": app_state.get("method"),
                "actual_state": app_state.get("actual_state"),
            }

        # ── Device state (ONLY for device_* queries) ──
        # The device_info structure is: {"jinju": {...}, "companion": {...}}
        # By default we read from "jinju". Only for battery_companion do we
        # read from "companion".
        if group == "device":
            for when in ("pre", "post"):
                key = f"device_info_{when}"
                state = meta_info.get(key, {})
                if not state:
                    continue

                # Select jinju or companion based on query
                is_companion = (feature == "battery" and action == "companion")
                device_data = state.get("companion", {}) if is_companion else state.get("jinju", {})

                # Only include the relevant feature
                relevant = {}
                if feature == "battery" and device_data.get("battery"):
                    relevant["battery"] = device_data["battery"]
                elif feature == "volume" and device_data.get("volume"):
                    relevant["volume"] = device_data["volume"]
                elif feature == "datetime":
                    if device_data.get("time"):
                        relevant["time"] = device_data["time"]
                    if device_data.get("date"):
                        relevant["date"] = device_data["date"]
                elif feature == "dnd" and device_data.get("dnd_mode") is not None:
                    relevant["dnd_mode"] = device_data.get("dnd_mode")
                elif feature == "mediacontrol" and device_data.get("media"):
                    relevant["media"] = device_data["media"]
                # notification: no device state — XRClaw app_state + screenshot handle it

                if relevant:
                    grounding[f"device_{when}"] = relevant

        # ── Camera/video flags (ONLY for camera queries) ──
        if group == "samsung" and feature == "camera":
            grounding["image_captured"] = get_flag(meta_info, "jinju_image_captured")
            grounding["video_captured"] = get_flag(meta_info, "jinju_video_captured")

        # ── Log analysis flags (filtered, for all queries) ──
        filtered = {k: v for k, v in (app_state.get("log_analysis") or {}).items()
                    if k not in ("jinju_image_captured", "jinju_image_path")}
        if filtered:
            grounding["log_analysis"] = filtered

        return grounding



    def render_report_func(self, out_dir):
        renderer = SummaryRenderer(jsonl_path = f"{self.out_path}/vqa_report.jsonl", output_dir = out_dir)

        renderer.write_report()
        jsonl_path = f"{self.out_path}/vqa_report.jsonl"
        header, samples = renderer.load_jsonl(jsonl_path)
        chunk_size = 200
        for start in range(0, len(samples), chunk_size):
            output_path = f"{out_dir}/report_visual_{start}_to_{start+chunk_size}.html"
            print("rendering", output_path)
            render_part_html(header, samples[start:start+chunk_size], output_path)
        # shutil.rmtree("maire_tmp")
    
    def generate_summary_func(self, out_dir):
        self.generate_json_report()
        self.render_report_func(out_dir)
        
        
