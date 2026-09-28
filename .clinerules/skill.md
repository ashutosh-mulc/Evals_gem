# Skill: Reliability Testing for App Evaluation Pipeline

## Purpose

This skill guides the process of testing the reliability of the Jinju Gemini app evaluation
pipeline. The workflow is: **run the full dataset evaluation first, then analyze failure
cases one by one after evaluation**. It covers running the automator, triaging failures from
reports, identifying unreliable components, and making structured code fixes — without
creating code bloat.

---

## When to Use

Use this skill when:
- You need to run a full dataset evaluation and analyze the results
- A specific test case (eval ID) needs reliability verification after a full run
- A test case is failing intermittently or consistently
- You need to verify that a code change didn't break existing behavior
- You need to establish a baseline pass rate for a new test case

---

## Prerequisites

Before running any evaluation, verify the environment:

```bash
# 1. Check all prerequisites (devices, services, config)
python scripts/pre_run_checks.py configs/jinju_gemini_config.json

# 2. Run smoke test (connectivity, services, single E2E case)
python scratch_pad/checks/smoke_test_jinju.py --config configs/jinju_gemini_config.json --skip-e2e --skip-invoke

# 3. Full smoke test with Jinju invoke + E2E
python scratch_pad/checks/smoke_test_jinju.py --config configs/jinju_gemini_config.json --eval-id q00065
```

All pre-run checks must pass. All smoke test checks must pass (8/8).

---

## Phase 1: Full Dataset Evaluation

Run the full evaluation pipeline via the automator. This orchestrates three screen sessions:
- `agent_tester` — device interaction, audio playback/recording, state capture
- `judge_worker` — LLM judging of responses
- `coordinator` — queue management, result collection

```bash
# Run the full evaluation pipeline
python -m automator.automator configs/jinju_gemini_config.json
```

### What happens during evaluation
1. The automator creates `eval_set_1/` under `root_folder` (from config)
2. The agent_tester processes each dataset entry: decode media → display image → capture pre-state → invoke device → play question audio → record response → capture post-state → capture app meta info
3. The judge_worker scores each response (QA, VQA, hallucination, app-eval tasks)
4. The coordinator collects results into `vqa_report.jsonl`
5. If `num_evaluations > 1`, subsequent rounds re-run only failures (rating < 3)
6. After all rounds, `PostProcessAutomator` generates:
   - `vqa_report.jsonl` — final aggregated report (best rating per eval ID)
   - `bad_responses.txt` — all failures with question, gt_answer, ai_response, rating
   - Category-wise bar charts and summary report
   - XR Board reports (if configured)

### Key output locations
```
{root_folder}/
├── eval_set_1/
│   ├── vqa_report.jsonl          # Per-round results
│   ├── bad_responses.txt         # Failures with details
│   ├── eval_config.json          # Config used for this round
│   └── {dataset_name}            # Copy of dataset
├── eval_set_2/                   # Round 2 (failures only, if num_evaluations > 1)
├── vqa_report.jsonl              # Final aggregated report
├── summary_report.txt            # Text summary with hit rates
└── *_category_wise.png           # Category-wise rating charts
```

---

## Phase 2: Triage Failures from Evaluation Report

After the full evaluation completes, analyze the failures systematically.

### Read the bad responses file
```bash
# View all failures with context
cat {root_folder}/eval_set_1/bad_responses.txt
```

### Parse the report programmatically
```bash
python3 -c "
import json

with open('{root_folder}/vqa_report.jsonl') as f:
    lines = f.readlines()

header = json.loads(lines[0])
entries = [json.loads(line) for line in lines[1:]]

# Group by eval type
by_type = {}
for entry in entries:
    # entry is a list of rounds (best first)
    best = entry[0] if isinstance(entry, list) else entry
    eval_type = best.get('eval_type', 'unknown')
    rating = best.get('rating', 0)
    by_type.setdefault(eval_type, []).append((best.get('eval_id', ''), rating, best.get('question_type', '')))

for et, items in sorted(by_type.items()):
    failures = [i for i in items if i[1] is None or int(i[1]) < 3]
    print(f'{et}: {len(failures)}/{len(items)} failed')
    for eval_id, rating, qt in failures:
        print(f'  {eval_id}: rating={rating} type={qt}')
"
```

