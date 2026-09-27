"""
Judge prompts module — loads prompts from app directories and JSON files.

App-specific evaluation prompts are co-located with each app in
``apps/<app_dir>/prompt.json`` and discovered by the registry into
``apps.JUDGE_PROMPTS``.  This module post-processes them into the
``app_eval_prompt`` dict that consumers expect:

    - app_eval_prompt   (dict keyed by version, then by app name)
    - qa_prompt         (dict keyed by version)
    - vqa_prompt        (dict keyed by version)
    - vqa_mistake_prompt (dict keyed by version)
    - hallucination_vqa_prompt (dict keyed by version)

The ``device`` entry inside ``app_eval_prompt`` is a callable (lambda) that
accepts ``(device_info_json, device_info_pre_json=None, question_type="")`` and
returns the assembled prompt string.  This preserves backward compatibility with
code that calls it as a function.
"""
import json
import os

from apps import JUDGE_PROMPTS as _RAW_APP_PROMPTS
from apps.judge_helpers import BASE_JUDGE_TEMPLATE

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def _load_json(filepath):
    """Load a JSON file and return its contents."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_device_lambda(data):
    """Build a callable that reproduces the original device lambda from JSON templates.

    The JSON stores two template strings (with and without pre-device-info) plus
    sentinel placeholders.  At call time we replace the sentinels with the actual
    arguments and return the appropriate template.
    """
    template_with_pre = data["template_with_pre"]
    template_without_pre = data["template_without_pre"]
    sentinels = data["sentinels"]
    sent_device = sentinels["device_info_json"]
    sent_pre = sentinels["device_info_pre_json"]
    sent_qtype = sentinels["question_type"]

    def _device_prompt(device_info_json, device_info_pre_json=None, question_type=""):
        if device_info_pre_json:
            template = template_with_pre
        else:
            template = template_without_pre
        return (
            template
            .replace(sent_device, device_info_json)
            .replace(sent_pre, device_info_pre_json or "")
            .replace(sent_qtype, question_type)
        )

    return _device_prompt


# ── Build app_eval_prompt from apps.JUDGE_PROMPTS ───────────────────────────
# JUDGE_PROMPTS stores raw JSON data per app_key. We post-process each entry
# the same way the old file-based loader did:
#   - "type": "dynamic" → callable lambda (device)
#   - dict with "prompt" key → string (join if list)
#   - other dict → stored as-is (e.g. googlemaps mode-specific prompts)
app_eval_prompt = {"1.0": {}}

def _inject_base_template(prompt_str):
    """If prompt references <<BASE_JUDGE_TEMPLATE>>, replace it with the actual template.
    
    This allows app prompt.json files to explicitly define where the base template
    should be inserted using the <<BASE_JUDGE_TEMPLATE>> placeholder.
    """
    if isinstance(prompt_str, str) and "<<BASE_JUDGE_TEMPLATE>>" in prompt_str:
        return prompt_str.replace("<<BASE_JUDGE_TEMPLATE>>", BASE_JUDGE_TEMPLATE)
    elif isinstance(prompt_str, str) and "BASE_JUDGE_TEMPLATE" in prompt_str:
        # Backward compatibility: handle old format that references BASE_JUDGE_TEMPLATE
        # Remove the "Use the..." instruction and prepend the template
        return BASE_JUDGE_TEMPLATE + "\n\n" + prompt_str.replace("Use the BASE_JUDGE_TEMPLATE from judge_helpers.py.\n\n", "")
    return prompt_str


for _app_key, _data in _RAW_APP_PROMPTS.items():
    if isinstance(_data, dict) and _data.get("type") == "dynamic":
        # device lambda
        app_eval_prompt["1.0"][_app_key] = _make_device_lambda(_data)
    elif isinstance(_data, dict) and "prompt" in _data:
        # plain string prompt (some originals were tuples → JSON lists; join them)
        _prompt_val = _data["prompt"]
        if isinstance(_prompt_val, list):
            _prompt_val = "".join(_prompt_val)
        # Inject BASE_JUDGE_TEMPLATE if referenced
        _prompt_val = _inject_base_template(_prompt_val)
        app_eval_prompt["1.0"][_app_key] = _prompt_val
    else:
        # dict of mode-keyed sub-prompts (e.g. googlemaps, samsungcamera).
        # Inject BASE_JUDGE_TEMPLATE into each mode's string independently —
        # the resolver (_resolve_app_eval_prompt) looks up app_prompt[app_mode],
        # so every mode key must remain present and each value must stay a string.
        app_eval_prompt["1.0"][_app_key] = {
            _mode: _inject_base_template(_mode_prompt)
            for _mode, _mode_prompt in _data.items()
        }

# ── Special: notifications prompt (not an app, lives in apps/device/) ─────────
_notifications_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "apps", "device", "prompt_notifications.json",
)
if os.path.exists(_notifications_path):
    _notif_data = _load_json(_notifications_path)
    _notif_prompt = _notif_data.get("prompt", _notif_data)
    if isinstance(_notif_prompt, list):
        _notif_prompt = "".join(_notif_prompt)
    app_eval_prompt["1.0"]["notifications"] = _notif_prompt

# ── Build standalone prompt dicts ────────────────────────────────────────────
qa_prompt = _load_json(os.path.join(_PROMPTS_DIR, "qa.json"))

vqa_prompt = _load_json(os.path.join(_PROMPTS_DIR, "vqa.json"))
vqa_mistake_prompt = _load_json(os.path.join(_PROMPTS_DIR, "vqa_mistake.json"))
hallucination_vqa_prompt = _load_json(os.path.join(_PROMPTS_DIR, "hallucination_vqa.json"))
