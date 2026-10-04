"""
Per-step verdicts for pipeline traces (boilerplate — nothing registered yet).

trace_injection calls evaluate(step, record) for every trace line and stores the result
in record["verdict"]. A verdict is None (no opinion) or {"ok": bool, "reason": str, "judge": str}.

To add a check, register a function for a step name:

    @check("stop_recording")
    def _recording_not_empty(record):
        ...  # return {"ok": ..., "reason": ..., "judge": "rule"} or None

An LLM judge would be a second registry of the same shape (judge="llm"), run offline over
saved traces so tracing never waits on a model.
"""

from __future__ import annotations

from typing import Callable, Optional

Verdict = Optional[dict]
CHECKS: dict[str, Callable[[dict], Verdict]] = {}


def check(step: str):
    """Decorator: register a rule check for a trace step name."""
    def register(fn: Callable[[dict], Verdict]) -> Callable[[dict], Verdict]:
        CHECKS[step] = fn
        return fn
    return register


def evaluate(step: str, record: dict) -> Verdict:
    """Run the registered check for ``step``. TODO: no checks registered yet, so always None."""
    fn = CHECKS.get(step)
    return fn(record) if fn else None
