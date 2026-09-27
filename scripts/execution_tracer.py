#!/usr/bin/env python3
"""
ExecutionTracer — Structured step-by-step execution tracer for reliability testing.

Records each pipeline step as a discrete event with timestamps, inputs, outputs,
and status. Produces a queryable JSON trace that can be replayed, visualized,
or aggregated by the reliability tracker.

Usage:
    tracer = ExecutionTracer(eval_id="q00001", run_id=1, output_dir="scratch_pad/runs/...")
    tracer.step("decode_audio", inputs={"base64_len": 12340}, outputs={"wav_path": "..."})
    tracer.step("invoke_device", outputs={"response_path": "..."}, status="success")
    ...
    trace_path = tracer.save()
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Optional


class ExecutionTracer:
    """Structured step-by-step execution tracer for reliability testing."""

    def __init__(self, eval_id: str, run_id: int, output_dir: str):
        """
        Initialize a new tracer for a single test case run.

        Args:
            eval_id: The evaluation ID (e.g., "q00001")
            run_id: The run number (1, 2, 3, etc.)
            output_dir: Directory where the trace JSON will be saved
        """
        self.eval_id = eval_id
        self.run_id = run_id
        self.output_dir = output_dir
        self.steps: list[dict[str, Any]] = []
        self.start_time = time.time()
        self._current_step_start: Optional[float] = None

    def step(
        self,
        step_name: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        """
        Record a single pipeline step.

        Args:
            step_name: Name of the step (e.g., "decode_audio", "invoke_device")
            inputs: Dictionary of input values for this step
            outputs: Dictionary of output values from this step
            status: "success", "failure", or "skipped"
            error: Error message if status is "failure"
        """
        now = time.time()
        elapsed_ms = round((now - self.start_time) * 1000, 2)

        self.steps.append(
            {
                "step": step_name,
                "timestamp": datetime.now().isoformat(),
                "elapsed_ms": elapsed_ms,
                "inputs": self._sanitize(inputs) if inputs else {},
                "outputs": self._sanitize(outputs) if outputs else {},
                "status": status,
                "error": error,
            }
        )

    def _sanitize(self, data: dict) -> dict:
        """Sanitize values for JSON serialization (truncate long strings, convert non-serializable)."""
        sanitized = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 500:
                sanitized[k] = v[:500] + "...[truncated]"
            elif isinstance(v, (str, int, float, bool, type(None))):
                sanitized[k] = v
            elif isinstance(v, (list, dict)):
                try:
                    # Try to serialize; if too large, summarize
                    s = json.dumps(v)
                    if len(s) > 2000:
                        sanitized[k] = f"[{type(v).__name__} with {len(v)} items, truncated]"
                    else:
                        sanitized[k] = v
                except (TypeError, ValueError):
                    sanitized[k] = str(v)[:200]
            else:
                sanitized[k] = str(v)[:200]
        return sanitized

    def save(self) -> str:
        """
        Save the full trace as a JSON file.

        Returns:
            Path to the saved trace file.
        """
        total_elapsed_ms = round((time.time() - self.start_time) * 1000, 2)

        trace = {
            "eval_id": self.eval_id,
            "run_id": self.run_id,
            "total_elapsed_ms": total_elapsed_ms,
            "num_steps": len(self.steps),
            "overall_status": self._compute_overall_status(),
            "steps": self.steps,
        }

        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"trace_{self.eval_id}_run{self.run_id}.json")
        with open(path, "w") as f:
            json.dump(trace, f, indent=2)

        return path

    def _compute_overall_status(self) -> str:
        """Compute overall status from all steps."""
        if not self.steps:
            return "unknown"
        if any(s["status"] == "failure" for s in self.steps):
            return "failure"
        if all(s["status"] == "skipped" for s in self.steps):
            return "skipped"
        return "success"

    def get_step(self, step_name: str) -> dict | None:
        """Get the last recorded step with the given name, or None."""
        for s in reversed(self.steps):
            if s["step"] == step_name:
                return s
        return None

    def get_step_output(self, step_name: str, key: str, default=None):
        """Get a specific output value from the last step with the given name."""
        step = self.get_step(step_name)
        if step:
            return step["outputs"].get(key, default)
        return default

    def summary(self) -> str:
        """Return a one-line summary string for console output."""
        status = self._compute_overall_status()
        num = len(self.steps)
        elapsed = round((time.time() - self.start_time) * 1000, 2)
        return f"[{self.eval_id} run={self.run_id}] steps={num} status={status} elapsed={elapsed}ms"


if __name__ == "__main__":
    # Quick self-test
    import tempfile

    tmpdir = tempfile.mkdtemp()
    tracer = ExecutionTracer("q_test", 1, tmpdir)

    tracer.step("decode_audio", inputs={"base64_len": 1000}, outputs={"wav_path": "/tmp/test.wav"})
    tracer.step("invoke_device", outputs={"response_path": "/tmp/resp.wav"}, status="success")
    tracer.step("judge", outputs={"score": 5, "analysis": "Perfect"}, status="success")

    path = tracer.save()
    print(f"Trace saved to: {path}")
    print(f"Summary: {tracer.summary()}")

    with open(path) as f:
        print(f.read())
