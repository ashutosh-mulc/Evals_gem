"""
Offline: ask the judge LLM what device state each dataset row needs, and how the
simulated user should answer confirmations. Writes a NEW dataset file for review;
runtime never guesses (see apps/setup_state.py, agent_testers/conversation.py).

    python scripts/gen_setup.py configs/jinju_gemini_config.json --out data/datasets/with_setup.jsonl

Rows that already have "setup"/"consent"/"followups" keep them. Follow-up lines are
written as {"text": ...}; render their "audio" with VoxCPM like the questions
(the conversation loop ignores follow-ups without audio).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

from common.question_type import QuestionType
from utils.file_utils import JSONFileManager, JSONLFileManager

# Only these apps can have their state built through XRClaw (see apps/setup_state.py).
KIND_BY_APP = {
    "clockalarm": "alarms",
    "samsungnote": "notes",
    "samsungreminder": "reminders",
    "clocktimer": "timers",
    "samsungcalendar": "events",
}

PROMPT = """You prepare a Samsung phone before a voice assistant is asked a query.
Query: {question}
Query type: {question_type}

Return JSON only: {{"setup": {{...}}, "consent": "yes" | "no" | null, "followups": [...]}}

setup: items that must ALREADY exist for the query to make sense, else {{}}.
  "delete the 6PM alarm" -> {{"alarms": [{{"time": "18:00", "label": ""}}]}};  "create a note ..." -> {{}}.
  Allowed kind for this query: {kind}. Item fields:
    alarms:    {{"time": "HH:MM" (24h), "label": str}}
    notes:     {{"title": str, "content": str}}
    reminders: {{"title": str, "description": str}}
    timers:    {{"duration_seconds": int, "label": str}}
    events:    {{"title": str, "description": str, "start_datetime": "yyyy-MM-ddTHH:mm:ss", "end_datetime": "yyyy-MM-ddTHH:mm:ss"}}
consent: the user's answer if the assistant asks to confirm. "yes" normally; null when the
  assistant asking a question IS the expected outcome (ambiguous or unknown contact).
followups: things the user says in later turns; [] for a single-turn query (at most 2)."""


def suggest(client, model, row) -> dict:
    kind = KIND_BY_APP.get(QuestionType.parse(row.get("question_type", "")).app_key)
    reply = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user", "content": PROMPT.format(
            question=row["question"], question_type=row["question_type"], kind=kind or "none (return {})")}],
    ).choices[0].message.content
    out = json.loads(reply[reply.find("{"): reply.rfind("}") + 1])
    # Never trust kinds the app can't build.
    out["setup"] = {k: v for k, v in (out.get("setup") or {}).items() if k == kind}
    out["followups"] = [{"text": t} for t in (out.get("followups") or [])[:2]]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config")
    parser.add_argument("--dataset", help="defaults to config paths.dataset_file")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = JSONFileManager.load_file(args.config)
    header, rows = JSONLFileManager.load_file(args.dataset or config["paths"]["dataset_file"])
    client = OpenAI(api_key="EMPTY", base_url=config["urls"]["judge_url"])
    model = client.models.list().data[0].id

    for row in rows:
        try:
            suggestion = suggest(client, model, row)
        except Exception as e:
            print(f"{row['eval_id']}: FAILED ({e}), row left unchanged")
            continue
        for key, value in suggestion.items():
            row.setdefault(key, value)
        print(f"{row['eval_id']}  {row['question']!r}\n    setup={row['setup']} consent={row['consent']} "
              f"followups={[f['text'] for f in row['followups']]}")

    JSONLFileManager.dump_file(header, rows, args.out)
    print(f"\nWrote {len(rows)} rows to {args.out}. Review before use.")


if __name__ == "__main__":
    main()
