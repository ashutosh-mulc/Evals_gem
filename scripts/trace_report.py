#!/usr/bin/env python3
"""Print per-question timelines from pipeline_traces/*.jsonl (written when PIPELINE_TRACE=1).

Usage: trace_report.py <eval_set_dir> [--eval-id q00065] [--failed-only]
"""
import argparse
import glob
import json
import os
from collections import defaultdict


def load(eval_set_dir):
    rows = []
    for path in glob.glob(os.path.join(eval_set_dir, "pipeline_traces", "*.jsonl")):
        with open(path) as f:
            rows += [json.loads(line) for line in f if line.strip()]
    return sorted(rows, key=lambda r: r["timestamp"])


def failed(row):
    return row["status"] == "failure" or (row.get("verdict") or {}).get("ok") is False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_set_dir")
    ap.add_argument("--eval-id")
    ap.add_argument("--failed-only", action="store_true")
    args = ap.parse_args()

    by_q = defaultdict(list)
    for r in load(args.eval_set_dir):
        by_q[r["eval_id"] or "(no eval_id)"].append(r)

    for eval_id, rows in sorted(by_q.items()):
        if args.eval_id and eval_id != args.eval_id:
            continue
        bad = [r for r in rows if failed(r)]
        if args.failed_only and not bad:
            continue
        print(f"\n== {eval_id}  {len(rows)} steps, {len(bad)} failed")
        for r in rows:
            mark = "FAIL" if failed(r) else " ok "
            print(f"  {mark} {r['timestamp'][11:23]} {r['component']:<13} {r['step']:<22} {r['duration_ms']:>9.0f}ms  {r['error'] or ''}")


if __name__ == "__main__":
    main()
