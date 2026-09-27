"""
Unit tests for the pure scoring logic inside ResponseScorer: rating/analysis
extraction from raw judge text, entropy-metric aggregation, and multi-prompt
consensus selection. These are the highest-risk, least-tested parts of the
judge pipeline (per CodeRedesign.md), so they're covered directly here rather
than through a full network-backed integration test.

ResponseScorer.__init__ talks to the judge and transcription servers to
verify they're healthy, so both are mocked out for construction; the tests
below only exercise the private, dependency-free scoring methods.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from judge_worker.response_scorer import ResponseScorer


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


# ── Rating / analysis extraction ──────────────────────────────────────────

def _judge_text(question="Q", analysis="Looks correct", rating=5):
    return f"<think></think>{{'question': '{question}','analysis': '{analysis}','rating': {rating}}}"


def test_get_rating_and_analysis_parses_well_formed_response(scorer):
    analysis, rating = scorer._ResponseScorer__get_rating_and_analysis(
        _judge_text(analysis="Matches expected answer", rating=5)
    )
    assert rating == 5
    assert analysis == "Matches expected answer"


def test_get_rating_and_analysis_returns_none_rating_when_missing(scorer):
    """Plain text with no structured data returns (text, None) — not (None, None).

    parse_judge_response returns the raw text as analysis (Step 6 fallback)
    so the user can see what the judge actually said, even if unparseable.
    """
    analysis, rating = scorer._ResponseScorer__get_rating_and_analysis(
        "not a judge-shaped response at all"
    )
    assert rating is None
    assert analysis == "not a judge-shaped response at all"



def test_get_rating_and_analysis_handles_multiline_analysis(scorer):
    """Python dict repr with \\n in analysis — ast.literal_eval converts \\n to actual newline."""
    text = "{'question': 'Q','analysis': 'Line one\\nLine two','rating': 3}"
    analysis, rating = scorer._ResponseScorer__get_rating_and_analysis(text)
    assert rating == 3
    assert analysis == "Line one\nLine two"  # \\n becomes actual newline after ast.literal_eval



# ── Entropy metric aggregation ────────────────────────────────────────────

def _fake_response_object(token_logprob_pairs_per_step):
    """Build a fake OpenAI-shaped response object for __get_entropy_metrics.

    token_logprob_pairs_per_step: list of (chosen_token, {token: logprob, ...})
    """
    content = []
    for chosen_token, top_logprobs in token_logprob_pairs_per_step:
        entry = SimpleNamespace(
            token=chosen_token,
            top_logprobs=[SimpleNamespace(token=t, logprob=lp) for t, lp in top_logprobs.items()],
        )
        content.append(entry)

    logprobs = SimpleNamespace(content=content)
    choice = SimpleNamespace(logprobs=logprobs)
    return SimpleNamespace(choices=[choice])


def test_get_entropy_metrics_averages_across_tokens(scorer):
    response_object = _fake_response_object([
        ("a", {"a": -0.1, "b": -5.0}),
        ("a", {"a": -0.1, "b": -5.0}),
    ])

    metrics = scorer._ResponseScorer__get_entropy_metrics(response_object)

    assert set(metrics.keys()) == {"entropy", "surprisal", "curvature", "entropy_delta"}
    # Identical steps -> averaging shouldn't change the per-step value.
    single_step = scorer.metric_scorer.score({"a": -0.1, "b": -5.0}, chosen_token="a")
    assert metrics["entropy"] == pytest.approx(single_step["entropy"], abs=1e-6)


def test_get_entropy_metrics_skips_none_entries(scorer):
    logprobs = SimpleNamespace(content=[
        None,
        SimpleNamespace(
            token="a",
            top_logprobs=[SimpleNamespace(token="a", logprob=-0.1), SimpleNamespace(token="b", logprob=-5.0)],
        ),
    ])
    response_object = SimpleNamespace(choices=[SimpleNamespace(logprobs=logprobs)])

    metrics = scorer._ResponseScorer__get_entropy_metrics(response_object)
    assert metrics["entropy"] > 0  # computed from the single non-None entry, not NaN/inf


# ── Multi-prompt consensus ────────────────────────────────────────────────

def _entry(rating, tag="", prompt=""):
    return (_judge_text(analysis=f"analysis{tag}", rating=rating), {"entropy": 0.0}, prompt)


def test_find_consensus_picks_clear_majority(scorer):
    responses = [_entry(5, "A", "promptA"), _entry(5, "B", "promptB"), _entry(3, "C", "promptC")]
    chosen_response, _, chosen_prompt = scorer._ResponseScorer__find_consensus(responses)
    assert "analysisA" in chosen_response  # first entry with the winning rating (5)
    assert chosen_prompt == "promptA"


def test_find_consensus_breaks_even_tie_with_lower_median(scorer):
    # Two ratings, one vote each -> even tie -> lower of the two wins (per current logic)
    responses = [_entry(5, "A", "promptA"), _entry(3, "B", "promptB")]
    chosen_response, _, chosen_prompt = scorer._ResponseScorer__find_consensus(responses)
    assert "analysisB" in chosen_response  # rating 3 wins over 5
    assert chosen_prompt == "promptB"


def test_find_consensus_breaks_odd_tie_with_median(scorer):
    responses = [_entry(5, "A", "promptA"), _entry(3, "B", "promptB"), _entry(1, "C", "promptC")]
    chosen_response, _, _ = scorer._ResponseScorer__find_consensus(responses)
    assert "analysisB" in chosen_response  # median of {1,3,5} is 3


def test_find_consensus_falls_back_to_first_when_all_ratings_unparsable(scorer):
    responses = [("garbage one", {"entropy": 0.0}, "prompt_one"), ("garbage two", {"entropy": 0.0}, "prompt_two")]
    chosen_response, _, chosen_prompt = scorer._ResponseScorer__find_consensus(responses)
    assert chosen_response == "garbage one"
    assert chosen_prompt == "prompt_one"


def test_find_consensus_returns_three_tuple(scorer):
    """Verify __find_consensus returns a 3-tuple (response, entropy_metrics, prompt)."""
    responses = [_entry(5, "A", "promptA")]
    result = scorer._ResponseScorer__find_consensus(responses)
    assert isinstance(result, tuple)
    assert len(result) == 3
    response, entropy, prompt = result
    assert "analysisA" in response
    assert entropy == {"entropy": 0.0}
    assert prompt == "promptA"

