#!/usr/bin/env python3
"""
Jinju Latency Breakdown Analyzer

Breaks down Jinju Gemini Live response latency into pipeline stages by
analyzing companion log, jinju log, and VQA report JSON.

Usage:
    python latency_analyzer.py \
        --companion <companion_log_path> \
        --jinju <jinju_log_path> \
        --vqa-report <vqa_report_json_path> \
        [--eval-id q00004] \
        [--iteration 1] \
        [--output <output_path>]

The script auto-detects evalId from log filenames if not provided.
The script auto-detects query type from the VQA report JSON filename
  - "Visual_QA_TASK" in filename → visual
  - "QA_TASK" (without "Visual") → non-visual (audio)
"""

import re
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Checkpoint:
    """A single detected checkpoint from the logs."""
    name: str
    description: str
    device: str          # "companion" or "jinju"
    time: str = ""       # "HH:MM:SS.mmm"
    evidence: str = ""   # log line
    remark: str = ""
    found: bool = False


@dataclass
class Stage:
    """A latency stage between two checkpoints."""
    name: str
    formula: str
    duration: str = ""   # "XXX ms" or "-"
    part_of_latency: str = ""  # "✅" or "❌"
    remark: str = ""


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    eval_id: str = ""
    iteration: int = 1
    query_type: str = ""                    # "visual" or "non-visual"
    camera_source: str = ""
    reported_latency_start_time: str = ""
    calculated_user_speech_end_time: str = ""
    reported_latency_end_time: str = ""
    reported_latency_ms: float = 0.0
    question_audio_duration: float = 0.0
    response_time: float = 0.0
    checkpoints: List[Checkpoint] = field(default_factory=list)
    stages: List[Stage] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Log parsing
# ──────────────────────────────────────────────────────────────────────────────

LOG_PATTERN = re.compile(
    r'^(\d{2}-\d{2})\s+'
    r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'
    r'(\d+)\s+'
    r'(\d+)\s+'
    r'([VDEWIF])\s+'
    r'([^:]+):\s+'
    r'(.*)$'
)


def parse_log_lines(filepath: str) -> List[dict]:
    """Parse a log file into a list of entry dicts."""
    entries = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            m = LOG_PATTERN.match(line)
            if m:
                entries.append({
                    'date': m.group(1),
                    'time': m.group(2),
                    'pid': int(m.group(3)),
                    'tid': int(m.group(4)),
                    'level': m.group(5),
                    'tag': m.group(6).strip(),
                    'message': m.group(7),
                    'raw': line,
                })
    return entries


def find_first_match(entries: List[dict], pattern: str, min_time: str = "") -> Optional[dict]:
    """Find the first log entry matching a regex pattern after min_time."""
    regex = re.compile(pattern)
    min_ts = parse_ts(min_time) if min_time else None
    for entry in entries:
        if min_ts:
            try:
                entry_ts = parse_ts(entry['time'])
                if entry_ts < min_ts:
                    continue
            except (ValueError, KeyError):
                continue
        if regex.search(entry['raw']):
            return entry
    return None


def find_closest_match(entries: List[dict], pattern: str, target_time: str, min_time: str = "") -> Optional[dict]:
    """Find the log entry matching a regex pattern whose timestamp is closest to target_time."""
    regex = re.compile(pattern)
    min_ts = parse_ts(min_time) if min_time else None
    target_ts = parse_ts(target_time) if target_time else None
    best_entry = None
    best_diff = float('inf')
    for entry in entries:
        if min_ts:
            try:
                entry_ts = parse_ts(entry['time'])
                if entry_ts < min_ts:
                    continue
            except (ValueError, KeyError):
                continue
        if regex.search(entry['raw']):
            if target_ts:
                try:
                    entry_ts = parse_ts(entry['time'])
                    diff = abs((entry_ts - target_ts).total_seconds())
                    if diff < best_diff:
                        best_diff = diff
                        best_entry = entry
                except (ValueError, KeyError):
                    continue
            else:
                return entry
    return best_entry


def find_all_matches(entries: List[dict], pattern: str, min_time: str = "") -> List[dict]:

    """Find all log entries matching a regex pattern after min_time."""
    regex = re.compile(pattern)
    min_ts = parse_ts(min_time) if min_time else None
    results = []
    for entry in entries:
        if min_ts:
            try:
                entry_ts = parse_ts(entry['time'])
                if entry_ts < min_ts:
                    continue
            except (ValueError, KeyError):
                continue
        if regex.search(entry['raw']):
            results.append(entry)
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Timestamp utilities
# ──────────────────────────────────────────────────────────────────────────────

