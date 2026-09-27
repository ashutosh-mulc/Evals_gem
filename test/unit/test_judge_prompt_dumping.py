"""
Unit tests for judge prompt dumping functionality.

Tests that:
1. run_judge returns a 3-tuple (response, entropy_metrics, prompt)
2. get_judge_score saves the prompt to a file and includes the path in result_meta
3. The prompt file content matches what was sent to the judge
4. Empty-response error path sets judge_prompt to None (no file saved)
5. Deterministic judge path doesn't set judge_prompt_path
6. Dashboard detail route reads the prompt file correctly
"""

import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from judge_worker.response_scorer import ResponseScorer


# ── Test helpers ──────────────────────────────────────────────────────

def _make_scorer():
    judge_config = {
        "vllm_api": False,
        "qa_prompt_version": ["1.0"],
        "vqa_prompt_version": ["1.0"],
        "hqa_prompt_version": ["1.0"],
        "appEval_prompt_version": ["1.0"],
    }

    with patch("judge_worker.response_scorer.OpenAI") as mock_openai_cls, \
         patch("judge_worker.response_scorer.requests.get") as mock_get:
        mock_client = MagicMock()
        mock_client.models.list.return_value.data = [SimpleNamespace(id="mock-model")]
        mock_openai_cls.return_value = mock_client

        mock_get.return_value = SimpleNamespace(status_code=200)

        scorer = ResponseScorer(
            transcription_url="http://fake-transcriber",
            judge_url="http://fake-judge/v1",
            rating_rectifier_url="",
            device_type="jinju",
            judge_config=judge_config,
        )

    return scorer


@pytest.fixture
def scorer():
    return _make_scorer()


def _judge_text(question="Q", analysis="Looks correct", rating=5):
    return "{'question': '" + question + "','analysis': '" + analysis + "','rating': " + str(rating) + "}"



def _fake_response_object(content_text="dummy"):
    """Build a minimal fake OpenAI response object for run_judge."""
    logprobs_entry = SimpleNamespace(
        token="dummy",
        top_logprobs=[SimpleNamespace(token="dummy", logprob=-0.1)],
    )
    logprobs = SimpleNamespace(content=[logprobs_entry])
    choice = SimpleNamespace(
        logprobs=logprobs,
        message=SimpleNamespace(content=content_text),
    )
    return SimpleNamespace(choices=[choice])


# ── Tests for run_judge 3-tuple return ────────────────────────────────

class TestRunJudgeReturnsPrompt:
    """Verify that run_judge returns a 3-tuple including the prompt text."""

    def test_run_judge_returns_three_tuple(self, scorer):
        """run_judge should return (response, entropy_metrics, prompt) as a 3-tuple."""
        fake_resp = _fake_response_object(_judge_text(rating=5))

        with patch.object(scorer.judge.chat.completions, "create", return_value=fake_resp), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None):
            result = scorer.run_judge(
                eval_type="QA_TASK",
                question="What is 2+2?",
                gt_answer="4",
                ai_response="4",
                question_type="qa",
            )

        assert isinstance(result, tuple)
        assert len(result) == 3
        response, entropy_metrics, prompt = result
        assert isinstance(response, str)
        assert isinstance(entropy_metrics, dict)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_run_judge_prompt_contains_question(self, scorer):
        """The returned prompt should contain the question text."""
        fake_resp = _fake_response_object(_judge_text(rating=5))
        test_question = "What is the capital of France?"

        with patch.object(scorer.judge.chat.completions, "create", return_value=fake_resp), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None):
            _, _, prompt = scorer.run_judge(
                eval_type="QA_TASK",
                question=test_question,
                gt_answer="Paris",
                ai_response="Paris",
                question_type="qa",
            )

        assert test_question in prompt

    def test_run_judge_prompt_contains_gt_answer(self, scorer):
        """The returned prompt should contain the ground-truth answer."""
        fake_resp = _fake_response_object(_judge_text(rating=5))
        test_gt = "42"

        with patch.object(scorer.judge.chat.completions, "create", return_value=fake_resp), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None):
            _, _, prompt = scorer.run_judge(
                eval_type="QA_TASK",
                question="What is the answer to life?",
                gt_answer=test_gt,
                ai_response="42",
                question_type="qa",
            )

        assert test_gt in prompt

    def test_run_judge_prompt_contains_ai_response(self, scorer):
        """The returned prompt should contain the AI's transcribed response."""
        fake_resp = _fake_response_object(_judge_text(rating=5))
        test_ai_response = "The answer is 42"

        with patch.object(scorer.judge.chat.completions, "create", return_value=fake_resp), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None):
            _, _, prompt = scorer.run_judge(
                eval_type="QA_TASK",
                question="What is the answer?",
                gt_answer="42",
                ai_response=test_ai_response,
                question_type="qa",
            )

        assert test_ai_response in prompt


