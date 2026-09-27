#!/usr/bin/env python3
"""
ReliabilityTracker — Aggregates execution traces into reliability metrics.

Reads all trace JSON files for a given eval_id (across multiple runs) and
computes pass rates, common failure steps, and reliability tiers.

Usage:
    tracker = ReliabilityTracker(scratch_pad_dir="scratch_pad")
    summary = tracker.aggregate_eval_id("q00001")
    report = tracker.generate_report()
    tracker.save_report()
"""

from __future__ import annotations

import json
import os
import glob
from collections import Counter, defaultdict
from typing import Optional


# Reliability tiers
TIER_STABLE = "STABLE"        # >90% pass rate
TIER_PARTIAL = "PARTIAL"      # 50-90% pass rate
TIER_UNSTABLE = "UNSTABLE"    # <50% pass rate


class ReliabilityTracker:
    """Aggregates execution traces into reliability metrics."""

    def __init__(self, scratch_pad_dir: str = "scratch_pad"):
        """
        Args:
            scratch_pad_dir: Path to the scratch_pad directory containing run traces.
        """
        self.scratch_pad_dir = scratch_pad_dir
        self.runs_dir = os.path.join(scratch_pad_dir, "runs")

    def find_traces_for_eval(self, eval_id: str) -> list[dict]:
        """Find and load all trace JSON files for a given eval_id."""
        pattern = os.path.join(self.runs_dir, "**", eval_id, "trace_*.json")
        trace_paths = glob.glob(pattern, recursive=True)
        traces = []
        for path in sorted(trace_paths):
            try:
                with open(path) as f:
                    traces.append(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load trace {path}: {e}")
        return traces

    def find_all_traces(self) -> list[dict]:
        """Find and load all trace JSON files in the runs directory."""
        pattern = os.path.join(self.runs_dir, "**", "trace_*.json")
        trace_paths = glob.glob(pattern, recursive=True)
        traces = []
        for path in sorted(trace_paths):
            try:
                with open(path) as f:
                    traces.append(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load trace {path}: {e}")
        return traces

    def aggregate_eval_id(self, eval_id: str) -> dict:
        """
        Aggregate all runs for a single eval_id into a reliability summary.

        Returns:
            Dict with pass_rate, reliability_tier, per-run results, failure analysis.
        """
        traces = self.find_traces_for_eval(eval_id)
        if not traces:
            return {
                "eval_id": eval_id,
                "total_runs": 0,
                "passes": 0,
                "failures": 0,
                "pass_rate": 0.0,
                "reliability_tier": "NO_DATA",
                "runs": [],
                "failure_steps": {},
            }

        runs = []
        passes = 0
        failures = 0
        failure_steps: Counter = Counter()

        for trace in sorted(traces, key=lambda t: t.get("run_id", 0)):
            run_id = trace.get("run_id", 0)
            overall_status = trace.get("overall_status", "unknown")
            is_pass = overall_status == "success"
            if is_pass:
                passes += 1
            else:
                failures += 1
                # Find which steps failed
                for step in trace.get("steps", []):
                    if step.get("status") == "failure":
                        failure_steps[step["step"]] += 1

            # Extract key outputs from steps
            run_summary = {
                "run_id": run_id,
                "overall_status": overall_status,
                "total_elapsed_ms": trace.get("total_elapsed_ms", 0),
                "num_steps": trace.get("num_steps", 0),
                "failure_reasons": [],
            }

            for step in trace.get("steps", []):
                if step.get("status") == "failure":
                    run_summary["failure_reasons"].append(
                        f"{step['step']}: {step.get('error', 'unknown')}"
                    )

            runs.append(run_summary)

        total = passes + failures
        pass_rate = passes / total if total > 0 else 0.0

        if pass_rate > 0.9:
            tier = TIER_STABLE
        elif pass_rate >= 0.5:
            tier = TIER_PARTIAL
        else:
            tier = TIER_UNSTABLE

        return {
            "eval_id": eval_id,
            "total_runs": total,
            "passes": passes,
            "failures": failures,
            "pass_rate": round(pass_rate, 4),
            "reliability_tier": tier,
            "runs": runs,
            "failure_steps": dict(failure_steps.most_common()),
        }

    def aggregate_all(self) -> dict:
        """
        Aggregate all traces across all eval_ids into a master report.

        Returns:
            Dict with per-eval summaries and overall statistics.
        """
        traces = self.find_all_traces()

        # Group traces by eval_id
        by_eval: dict[str, list[dict]] = defaultdict(list)
        for trace in traces:
            eval_id = trace.get("eval_id", "")
            if eval_id:
                by_eval[eval_id].append(trace)

        eval_summaries = []
        for eval_id in sorted(by_eval.keys()):
            summary = self.aggregate_eval_id(eval_id)
            # Enrich with question_type from the first trace
            if by_eval[eval_id]:
                first = by_eval[eval_id][0]
                # Try to find question_type in step inputs/outputs
                for step in first.get("steps", []):
                    qt = step.get("inputs", {}).get("question_type") or step.get("outputs", {}).get("question_type")
                    if qt:
                        summary["question_type"] = qt
                        break
                    q = step.get("inputs", {}).get("question") or step.get("outputs", {}).get("question")
                    if q:
                        summary["question"] = q
                        break
            eval_summaries.append(summary)

        # Overall stats
        total_evals = len(eval_summaries)
        total_runs = sum(s["total_runs"] for s in eval_summaries)
        total_passes = sum(s["passes"] for s in eval_summaries)
        total_failures = sum(s["failures"] for s in eval_summaries)

        tier_counts = Counter(s["reliability_tier"] for s in eval_summaries)

        return {
            "total_evals": total_evals,
            "total_runs": total_runs,
            "total_passes": total_passes,
            "total_failures": total_failures,
            "overall_pass_rate": round(total_passes / total_runs, 4) if total_runs > 0 else 0.0,
            "tier_distribution": dict(tier_counts),
            "eval_summaries": eval_summaries,
        }

    def save_report(self, output_path: Optional[str] = None) -> str:
        """
        Generate and save the master reliability report as JSON.

        Args:
            output_path: Custom output path. Defaults to scratch_pad/reliability_report.json

        Returns:
            Path to the saved report.
        """
        if output_path is None:
            output_path = os.path.join(self.scratch_pad_dir, "reliability_report.json")

        report = self.aggregate_all()

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"Reliability report saved to: {output_path}")
        print(f"  Total evals: {report['total_evals']}")
        print(f"  Total runs: {report['total_runs']}")
        print(f"  Overall pass rate: {report['overall_pass_rate']:.1%}")
        print(f"  Tier distribution: {report['tier_distribution']}")

        return output_path

    def generate_html_report(self, output_path: Optional[str] = None) -> str:
        """
        Generate a simple HTML dashboard from the reliability report.

        Returns:
            Path to the saved HTML report.
        """
        if output_path is None:
            output_path = os.path.join(self.scratch_pad_dir, "reliability_report.html")

        report = self.aggregate_all()

        rows_html = []
        for s in report.get("eval_summaries", []):
            tier_color = {
                TIER_STABLE: "#4CAF50",
                TIER_PARTIAL: "#FF9800",
                TIER_UNSTABLE: "#F44336",
                "NO_DATA": "#9E9E9E",
            }.get(s["reliability_tier"], "#9E9E9E")

            rows_html.append(f"""
            <tr>
                <td>{s['eval_id']}</td>
                <td>{s.get('question_type', 'N/A')}</td>
                <td>{s['total_runs']}</td>
                <td>{s['passes']}</td>
                <td>{s['failures']}</td>
                <td><strong>{s['pass_rate']:.1%}</strong></td>
                <td style="background-color: {tier_color}; color: white; font-weight: bold;">{s['reliability_tier']}</td>
            </tr>""")

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Reliability Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        tr:hover {{ background-color: #ddd; }}
    </style>
</head>
<body>
    <h1>Reliability Report</h1>
    <div class="summary">
        <p><strong>Total Evals:</strong> {report['total_evals']} |
           <strong>Total Runs:</strong> {report['total_runs']} |
           <strong>Overall Pass Rate:</strong> {report['overall_pass_rate']:.1%}</p>
        <p><strong>Tier Distribution:</strong> {report['tier_distribution']}</p>
    </div>
    <table>
        <thead>
            <tr>
                <th>Eval ID</th>
                <th>Question Type</th>
                <th>Runs</th>
                <th>Passes</th>
                <th>Failures</th>
                <th>Pass Rate</th>
                <th>Reliability Tier</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows_html)}
        </tbody>
    </table>
</body>
</html>"""

        with open(output_path, "w") as f:
            f.write(html)

        print(f"HTML report saved to: {output_path}")
        return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Reliability Tracker")
    parser.add_argument("--scratch-pad", default="scratch_pad", help="Path to scratch_pad directory")
    parser.add_argument("--html", action="store_true", help="Also generate HTML report")
    args = parser.parse_args()

    tracker = ReliabilityTracker(scratch_pad_dir=args.scratch_pad)
    tracker.save_report()
    if args.html:
        tracker.generate_html_report()