def parse_ts(ts_str: str) -> datetime:
    """Parse 'HH:MM:SS.mmm' into datetime (using today's date as base)."""
    return datetime.strptime(ts_str, "%H:%M:%S.%f")


def ts_diff_ms(start: str, end: str) -> float:
    """Compute difference in milliseconds between two 'HH:MM:SS.mmm' timestamps.

    Handles overnight wrap (if diff < -12h, add 24h).
    """
    t_start = parse_ts(start)
    t_end = parse_ts(end)
    diff = (t_end - t_start).total_seconds() * 1000
    if diff < -(12 * 3600 * 1000):
        diff += 24 * 3600 * 1000
    return diff


def add_seconds_to_ts(ts_str: str, seconds: float) -> str:
    """Add seconds to a 'HH:MM:SS.mmm' timestamp string."""
    t = parse_ts(ts_str)
    t = t + timedelta(seconds=seconds)
    return t.strftime("%H:%M:%S.%f")[:-3]


# ──────────────────────────────────────────────────────────────────────────────
# evalId extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_eval_id_from_path(filepath: str) -> str:
    """Extract evalId from log filename like 'companion_log_00004.txt' → 'q00004'."""
    p = Path(filepath)
    m = re.search(r'_(\d+)\.', p.name)
    if m:
        num = m.group(1)
        return f"q{num}"
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# VQA report JSON parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_vqa_report(json_path: str, eval_id: str, iteration: Optional[int] = None) -> Optional[dict]:
    """Find the matching entry in the VQA report JSON by evalId (and iteration)."""
    with open(json_path, 'r') as f:
        data = json.load(f)

    entries = data.get('kpiRaw', {}).get('data', [])
    if not entries:
        entries = data.get('data', [])

    matches = [e for e in entries if e.get('evalId') == eval_id]

    if not matches:
        return None

    if iteration is not None:
        for e in matches:
            if e.get('iteration', 1) == iteration:
                return e
    return matches[0]


def detect_query_type_from_filename(json_path: str) -> str:
    """Detect query type from VQA report JSON filename.
    
    'Visual_QA_TASK' in filename → visual
    'QA_TASK' (without 'Visual') → non-visual
    """
    filename = Path(json_path).name
    if 'Visual_QA_TASK' in filename:
        return "visual"
    elif 'QA_TASK' in filename:
        return "non-visual"
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Checkpoint definitions
# ──────────────────────────────────────────────────────────────────────────────

# Each checkpoint: (name, description, device, pattern)
CHECKPOINT_DEFS = [
    ("SessionInvoke", "Button press to invoke AI agent", "companion",
     r'ACTION_UP.*KEYCODE_FEATURED_APP_1'),

    ("SessionReady", "Agent session enters STARTING state", "companion",
     r'GC_AgentRequestHandlerI.*state=STARTING'),
    ("SessionAudioStart", "MCU begins audio capture", "jinju",
     r'PROJ_AUDIOCAP service\.cc:505.*Begin audio capture'),
    ("UserSpeechStart", "VAD detects user speech onset", "companion",
     r'\[Latency Tracing\] User speech starts'),
    ("UserSpeechEnd", "VAD detects user speech end", "companion",
     r'\[Latency Tracing\] User speech ends'),
    ("AudioEnhancementStart", "SEANet model selection begins", "companion",
     r'Starting SEANet model selection'),
    ("AudioEnhancementDumpStart", "Denoised audio saved to WAV", "companion",
     r'Saving WAV file for stream DENOISED'),
    ("CameraOpen", "CameraService receives openStream request", "jinju",
     r'CameraService: openStream: received \(LatencyMilestone\)'),
    ("CameraReady", "CameraService finishes openStream", "jinju",
     r'CameraService: openStream\(\d+\) finished \(LatencyMilestone\)'),
    ("TinyGemmaClassification", "TinyGemma outputs classification", "companion",
     r'GC_TinyGemmaCommandReco.*\[PRIMARY FC PROMPT\] model output:'),
    ("GeminiProcessingStart", "Agent enters PROCESSING state", "companion",
     r'GC_AgentRequestHandlerI.*state=PROCESSING'),
    ("ServerVisualClassification", "Server/ODA activates dynamic camera", "companion",
     r'ODA or server path activates dynamic camera'),
    ("CameraStreamingStart", "Camera stream starts (prewarmed)", "companion",
     r'Camera stream already prewarmed with same parameters, starting stream'),
    ("ServerImageConfirmation", "Server receives frames from camera", "companion",
     r'ODA or server path returning frames from camera'),
    ("GeminiResponse", "Agent enters RESPONDING state", "companion",
     r'GC_AgentRequestHandlerI.*state=RESPONDING'),
]

