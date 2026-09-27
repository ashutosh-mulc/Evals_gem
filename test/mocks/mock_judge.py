"""
MockJudgeServer — mock for the VLM judge service.

Returns canned judge responses (rating + analysis) for testing the
pipeline without a real vLLM server. Can be configured per question
or return a default response.
"""

from __future__ import annotations

import json


class MockJudgeServer:
    """Mock VLM judge server that returns canned responses.

    Usage:
        server = MockJudgeServer()
        server.set_response("What time is it?", rating=5, analysis="Correct time")
        result = server.judge("What time is it?", "It is 1pm", {})
        assert result["rating"] == 5
    """

    def __init__(self, default_rating: int = 3, default_analysis: str = "Mock judge response"):
        self._responses: dict[str, dict] = {}
        self._default_rating = default_rating
        self._default_analysis = default_analysis
        self.call_log: list[tuple] = []

    def set_response(self, question: str, rating: int, analysis: str = ""):
        """Set the judge response for a specific question."""
        self._responses[question] = {"rating": rating, "analysis": analysis}

    def judge(self, question: str, ai_response: str, metadata: dict) -> dict:
        """Return a canned judge response.

        Returns:
            Dict with "rating" (int) and "analysis" (str) keys.
        """
        self.call_log.append((question, ai_response))
        if question in self._responses:
            return dict(self._responses[question])
        return {"rating": self._default_rating, "analysis": self._default_analysis}

    def judge_json(self, question: str, ai_response: str, metadata: dict) -> str:
        """Return a JSON-encoded judge response (matching the real API)."""
        result = self.judge(question, ai_response, metadata)
        return json.dumps({
            "question": question,
            "analysis": result["analysis"],
            "rating": result["rating"],
        }, ensure_ascii=False)

    def reset(self):
        """Clear all configured responses and call log."""
        self._responses = {}
        self.call_log = []
        self._default_rating = 3
        self._default_analysis = "Mock judge response"
