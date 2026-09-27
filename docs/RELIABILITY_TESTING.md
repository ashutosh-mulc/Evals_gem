# Reliability Testing System

## Overview

The reliability testing system provides a structured, traceable way to run app evaluation
test cases multiple times and measure their reliability (pass rate, failure patterns, flakiness).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    run_batch.py                              │
│  (Groups dataset by category, runs each category in batch)  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   run_test_case.py                           │
│  (Runs a single test case through the full pipeline)        │
│                                                             │
│  Pipeline Steps:                                            │
│  1. init          → Record question metadata                │
│  2. decode_media  → Decode base64 audio + image             │
│  3. capture_pre_state → Device info before invocation       │
│  4. invoke_device → Trigger Jinju Gemini + play audio      │
│  5. record_response → ARAP records the response             │
│  6. capture_post_state → Device info after invocation       │
│  7. transcribe_response → Whisper transcription service     │
│  8. verify_state_change → Programmatic state verification  │
│  9. judge → LLM judge scores the response                   │
│  10. image_verification → Multimodal LLM screenshot check   │
│  11. overall → Aggregate pass/fail                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   execution_tracer.py                        │
│  (Records each step as a JSON trace with timestamps,        │
│   inputs, outputs, status, and error info)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  reliability_tracker.py                      │
│  (Aggregates traces into reliability report:                │
│   - Per-eval pass rates                                    │
│   - Reliability tiers (STABLE/PARTIAL/UNSTABLE)             │
│   - Failure step analysis                                  │
│   - HTML dashboard)                                        │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. `scripts/execution_tracer.py`
Structured step-by-step execution tracer. Records each pipeline step with:
- Timestamp and elapsed time
- Inputs and outputs (sanitized for JSON)
- Status (success/failure/skipped)
- Error messages

**Output:** `scratch_pad/runs/<eval_id>/trace_<eval_id>_run<N>.json`

### 2. `scripts/run_test_case.py`
Parameterized single test-case runner. Runs one dataset question through the full pipeline.

```bash
# Single run
python scripts/run_test_case.py --eval-id q00001 --config configs/jinju_gemini_config.json

# 3 runs for reliability testing
python scripts/run_test_case.py --eval-id q00001 --runs 3

# Batch of eval IDs
python scripts/run_test_case.py --eval-ids q00001,q00002,q00003 --runs 2

# Dry run (no device interaction)
python scripts/run_test_case.py --eval-id q00001 --dry-run
```

### 3. `scripts/run_batch.py`
Batch runner that groups dataset entries by question type category.

```bash
# List all categories
python scripts/run_batch.py --list

# Run all volume questions, 3 runs each
python scripts/run_batch.py --filter volume --runs 3

# Run all device-control questions
python scripts/run_batch.py --group device --runs 2

# Quick smoke test: 5 questions per category
python scripts/run_batch.py --per-category 5 --runs 1
```

### 4. `scripts/reliability_tracker.py`
Aggregates execution traces into reliability metrics.

```bash
# Generate JSON + HTML report
python scripts/reliability_tracker.py --html
```

**Output:**
- `scratch_pad/reliability_report.json` — Machine-readable report
- `scratch_pad/reliability_report.html` — Visual dashboard

### 5. `scripts/image_verifier.py`
Uses a multimodal LLM to verify before/after screenshots.

```bash
python scripts/image_verifier.py \
  --before screenshot_before.png \
  --after screenshot_after.png \
  --question-type online_device_volume_up \
  --question "Turn it up"
```

## Reliability Tiers

| Tier | Pass Rate | Meaning |
|------|-----------|---------|
| STABLE | >90% | Consistently passes, ready for production |
| PARTIAL | 50-90% | Intermittent failures, needs investigation |
| UNSTABLE | <50% | Frequently fails, needs debugging |
| NO_DATA | N/A | No traces found |

## scratch_pad/ Directory Structure

```
scratch_pad/                    # NOT pushed to git
├── runs/                       # All run traces
│   ├── q00001/
│   │   ├── trace_q00001_run1.json
│   │   ├── trace_q00001_run2.json
│   │   ├── audio_question.wav
│   │   ├── image_question.png
│   │   └── response_q00001_run1.mp3
│   ├── q00002/
│   │   └── ...
│   └── ...
├── audio/                      # Audio artifacts
├── images/                     # Image artifacts
├── failed_cases/               # Failed case analysis
├── reliability_report.json     # Aggregated reliability report
└── reliability_report.html     # Visual dashboard
```

## Trace JSON Format

```json
{
  "eval_id": "q00001",
  "run_id": 1,
  "total_elapsed_ms": 12453.22,
  "num_steps": 10,
  "overall_status": "success",
  "steps": [
    {
      "step": "decode_media",
      "timestamp": "2026-08-26T03:03:58.413247",
      "elapsed_ms": 0.31,
      "inputs": {"audio_b64_len": 51944, "image_b64_len": 2596},
      "outputs": {"audio_path": "...", "image_path": "..."},
      "status": "success",
      "error": null
    },
    ...
  ]
}
```

## Workflow

1. **Smoke test** (dry run, no device):
   ```bash
   python scripts/run_batch.py --group device --per-category 2 --runs 1 --dry-run
   ```

2. **Batch 1: Device controls** (volume, battery, datetime, DND, media, notification):
   ```bash
   python scripts/run_batch.py --group device --runs 3
   ```

3. **Batch 2: Samsung apps** (notes, reminders, calendar, clock, camera, message, call):
   ```bash
   python scripts/run_batch.py --group samsung --runs 3
   ```

4. **Batch 3: Google apps** (calendar, keep, mail, maps, tasks, translate, youtube music):
   ```bash
   python scripts/run_batch.py --group google --runs 3
   ```

5. **Batch 4: Third-party apps** (spotify, whatsapp):
   ```bash
   python scripts/run_batch.py --group thirdparty --runs 3
   ```

6. **Review results**:
   ```bash
   # Open the HTML dashboard
   open scratch_pad/reliability_report.html
   ```

## Services Required

| Service | URL | Purpose |
|---------|-----|---------|
| Transcription | `http://107.99.238.186:8080` | Whisper transcription of response audio |
| Judge (VLM) | `http://107.99.238.186:8282/v1` | LLM judge + multimodal image verification |
| ARAP | ADB devices | Audio playback + recording |
| Jinju Gemini | ADB device | AI assistant being tested |
| Companion (S25) | ADB device | Phone running the apps |