# Camera source patterns
PATTERN_DIRECT_INFERENCE_CAMERA = r'Direct inference command activates dynamic camera'
PATTERN_ODA_SERVER_CAMERA = r'ODA or server path activates dynamic camera'


# ──────────────────────────────────────────────────────────────────────────────
# Main analysis
# ──────────────────────────────────────────────────────────────────────────────

def analyze(
    companion_log: str,
    jinju_log: str,
    vqa_report: str,
    eval_id: str = "",
    iteration: Optional[int] = None,
) -> AnalysisResult:
    """Run the full latency breakdown analysis."""

    result = AnalysisResult()

    # ── Step 1: Extract evalId if not provided ──
    if not eval_id:
        eval_id = extract_eval_id_from_path(companion_log) or extract_eval_id_from_path(jinju_log)
    result.eval_id = eval_id

    # ── Step 2: Detect query type from JSON filename ──
    result.query_type = detect_query_type_from_filename(vqa_report)

    # ── Step 3: Parse VQA report JSON ──
    vqa_entry = parse_vqa_report(vqa_report, eval_id, iteration)
    if not vqa_entry:
        print(f"ERROR: Could not find evalId '{eval_id}' in VQA report.", file=sys.stderr)
        sys.exit(1)
        return AnalysisResult()  # unreachable, for type checker


    result.iteration = vqa_entry.get('iteration', 1)
    meta = vqa_entry.get('metaInfo', {})
    jinju_invoke_ts = meta.get('extraLogs', {}).get('jinjuInvokeTs', "")
    result.question_audio_duration = meta.get('questionAudioDuration', 0.0)
    result.response_time = vqa_entry.get('responseTime', 0.0)

    # Parse jinjuInvokeTs — format: "08-10 21:57:36.748"
    parts = jinju_invoke_ts.split()
    invoke_time_str = parts[1] if len(parts) >= 2 else jinju_invoke_ts

    # Compute metadata times
    result.reported_latency_start_time = invoke_time_str
    result.calculated_user_speech_end_time = add_seconds_to_ts(invoke_time_str, result.question_audio_duration)
    result.reported_latency_end_time = add_seconds_to_ts(result.calculated_user_speech_end_time, result.response_time)
    result.reported_latency_ms = ts_diff_ms(result.reported_latency_start_time, result.reported_latency_end_time)

    # ── Step 4: Parse logs ──
    companion_entries = parse_log_lines(companion_log)
    jinju_entries = parse_log_lines(jinju_log)

    # ── Step 5: Find all checkpoints ──
    # Use SessionInvoke time as min_time floor for all checkpoints
    # (each log file is per-query, so this prevents stale matches)
    session_invoke_entry = find_first_match(companion_entries, CHECKPOINT_DEFS[0][3])
    min_time = session_invoke_entry['time'] if session_invoke_entry else ""

    checkpoints = []
    checkpoint_map = {}

    # Checkpoints that should use closest-match to calculated_user_speech_end_time
    # (because the pattern appears multiple times in the log)
    CLOSEST_MATCH_CKPTS = {"TinyGemmaClassification"}

    for name, desc, device, pattern in CHECKPOINT_DEFS:
        entries = companion_entries if device == "companion" else jinju_entries

        if name in CLOSEST_MATCH_CKPTS:
            entry = find_closest_match(entries, pattern, result.calculated_user_speech_end_time, min_time)
        else:
            entry = find_first_match(entries, pattern, min_time)

        cp = Checkpoint(name=name, description=desc, device=device)

        # Camera-related checkpoints that are N/A for non-visual queries
        CAMERA_CKPTS = {
            "CameraOpen", "CameraReady", "ServerVisualClassification",
            "CameraStreamingStart", "ServerImageConfirmation"
        }

        if result.query_type == "non-visual" and name in CAMERA_CKPTS:
            # For non-visual queries, camera checkpoints are not applicable
            cp.time = "-"
            cp.evidence = "-"
        elif entry:
            cp.time = entry['time']
            cp.evidence = entry['raw']
            cp.found = True
        else:
            cp.time = "NOT FOUND"
            cp.evidence = "NOT FOUND"



        # Add remarks for known checkpoints
        if name == "UserSpeechEnd" and cp.found:
            delta_ms = ts_diff_ms(result.calculated_user_speech_end_time, cp.time)
            if abs(delta_ms) > 500:
                cp.remark = f"Log-based end ({cp.time}) is {delta_ms:.0f}ms after calculated end ({result.calculated_user_speech_end_time}) — VAD/silence detection delay"

        checkpoints.append(cp)
        checkpoint_map[name] = cp

    result.checkpoints = checkpoints

    # ── Step 6: Determine camera source ──
    if result.query_type == "visual":
        direct_inference = find_first_match(companion_entries, PATTERN_DIRECT_INFERENCE_CAMERA, min_time)
        oda_server = find_first_match(companion_entries, PATTERN_ODA_SERVER_CAMERA, min_time)

        if direct_inference and oda_server:
            # Compare timestamps
            if direct_inference['time'] <= oda_server['time']:
                result.camera_source = "TinyGemma (server also fired but camera already on)"
            else:
                result.camera_source = "server (TinyGemma also fired later)"
        elif direct_inference:
            result.camera_source = "TinyGemma"
        elif oda_server:
            result.camera_source = "server"
        else:
            result.camera_source = "Unknown"
    else:
        result.camera_source = "N/A (non-visual query)"

    # ── Step 7: Compute stages ──
    is_visual = result.query_type == "visual"
    stages = []

    def get_time(name):
        cp = checkpoint_map.get(name)
        if cp and cp.found:
            return cp.time
        return None

    def make_stage(name, formula, start_name, end_name, part_of_latency, remark=""):
        start_t = get_time(start_name)
        end_t = get_time(end_name)
        if start_t and end_t and start_t != "-" and end_t != "-":
            duration = f"{ts_diff_ms(start_t, end_t):.0f} ms"
        else:
            duration = "-"
        stages.append(Stage(
            name=name, formula=formula, duration=duration,
            part_of_latency=part_of_latency, remark=remark
        ))

    # Session Start Latency
    make_stage("Session Start Latency", "SessionReady - SessionInvoke",
               "SessionInvoke", "SessionReady", "❌")

    # Camera PreWarm Duration (visual only)
    if is_visual:
        make_stage("Camera PreWarm Duration", "CameraReady - CameraOpen",
                   "CameraOpen", "CameraReady", "❌")
    else:
        stages.append(Stage(name="Camera PreWarm Duration", formula="CameraReady - CameraOpen",
                            duration="-", part_of_latency="❌"))

    # User Speech Duration
    speech_start_t = get_time("UserSpeechStart")
    speech_end_t = get_time("UserSpeechEnd")
    if speech_start_t and speech_end_t:
        log_duration_s = ts_diff_ms(speech_start_t, speech_end_t) / 1000.0
        delta_s = log_duration_s - result.question_audio_duration
        remark = f"Log-based duration ({log_duration_s:.3f}s) vs actual audio duration ({result.question_audio_duration:.3f}s) — delta {delta_s:.3f}s, VAD/silence detection delay"
    else:
        remark = ""
    make_stage("User Speech Duration", "UserSpeechEnd - UserSpeechStart",
               "UserSpeechStart", "UserSpeechEnd", "O", remark)


    # TinyGemma Latency
    # Use calculated_user_speech_end_time as start
    tg_t = get_time("TinyGemmaClassification")
    if tg_t:
        duration = f"{ts_diff_ms(result.calculated_user_speech_end_time, tg_t):.0f} ms"
    else:
        duration = "-"
    stages.append(Stage(name="TinyGemma Latency",
                         formula="TinyGemmaClassification - calculated_user_speech_end_time",
                         duration=duration, part_of_latency="✅"))

    # Image Stream (visual only)
    if is_visual:
        make_stage("Image Stream", "CameraStreamingStart - TinyGemmaClassification",
                   "TinyGemmaClassification", "CameraStreamingStart", "✅")
    else:
        stages.append(Stage(name="Image Stream", formula="CameraStreamingStart - TinyGemmaClassification",
                            duration="-", part_of_latency="❌"))

    # Image Transmission Server (visual only)
    if is_visual:
        make_stage("Image Transmission Server", "ServerImageConfirmation - CameraStreamingStart",
                   "CameraStreamingStart", "ServerImageConfirmation", "✅")
    else:
        stages.append(Stage(name="Image Transmission Server", formula="ServerImageConfirmation - CameraStreamingStart",
                            duration="-", part_of_latency="❌"))

    # Gemini Response Latency
    if is_visual:
        make_stage("Gemini Response Latency", "GeminiResponse - ServerImageConfirmation",
                   "ServerImageConfirmation", "GeminiResponse", "✅")
    else:
        # For non-visual: GeminiResponse - TinyGemmaClassification
        # (covers server takeover + processing + responding, parallel to camera pipeline in visual)
        make_stage("Gemini Response Latency", "GeminiResponse - TinyGemmaClassification",
                   "TinyGemmaClassification", "GeminiResponse", "✅")


    result.stages = stages

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Output formatting
# ──────────────────────────────────────────────────────────────────────────────

