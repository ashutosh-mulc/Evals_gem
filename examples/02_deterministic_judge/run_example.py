#!/usr/bin/env python3
"""
Example 02: Deterministic Judge — Battery & Volume Queries

This example demonstrates how the DeterministicJudge evaluates device
queries (battery, volume) without an LLM, by comparing TTS responses
against grounding device state.

Flow:
  1. Build metadata with pre/post device state
  2. Run DeterministicJudge on a battery query
  3. Run DeterministicJudge on a volume up query
  4. Print results

Run:
    python examples/02_deterministic_judge/run_example.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from judge_worker.deterministic_judge import DeterministicJudge


def build_metadata(question_type, pre_battery=75, post_battery=75,
                   pre_volume=5, post_volume=7):
    """Build metadata dict in the format DeterministicJudge expects."""
    jinju_pre = {
        "battery": {"level": pre_battery, "status": "Discharging", "charging": False},
        "time": {"datetime_str": "Mon Aug 25 13:00:00 IST 2026", "timezone": "IST", "epoch_ms": 1756110000000},
        "date": {"day": 25, "month": "Aug", "year": 2026, "day_of_week": "Mon"},
        "volume": {"muted": False, "min": 0, "max": 15, "current": pre_volume},
        "dnd_mode": "false",
    }
    jinju_post = {
        "battery": {"level": post_battery, "status": "Discharging", "charging": False},
        "time": {"datetime_str": "Mon Aug 25 13:00:00 IST 2026", "timezone": "IST", "epoch_ms": 1756110000000},
        "date": {"day": 25, "month": "Aug", "year": 2026, "day_of_week": "Mon"},
        "volume": {"muted": False, "min": 0, "max": 15, "current": post_volume},
        "dnd_mode": "false",
    }
    return {
        "question_type": question_type,
        "device_info_pre": {"jinju": jinju_pre, "companion": {}},
        "device_info_post": {"jinju": jinju_post, "companion": {}},
    }


def main():
    print("=" * 60)
    print("Example 02: Deterministic Judge — Battery & Volume")
    print("=" * 60)

    judge = DeterministicJudge()

    # ── Battery query ──
    print("\n--- Battery Query ---")
    metadata = build_metadata("online_device_battery_glasses", post_battery=75)
    result = judge.evaluate(
        "online_device_battery_glasses",
        "What's my battery level?",
        "Your battery is at 75 percent",
        metadata,
    )
    if result:
        response_json, entropy = result
        response = json.loads(response_json)
        print(f"  Rating:   {response['rating']}")
        print(f"  Analysis: {response['analysis']}")
    else:
        print("  Not handled by DeterministicJudge")

    # ── Volume up query ──
    print("\n--- Volume Up Query ---")
    metadata = build_metadata("online_device_volume_up", pre_volume=5, post_volume=7)
    result = judge.evaluate(
        "online_device_volume_up",
        "Turn up the volume",
        "Volume increased",
        metadata,
    )
    if result:
        response_json, entropy = result
        response = json.loads(response_json)
        print(f"  Rating:   {response['rating']}")
        print(f"  Analysis: {response['analysis']}")
    else:
        print("  Not handled by DeterministicJudge")

    # ── Volume up — unchanged (should fail) ──
    print("\n--- Volume Up Query (unchanged — should fail) ---")
    metadata = build_metadata("online_device_volume_up", pre_volume=7, post_volume=7)
    result = judge.evaluate(
        "online_device_volume_up",
        "Turn up the volume",
        "Volume increased",
        metadata,
    )
    if result:
        response_json, entropy = result
        response = json.loads(response_json)
        print(f"  Rating:   {response['rating']}")
        print(f"  Analysis: {response['analysis']}")
    else:
        print("  Not handled by DeterministicJudge")


if __name__ == "__main__":
    main()
