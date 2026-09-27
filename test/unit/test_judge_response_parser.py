"""
Unit tests for judge_worker.judge_response_parser.parse_judge_response()

Tests cover all observed real-world judge response formats:
  - Clean JSON with double quotes
  - Markdown-fenced JSON (```json ... ```)
  - Python dict repr with single quotes (from dummy response generator)
  - JSON embedded in surrounding text
  - Plain text with no structured data
  - Empty / malformed inputs
  - Edge cases: N/A ratings, nested quotes, multiline analysis
"""

import pytest
from judge_worker.judge_response_parser import parse_judge_response


# ── Clean JSON ──────────────────────────────────────────────────────

class TestCleanJSON:
    """Tests for clean JSON responses with double quotes."""

    def test_json_analysis_first(self):
        """Analysis key before rating key (most common real format)."""
        content = '{ "question": "Turn it up", "analysis": "Volume was at max.", "rating": 5 }'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Volume was at max."
        assert rating == 5

    def test_json_rating_first(self):
        """Rating key before analysis key."""
        content = '{"rating": 3, "analysis": "Partial response.", "question": "What time is it?"}'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Partial response."
        assert rating == 3

    def test_json_with_escaped_quotes_in_analysis(self):
        """Analysis text containing escaped single quotes."""
        content = """{"question": "Open Call app", "analysis": "The AI said 'phone app' because it couldn't find a 'call app'.", "rating": 4}"""
        analysis, rating = parse_judge_response(content)
        assert "phone app" in analysis
        assert rating == 4

    def test_json_multiline_analysis(self):
        """Analysis text spanning multiple lines."""
        content = """{"question": "Q", "analysis": "Line 1.\\nLine 2.\\nLine 3.", "rating": 2}"""
        analysis, rating = parse_judge_response(content)
        assert "Line 1" in analysis
        assert "Line 3" in analysis
        assert rating == 2

    def test_json_extra_whitespace(self):
        """JSON with extra whitespace and newlines."""
        content = """
        {
            "question": "Q",
            "analysis": "Some analysis",
            "rating": 1
        }
        """
        analysis, rating = parse_judge_response(content)
        assert analysis == "Some analysis"
        assert rating == 1


# ── Markdown Fenced JSON ─────────────────────────────────────────────

class TestMarkdownFenced:
    """Tests for JSON wrapped in ```json ... ``` fences (58 cases observed)."""

    def test_json_fence(self):
        """Standard ```json ... ``` fence."""
        content = '```json\n{\n  "question": "Open Call app",\n  "analysis": "Phone app is open.",\n  "rating": 5\n}\n```'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Phone app is open."
        assert rating == 5

    def test_plain_fence(self):
        """Plain ``` ... ``` fence without 'json' label."""
        content = '```\n{"analysis": "Done.", "rating": 4}\n```'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Done."
        assert rating == 4

    def test_fence_with_escaped_quotes(self):
        """Markdown-fenced JSON with escaped single quotes in analysis."""
        content = '```json\n{"analysis": "The AI said \'hello\' to the user.", "rating": 3}\n```'
        analysis, rating = parse_judge_response(content)
        assert "hello" in analysis
        assert rating == 3

    def test_fence_extra_text_after(self):
        """Markdown fence with trailing whitespace/newlines."""
        content = '```json\n{"analysis": "Trailing.", "rating": 5}\n```\n\n'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Trailing."
        assert rating == 5

    def test_fence_with_single_quotes_in_analysis(self):
        """Markdown-fenced JSON with single quotes inside analysis text.

        This is the real-world format from the user's evaluation data:
        the VLM wraps its response in ```json fences and the analysis
        contains apostrophes (e.g., 'John').
        """
        content = '''```json
{
  "question": "Can you call John ?",
  "analysis": "The user requested to call 'John'. The screenshot shows the Gemini AI app interface where the AI is asking for clarification ('What would you like to do regarding John?'). There is no evidence of a phone call being initiated, an active call screen, or a recent call log entry. The task was not completed as the AI did not place the call.",
  "rating": 0
}
```'''
        analysis, rating = parse_judge_response(content)
        assert rating == 0
        assert "call 'John'" in analysis
        assert "task was not completed" in analysis



# ── Python Dict Repr (Single Quotes) ───────────────────────────────

