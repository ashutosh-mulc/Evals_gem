#!/usr/bin/env python3
"""One-time script: extracts all prompts from judge_prompts.py into JSON files.

Run from project root:
    python3 judge_worker/prompts/_extract_prompts.py
"""
import json
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from judge_worker.judge_prompts import (
    app_eval_prompt,
    qa_prompt,
    vqa_prompt,
    vqa_mistake_prompt,
    hallucination_vqa_prompt,
)

PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_EVAL_DIR = os.path.join(PROMPTS_DIR, "app_eval")
os.makedirs(APP_EVAL_DIR, exist_ok=True)

# Sentinels for the device lambda (unique strings that won't appear in real data)
SENT_DEVICE_INFO = "<<DEVICE_INFO_JSON>>"
SENT_PRE_INFO = "<<DEVICE_INFO_PRE_JSON>>"
SENT_QTYPE = "<<QUESTION_TYPE>>"

# -- app_eval_prompt --
for key, value in app_eval_prompt["1.0"].items():
    filepath = os.path.join(APP_EVAL_DIR, f"{key}.json")

    if callable(value):
        # device lambda -- call with sentinels to capture both branches
        result_with_pre = value(SENT_DEVICE_INFO, SENT_PRE_INFO, SENT_QTYPE)
        result_without_pre = value(SENT_DEVICE_INFO, None, SENT_QTYPE)
        data = {
            "type": "dynamic",
            "template_with_pre": result_with_pre,
            "template_without_pre": result_without_pre,
            "sentinels": {
                "device_info_json": SENT_DEVICE_INFO,
                "device_info_pre_json": SENT_PRE_INFO,
                "question_type": SENT_QTYPE,
            },
        }
    elif isinstance(value, dict):
        # googlemaps sub-prompts
        data = value
    else:
        # plain string prompt
        data = {"prompt": value}

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  wrote app_eval/{key}.json")

# -- standalone prompt dicts --
for name, prompt_dict in [
    ("qa", qa_prompt),
    ("vqa", vqa_prompt),
    ("vqa_mistake", vqa_mistake_prompt),
    ("hallucination_vqa", hallucination_vqa_prompt),
]:
    filepath = os.path.join(PROMPTS_DIR, f"{name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(prompt_dict, f, indent=2, ensure_ascii=False)
    print(f"  wrote {name}.json")

print("\nDone! All prompts extracted to JSON.")
