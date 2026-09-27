"""
Judge response parser — robustly extracts rating and analysis from VLM/LLM judge responses.

The judge (VLM/LLM) returns responses in various formats:
  - Clean JSON:          {"question": "...", "analysis": "...", "rating": 5}
  - Markdown-fenced JSON: ```json\n{...}\n```
  - Python dict repr:     {'question': '...', 'analysis': '...', 'rating': '0'}
  - Plain text:           "The ai_agent failed to give a valid response!"
  - Empty / malformed

This module provides a single entry point ``parse_judge_response()`` that handles
all of these cases and returns ``(analysis, rating)`` where ``analysis`` is a string
(or None) and ``rating`` is an int (or None).
"""

import ast
import json
import re
import logging

logger = logging.getLogger(__name__)


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences from text."""
    # Match ```json\n...\n``` or ```\n...\n```
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```\s*$"
    match = re.match(pattern, text.strip(), re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_json_block(text: str) -> str | None:
    """Extract the first JSON object ({...}) from text that may contain extra content."""
    # Find the first { and matching }
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_parse_json(text: str) -> dict | None:
    """Try to parse text as JSON, return dict or None."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _try_parse_python_dict(text: str) -> dict | None:
    """Try to parse text as a Python dict literal (handles single quotes).

    Uses ``ast.literal_eval`` which safely evaluates Python literals.
    """
    try:
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass
    return None


def _extract_rating(data: dict) -> int | None:
    """Extract and normalize rating from a parsed dict."""
    rating = data.get("rating")
    if rating is None:
        return None
    if isinstance(rating, int):
        return rating
    if isinstance(rating, float):
        return int(rating)
    if isinstance(rating, str):
        rating = rating.strip()
        if rating.lower() in ("n/a", "na", "none", ""):
            return None
        try:
            return int(rating)
        except ValueError:
            try:
                return int(float(rating))
            except ValueError:
                logger.warning("Could not parse rating string: %r", rating)
                return None
    return None


def _extract_analysis(data: dict) -> str | None:
    """Extract analysis text from a parsed dict."""
    analysis = data.get("analysis")
    if analysis is None:
        return None
    return str(analysis)


def _regex_fallback(text: str) -> tuple[str | None, int | None]:
    """Last-resort regex extraction when structured parsing fails."""
    # Try to find rating
    rating = None
    rating_match = re.search(r'[\'"]?rating[\'"]?\s*:\s*[\'"]?(\d+)[\'"]?', text, re.IGNORECASE)
    if rating_match:
        rating = int(rating_match.group(1))

    # Try to find analysis
    analysis = None
    analysis_match = re.search(
        r'[\'"]?analysis[\'"]?\s*:\s*[\'"](.*?)[\'"]\s*[,}]',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if analysis_match:
        analysis = analysis_match.group(1)

    return analysis, rating


def parse_judge_response(content: str) -> tuple[str | None, int | None]:
    """Parse a judge response string and extract (analysis, rating).

    Handles multiple formats:
      - Clean JSON with double quotes
      - Markdown-fenced JSON (```json ... ```)
      - Python dict repr with single quotes
      - Text with embedded JSON
      - Plain text with no structured data

    Args:
        content: Raw response string from the judge VLM/LLM.

    Returns:
        Tuple of (analysis, rating). Both may be None if parsing fails.
    """
    if not content or not content.strip():
        return None, None

    # Strip any leading/trailing whitespace
    text = content.strip()

    # Remove common LLM artifacts
    # e.g., "<｜begin▁of▁sentence｜>" prefix
    text = re.sub(r"<[｜\w]+>", "", text).strip()

    # Step 1: Strip markdown fences
    text = _strip_markdown_fences(text)

    # Step 2: Try direct JSON parse
    parsed = _try_parse_json(text)
    if parsed is not None:
        return _extract_analysis(parsed), _extract_rating(parsed)

    # Step 3: Try Python dict literal (single quotes)
    parsed = _try_parse_python_dict(text)
    if parsed is not None:
        return _extract_analysis(parsed), _extract_rating(parsed)

    # Step 4: Extract JSON block from surrounding text
    json_block = _extract_json_block(text)
    if json_block:
        parsed = _try_parse_json(json_block)
        if parsed is not None:
            return _extract_analysis(parsed), _extract_rating(parsed)
        parsed = _try_parse_python_dict(json_block)
        if parsed is not None:
            return _extract_analysis(parsed), _extract_rating(parsed)

    # Step 5: Regex fallback
    analysis, rating = _regex_fallback(text)
    if analysis is not None or rating is not None:
        return analysis, rating

    # Step 6: Return raw text as analysis with no rating
    logger.debug("Could not parse judge response, returning raw text as analysis")
    return text, None