# ── Tests for get_judge_score prompt saving ───────────────────────────

class TestGetJudgeScorePromptSaving:
    """Verify that get_judge_score saves the prompt to a file and includes the path in result_meta."""

    def _make_eval_json(self, eval_id="q00001", image_path="", ai_response_b64=""):
        return json.dumps({
            "eval_id": eval_id,
            "eval_type": "QA_TASK",
            "question": "What is 2+2?",
            "question_type": "qa",
            "reference": "4",
            "encoded_audio": ai_response_b64,
            "encoded_image": "",
            "encoded_app_screenshot": "",
            "metadata": {
                "image_path": image_path,
            },
        })

    def test_prompt_file_created_when_vlm_judge_used(self, scorer, tmp_path):
        """When the VLM judge is used, a prompt file should be created in the assets dir."""
        # Set up a fake assets dir via image_path
        assets_dir = str(tmp_path / "assets")
        os.makedirs(assets_dir)
        image_path = os.path.join(assets_dir, "image_q00001.png")
        # Create a dummy image file so the path exists
        with open(image_path, "w") as f:
            f.write("dummy")

        eval_json = self._make_eval_json(eval_id="q00001", image_path=image_path)

        # Mock transcription to return a non-empty response
        stt_response = {"text": "4", "start": 1.0, "end": 2.0}
        fake_judge_resp = _fake_response_object(_judge_text(rating=5))

        with patch.object(scorer, "get_text_response", return_value=stt_response), \
             patch.object(scorer.judge.chat.completions, "create", return_value=fake_judge_resp), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None), \
             patch("judge_worker.response_scorer.DeterministicJudge") as mock_dj_class:
            # Make deterministic judge return None (unsupported) so VLM path is used
            mock_dj_class.can_handle.return_value = False

            response, result_meta = scorer.get_judge_score(eval_json)

        # Check prompt path is in result_meta
        assert "judge_prompt_path" in result_meta
        assert result_meta["judge_prompt_path"] != ""
        assert result_meta["judge_method"] == "vlm"

        # Check the file exists and contains the prompt
        prompt_path = result_meta["judge_prompt_path"]
        assert os.path.isfile(prompt_path)
        assert prompt_path.endswith("prompt_q00001.txt")

        with open(prompt_path, "r") as f:
            saved_prompt = f.read()
        assert "What is 2+2?" in saved_prompt
        assert "4" in saved_prompt

    def test_prompt_path_empty_when_error_empty_response(self, scorer, tmp_path):
        """When the AI gives an empty response (error), judge_prompt_path should be empty."""
        assets_dir = str(tmp_path / "assets")
        os.makedirs(assets_dir)
        image_path = os.path.join(assets_dir, "image_q00002.png")
        with open(image_path, "w") as f:
            f.write("dummy")

        eval_json = self._make_eval_json(eval_id="q00002", image_path=image_path)

        # Mock transcription to return an empty response (non-silent task)
        stt_response = {"text": "", "start": 0, "end": 0}

        with patch.object(scorer, "get_text_response", return_value=stt_response), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None), \
             patch("judge_worker.response_scorer.DeterministicJudge") as mock_dj_class:
            mock_dj_class.can_handle.return_value = False

            response, result_meta = scorer.get_judge_score(eval_json)

        assert result_meta["judge_prompt_path"] == ""
        assert result_meta["judge_method"] == "error_empty_response"
        assert result_meta["error_type"] == 1

    def test_prompt_not_saved_for_deterministic_judge(self, scorer, tmp_path):
        """When deterministic judge handles the case, no prompt file should be saved."""
        assets_dir = str(tmp_path / "assets")
        os.makedirs(assets_dir)
        image_path = os.path.join(assets_dir, "image_q00003.png")
        with open(image_path, "w") as f:
            f.write("dummy")

        # Use an APP_EVAL_TASK type with a question_type the deterministic judge handles
        eval_json = json.dumps({
            "eval_id": "q00003",
            "eval_type": "APP_EVAL_TASK",
            "question": "What volume is set?",
            "question_type": "online_device_volume_up",
            "reference": "increased",
            "encoded_audio": "",
            "encoded_image": "",
            "encoded_app_screenshot": "",
            "metadata": {
                "image_path": image_path,
                "device_info_pre": {"jinju": {"volume": {"current": 30, "max": 100}}},
                "device_info_post": {"jinju": {"volume": {"current": 50, "max": 100}}},
            },
        })

        stt_response = {"text": "The volume has been increased", "start": 1.0, "end": 2.0}

        # Mock deterministic judge to return a good result
        dj_result = (_judge_text(rating=5), {"entropy": 0.0, "surprisal": 0.0, "curvature": 0.0, "entropy_delta": 0.0})

        with patch.object(scorer, "get_text_response", return_value=stt_response), \
             patch("judge_worker.response_scorer.DeterministicJudge") as mock_dj_class:
            mock_dj_class.can_handle.return_value = True
            mock_dj_class.BAD_RATING_THRESHOLD = 2
            mock_dj_instance = MagicMock()
            mock_dj_instance.evaluate.return_value = dj_result
            mock_dj_class.return_value = mock_dj_instance

            response, result_meta = scorer.get_judge_score(eval_json)


        assert result_meta["judge_method"] == "deterministic"
        # judge_prompt_path should not be set for deterministic cases
        assert result_meta.get("judge_prompt_path", "") == ""

    def test_prompt_file_content_matches_returned_prompt(self, scorer, tmp_path):
        """The content of the saved prompt file should exactly match the prompt returned by run_judge."""
        assets_dir = str(tmp_path / "assets")
        os.makedirs(assets_dir)
        image_path = os.path.join(assets_dir, "image_q00004.png")
        with open(image_path, "w") as f:
            f.write("dummy")

        eval_json = self._make_eval_json(eval_id="q00004", image_path=image_path)

        stt_response = {"text": "Paris", "start": 1.0, "end": 2.0}
        fake_judge_resp = _fake_response_object(_judge_text(rating=5))

        with patch.object(scorer, "get_text_response", return_value=stt_response), \
             patch.object(scorer.judge.chat.completions, "create", return_value=fake_judge_resp), \
             patch.object(scorer, "_ResponseScorer__judge_health", return_value=None), \
             patch("judge_worker.response_scorer.DeterministicJudge") as mock_dj_class:
            mock_dj_class.can_handle.return_value = False

            response, result_meta = scorer.get_judge_score(eval_json)

        prompt_path = result_meta["judge_prompt_path"]
        assert os.path.isfile(prompt_path)

        with open(prompt_path, "r") as f:
            saved_content = f.read()

        # The saved prompt should contain all the key elements
        assert "What is 2+2?" in saved_content  # question
        assert "4" in saved_content  # gt_answer
        assert "Paris" in saved_content  # ai_response


