#!/usr/bin/env python3
"""
run_batch.py — Batch runner for reliability testing by question type category.

Groups dataset entries by question type and runs them in batches.
Useful for systematically validating each app/feature category.

Usage:
    # Run all volume-related questions, 3 runs each
    python scripts/run_batch.py --filter volume --runs 3 --config configs/jinju_gemini_config.json

    # Run all device-control questions (volume, battery, datetime)
    python scripts/run_batch.py --group device --runs 2

    # Run first 5 questions of each category (quick smoke test)
    python scripts/run_batch.py --per-category 5 --runs 1

    # Dry run to see what would be executed
    python scripts/run_batch.py --filter volume --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.run_test_case import load_dataset, run_single
from common.question_type import QuestionType


def group_by_category(dataset: dict[str, dict]) -> dict[str, list[str]]:
    """Group eval_ids by their question type category (group_feature)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for eval_id, entry in dataset.items():
        qt = QuestionType.parse(entry.get("question_type", ""))
        category = f"{qt.group}_{qt.feature}" if qt.group and qt.feature else "unknown"
        groups[category].append(eval_id)
    return dict(groups)


def group_by_group(dataset: dict[str, dict]) -> dict[str, list[str]]:
    """Group eval_ids by their question type group (samsung, google, device, thirdparty)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for eval_id, entry in dataset.items():
        qt = QuestionType.parse(entry.get("question_type", ""))
        category = qt.group if qt.group else "unknown"
        groups[category].append(eval_id)
    return dict(groups)


def main():
    parser = argparse.ArgumentParser(
        description="Batch runner for reliability testing by question type category",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all volume-related questions, 3 runs each
  python scripts/run_batch.py --filter volume --runs 3

  # Run all device-control questions
  python scripts/run_batch.py --group device --runs 2

  # Run first 5 questions of each category
  python scripts/run_batch.py --per-category 5 --runs 1

  # Dry run to see what would be executed
  python scripts/run_batch.py --filter volume --dry-run
        """,
    )
    parser.add_argument("--filter", help="Filter question types containing this substring (e.g., 'volume', 'notes')")
    parser.add_argument("--group", help="Filter by group: device, samsung, google, thirdparty")
    parser.add_argument("--per-category", type=int, help="Limit N questions per category")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per eval ID")
    parser.add_argument("--config", default="configs/jinju_gemini_config.json", help="Path to config JSON")
    parser.add_argument("--scratch-pad", default="scratch_pad", help="Path to scratch_pad directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip device interaction")
    parser.add_argument("--list", action="store_true", help="List categories and counts, then exit")
    args = parser.parse_args()

    # Load config
    with open(args.config) as f:
        config = json.load(f)

    # Load dataset
    dataset_path = config["paths"]["dataset_file"]
    print(f"Loading dataset from: {dataset_path}")
    dataset = load_dataset(dataset_path)
    print(f"Loaded {len(dataset)} entries from dataset\n")

    # Group by category
    categories = group_by_category(dataset)

    if args.list:
        print("Categories (group_feature: count):")
        for cat in sorted(categories.keys()):
            print(f"  {cat}: {len(categories[cat])}")
        return

    # Filter
    selected: dict[str, list[str]] = {}
    for cat, eval_ids in categories.items():
        if args.filter and args.filter.lower() not in cat.lower():
            continue
        if args.group:
            qt_group = cat.split("_")[0] if "_" in cat else cat
            if qt_group.lower() != args.group.lower():
                continue
        selected[cat] = eval_ids

    if not selected:
        print("No categories matched the filter criteria.")
        print("Available categories:")
        for cat in sorted(categories.keys()):
            print(f"  {cat}: {len(categories[cat])}")
        return

    # Apply per-category limit
    if args.per_category:
        for cat in selected:
            selected[cat] = selected[cat][:args.per_category]

    # Print plan
    total_runs = 0
    print("=" * 60)
    print("BATCH EXECUTION PLAN")
    print("=" * 60)
    for cat in sorted(selected.keys()):
        eval_ids = selected[cat]
        n_runs = len(eval_ids) * args.runs
        total_runs += n_runs
        print(f"  {cat}: {len(eval_ids)} questions x {args.runs} runs = {n_runs} total runs")
        for eid in eval_ids:
            entry = dataset[eid]
            print(f"    - {eid}: '{entry.get('question', '')}' ({entry.get('question_type', '')})")
    print(f"\nTotal runs: {total_runs}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 60)

    # Execute
    for cat in sorted(selected.keys()):
        eval_ids = selected[cat]
        print(f"\n{'='*60}")
        print(f"Category: {cat}")
        print(f"{'='*60}")

        for eval_id in eval_ids:
            entry = dataset[eval_id]
            print(f"\n  {eval_id}: '{entry.get('question', '')}'")

            for run_id in range(1, args.runs + 1):
                print(f"    Run {run_id}/{args.runs}...")
                trace_path = run_single(
                    eval_id=eval_id,
                    run_id=run_id,
                    dataset_entry=entry,
                    config=config,
                    scratch_pad=args.scratch_pad,
                    skip_device=args.dry_run,
                )
                print(f"    Trace: {trace_path}")

    # Generate reliability report
    print(f"\n{'='*60}")
    print("Generating reliability report...")
    print(f"{'='*60}")
    from scripts.reliability_tracker import ReliabilityTracker
    tracker = ReliabilityTracker(scratch_pad_dir=args.scratch_pad)
    tracker.save_report()
    tracker.generate_html_report()
    print("\nDone! Check scratch_pad/reliability_report.html for the dashboard.")


if __name__ == "__main__":
    main()
