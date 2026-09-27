from openai import OpenAI
from judge_worker.judge_prompts import *
from judge_worker.judge_response_parser import parse_judge_response
from judge_worker.device_info_filter import filter_device_info
import requests
import json, re
import logging
import os
import warnings
from collections import Counter

from judge_worker.entropy import HallucinationScorer
from judge_worker.deterministic_judge import DeterministicJudge
from utils.file_utils import *


class ResponseScorer:
    def __init__(self, transcription_url: str, judge_url: str, rating_rectifier_url: str, device_type: str, judge_config: dict):
        # setup judge
        self.judge = OpenAI(
            api_key="EMPTY",
            base_url=judge_url,
        )

        hosted_models = self.judge.models.list().data  # raises if the judge server is down
        assert hosted_models, f"No hosted models at {judge_url}"
        self.model_id = hosted_models[0].id
        self.use_vllm_apis = judge_config["vllm_api"]
        self.eval_type_to_prompt = {
            "Visual_QA_TASK": [vqa_prompt[prompt_version] for prompt_version in judge_config["vqa_prompt_version"]],
            "Hallucination_TASK": [hallucination_vqa_prompt[prompt_version] for prompt_version in judge_config["hqa_prompt_version"]],
            "QA_TASK": [qa_prompt[prompt_version] for prompt_version in judge_config["qa_prompt_version"]],
            "APP_EVAL_TASK": [app_eval_prompt[prompt_version] for prompt_version in judge_config["appEval_prompt_version"]]
        }

        #setup transcription
        response = requests.get(f"{transcription_url}/health/")
        assert response.status_code == 200, "Transcription server is not running!"
        self.transcription_url = transcription_url

        # setup rating rectifier
        self.rating_rectifier_url = rating_rectifier_url.rstrip("/") if rating_rectifier_url else ""
        self.device_type = device_type

        self.metric_scorer = HallucinationScorer()


    def __rating_rectifier_health(self) -> bool:
        """Check if the rating rectifier server is up. Returns True if healthy, False otherwise.
        Shows a warning if the server is not reachable."""
        if not self.rating_rectifier_url:
            warnings.warn("Rating rectifier URL is not configured.")
            return False
        try:
            response = requests.get(f"{self.rating_rectifier_url}/health", timeout=5)
            if response.status_code == 200:
                return True
            else:
                warnings.warn(f"Rating rectifier server returned status {response.status_code}.")
                return False
        except requests.exceptions.RequestException as e:
            warnings.warn(f"Rating rectifier server is not reachable: {e}")
            return False

    def __create_dummy_response_object(self, question, analysis, rating) -> object:
        class DummyResponse:
            def __init__(self, data):
                for key, value in data.items():
                    if isinstance(value, dict):
                        value = DummyResponse(value)
                    elif isinstance(value, list):
                        value = [DummyResponse(v) if isinstance(v, dict) else v for v in value]
                    setattr(self, key, value)

        dummy_response = {'choices': [
                                {
                                    'index': 0,
                                    'message': {
                                        'role': 'assistant',
                                        'content': "{'question': '" + question + "','analysis': '" + analysis + "','rating': '" + rating + "'}",
                                    },

                                    'logprobs':{
                                        'content': [{
                                            'top_logprobs': [{'logprob': 0, 'token': '0'}],
                                            'token': '0'
                                        }]
                                    }
                                }
                            ]
                        }
        return DummyResponse(dummy_response)

    def __get_rating_and_analysis(self, judge_response_content: str):
        """Extract analysis and rating from judge response using the robust parser.

        Delegates to ``parse_judge_response()`` which handles JSON, markdown-fenced
        JSON, Python dict reprs (single quotes), and plain text fallbacks.
        """
        return parse_judge_response(judge_response_content)


    def __get_entropy_metrics(self, response_object: object):
        count = 0
        logprobs = response_object.choices[0].logprobs
        scores_final = {
            "entropy": 0.0,
            "surprisal": 0.0,
            "curvature": 0.0,
            "entropy_delta": 0.0,
        }
        for entry in logprobs.content:
            if entry == None:
                continue
            top_lp = {t.token : t.logprob for t in entry.top_logprobs}
            scores = self.metric_scorer.score(top_lp, entry.token)
            for key, value in scores.items():
                scores_final[key] += value
            count += 1
        for i, j in scores_final.items():
            scores_final[i] = j / count
        return scores_final

    def __find_consensus(self, prompt_response_list: list) -> (str, object, str):
        # Extract ratings from all prompt responses
        rating_list = []
        for idx, _response in enumerate(prompt_response_list):
            response, entropy_metrics, _prompt = _response
            analysis, rating = self.__get_rating_and_analysis(response)
            rating_list.append(rating)


        # Filter out None ratings
        valid_ratings = [r for r in rating_list if r is not None]

        if not valid_ratings:
            # Fallback: return the first response if no valid ratings
            return prompt_response_list[0]

        # Find mode using Counter
        rating_counts = Counter(valid_ratings)
        max_count = max(rating_counts.values())

        # Get all ratings that share the maximum frequency (mode winners)
        mode_winners = sorted([r for r, c in rating_counts.items() if c == max_count])

        if len(mode_winners) == 1:
            # Clear winner: use the mode directly
            final_rating = mode_winners[0]
        else:
            # No clear winner: find the integer median of the mode winners
            n = len(mode_winners)
            if n % 2 == 1:
                final_rating = mode_winners[n // 2]
            else:
                # For even number of mode winners, take the lower mid element
                # (integer median floor for even count)
                final_rating = mode_winners[n // 2 - 1]

        # Find the element of prompt_response_list whose rating is closest to final_rating
        # In case of tie, choose the first one
        best_idx = None
        best_dist = float('inf')
        for idx, rating in enumerate(rating_list):
            if rating is None:
                continue
            dist = abs(rating - final_rating)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx is None:
            # Fallback: return the first response
            return prompt_response_list[0]

        return prompt_response_list[best_idx]


    # ── Prompt resolution helpers (extracted from run_judge) ──────────

    def _resolve_app_eval_prompt(self, prompt_set, question_type, device_info,
                                  device_info_pre, eval_json):
        """Resolve the correct prompt template for an APP_EVAL_TASK.

        Handles:
        - 4-part question_type parsing → app_name + app_mode
        - Compound features (clock_timer, clock_alarm)
        - Notification redirect to dedicated prompt
        - Callable device lambda (with filtered device_info)
        - Mode-specific dict prompts
        - Legacy string prompts
        - Fallback to generic QA prompt

        Returns the resolved prompt string.
        """
        from apps import get_app_key

        app_name = get_app_key(question_type) or ""

        # Extract action (app_mode) from the 4-part format
        parts = question_type.lower().split("_")
        app_mode = parts[3] if len(parts) >= 4 else ""
        # For compound features (e.g. clock_timer), action is parts[4]
        if len(parts) >= 5:
            from apps import APP_CONFIGS
            group_config = APP_CONFIGS.get(parts[1], {})
            if f"{parts[2]}_{parts[3]}" in group_config:
                app_mode = parts[4] if len(parts) >= 5 else ""

        # For device_notifications queries, use the dedicated "notifications" prompt
        if app_name in ("device", "notification") and "notification" in question_type.lower():
            app_name = "notifications"

        # Check if prompt structure is mode-specific (dict) or legacy (string)
        if app_name not in prompt_set:
            print(f"Warning: No judge prompt defined for app '{app_name}' (question_type='{question_type}'). Falling back to generic QA prompt.")
            logging.warning(f"No judge prompt defined for app '{app_name}' (question_type='{question_type}'). Falling back to generic QA prompt.")
            return qa_prompt["1.0"]

        app_prompt = prompt_set[app_name]
        if isinstance(app_prompt, dict):
            # Mode-specific prompt structure
            resolved = "".join(app_prompt.get(app_mode, ""))
            if not resolved:
                print(f"Warning: No prompt defined for mode '{app_mode}' in app '{app_name}'")
            return resolved
        elif callable(app_prompt):
            # Lambda function prompt (e.g., device prompt with formatted device_info)
            # Use filtered device_info instead of full JSON dump
            device_info_xml = filter_device_info(device_info, question_type) or "{}"
            device_info_pre_xml = filter_device_info(device_info_pre, question_type) if device_info_pre else None

            # For volume queries, append a diff summary of changed channels
            if device_info_pre and device_info_pre_xml is not None:
                from judge_worker.device_info_filter import _get_feature, format_volume_diff
                if _get_feature(question_type) == "volume":
                    diff_xml = format_volume_diff(device_info_pre, device_info)
                    if diff_xml and "</device_state>" in device_info_xml:
                        device_info_xml = device_info_xml.replace(
                            "</device_state>", f"  {diff_xml}\n</device_state>"
                        )

            return app_prompt(device_info_xml, device_info_pre_xml, question_type)
        else:
            # Legacy prompt structure (same prompt for all modes)
            return "".join(app_prompt)

    def _inject_placeholders(self, prompt, question, ai_response, gt_answer,
                              question_type, eval_type, eval_json):
        """Replace all placeholder tokens in the prompt with actual values.

        Handles: <<question>>, <<ai_response>>, <<gt_answer>>, <<category>>,
        <<app_state>> — the unified state channel that includes state collector
        results, log analysis flags (image_captured, video_captured, liked,
        disliked, etc.), and any other device/app state.
        """
        prompt = prompt.replace("<<question>>", question) \
                       .replace("<<ai_response>>", ai_response) \
                       .replace("<<gt_answer>>", gt_answer) \
                       .replace("<<category>>", question_type)

        # Per-turn user line + live agent transcript (Gemini Live conversation loop)
        turns = ((eval_json or {}).get("metadata", {}).get("conversation") or {}).get("turns", [])
        conversation = [{"user": t.get("user", ""), "agent": t.get("agent_text", "")} for t in turns]
        prompt = prompt.replace("<<conversation>>", json.dumps(conversation, ensure_ascii=False, indent=2))

        # Inject <app_state> — unified state channel
        # Includes: state collector results (actual_state, verified, rating, etc.)
        # AND log analysis results (log_analysis: image_captured, video_captured,
        # liked, disliked, song_title, power metrics, etc.)
        if eval_type == "APP_EVAL_TASK" and eval_json:
            metadata = eval_json.get("metadata", {})
            collected_state = metadata.get("app_state")
            if collected_state is None:
                collected_state = metadata.get("xrclaw_state")
            if collected_state and isinstance(collected_state, dict):
                app_state_str = json.dumps(collected_state, ensure_ascii=False, indent=2)
            else:
                app_state_str = "{}"
            prompt = prompt.replace("<<app_state>>", app_state_str)

            # Inject camera-specific flags from extra_logs
            # (jinju_image_captured / jinju_video_captured are the same source
            # used by the deterministic judge's get_flag() helper)
            extra_logs = metadata.get("extra_logs", {})
            image_captured = extra_logs.get("jinju_image_captured", False)
            video_captured = extra_logs.get("jinju_video_captured", False)
            prompt = prompt.replace("<<image_captured>>", str(image_captured))
            prompt = prompt.replace("<<video_captured>>", str(video_captured))
        else:
            prompt = prompt.replace("<<app_state>>", "{}")
            prompt = prompt.replace("<<image_captured>>", "False")
            prompt = prompt.replace("<<video_captured>>", "False")

        return prompt

    def _build_messages(self, prompt, eval_type, question_type, encoded_image,
                         encoded_post_screenshots):
        """Build the messages list for the VLM API call.

        Determines whether to send:
        - Text only (QA_TASK, camera/device queries)
        - Image + text (VQA, Hallucination, APP_EVAL without device/camera)
        - Notification screenshot only (notification queries)
        - Dual image (Jinju + companion screenshot(s))
        
        Args:
            encoded_post_screenshots: List of base64-encoded post-state screenshots (can be 1 or many)
        """
        q_type_lower = question_type.lower()
        is_notifications_query = "notifications" in q_type_lower
        is_device_or_camera_query = (
            ("camera" in q_type_lower or "device" in q_type_lower or "video" in q_type_lower)
            and not is_notifications_query
        )

        # Handle notification queries with screenshot
        if is_notifications_query and encoded_post_screenshots:
            screenshot_b64 = encoded_post_screenshots[0] if isinstance(encoded_post_screenshots, list) else encoded_post_screenshots
            if self.use_vllm_apis:
                image_content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                ]
            else:
                image_content = [
                    {"type": "image", "image": f"data:image/png;base64,{screenshot_b64}"},
                    {"type": "text", "text": prompt},
                ]
            return [{"role": "user", "content": image_content}]

        elif eval_type in ["Visual_QA_TASK", "Hallucination_TASK", "APP_EVAL_TASK"] and not is_device_or_camera_query:
            # Build image content list — always includes the Jinju screen image.
            if self.use_vllm_apis:
                image_content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image}"}},
                ]
                # Add all post-state screenshots
                if encoded_post_screenshots and isinstance(encoded_post_screenshots, list):
                    for i, screenshot_b64 in enumerate(encoded_post_screenshots):
                        image_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                        })
                elif encoded_post_screenshots:
                    # Backward compat: single string
                    image_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded_post_screenshots}"},
                    })
            else:
                image_content = [
                    {"type": "image", "image": f"data:image/png;base64,{encoded_image}"},
                    {"type": "text", "text": prompt},
                ]
                # Add all post-state screenshots
                if encoded_post_screenshots and isinstance(encoded_post_screenshots, list):
                    for i, screenshot_b64 in enumerate(encoded_post_screenshots):
                        image_content.insert(i, {
                            "type": "image",
                            "image": f"data:image/png;base64,{screenshot_b64}",
                        })
                elif encoded_post_screenshots:
                    # Backward compat: single string
                    image_content.insert(0, {
                        "type": "image",
                        "image": f"data:image/png;base64,{encoded_post_screenshots}",
                    })
            return [{"role": "user", "content": image_content}]

        else:
            # Text-only messages (QA_TASK, or camera/device queries)
            return [{
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }]

    def _call_judge_api(self, messages):
        """Call the VLM judge API with error handling.

        Returns the response_object on success, or a dummy error response on failure.
        """
        # Debug: Print prompt and messages
        print(f"\n{'='*60}")
        print(f"=== JUDGE PROMPT (first 3000 chars) ===")
        print(f"{'='*60}")
        # Extract prompt text from messages for debugging
        for msg in messages:
            content = msg.get('content', [])
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and 'text' in c:
                        print(c['text'][:3000])
                        break
        print(f"\n=== MESSAGES STRUCTURE ===")
        print(f"Number of messages: {len(messages)}")
        if messages and 'content' in messages[0]:
            content = messages[0]['content']
            if isinstance(content, list):
                for i, c in enumerate(content):
                    if isinstance(c, dict):
                        print(f"  Content[{i}]: type={c.get('type', 'unknown')}")
                        if 'text' in c:
                            print(f"    text length: {len(c['text'])}")
                        if 'image_url' in c:
                            img_url = c['image_url']
                            if isinstance(img_url, dict):
                                print(f"    image_url: {img_url.get('url', '')[:50]}...")
        print(f"{'='*60}\n")

        try:
            if self.use_vllm_apis:
                response_object = self.judge.chat.completions.create(
                    model=self.model_id, messages=messages, max_tokens=18192, temperature=0.0,
                    logprobs=True, top_logprobs=5,
                    top_p=0.95,
                    presence_penalty=1.5,
                    extra_body={
                        "top_k": 20,
                        "chat_template_kwargs": {"enable_thinking": False}
                    },
                )
            else:
                response_object = self.judge.chat.completions.create(
                    model=self.model_id, messages=messages, max_tokens=20000,
                    temperature=0, logprobs=True, top_logprobs=5, frequency_penalty=0.7,
                    presence_penalty=0.1,
                )

        except Exception as e:
            print(f"\n{'='*60}")
            print(f"=== JUDGE API ERROR ===")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {e}")
            print(f"Model ID: {self.model_id}")
            print(f"Judge URL: {self.judge.base_url}")
            print(f"Messages sent (truncated): {str(messages)[:1000]}...")
            print(f"{'='*60}\n")
            response_object = self.__create_dummy_response_object(
                "", f"Judge API failed: {type(e).__name__}: {e}", "N/A"
            )

        return response_object

    # ── Main judge method (refactored) ───────────────────────────────

    def run_judge(self, eval_type: str, question: str, gt_answer: str, ai_response: str,
                  encoded_image: str = "", question_type: str = "", device_info: dict = None,
                  eval_json: dict = None, device_info_pre: dict = None,
                  encoded_app_screenshot: str = "") -> (str, object, str):

        assert eval_type not in ["Visual_QA_TASK", "Hallucination_TASK"] or \
            (eval_type in ["Visual_QA_TASK", "Hallucination_TASK"] and encoded_image != ""), "encoded_image cannot be empty for VQA"

        print("----ASKING JUDGE----"); logging.debug("----ASKING JUDGE----")
        print(f"Question: {question}"); logging.debug(f"Question: {question}")
        print(f"Expected Answer: {gt_answer}"); logging.debug(f"Expected Answer: {gt_answer}")
        print(f"Answer:{ai_response}"); logging.debug((f"Answer:{ai_response}"))

        prompt_response_list = []

        # For VQA tasks, get failed responses to append as prior judgments
        failed_responses = []
        if eval_type == "Visual_QA_TASK":
            failed_responses = self.__get_failed_responses(encoded_image, question, gt_answer)

        for prompt_set in self.eval_type_to_prompt[eval_type]:
            # 1. Resolve prompt template
            if eval_type == "APP_EVAL_TASK":
                prompt = self._resolve_app_eval_prompt(
                    prompt_set, question_type, device_info, device_info_pre, eval_json
                )
            else:
                prompt = prompt_set

            # 2. Inject placeholders
            prompt = self._inject_placeholders(
                prompt, question, ai_response, gt_answer, question_type, eval_type, eval_json
            )

            # 3. Append mistake prompt for VQA if failed responses exist
            if eval_type == "Visual_QA_TASK" and failed_responses:
                past_failures = ""
                for fr in failed_responses:
                    past_failures += (
                        "<example>\n"
                        f"<question>{fr['question']}</question>\n"
                        f"<answer>{fr['response']}</answer>\n"
                        f"<judge_rating>{fr['judge_rating']}</judge_rating>\n"
                        f"<correct_rating>{fr['correct_rating']}</correct_rating>\n"
                        "</example>\n"
                    )
                mistake_prompt = vqa_mistake_prompt.get("1.0", "")
                mistake_prompt = mistake_prompt.replace("<<past_failures>>", past_failures)
                prompt += mistake_prompt
                print("----PAST ERRORS ADDED----")

            # 4. Build messages
            messages = self._build_messages(
                prompt, eval_type, question_type, encoded_image, encoded_app_screenshot
            )

            # 5. Call judge API
            response_object = self._call_judge_api(messages)

            # 6. Parse response
            response = response_object.choices[0].message.content
            response = response.replace("<｜begin▁of▁sentence｜>", "")

            analysis, rating = self.__get_rating_and_analysis(response)
            print(f"Rating: {rating}"); logging.debug(f"Rating: {rating}")
            print(f"Analysis: {analysis}"); logging.debug(f"Analysis: {analysis}")

            entropy_metrics = self.__get_entropy_metrics(response_object)

            prompt_response_list.append((response, entropy_metrics, prompt))

        return self.__find_consensus(prompt_response_list)


    # ── get_judge_score helpers (extracted) ──────────────────────────

    def _try_deterministic_judge(self, question_type, question, ai_response_text,
                                  metadata, eval_id, eval_type, gt_answer,
                                  start_time, end_time):
        """Try deterministic judge for supported question types.

        Returns (dj_response, result_meta) if deterministic judge succeeds,
        or None to fall through to VLM judge.
        """
        if eval_type != "APP_EVAL_TASK" or not DeterministicJudge.can_handle(question_type):
            return None

        print("----DETERMINISTIC JUDGE----"); logging.info("----DETERMINISTIC JUDGE----")
        dj = DeterministicJudge()
        dj_result = dj.evaluate(question_type, question, ai_response_text, metadata)

        if dj_result is None:
            return None

        dj_response, dj_entropy = dj_result
        _, dj_rating = self.__get_rating_and_analysis(dj_response)
        print(f"Deterministic Rating: {dj_rating}"); logging.debug(f"Deterministic Rating: {dj_rating}")

        # If rating is good enough, use the deterministic result
        if dj_rating is None or dj_rating > DeterministicJudge.BAD_RATING_THRESHOLD:
            result_meta = {
                "eval_id": eval_id,
                "eval_type": eval_type,
                "question_type": question_type,
                "question": question,
                "reference": gt_answer,
                "answer": ai_response_text,
                "response_time": start_time,
                "duration": end_time - start_time,
                "error_type": 0,
                "judge_method": "deterministic",
                "entropy_metrics": dj_entropy
            }
            return dj_response, result_meta
        else:
            print(f"Deterministic judge gave low rating ({dj_rating}) — falling back to VLM judge")
            logging.info(f"Deterministic judge gave low rating ({dj_rating}) — falling back to VLM judge")
            return None

    def _save_judge_prompt(self, eval_id, judge_prompt, metadata):
        """Save the judge prompt to the assets folder for debugging/visualization.

        Returns the path to the saved file, or empty string if not saved.
        """
        if not judge_prompt:
            return ""

        # Derive assets directory from image_path in metadata
        image_path = metadata.get("image_path", "")
        if image_path:
            assets_dir = os.path.dirname(image_path)
        else:
            assets_dir = os.path.join("data", "results", "assets")
        os.makedirs(assets_dir, exist_ok=True)

        prompt_filename = f"prompt_{eval_id}.txt"
        prompt_filepath = os.path.join(assets_dir, prompt_filename)
        try:
            with open(prompt_filepath, "w", encoding="utf-8") as f:
                f.write(judge_prompt)
            print(f"Judge prompt saved to: {prompt_filepath}")
            return prompt_filepath
        except Exception as e:
            print(f"Warning: Failed to save judge prompt: {e}")
            return ""

    def _build_result_meta(self, eval_id, eval_type, question_type, question,
                            gt_answer, ai_response_text, start_time, end_time,
                            error_type, judge_method, entropy_metrics,
                            judge_prompt_path=""):
        """Build the result_meta dict for get_judge_score."""
        return {
            "eval_id": eval_id,
            "eval_type": eval_type,
            "question_type": question_type,
            "question": question,
            "reference": gt_answer,
            "answer": ai_response_text,
            "response_time": start_time,
            "duration": end_time - start_time,
            "error_type": error_type,
            "judge_method": judge_method,
            "entropy_metrics": entropy_metrics,
            "judge_prompt_path": judge_prompt_path
        }

    # ── Main scoring method (refactored) ─────────────────────────────

    def get_text_response(self, encoded_audio: str) -> str:
        response = requests.post(
            f"{self.transcription_url}/transcribe",
            json={"data": encoded_audio},
            timeout=600  # long audios can take time
        )
        response.raise_for_status()
        return response.json()

    def get_judge_score(self, eval_json: str) -> str:
        eval_db = json.loads(eval_json)

        eval_id = eval_db["eval_id"]
        eval_type = eval_db["eval_type"]
        question = eval_db["question"]
        question_type = eval_db["question_type"]
        gt_answer = eval_db["reference"]
        base64_ai_response = eval_db["encoded_audio"]
        base64_image = eval_db["encoded_image"]
        metadata = eval_db.get("metadata", {})
        
        # Get post-state screenshots for judge (new multi-screenshot support)
        post_screenshot_paths = metadata.get("post_state_screenshots", [])
        encoded_post_screenshots = []
        for ss_path in post_screenshot_paths:
            if os.path.exists(ss_path):
                encoded = Base64Converter.encode_to_base64(ss_path)["file_base64"]
                encoded_post_screenshots.append(encoded)
        
        # Fallback to old single screenshot field for backward compatibility
        if not encoded_post_screenshots:
            base64_app_screenshot = eval_db.get("encoded_app_screenshot", "")
            if base64_app_screenshot:
                encoded_post_screenshots = [base64_app_screenshot]

        # Skipped app — return 0-rated dummy without calling transcription/judge
        if metadata.get("skip"):
            reason = metadata.get("skip_reason", "AUTOMATED EVALUATION NOT SUPPORTED")
            print(f"{reason} — skipping judge")
            response = json.dumps({
                "question": question,
                "analysis": reason,
                "rating": 0
            })
            result_meta = self._build_result_meta(
                eval_id, eval_type, question_type, question, gt_answer,
                "", 0, 0, 0, "skipped",
                {"entropy": 0.0, "surprisal": 0.0, "curvature": 0.0, "entropy_delta": 0.0}
            )
            return response, result_meta

        # Support both single device_info (backward compatible) and dual-state (device_info_pre/post)
        device_info_post = metadata.get("device_info_post", metadata.get("device_info", {}))
        device_info_pre = metadata.get("device_info_pre", {})

        stt_json = self.get_text_response(base64_ai_response)

        error_type = 0; response = ""
        start_time = 25; end_time = 0

        # Extract app name to check if this is a task that may not produce a spoken response
        parts = question_type.lower().split("_") if question_type else []
        group = parts[1] if len(parts) >= 2 else ""
        feature = parts[2] if len(parts) >= 3 else ""


        ai_response_text = stt_json["text"]
        if ai_response_text:
            start_time = stt_json["start"]; end_time = stt_json["end"]

        # ── Deterministic Judge (no LLM) ──
        dj_result = self._try_deterministic_judge(
            question_type, question, ai_response_text, metadata,
            eval_id, eval_type, gt_answer, start_time, end_time
        )
        if dj_result is not None:
            return dj_result

        # ── VLM Judge ──
        judge_prompt = None
        entropy_metrics = {"entropy": 0.0, "surprisal": 0.0, "curvature": 0.0, "entropy_delta": 0.0}

        ## Filter tts false positive cases
        if stt_json["text"].lower().replace("you", "").replace("i", "").replace("oh", "").replace(".", "").replace(" ", "") == "":
            
            ## Empty response might not be an error for app_eval_tasks
            if eval_type=="APP_EVAL_TASK":
                # Action-only tasks (camera, device) don't require audio response
                print(f"{question_type} task with no audio response - evaluating based on device state/screenshot")
                logging.debug(f"{question_type} task with no audio response - evaluating based on device state/screenshot")
                response, entropy_metrics, judge_prompt = self.run_judge(
                    eval_type, question, gt_answer, "", base64_image, question_type,
                    device_info_post, eval_db, device_info_pre, encoded_post_screenshots
                )
                
            else:
                # Non-silent tasks: empty response is an error
                error_type = 1
                response_object = self.__create_dummy_response_object(question, "The ai_agent failed to give a valid response!", "0")
                entropy_metrics = self.__get_entropy_metrics(response_object)
                response = response_object.choices[0].message.content
                judge_prompt = None
                print("Empty Response")
                logging.debug("Empty Response")
        else:
            response, entropy_metrics, judge_prompt = self.run_judge(
                eval_type, question, gt_answer, stt_json["text"], base64_image, question_type,
                device_info_post, eval_db, device_info_pre, encoded_post_screenshots
            )

        # Determine judge method
        judge_method = "error_empty_response" if error_type == 1 else "vlm"

        # Save the judge prompt to assets folder
        judge_prompt_path = self._save_judge_prompt(eval_id, judge_prompt, metadata)

        result_meta = self._build_result_meta(
            eval_id, eval_type, question_type, question, gt_answer,
            ai_response_text, start_time, end_time, error_type, judge_method,
            entropy_metrics, judge_prompt_path
        )

        return response, result_meta


    def __get_failed_responses(self, image_b64: str, question: str, gt_answer: str, example_count: int = 1) -> list:
        """Get failed responses from the rating rectifier. Returns a list of dicts with keys: question, gt_answer, judge_rating, correct_rating."""
        if not self.__rating_rectifier_health():
            return []

        try:
            # Compute unique_id via the rating rectifier's endpoint
            uid_response = requests.post(
                f"{self.rating_rectifier_url}/compute_unique_id",
                json={"image_b64": image_b64, "question": question, "gt_answer": gt_answer},
                timeout=10,
            )
            uid_response.raise_for_status()
            unique_id = uid_response.json()["unique_id"]

            # Get mistakes using the computed unique_id
            mistakes_response = requests.post(
                f"{self.rating_rectifier_url}/get_mistakes",
                json={"unique_id": unique_id, "device_type": self.device_type, "example_count": example_count},
                timeout=10,
            )
            mistakes_response.raise_for_status()
            mistakes_data = mistakes_response.json()

            # Extract only the required keys
            return [
                {
                    "question": m.get("question", ""),
                    "response": m.get("judge_response", ""),
                    "judge_rating": m.get("judge_rating", ""),
                    "correct_rating": m.get("correct_rating", ""),
                }
                for m in mistakes_data.get("mistakes", [])
            ]

        except requests.exceptions.RequestException as e:
            warnings.warn(f"Failed to get failed responses from rating rectifier: {e}")
            return []
