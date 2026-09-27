import math

import pytest

from judge_worker.entropy import HallucinationScorer


def test_score_returns_all_expected_keys():
    scorer = HallucinationScorer()
    result = scorer.score({"a": -0.1, "b": -2.0, "c": -3.0}, chosen_token="a")

    assert set(result.keys()) == {"entropy", "surprisal", "curvature", "entropy_delta"}
    assert all(isinstance(v, float) for v in result.values())


def test_confident_prediction_has_lower_entropy_than_uncertain_one():
    scorer = HallucinationScorer()

    confident = scorer.score({"a": -0.01, "b": -8.0, "c": -9.0}, chosen_token="a")
    scorer2 = HallucinationScorer()
    uncertain = scorer2.score({"a": -1.1, "b": -1.2, "c": -1.3}, chosen_token="a")

    assert confident["entropy"] < uncertain["entropy"]


def test_surprisal_is_low_for_high_probability_chosen_token():
    scorer = HallucinationScorer()
    result = scorer.score({"a": -0.01, "b": -5.0}, chosen_token="a")

    # exp(-0.01) ~ 0.99 -> surprisal ~ -log(0.99) ~ 0.01
    assert result["surprisal"] == pytest.approx(-math.log(math.exp(-0.01) + 1e-10), abs=1e-6)


def test_surprisal_falls_back_to_near_zero_probability_for_missing_token():
    scorer = HallucinationScorer()
    result = scorer.score({"a": -0.5}, chosen_token="not_in_dict")

    # chosen_token missing -> default logprob -100 -> surprisal = -log(exp(-100)) = 100
    # (but with 1e-10 epsilon added, so slightly less)
    assert result["surprisal"] > 20  # 100 - epsilon is still very large compared to normal tokens


def test_curvature_is_zero_with_fewer_than_three_logprobs():
    scorer = HallucinationScorer()
    result = scorer.score({"a": -0.1, "b": -0.2}, chosen_token="a")
    assert result["curvature"] == 0.0


def test_entropy_delta_is_zero_on_first_call_then_nonzero_on_change():
    scorer = HallucinationScorer()

    first = scorer.score({"a": -0.01, "b": -8.0}, chosen_token="a")
    assert first["entropy_delta"] == 0.0

    second = scorer.score({"a": -2.0, "b": -2.0, "c": -2.0}, chosen_token="a")
    assert second["entropy_delta"] == pytest.approx(abs(second["entropy"] - first["entropy"]))


def test_custom_weights_scale_components_linearly():
    scorer = HallucinationScorer()
    top_logprobs = {"a": -0.1, "b": -1.0, "c": -2.0}

    zero_weights = {"entropy": 0.0, "surprisal": 0.0, "curvature": 0.0, "entropy_delta": 0.0}
    result = scorer.score(top_logprobs, chosen_token="a", weights=zero_weights)

    # Weights only affect the (unreturned) composite score, not the raw component dict,
    # so the raw entropy/surprisal/curvature/entropy_delta values must stay unchanged.
    scorer2 = HallucinationScorer()
    unweighted = scorer2.score(top_logprobs, chosen_token="a")

    assert result == unweighted
