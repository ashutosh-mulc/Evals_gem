import math
from typing import Dict, List, Optional


class HallucinationScorer:
    def __init__(self):
        self.prev_top_logprobs: Optional[Dict[str, float]] = None
        self.prev_entropy: Optional[float] = None

    def _entropy(self, probs: List[float]) -> float:
        return -sum(p * math.log(p + 1e-10) for p in probs)

    def _surprisal(self, chosen_prob: float) -> float:
        return -math.log(chosen_prob + 1e-10)

    def _curvature(self, logprobs: List[float]) -> float:
        if len(logprobs) >= 3:
            return logprobs[0] - 2 * logprobs[1] + logprobs[2]
        return 0.0

    def _jacobian(self, current: Dict[str, float], prev: Dict[str, float]) -> float:
        all_tokens = set(current.keys()) | set(prev.keys())
        return sum(abs(current.get(tok, -100.0) - prev.get(tok, -100.0)) for tok in all_tokens)

    def score(
        self,
        top_logprobs: Dict[str, float],
        chosen_token: str,
        weights: Dict[str, float] = None
    ) -> Dict[str, float]:
        if weights is None:
            weights = {
                "entropy": 1.0,
                "surprisal": 1.0,
                "curvature": 1.0,
                "entropy_delta": 1.0,
            }

        # Convert logprobs to sorted lists
        sorted_logprobs = sorted(top_logprobs.values(), reverse=True)
        sorted_probs = [max(0,math.exp(lp)) for lp in sorted_logprobs]
        residual_prob = max(0,1-sum(sorted_probs))
        sorted_probs+=[residual_prob]
        # print(sorted_probs)
        # exit(1)
        entropy = self._entropy(sorted_probs)
        surprisal = self._surprisal(math.exp(top_logprobs.get(chosen_token, -100.0)))
        curvature = self._curvature(sorted_logprobs)

        # jacobian = 0.0
        # if self.prev_top_logprobs:
        #     jacobian = self._jacobian(top_logprobs, self.prev_top_logprobs)

        entropy_delta = 0.0
        if self.prev_entropy is not None:
            entropy_delta = abs(entropy - self.prev_entropy)

        # Composite hallucination score
        hallucination_score = (
            weights["entropy"] * entropy +
            weights["surprisal"] * surprisal -
            weights["curvature"] * curvature +
            weights["entropy_delta"] * entropy_delta
        )

        # Update state
        self.prev_top_logprobs = top_logprobs
        self.prev_entropy = entropy

        return {
            "entropy": entropy,
            "surprisal": surprisal,
            "curvature": curvature,
            "entropy_delta": entropy_delta,
        }
