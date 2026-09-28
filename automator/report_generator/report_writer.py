import json, os, time, random, io, subprocess
import wave
import contextlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Literal, Optional, Union, Any

from utils.file_utils import Base64Converter

    
class QueueDBReader:
    def __init__(self, db_path: str = "queue.db"):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def fetch_all(
        self,
        conditions: Dict = {},
        limit: Optional[int] = None,
        order: Literal = "desc"
    ) -> List[Dict[str, Any]]:
        query = '''
            SELECT id, question, eval_json, status, result_json, created_at
            FROM metric_queue
        '''
        params = []

        for c_type, c_value in conditions.items():
            if query[-1] != '?':
                query += f" WHERE {c_type} {c_value[0]} ?"
                params.append(c_value[1])
            else:
                query += f" AND {c_type} {c_value[0]} ?"
                params.append(c_value[1])

        query += f" ORDER BY created_at {order.upper()}"

        if limit:
            query += " LIMIT ?"
            params.append(order)
        print(query)
        with self._connect() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: tuple) -> Dict[str, Any]:
        request_id, question, eval_json, status, result_json, created_at = row
        return {"id": request_id, "question": question, "eval_json": eval_json, "status": status, 
            "result_json": result_json, "created_at": created_at, "created_at_readable": datetime.fromtimestamp(created_at).isoformat()}

    def to_json(self, rows: List[Dict[str, Any]]) -> str:
        return json.dumps(rows, indent=2)    


class MediaEncoder:
    """Handles encoding of image and audio data."""

    @staticmethod
    def get_audio_duration(audio_path: Union[str, Path]) -> float:
        try:
            with contextlib.closing(wave.open(str(audio_path).replace(".mp3", ".wav"), 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return round(frames / float(rate), 3)
        except:
            return 0


    @staticmethod
    def get_video_duration(video_path: Union[str, Path]) -> float:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        info = json.loads(result.stdout)
        duration = info['format'].get('duration', None)
        return float(duration)



class VQASample:
    """Represents a single VQA sample with encoded media."""
    def __init__(self, eval_id: str, original_image_path: Union[str, Path], image_path: Union[str, Path], 
        screen_path: Union[str, Path], audio_path: Union[str, Path], question: str, gt_answer: str, question_type: str, 
        ai_response: str, rating: float, reason: str, response_time: float, response_duration: float, eval_type: str, error_type: str, meta_info: dict,
        grounding_info: dict = None, judge_method: str = "vlm"):

        self.eval_id = eval_id
        self.original_image_path = original_image_path; self.image_path = image_path; self.audio_path = audio_path
        self.question = question; self.gt_answer = gt_answer; self.question_type = question_type
        self.rating = rating; self.reason = reason; self.response_time = response_time; self.response_duration = response_duration
        self.ai_response = ai_response; self.error_type = error_type
        self.image_bytes = Base64Converter.encode_to_base64(self.image_path)["file_base64"] if os.path.exists(self.image_path) else ""
        # NOTE: no trailing comma — a tuple here breaks the template's typeof check
        self.screen_bytes = Base64Converter.encode_to_base64(screen_path)["file_base64"] if os.path.exists(screen_path) else ""
        self.audio_bytes = Base64Converter.encode_to_base64(self.audio_path)["file_base64"] if os.path.exists(self.audio_path) else ""
        self.eval_type = eval_type; self.meta_info = meta_info
        self.grounding_info = grounding_info or {}
        self.judge_method = judge_method


        # Encode pre-state screenshots (for human interpretability)
        self.pre_screenshot_bytes_list = []
        pre_screenshots = meta_info.get("pre_state_screenshots", [])
        for ss_path in pre_screenshots:
            if os.path.exists(ss_path):
                self.pre_screenshot_bytes_list.append(Base64Converter.encode_to_base64(ss_path)["file_base64"])

        # Encode post-state screenshots (for judge - primary evidence)
        self.post_screenshot_bytes_list = []
        post_screenshots = meta_info.get("post_state_screenshots", [])
        for ss_path in post_screenshots:
            if os.path.exists(ss_path):
                self.post_screenshot_bytes_list.append(Base64Converter.encode_to_base64(ss_path)["file_base64"])

        # Single app screenshot (base64 or empty string) for the template's legacy block
        self.app_screenshot_bytes = self.post_screenshot_bytes_list[0] if self.post_screenshot_bytes_list else ""

    def to_dict(self) -> dict:
        return {"eval_id": self.eval_id, "image": self.image_bytes, "audio": self.audio_bytes, "screen": self.screen_bytes,
            "pre_state_screenshots": self.pre_screenshot_bytes_list,  # List of base64 strings
            "post_state_screenshots": self.post_screenshot_bytes_list,  # List of base64 strings (for judge)
            "app_screenshot": self.app_screenshot_bytes,  # Single base64 string (legacy fallback)
            "image_path": self.original_image_path, "question": self.question, "gt_answer": self.gt_answer, 
            "question_type": self.question_type, "ai_response": self.ai_response, "rating" : self.rating, "reason" : self.reason, 
            "response_time" : self.response_time, "response_duration": self.response_duration, "eval_type": self.eval_type, "error_type" : self.error_type, 
            "manual_verification": False, "meta_info" : self.meta_info, "grounding_info": self.grounding_info,
            "judge_method": self.judge_method}




class VQADatasetWriter:
    """Generates a JSONL dataset file for evaluating VQA agents."""
    def __init__(self, version: str = "1.0.0"):
        self.version = version
        self.samples: List[VQASample] = []

    def add_sample(self, sample: VQASample):
        self.samples.append(sample.to_dict())

    def write(self, output_path: Union[str, Path], append_to_existing: bool = False):
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        header = {
            "version": self.version,
            "fields": {
                "eval_id": "Unique identifier for the QA pair", "image": "Base64-encoded image (e.g. PNG or JPEG)", 
                "audio": "Base64-encoded audio (e.g. WAV)", "screen": "Image seen by tester device",
                "image_path": "Original image path", "question": "Text transcription of the question", "gt_answer": "Ground-truth answer", 
                "question_type": "Type/category of question (e.g., Object Recognition, Spatial Understaning)",
                "ai_response": "Text transcription of AI's response", "rating": "Rating of AI's response on Likert scale", 
                "reason": "Reasoning for the rating awarded", "response_time": "Time taken by AI to respond", "response_duration": "Duration of AI's response",
                "eval_type": "Type of Evaluation Task (e.g. QA Task, or, VQA Task)", "error_type": "Error type seen during evaluation",
                "manual_verification": "Was human intervention needed for rating/analysis", "meta_info": "extra information",
                "app_screenshot": "Base64-encoded app screenshot from companion device (for APP_EVAL_TASK)",
                "grounding_info": "Extracted grounding/validation info (XRClaw state, device state, camera flags)",
                "judge_method": "Which judge was used: 'deterministic' or 'vlm'"}


        }

        # Choose mode based on append_to_existing
        mode = "a" if append_to_existing else "w"

        with output_file.open(mode, encoding="utf-8") as f:
            # Only write header when NOT appending (fresh file)
            if not append_to_existing:
                f.write(json.dumps(header) + "\n")
            for sample in self.samples[::-1]:
                f.write(json.dumps(sample) + "\n")
