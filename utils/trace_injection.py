"""
Pipeline Trace Injection — Monkey-patches pipeline classes with tracing wrappers.

When PIPELINE_TRACE env var is set, each process (agent_tester, judge_worker,
coordinator) calls install_tracing() at startup.  This replaces key methods
on DeviceManager, ARAPManager, PreconditionManager, DisplayServer,
ResponseScorer, and DBManager with wrappers that log each call as a JSONL
line to {root_folder}/pipeline_traces/{component}_trace.jsonl.

Zero functional changes to existing pipeline code — only 3-line conditional
imports in the three entry-point __main__ blocks.

Trace JSONL format (one JSON object per line, append-only):
    {"step": "invoke_device", "component": "agent_tester", "eval_id": "q00065",
     "timestamp": "2026-09-17T10:30:45.123", "duration_ms": 1234.5,
     "inputs": {"question_type": "online_device_volume_up"},
     "outputs": {"status": "invoked"}, "status": "success", "error": null}
"""

from __future__ import annotations

import functools
import importlib
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Callable

from agent_testers.device_managers import DEVICE_MANAGERS

# ── Module-level state ──────────────────────────────────────────────

_trace_dir: str | None = None
_current_eval_id: str | None = None

# ── Helpers ─────────────────────────────────────────────────────────

def _sanitize(data: Any) -> Any:
    """Sanitize values for JSON serialization — truncate long strings, summarize large collections."""
    if data is None:
        return {}
    if not isinstance(data, dict):
        return data
    sanitized = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > 500:
            sanitized[k] = v[:500] + "...[truncated]"
        elif isinstance(v, (str, int, float, bool, type(None))):
            sanitized[k] = v
        elif isinstance(v, (list, dict)):
            try:
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


def _extract_eval_id(*args, **kwargs) -> str | None:
    """Try to extract eval_id from method arguments."""
    global _current_eval_id
    for arg in args[1:]:  # skip self
        if isinstance(arg, dict) and "eval_id" in arg:
            return str(arg["eval_id"])
        if isinstance(arg, str) and re.match(r"q?\d{5}", arg):
            return arg
    for v in kwargs.values():
        if isinstance(v, dict) and "eval_id" in v:
            return str(v["eval_id"])
    return _current_eval_id