def format_markdown(result: AnalysisResult) -> str:
    """Format the analysis result as markdown."""
    lines = []

    lines.append(f"# Jinju Latency Breakdown — evalId: {result.eval_id}, iteration: {result.iteration}")
    lines.append("")
    lines.append(f"**Query type:** {result.query_type}")
    lines.append(f"**Camera turn-on source:** {result.camera_source}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append("```")
    lines.append(f"reported_user_speech_start_time = 08-10 {result.reported_latency_start_time}  (jinjuInvokeTs from JSON)")
    lines.append(f"calculated_user_speech_end_time = 08-10 {result.calculated_user_speech_end_time}  (jinjuInvokeTs + questionAudioDuration = {result.reported_latency_start_time} + {result.question_audio_duration}s)")
    lines.append(f"reported_latency_end_time       = 08-10 {result.reported_latency_end_time}  (calculated_user_speech_end_time + responseTime = {result.calculated_user_speech_end_time} + {result.response_time}s)")
    lines.append("")
    lines.append(f"reported_latency = responseTime = {result.response_time * 1000:.0f} ms")

    lines.append("```")

    lines.append("")
    lines.append("NOTE: Since the models stream the required input, latency here has been defined as the difference b/w input end time and model output.")
    lines.append("")

    # Inferred Flow table
    lines.append("## Inferred Flow")
    lines.append("")
    lines.append("| Checkpoint | Description | Device | Time | Evidence (Log) | Remark |")
    lines.append("|---|---|---|---|---|---|")
    for cp in result.checkpoints:
        # Truncate evidence for table readability
        evidence = cp.evidence
        if len(evidence) > 100:
            evidence = evidence[:97] + "..."
        lines.append(f"| {cp.name} | {cp.description} | {cp.device} | {cp.time} | `{evidence}` | {cp.remark} |")
    lines.append("")

    # Latency Stages table
    lines.append("## Latency Stages")
    lines.append("")
    lines.append("| Stage | Formula (Ckpt A - Ckpt B) | Duration | Part of Latency Duration | Remark |")
    lines.append("|---|---|---|---|---|")
    for stage in result.stages:
        lines.append(f"| {stage.name} | {stage.formula} | {stage.duration} | {stage.part_of_latency} | {stage.remark} |")
    lines.append("")

    return "\n".join(lines)


def format_json(result: AnalysisResult) -> str:
    """Format the analysis result as JSON."""
    return json.dumps({
        'evalId': result.eval_id,
        'iteration': result.iteration,
        'queryType': result.query_type,
        'cameraSource': result.camera_source,
        'reported_latency_start_time': result.reported_latency_start_time,
        'calculated_user_speech_end_time': result.calculated_user_speech_end_time,
        'reported_latency_end_time': result.reported_latency_end_time,
        'reported_latency_ms': result.reported_latency_ms,
        'questionAudioDuration': result.question_audio_duration,
        'responseTime': result.response_time,
        'checkpoints': [asdict(c) for c in result.checkpoints],
        'stages': [asdict(s) for s in result.stages],
    }, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Jinju Latency Breakdown Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python latency_analyzer.py \\
    --companion companion_log_00004.txt \\
    --jinju jinju_log_00004.txt \\
    --vqa-report vqa_report_for_KPI_Visual_QA_TASK.json

  python latency_analyzer.py \\
    --companion companion_log_00004.txt \\
    --jinju jinju_log_00004.txt \\
    --vqa-report vqa_report_for_KPI_Visual_QA_TASK.json \\
    --eval-id q00004 --iteration 1
        """,
    )
    parser.add_argument('--companion', required=True, help='Companion device log file path')
    parser.add_argument('--jinju', required=True, help='Jinju device log file path')
    parser.add_argument('--vqa-report', required=True, help='VQA report JSON file path')
    parser.add_argument('--eval-id', default='', help='evalId (auto-detected from log filename if not provided)')
    parser.add_argument('--iteration', type=int, default=None, help='Iteration number (default: first match)')
    parser.add_argument('--output', '-o', default='', help='Output file path. If not provided, prints to stdout.')
    parser.add_argument('--format', '-f', default='markdown', choices=['markdown', 'json'],
                        help='Output format (default: markdown)')

    args = parser.parse_args()

    result = analyze(
        companion_log=args.companion,
        jinju_log=args.jinju,
        vqa_report=args.vqa_report,
        eval_id=args.eval_id,
        iteration=args.iteration,
    )

    if args.format == 'json':
        output = format_json(result)
    else:
        output = format_markdown(result)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
