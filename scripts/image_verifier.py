#!/usr/bin/env python3
"""
ImageVerifier — Uses a multimodal LLM to verify before/after screenshots.

Sends before/after screenshots to a vision-language model and asks it to verify
that the expected state change occurred. This catches false positives from the
state collector (e.g., state collector says "pass" but screen doesn't show it).

Usage:
    verifier = ImageVerifier(judge_url="http://107.99.238.186:8282/v1")
    result = verifier.verify(
        before_path="screenshot_before.png",
        after_path="screenshot_after.png",
        question_type="online_device_volume_up",
        question="Turn it up",
    )
    # result = {"match": True, "description": "Volume slider visible at higher position", "confidence": 0.9}
"""

from __future__ import annotations

import base64
import json
import os
import requests
from typing import Optional


# Prompt templates for different question type categories
PROMPT_TEMPLATES = {
    "volume": "Compare these two screenshots of a device screen. The user asked to '{question}'. "
              "In the 'after' screenshot, has the volume level changed as expected? "
              "Describe what you see in each screenshot and whether the volume indicator changed.",

    "battery": "Compare these two screenshots. The user asked '{question}'. "
              "Does the 'after' screenshot show the battery level information? "
              "Describe what you see.",

    "datetime": "Compare these two screenshots. The user asked '{question}'. "
                "Does the 'after' screenshot show the current time/date information? "
                "Describe what you see.",

    "camera": "Compare these two screenshots. The user asked to '{question}'. "
              "In the 'after' screenshot, was a photo taken or video recording started/stopped? "
              "Describe what you see in each screenshot.",

    "notes": "Compare these two screenshots of a notes app. The user asked to '{question}'. "
             "In the 'after' screenshot, was a note created, modified, or deleted as expected? "
             "Describe what changed.",

    "reminder": "Compare these two screenshots of a reminders app. The user asked to '{question}'. "
                "In the 'after' screenshot, was a reminder created, modified, or deleted? "
                "Describe what changed.",

    "calendar": "Compare these two screenshots of a calendar app. The user asked to '{question}'. "
                "In the 'after' screenshot, was a calendar event created, modified, or deleted? "
                "Describe what changed.",

    "clock": "Compare these two screenshots of a clock app. The user asked to '{question}'. "
             "In the 'after' screenshot, was a timer/alarm/stopwatch action performed? "
             "Describe what changed.",

    "message": "Compare these two screenshots of a messaging app. The user asked to '{question}'. "
               "In the 'after' screenshot, was a message sent, drafted, or read? "
               "Describe what changed.",

    "call": "Compare these two screenshots. The user asked to '{question}'. "
            "In the 'after' screenshot, was a call initiated? Describe what you see.",

    "translate": "Compare these two screenshots. The user asked to '{question}'. "
                 "In the 'after' screenshot, is the translation app open and showing a translation? "
                 "Describe what you see.",

    "maps": "Compare these two screenshots. The user asked to '{question}'. "
            "In the 'after' screenshot, is Google Maps showing navigation or search results? "
            "Describe what you see.",

    "music": "Compare these two screenshots. The user asked to '{question}'. "
             "In the 'after' screenshot, is music playing or a playlist created? "
             "Describe what you see.",

    "default": "Compare these two screenshots. The user asked to '{question}'. "
               "In the 'after' screenshot, did the expected action occur? "
               "Describe what you see in each screenshot and whether the expected change happened.",
}


def _get_prompt(question_type: str, question: str) -> str:
    """Get the appropriate prompt template based on question_type."""
    qt_lower = question_type.lower()
    for keyword, template in PROMPT_TEMPLATES.items():
        if keyword in qt_lower:
            return template.format(question=question)
    return PROMPT_TEMPLATES["default"].format(question=question)