### Triage strategy
1. **Group failures by question type** — If many cases of the same type fail, it's likely a systemic issue (e.g., all `volume_up` cases fail → device state capture issue)
2. **Group by failure pattern**:
   - `rating=0` or `None` → pipeline crash (device didn't respond, transcription failed, judge errored)
   - `rating=1-2` → AI responded but answer was wrong/incomplete
   - `rating=None` → eval ID crashed/timed out, never made it into the report
3. **Prioritize systemic fixes first** — Fixing one shared component (e.g., transcription service) may resolve many failures at once
4. **Then fix individual cases** — One by one, starting with the most common failure pattern

---

## Phase 3: Analyze & Fix Individual Failures (One by One)

For each failing eval ID, follow this loop:

### Step 1: Locate artifacts
Artifacts are in `{root_folder}/eval_set_N/assets/`:
- `image_{eval_id}.png` — image shown to the AI
- `audio_{eval_id}.wav` — question audio
- `response_{eval_id}.mp3` — AI's recorded response
- `logcat_{eval_id}.txt` — device logs (if `dump_device_logs: true`)
- `app_screenshot_{eval_id}.png` — companion device screenshot (if captured)

### Step 2: Analyze the failure
- **If rating=0 or None**: Check if the device was invoked, if audio was recorded, if transcription succeeded, if the judge returned a valid response
- **If rating=1-2**: The AI responded but the answer was wrong. Check:
  - Is the transcription accurate? (listen to `response_{eval_id}.mp3`)
  - Did the device state actually change? (check pre/post state in metadata)
  - Was the judge prompt appropriate for this question type?

### Step 3: Check the app screenshot (companion device)
Use the image analysis tool to verify the app screenshot:
```
analyze_image(["{root_folder}/eval_set_1/assets/app_screenshot_{eval_id}.png"],
  "This is a screenshot from a Samsung phone after asking an AI to 'Launch Samsung Notes app'.
   1. What app is shown? 2. Is Samsung Notes in the foreground? 3. Describe briefly.")
```

### Step 4: Check the Jinju logcat (glass device — no UI)
```
{root_folder}/eval_set_1/assets/logcat_{eval_id}.txt
```
Look for Gemini/Bard activity keywords to confirm the AI was invoked.

### Step 5: Identify the unreliable component

| Failure Pattern | Likely Cause | Investigation |
|----------------|-------------|----------------|
| No response audio | ARAP recorder not working | Check ARAP app is running |
| Empty transcription | Transcription service down | Check `curl http://<url>/health/` |
| Transcription is garbage | Background noise / ARAP quality | Listen to `response_{eval_id}.mp3` |
| Rating=0 from judge | Judge service error | Check `curl http://<url>/v1/models` |
| Rating=1-2 (wrong answer) | AI didn't understand the task | Check question audio, image shown |
| No state change detected | Device didn't respond to command | Check logcat for Gemini keywords |
| No app screenshot | App not in foreground | Check companion device screen |
| image_captured=False | Camera capture flag from logcat unreliable | Check `jinju_image_captured` flag in metadata |
| Crash / eval ID missing | Pipeline crashed mid-evaluation | Check agent_tester.log for tracebacks |

### Step 6: Make the minimal fix

#### Principles for Code Changes
1. **Minimal changes** — Fix only the broken component, don't refactor unrelated code
2. **No code bloat** — Don't add new abstractions or layers; fix in place
3. **Match existing patterns** — Follow the patterns already in the codebase
4. **Test before and after** — Run the test case before and after the fix to confirm
5. **One fix at a time** — Don't batch multiple unrelated fixes

#### Where to Make Changes

| Component | File | Notes |
|-----------|------|-------|
| Device invocation | `agent_testers/device_managers/jinju_gemini_manager.py` | `invoke()` method |
| Agent tester pipeline | `agent_testers/agent_tester.py` | `execute()` method — main pipeline |
| ARAP audio | `agent_testers/arap_manager.py` | `play_audio()`, `start_recording()` |
| State collection | `agent_testers/device_managers/mixins/` | `device_info.py`, `app_meta_info.py` |
| XRClaw state | `agent_testers/device_managers/xrclaw_state_collector.py` | App state via XRClaw |
| Consent audio | `agent_testers/consent_player.py` | `play_consent()` |
| Judge prompts | `judge_worker/prompts/` | JSON files per app, loaded by `judge_prompts.py` |
| Judge scoring | `judge_worker/response_scorer.py` | `run_judge()`, `get_judge_score()` |
| Deterministic judge | `judge_worker/deterministic_judge.py` | Programmatic verification |
| Transcription | `services/host/transcription_server.py` | Whisper service |
| Automator | `automator/automator.py` | Evaluation orchestration |
| Coordinator | `metric_coordinator/coordinator.py` | Queue management |
| Pre-run checks | `scripts/pre_run_checks.py` | Environment validation |

### Step 7: Verify the fix
Re-run just the fixed eval ID to confirm:

```bash
# Quick single-case verification (3 runs for reliability)
python scripts/run_test_case.py \
  --eval-id <eval_id> \
  --runs 3 \
  --config configs/jinju_gemini_config.json \
  --scratch-pad scratch_pad/verify_<eval_id>
```

Alternatively, re-run via the automator with a filtered dataset containing only the fixed cases.

### Step 8: Move to the next failure
Repeat Steps 1-7 for each failing eval ID.

---

## Phase 4: Regression Check

After fixing individual failures:

### Re-run the full evaluation
```bash
# Full re-run (or just the affected categories)
python -m automator.automator configs/jinju_gemini_config.json
```

### Compare before/after
- Check that previously failing cases now pass (rating >= 3)
- Check that no previously passing cases regressed
- Compare `vqa_report.jsonl` and `summary_report.txt` against the baseline

### Run unit tests
```bash
# Run existing tests
python -m pytest test/ -v

# Run specific test
python -m pytest test/unit/test_deterministic_judge.py -v
```

---

## Document Known Limitations

Some test cases have inherent verification limitations. Document these:

### Ambiguous / Hard-to-Verify Test Cases

| Question Type | Limitation | Workaround |
|--------------|------------|------------|
| `online_device_volume_up` | "Turn it up" is ambiguous — volume up could mean media, call, or alarm volume | Check `device_info` for media volume specifically |
| `online_samsung_notes_create` | Can't verify note content matches exactly (OCR unreliable) | Use XRClaw `get_notes()` for programmatic content check |
| `online_samsung_notes_read` | Can't verify what Gemini actually read aloud | Check transcription for key phrases from the note |
| `online_samsung_camera_*` | Camera capture flag from logcat is unreliable | Check `jinju_image_captured` flag in metadata |
| `online_device_notifications` | Notification panel state is transient | Screenshot must be taken immediately after response |
| `online_google_maps_*` | Maps UI changes frequently, OCR unreliable | Use location/coordinates from XRClaw if available |
| `online_thirdparty_spotify_*` | Spotify requires login, may not be logged in | Pre-check Spotify login state before running |
| `online_thirdparty_whatsapp_*` | WhatsApp requires contact selection, UI varies | Pre-seed contacts before test |

### Technical Limitations

1. **Jinju is a glass device** — No UI screenshots. Verify via logcat only.
2. **ARAP recording quality** — Background noise can affect transcription accuracy.
3. **Judge LLM temperature** — Even at temperature=0, vLLM may produce slightly different
   outputs across runs due to batching. Use `enable_thinking=False` for consistency.
4. **Bluetooth pairing** — Jinju ↔ companion Bluetooth can drop. Check pairing before each run.
5. **Display server** — Image must be shown on physical display monitor for Jinju camera.
   The display server (port 5051) must be running and the monitor must be on.
6. **Consent audio timing** — Consent audio plays during recording. If timing is off,
   the consent audio may be transcribed as part of the response.

---

## Structured Change Management

### Before Making Code Changes

1. **Create a branch** (if using git):
   ```bash
   git checkout -b fix/reliability-<eval-id>-<issue>
   ```

2. **Record the baseline** — Note the current pass rate from the full evaluation run.

3. **Document the issue** — Write a brief description of what's broken:
   ```
   Issue: <eval_id> fails with rating <N> — <brief description>
   Root cause: <analysis>
   Fix: <description of change>
   Files changed: <list>
   ```

### After Making Code Changes

1. **Re-run the fixed eval ID** to confirm the fix works.

2. **Compare before/after** — Check that:
   - The previously failing case now passes
   - No previously passing cases regressed
   - The overall pass rate improved

3. **Run related test cases** — If you changed a shared component (e.g., `jinju_gemini_manager.py`),
   run other test cases that use the same component:
   ```bash
   python scripts/run_test_case.py --eval-ids q00065,q00066,q00067 --runs 1
   ```

4. **Update tests** — If you changed behavior, update or add unit tests:
   ```bash
   # Run existing tests
   python -m pytest test/ -v

   # Run specific test
   python -m pytest test/unit/test_deterministic_judge.py -v
   ```

5. **Commit with descriptive message**:
   ```bash
   git add -A
   git commit -m "fix: <eval_id> <step> — <brief description>

   - Root cause: <analysis>
   - Fix: <description>
   - Verified: 3/3 runs pass for <eval_id>

   Co-Authored-By: Cline SR"
   ```

---

## Quick Reference: Common Commands

```bash
# ── Full Dataset Evaluation ──────────────────────────────────────
# Run the full evaluation pipeline (agent_tester + judge_worker + coordinator)
python -m automator.automator configs/jinju_gemini_config.json

# Pre-run checks
python scripts/pre_run_checks.py configs/jinju_gemini_config.json

# ── Failure Analysis ─────────────────────────────────────────────
# View all failures from a round
cat {root_folder}/eval_set_1/bad_responses.txt

# View the final aggregated report
cat {root_folder}/vqa_report.jsonl

# View summary report (hit rates, mean ratings)
cat {root_folder}/summary_report.txt

# ── Single Case Verification (quick check after fix) ────────────
# Single run
python scripts/run_test_case.py --eval-id q00065 --config configs/jinju_gemini_config.json

# Reliability test (3 runs)
python scripts/run_test_case.py --eval-id q00065 --runs 3 --config configs/jinju_gemini_config.json

# Dry run (no device interaction, test runner logic only)
python scripts/run_test_case.py --eval-id q00065 --dry-run --config configs/jinju_gemini_config.json

# ── Batch Verification ──────────────────────────────────────────
# Run specific category
python scripts/run_batch.py --group samsung --runs 1

# List dataset categories
python scripts/run_batch.py --list

# ── Reports ─────────────────────────────────────────────────────
# Reliability report (from run_test_case / run_batch traces)
python scripts/reliability_tracker.py --html

# ── Tests ───────────────────────────────────────────────────────
# Run unit tests
python -m pytest test/ -v

# Run specific test
python -m pytest test/unit/test_deterministic_judge.py -v
```

---

## Output Directory Structure

```
{root_folder}/                          # From config: paths.root_folder
├── eval_set_1/                         # Round 1 (full dataset)
│   ├── vqa_report.jsonl                # Per-round results
│   ├── bad_responses.txt               # Failures with details
│   ├── eval_config.json                # Config used for this round
│   ├── {dataset_name}                  # Copy of dataset
│   └── assets/                         # All evaluation artifacts
│       ├── image_{eval_id}.png         # Image shown to AI
│       ├── audio_{eval_id}.wav         # Question audio
│       ├── response_{eval_id}.mp3      # AI's recorded response
│       ├── logcat_{eval_id}.txt        # Device logs
│       └── app_screenshot_{eval_id}.png # Companion device screenshot
├── eval_set_2/                         # Round 2 (failures only, if num_evaluations > 1)
├── vqa_report.jsonl                    # Final aggregated report
├── summary_report.txt                  # Text summary with hit rates
├── *_category_wise.png                 # Category-wise rating charts
└── *_bad_iterations.png                # Bad iterations bar chart

scratch_pad/                            # NOT pushed to git (.gitignore)
├── checks/                             # Prerequisite + smoke test scripts
│   ├── prereq_check.py                 # 16-point prerequisite checker
│   └── smoke_test_jinju.py             # 8-point smoke test
├── runs/                               # Single-case verification runs
│   └── <eval_id>/
│       └── trace_<eval_id>_run<N>.json
├── verify_<eval_id>/                   # Post-fix verification runs
├── reliability_report.json             # Aggregated reliability metrics
└── reliability_report.html             # Visual dashboard
```