def _write_trace(component, step, eval_id, inputs, outputs, status, error, duration_ms):
    """Write a single trace line to the component's JSONL file."""
    global _trace_dir, _current_eval_id
    if not _trace_dir:
        return
    if eval_id:
        _current_eval_id = eval_id
    entry = {
        "step": step,
        "component": component,
        "eval_id": eval_id or _current_eval_id or "",
        "timestamp": datetime.now().isoformat(),
        "duration_ms": round(duration_ms, 2),
        "inputs": _sanitize(inputs),
        "outputs": _sanitize(outputs),
        "status": status,
        "error": error,
    }
    trace_file = os.path.join(_trace_dir, f"{component}_trace.jsonl")
    try:
        with open(trace_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (IOError, OSError):
        pass  # Don't let tracing break the pipeline


def _make_wrapper(original, component, step_name, extract_inputs=None, extract_outputs=None):
    """Create a tracing wrapper around an original method.

    Args:
        original: The unbound method to wrap.
        component: Component name (agent_tester, judge_worker, coordinator).
        step_name: Step name string, or callable(*args, **kwargs) -> str.
        extract_inputs: Optional callable(*args, **kwargs) -> dict.
        extract_outputs: Optional callable(result, *args, **kwargs) -> dict.
    """

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        start = time.time()
        eval_id = _extract_eval_id(*args, **kwargs)
        step = step_name(*args, **kwargs) if callable(step_name) else step_name
        inputs = {}
        if extract_inputs:
            try:
                inputs = extract_inputs(*args, **kwargs) or {}
            except Exception:
                pass
        status = "success"
        error = None
        result = None
        try:
            result = original(*args, **kwargs)
            return result
        except Exception as e:
            status = "failure"
            error = str(e)
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            outputs = {}
            if extract_outputs and result is not None:
                try:
                    outputs = extract_outputs(result, *args, **kwargs) or {}
                except Exception:
                    pass
            _write_trace(component, step, eval_id, inputs, outputs, status, error, duration_ms)

    return wrapper


# ── Patch installers ────────────────────────────────────────────────

def _patch_agent_tester_side(config: dict) -> None:
    """Patch DeviceManager, ARAPManager, PreconditionManager, DisplayServer."""
    dm_type = config["device_manager_type"]
    dm_module_path = DEVICE_MANAGERS.get(dm_type)
    if not dm_module_path:
        return

    dm_module = importlib.import_module(dm_module_path)
    DeviceManager = dm_module.DeviceManager

    # --- DeviceManager methods ---

    if hasattr(DeviceManager, "reset_device_to_default_state"):
        orig = DeviceManager.reset_device_to_default_state
        DeviceManager.reset_device_to_default_state = _make_wrapper(
            orig, "agent_tester", "reset_device",
            extract_outputs=lambda result, *a, **kw: {
                "set": result.get("set", []) if isinstance(result, dict) else [],
                "failed": result.get("failed", []) if isinstance(result, dict) else [],
            },
        )

    if hasattr(DeviceManager, "capture_device_info"):
        orig = DeviceManager.capture_device_info

        def _cap_step(*a, **kw):
            ct = kw.get("capture_type", a[2] if len(a) > 2 else "post")
            return f"capture_{ct}_state"

        def _cap_in(*a, **kw):
            ct = kw.get("capture_type", a[2] if len(a) > 2 else "post")
            return {"capture_type": ct}

        def _cap_out(result, *a, **kw):
            q = a[1] if len(a) > 1 else kw.get("q_info", {})
            ct = kw.get("capture_type", a[2] if len(a) > 2 else "post")
            meta = q.get("metadata", {}) if isinstance(q, dict) else {}
            return {"device_info_keys": list(meta.get(f"device_info_{ct}", {}).keys())}

        DeviceManager.capture_device_info = _make_wrapper(
            orig, "agent_tester", _cap_step, _cap_in, _cap_out,
        )

    if hasattr(DeviceManager, "capture_pre_state_meta_info"):
        orig = DeviceManager.capture_pre_state_meta_info
        DeviceManager.capture_pre_state_meta_info = _make_wrapper(
            orig, "agent_tester", "capture_pre_meta",
        )

    if hasattr(DeviceManager, "capture_post_state_meta_info"):
        orig = DeviceManager.capture_post_state_meta_info
        DeviceManager.capture_post_state_meta_info = _make_wrapper(
            orig, "agent_tester", "capture_post_meta",
        )

    if hasattr(DeviceManager, "capture_pre_state"):
        orig = DeviceManager.capture_pre_state
        DeviceManager.capture_pre_state = _make_wrapper(
            orig, "agent_tester", "capture_xrclaw_pre",
            extract_outputs=lambda result, *a, **kw: {
                "app_state_keys": list(
                    a[1].get("metadata", {}).get("app_state", {}).keys()
                ) if len(a) > 1 and isinstance(a[1], dict) else {},
            },
        )

    if hasattr(DeviceManager, "invoke"):
        orig = DeviceManager.invoke
        DeviceManager.invoke = _make_wrapper(
            orig, "agent_tester", "invoke_device",
            extract_inputs=lambda *a, **kw: {
                "question_type": a[1].get("question_type", "") if len(a) > 1 and isinstance(a[1], dict) else "",
            },
        )

    for method_name in ("start_logging", "stop_logging"):
        if hasattr(DeviceManager, method_name):
            orig = getattr(DeviceManager, method_name)
            setattr(DeviceManager, method_name, _make_wrapper(
                orig, "agent_tester", method_name,
                extract_outputs=lambda result, *a, **kw: result if isinstance(result, dict) else {"raw": str(result)[:200]},
            ))

    # --- ARAPManager methods ---

    from agent_testers.arap_manager import ARAPManager

    if hasattr(ARAPManager, "play_audio"):
        orig = ARAPManager.play_audio
        ARAPManager.play_audio = _make_wrapper(
            orig, "agent_tester", "play_audio",
            extract_inputs=lambda *a, **kw: {"audio_path": a[1] if len(a) > 1 else kw.get("audio_path", "")},
        )

    if hasattr(ARAPManager, "start_recording"):
        orig = ARAPManager.start_recording
        ARAPManager.start_recording = _make_wrapper(
            orig, "agent_tester", "start_recording",
            extract_inputs=lambda *a, **kw: {"filename": a[1] if len(a) > 1 else kw.get("response_file", "")},
        )

    if hasattr(ARAPManager, "stop_recording"):
        orig = ARAPManager.stop_recording
        ARAPManager.stop_recording = _make_wrapper(
            orig, "agent_tester", "stop_recording",
            extract_inputs=lambda *a, **kw: {"response_path": a[1] if len(a) > 1 else kw.get("response_path", "")},
            extract_outputs=lambda result, *a, **kw: {
                "file_size": os.path.getsize(a[1]) if len(a) > 1 and os.path.exists(a[1]) else 0,
            },
        )

    # --- PreconditionManager ---

    from agent_testers.preconditions import PreconditionManager

    if hasattr(PreconditionManager, "setup"):
        orig = PreconditionManager.setup
        PreconditionManager.setup = _make_wrapper(
            orig, "agent_tester", "preconditions",
            extract_outputs=lambda result, *a, **kw: {
                "passed": result.get("passed", False) if isinstance(result, dict) else False,
                "set": result.get("set", []) if isinstance(result, dict) else [],
                "failed": result.get("failed", []) if isinstance(result, dict) else [],
            },
        )

    # --- DisplayServer ---

    from services.host.display_server import DisplayServer

    if hasattr(DisplayServer, "set_image_status"):
        orig = DisplayServer.set_image_status
        DisplayServer.set_image_status = _make_wrapper(
            orig, "agent_tester", "display_image",
            extract_inputs=lambda *a, **kw: {"action": a[2] if len(a) > 2 else kw.get("action", "")},
        )


def _patch_judge_worker_side(config: dict) -> None:
    """Patch ResponseScorer methods."""
    from judge_worker.response_scorer import ResponseScorer

    # get_text_response(encoded_audio) -> dict with text, language, start, end
    if hasattr(ResponseScorer, "get_text_response"):
        orig = ResponseScorer.get_text_response
        ResponseScorer.get_text_response = _make_wrapper(
            orig, "judge_worker", "transcribe",
            extract_outputs=lambda result, *a, **kw: {
                "text": result.get("text", "") if isinstance(result, dict) else "",
                "language": result.get("language", "") if isinstance(result, dict) else "",
            },
        )

    # _try_deterministic_judge(question_type, question, ai_response_text, ...)
    if hasattr(ResponseScorer, "_try_deterministic_judge"):
        orig = ResponseScorer._try_deterministic_judge
        ResponseScorer._try_deterministic_judge = _make_wrapper(
            orig, "judge_worker", "deterministic_judge",
            extract_inputs=lambda *a, **kw: {"question_type": a[1] if len(a) > 1 else ""},
            extract_outputs=lambda result, *a, **kw: {
                "result": "determined" if result is not None else "none",
            },
        )

    # run_judge(eval_type, question, gt_answer, ai_response, ...)
    if hasattr(ResponseScorer, "run_judge"):
        orig = ResponseScorer.run_judge

        def _judge_out(result, *a, **kw):
            raw = result[0] if isinstance(result, tuple) else result
            raw_str = str(raw)
            m = re.search(r'["\']rating["\']\s*:\s*(\d+)', raw_str)
            return {
                "rating": int(m.group(1)) if m else 0,
                "response_length": len(raw_str),
            }

        ResponseScorer.run_judge = _make_wrapper(
            orig, "judge_worker", "vlm_judge",
            extract_inputs=lambda *a, **kw: {"eval_type": a[1] if len(a) > 1 else ""},
            extract_outputs=_judge_out,
        )

    # get_judge_score(eval_json) -> (response, result_meta)
    if hasattr(ResponseScorer, "get_judge_score"):
        orig = ResponseScorer.get_judge_score
        ResponseScorer.get_judge_score = _make_wrapper(
            orig, "judge_worker", "judge_score",
            extract_outputs=lambda result, *a, **kw: {
                "final_rating": result[1].get("rating", 0) if isinstance(result, tuple) and isinstance(result[1], dict) else 0,
                "eval_id": result[1].get("eval_id", "") if isinstance(result, tuple) and isinstance(result[1], dict) else "",
            },
        )


def _patch_coordinator_side(config: dict) -> None:
    """Patch DBManager methods."""
    from metric_coordinator.db_manager import DBManager

    if hasattr(DBManager, "add_task"):
        orig = DBManager.add_task
        DBManager.add_task = _make_wrapper(
            orig, "coordinator", "dispatch_question",
            extract_inputs=lambda *a, **kw: {
                "payload": a[1][:200] if len(a) > 1 and isinstance(a[1], str) else "",
            },
            extract_outputs=lambda result, *a, **kw: {"eval_id": result if isinstance(result, str) else ""},
        )

    if hasattr(DBManager, "update_task"):
        orig = DBManager.update_task
        DBManager.update_task = _make_wrapper(
            orig, "coordinator", "task_update",
            extract_inputs=lambda *a, **kw: {
                "eval_id": a[1] if len(a) > 1 else "",
                "status": a[2] if len(a) > 2 else "",
            },
        )


# ── Public API ──────────────────────────────────────────────────────

def install_tracing(config_path: str) -> None:
    """Install tracing wrappers on pipeline classes.

    Called from each process's __main__ block when PIPELINE_TRACE env var is set.
    Reads the config to determine root_folder and device_manager_type, then
    patches all relevant classes.

    Args:
        config_path: Path to the evaluation config JSON.
    """
    global _trace_dir

    with open(config_path) as f:
        config = json.load(f)

    root_folder = config["paths"]["root_folder"]
    _trace_dir = os.path.join(root_folder, "pipeline_traces")
    os.makedirs(_trace_dir, exist_ok=True)

    # Patch all sides — unused patches in a given process are harmless
    try:
        _patch_agent_tester_side(config)
    except Exception as e:
        print(f"[trace_injection] agent_tester patch failed: {e}")

    try:
        _patch_judge_worker_side(config)
    except Exception as e:
        print(f"[trace_injection] judge_worker patch failed: {e}")

    try:
        _patch_coordinator_side(config)
    except Exception as e:
        print(f"[trace_injection] coordinator patch failed: {e}")

    print(f"[trace_injection] Tracing enabled → {_trace_dir}")