def _encode_image(path: str) -> str:
    """Encode an image file as base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


class ImageVerifier:
    """Uses a multimodal LLM to verify before/after screenshots."""

    def __init__(
        self,
        judge_url: str = "http://107.99.238.186:8282/v1",
        model: str = "Qwen/Qwen2-VL-72B-Instruct",
        timeout: int = 30,
    ):
        """
        Args:
            judge_url: URL of the multimodal LLM API (OpenAI-compatible /v1 endpoint).
            model: Model name to use for image analysis.
            timeout: Request timeout in seconds.
        """
        self.judge_url = judge_url
        self.model = model
        self.timeout = timeout

    def verify(
        self,
        before_path: str,
        after_path: str,
        question_type: str,
        question: str,
    ) -> dict:
        """
        Verify that the expected state change occurred between before/after screenshots.

        Args:
            before_path: Path to the before screenshot.
            after_path: Path to the after screenshot.
            question_type: The question type (e.g., "online_device_volume_up").
            question: The original question text.

        Returns:
            Dict with:
                - "match": bool — whether the expected change is visible
                - "description": str — LLM's description of what it sees
                - "confidence": float — confidence score (0-1)
                - "error": str or None — error message if verification failed
        """
        # Check files exist
        if not os.path.exists(before_path):
            return {"match": False, "description": "", "confidence": 0.0,
                    "error": f"Before screenshot not found: {before_path}"}
        if not os.path.exists(after_path):
            return {"match": False, "description": "", "confidence": 0.0,
                    "error": f"After screenshot not found: {after_path}"}

        prompt = _get_prompt(question_type, question)

        try:
            before_b64 = _encode_image(before_path)
            after_b64 = _encode_image(after_path)

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "text", "text": "BEFORE screenshot:"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{before_b64}"}},
                            {"type": "text", "text": "AFTER screenshot:"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{after_b64}"}},
                            {"type": "text", "text": "Respond in JSON format: {\"match\": true/false, \"description\": \"...\", \"confidence\": 0.0-1.0}"},
                        ],
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.1,
            }

            response = requests.post(
                f"{self.judge_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result_text = response.json()["choices"][0]["message"]["content"]

            # Try to parse JSON from the response
            try:
                # Find JSON in the response
                import re
                json_match = re.search(r'\{[^}]+\}', result_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(result_text)
            except (json.JSONDecodeError, KeyError):
                # If JSON parsing fails, return raw text
                return {
                    "match": False,
                    "description": result_text,
                    "confidence": 0.0,
                    "error": "Failed to parse LLM response as JSON",
                }

            return {
                "match": result.get("match", False),
                "description": result.get("description", ""),
                "confidence": float(result.get("confidence", 0.0)),
                "error": None,
            }

        except requests.exceptions.RequestException as e:
            return {"match": False, "description": "", "confidence": 0.0,
                    "error": f"Request failed: {e}"}
        except Exception as e:
            return {"match": False, "description": "", "confidence": 0.0,
                    "error": f"Unexpected error: {e}"}

    def verify_single(
        self,
        image_path: str,
        question_type: str,
        question: str,
        expected_description: str = "",
    ) -> dict:
        """
        Verify a single screenshot against expected state.

        Args:
            image_path: Path to the screenshot.
            question_type: The question type.
            question: The original question text.
            expected_description: What the screen should show.

        Returns:
            Dict with match, description, confidence, error.
        """
        if not os.path.exists(image_path):
            return {"match": False, "description": "", "confidence": 0.0,
                    "error": f"Screenshot not found: {image_path}"}

        prompt = f"The user asked: '{question}'. Expected: {expected_description}. "
        prompt += "Does this screenshot show the expected result? "
        prompt += 'Respond in JSON: {"match": true/false, "description": "...", "confidence": 0.0-1.0}'

        try:
            img_b64 = _encode_image(image_path)
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                        ],
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            }

            response = requests.post(
                f"{self.judge_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result_text = response.json()["choices"][0]["message"]["content"]

            try:
                import re
                json_match = re.search(r'\{[^}]+\}', result_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(result_text)
            except (json.JSONDecodeError, KeyError):
                return {"match": False, "description": result_text, "confidence": 0.0,
                        "error": "Failed to parse LLM response as JSON"}

            return {
                "match": result.get("match", False),
                "description": result.get("description", ""),
                "confidence": float(result.get("confidence", 0.0)),
                "error": None,
            }

        except Exception as e:
            return {"match": False, "description": "", "confidence": 0.0,
                    "error": f"Unexpected error: {e}"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Image Verifier")
    parser.add_argument("--before", help="Path to before screenshot")
    parser.add_argument("--after", help="Path to after screenshot")
    parser.add_argument("--question-type", default="default", help="Question type")
    parser.add_argument("--question", default="", help="Question text")
    parser.add_argument("--judge-url", default="http://107.99.238.186:8282/v1")
    args = parser.parse_args()

    verifier = ImageVerifier(judge_url=args.judge_url)
    result = verifier.verify(args.before, args.after, args.question_type, args.question)
    print(json.dumps(result, indent=2))