class TestPythonDictRepr:
    """Tests for Python dict repr with single quotes (17 cases observed).

    These come from __create_dummy_response_object() which formats using
    Python f-strings with single quotes.
    """

    def test_single_quote_dict(self):
        """Standard single-quote dict repr from dummy response."""
        content = "{'question': 'Read the items on my To Do list on samsung note','analysis': 'The ai_agent failed to give a valid response!','rating': '0'}"
        analysis, rating = parse_judge_response(content)
        assert analysis == "The ai_agent failed to give a valid response!"
        assert rating == 0

    def test_single_quote_dict_na_rating(self):
        """Single-quote dict with 'N/A' rating string."""
        content = "{'question': 'Q','analysis': 'Judge API failed: ConnectionError','rating': 'N/A'}"
        analysis, rating = parse_judge_response(content)
        assert analysis == "Judge API failed: ConnectionError"
        assert rating is None

    def test_single_quote_with_apostrophe_in_analysis(self):
        """Single-quote dict with apostrophe in analysis text."""
        content = "{'analysis': 'The AI couldn\\'t respond.', 'rating': '0'}"
        analysis, rating = parse_judge_response(content)
        assert "couldn't" in analysis
        assert rating == 0

    def test_single_quote_int_rating(self):
        """Single-quote dict with integer rating (no quotes around number)."""
        content = "{'analysis': 'Good response.', 'rating': 4}"
        analysis, rating = parse_judge_response(content)
        assert analysis == "Good response."
        assert rating == 4


# ── JSON Embedded in Text ───────────────────────────────────────────

class TestEmbeddedJSON:
    """Tests for JSON embedded in surrounding text."""

    def test_text_before_json(self):
        """Random text before the JSON object."""
        content = 'Here is my response:\n{"analysis": "Embedded.", "rating": 3}'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Embedded."
        assert rating == 3

    def test_text_after_json(self):
        """Random text after the JSON object."""
        content = '{"analysis": "Embedded.", "rating": 3}\n\nHope this helps!'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Embedded."
        assert rating == 3

    def test_text_around_json(self):
        """Text both before and after JSON."""
        content = 'Sure!\n{"analysis": "Middle.", "rating": 2}\nLet me know.'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Middle."
        assert rating == 2


# ── Plain Text (No JSON) ────────────────────────────────────────────

class TestPlainText:
    """Tests for plain text responses with no structured data."""

    def test_plain_text_no_json(self):
        """Plain text with no JSON structure."""
        content = "The ai_agent failed to give a valid response!"
        analysis, rating = parse_judge_response(content)
        assert analysis == content
        assert rating is None

    def test_empty_string(self):
        """Empty string input."""
        analysis, rating = parse_judge_response("")
        assert analysis is None
        assert rating is None

    def test_whitespace_only(self):
        """Whitespace-only string."""
        analysis, rating = parse_judge_response("   \n\t  ")
        assert analysis is None
        assert rating is None

    def test_none_input(self):
        """None input should not crash (defensive)."""
        # parse_judge_response checks for falsy, so None returns (None, None)
        analysis, rating = parse_judge_response(None)
        assert analysis is None
        assert rating is None


# ── LLM Artifacts ────────────────────────────────────────────────────

class TestLLMArtifacts:
    """Tests for common LLM response artifacts."""

    def test_begin_of_sentence_prefix(self):
        """VLM sometimes prepends <｜begin▁of▁sentence｜>."""
        content = '<｜begin▁of▁sentence｜>{"analysis": "Cleaned.", "rating": 5}'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Cleaned."
        assert rating == 5

    def test_markdown_fence_with_prefix(self):
        """Markdown fence with LLM prefix."""
        content = '<｜begin▁of▁sentence｜>```json\n{"analysis": "Fenced.", "rating": 4}\n```'
        analysis, rating = parse_judge_response(content)
        assert analysis == "Fenced."
        assert rating == 4


# ── Rating Edge Cases ───────────────────────────────────────────────

class TestRatingEdgeCases:
    """Tests for various rating value formats."""

    def test_rating_as_float_string(self):
        """Rating as a float string like '4.0'."""
        content = '{"analysis": "A.", "rating": 4.0}'
        analysis, rating = parse_judge_response(content)
        assert rating == 4

    def test_rating_as_float(self):
        """Rating as a JSON float."""
        content = '{"analysis": "A.", "rating": 4.5}'
        analysis, rating = parse_judge_response(content)
        assert rating == 4  # int(4.5) == 4

    def test_rating_na_string(self):
        """Rating as 'N/A' string."""
        content = '{"analysis": "Failed.", "rating": "N/A"}'
        analysis, rating = parse_judge_response(content)
        assert rating is None

    def test_rating_missing(self):
        """No rating key in JSON."""
        content = '{"analysis": "No rating given.", "question": "Q"}'
        analysis, rating = parse_judge_response(content)
        assert analysis == "No rating given."
        assert rating is None

    def test_rating_zero(self):
        """Rating of 0 (valid, means failure)."""
        content = '{"analysis": "Complete failure.", "rating": 0}'
        analysis, rating = parse_judge_response(content)
        assert rating == 0
        assert analysis == "Complete failure."