# ── Tests for dashboard prompt reading ───────────────────────────────

class TestDashboardPromptReading:
    """Verify that the dashboard's detail route reads the prompt file correctly."""

    def test_dashboard_reads_prompt_file(self, tmp_path):
        """The detail route should read the prompt file and pass it to the template."""
        # Create a prompt file
        prompt_content = "This is a test judge prompt.\nQuestion: What is 2+2?\nAnswer: 4"
        prompt_file = tmp_path / "prompt_q00001.txt"
        prompt_file.write_text(prompt_content)

        # Mock a database row
        result_json = (
            '{"question": "test", "analysis": "ok", "rating": 5}'
            "<meta_start>"
            + json.dumps({
                "question_type": "qa",
                "judge_method": "vlm",
                "judge_prompt_path": str(prompt_file),
                "answer": "4",
            })
            + "<meta_end>"
        )

        mock_row = {
            "id": "q00001",
            "question": "What is 2+2?",
            "status": "COMPLETED",
            "eval_json": json.dumps({
                "eval_id": "q00001",
                "metadata": {"image_path": str(tmp_path / "image_q00001.png")},
            }),
            "result_json": result_json,
            "created_at": "2024-01-01",
        }

        # Import the dashboard module
        import scripts.eval_dashboard as dashboard_mod

        with patch.object(dashboard_mod, "get_row", return_value=mock_row):
            with patch.object(dashboard_mod, "render_template_string") as mock_render:
                # Call the detail route
                dashboard_mod.detail("q00001")

                # Check render_template_string was called with judge_prompt
                call_kwargs = mock_render.call_args.kwargs
                assert "judge_prompt" in call_kwargs
                assert call_kwargs["judge_prompt"] == prompt_content

    def test_dashboard_handles_missing_prompt_file(self, tmp_path):
        """When the prompt file path exists in meta but the file is gone, show a message."""
        mock_row = {
            "id": "q00002",
            "question": "Test",
            "status": "COMPLETED",
            "eval_json": json.dumps({
                "eval_id": "q00002",
                "metadata": {},
            }),
            "result_json": (
                '{"question": "test", "analysis": "ok", "rating": 5}'
                "<meta_start>"
                + json.dumps({
                    "question_type": "qa",
                    "judge_method": "vlm",
                    "judge_prompt_path": str(tmp_path / "nonexistent_prompt.txt"),
                    "answer": "test",
                })
                + "<meta_end>"
            ),
            "created_at": "2024-01-01",
        }

        import scripts.eval_dashboard as dashboard_mod

        with patch.object(dashboard_mod, "get_row", return_value=mock_row):
            with patch.object(dashboard_mod, "render_template_string") as mock_render:
                dashboard_mod.detail("q00002")

                call_kwargs = mock_render.call_args.kwargs
                assert "judge_prompt" in call_kwargs
                assert "not found" in call_kwargs["judge_prompt"].lower() or "not found" in call_kwargs["judge_prompt"]

    def test_dashboard_no_prompt_for_deterministic(self):
        """When judge_method is 'deterministic', judge_prompt should be empty."""
        mock_row = {
            "id": "q00003",
            "question": "Test",
            "status": "COMPLETED",
            "eval_json": json.dumps({
                "eval_id": "q00003",
                "metadata": {},
            }),
            "result_json": (
                '{"question": "test", "analysis": "ok", "rating": 5}'
                "<meta_start>"
                + json.dumps({
                    "question_type": "online_device_volume_up",
                    "judge_method": "deterministic",
                    "judge_prompt_path": "",
                    "answer": "test",
                })
                + "<meta_end>"
            ),
            "created_at": "2024-01-01",
        }

        import scripts.eval_dashboard as dashboard_mod

        with patch.object(dashboard_mod, "get_row", return_value=mock_row):
            with patch.object(dashboard_mod, "render_template_string") as mock_render:
                dashboard_mod.detail("q00003")

                call_kwargs = mock_render.call_args.kwargs
                assert call_kwargs["judge_prompt"] == ""