# ── Analysis Edge Cases ─────────────────────────────────────────────

class TestAnalysisEdgeCases:
    """Tests for analysis text edge cases."""

    def test_analysis_missing(self):
        """No analysis key in JSON."""
        content = '{"question": "Q", "rating": 3}'
        analysis, rating = parse_judge_response(content)
        assert analysis is None
        assert rating == 3

    def test_analysis_empty_string(self):
        """Analysis is an empty string."""
        content = '{"analysis": "", "rating": 2}'
        analysis, rating = parse_judge_response(content)
        assert analysis == ""
        assert rating == 2

    def test_analysis_with_braces(self):
        """Analysis text containing curly braces (could confuse JSON parser)."""
        content = '{"analysis": "The state changed from {volume: 5} to {volume: 10}.", "rating": 5}'
        analysis, rating = parse_judge_response(content)
        assert "{volume: 5}" in analysis
        assert rating == 5

    def test_analysis_with_newlines(self):
        """Analysis with literal newlines (not \\n escape)."""
        content = '{"analysis": "Line one\nLine two", "rating": 3}'
        analysis, rating = parse_judge_response(content)
        # json.loads should handle literal newlines in strings (invalid JSON, but our parser tries literal_eval too)
        assert rating == 3


# ── Real-World Scenarios ────────────────────────────────────────────

class TestRealWorldScenarios:
    """Tests based on actual data observed in the evaluation database."""

    def test_q00001_clean_json(self):
        """Actual q00001 response (clean JSON, analysis first)."""
        content = '{ "question": "Turn it up", "analysis": "The user requested to increase the volume. According to the device_info, the volume was already at maximum (current: 100, max: 100) in both pre and post states. The guidelines specify that if the volume is already at maximum and the user asks to increase, this is an edge case where no change is possible, and the rating should be 5.", "rating": 5 }'
        analysis, rating = parse_judge_response(content)
        assert rating == 5
        assert "volume was already at maximum" in analysis

    def test_q00038_markdown_fenced(self):
        """Actual q00038 response (markdown-fenced JSON)."""
        content = '```json\n{\n  "question": "Open Call app",\n  "analysis": "The user requested to open the Call app. The Phone app is open.",\n  "rating": 5\n}\n```'
        analysis, rating = parse_judge_response(content)
        assert rating == 5
        assert "Phone app is open" in analysis

    def test_q00070_single_quote_dict(self):
        """Actual q00070 response (Python dict repr with single quotes)."""
        content = "{'question': 'Read the items on my To Do list on samsung note','analysis': 'The ai_agent failed to give a valid response!','rating': '0'}"
        analysis, rating = parse_judge_response(content)
        assert rating == 0
        assert analysis == "The ai_agent failed to give a valid response!"

    def test_dummy_response_format(self):
        """Format produced by __create_dummy_response_object."""
        content = "{'question': 'Can you call Max on WhatsApp','analysis': 'The ai_agent failed to give a valid response!','rating': '0'}"
        analysis, rating = parse_judge_response(content)
        assert rating == 0
        assert "failed to give a valid response" in analysis

    def test_judge_api_error_format(self):
        """Format produced when judge API fails (N/A rating)."""
        content = "{'question': 'Q','analysis': 'Judge API failed: ConnectionError: timeout','rating': 'N/A'}"
        analysis, rating = parse_judge_response(content)
        assert rating is None
        assert "Judge API failed" in analysis


# ── Return Type Contract ────────────────────────────────────────────

class TestReturnType:
    """Verify the return type contract is always (str|None, int|None)."""

    def test_return_types_from_json(self):
        content = '{"analysis": "A.", "rating": 3}'
        analysis, rating = parse_judge_response(content)
        assert isinstance(analysis, str)
        assert isinstance(rating, int)

    def test_return_types_from_markdown(self):
        content = '```json\n{"analysis": "B.", "rating": 4}\n```'
        analysis, rating = parse_judge_response(content)
        assert isinstance(analysis, str)
        assert isinstance(rating, int)

    def test_return_types_from_single_quote(self):
        content = "{'analysis': 'C.', 'rating': '2'}"
        analysis, rating = parse_judge_response(content)
        assert isinstance(analysis, str)
        assert isinstance(rating, int)

    def test_return_types_from_plain_text(self):
        content = "Just some text"
        analysis, rating = parse_judge_response(content)
        assert isinstance(analysis, str)
        assert rating is None

    def test_return_types_from_empty(self):
        analysis, rating = parse_judge_response("")
        assert analysis is None
        assert rating is None
