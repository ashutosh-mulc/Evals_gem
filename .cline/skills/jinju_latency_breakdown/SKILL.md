---
name: jinju_latency_breakdown
description: Breaks down a single Jinju Gemini Live query's response latency into named pipeline stages (session start, user speech, TinyGemma, camera, image stream, Gemini response) using a dedicated analyzer script. Use ONLY when the user wants a per-stage latency breakdown table for one specific Jinju query and has provided companion log + jinju log + VQA report JSON. Do NOT use for general log analysis, root cause investigation, bug hunting, or bad-vs-good case comparison — use the log_analysis skill for those.
---

# Jinju Latency Breakdown Skill

A structured approach to breaking down **a single** Jinju Gemini Live query's response latency into individual pipeline stages. Analyzes companion log + jinju log + VQA report JSON to produce a per-stage latency table with exact log line evidence. This is a **narrow, measurement-focused** skill — it quantifies latency, it does not diagnose bugs.

## When to Use This Skill

Activate this skill **only** when ALL of the following are true:
- The user wants a **per-stage latency breakdown** of a **single** Jinju Gemini Live query (i.e., "how long did each pipeline stage take for this query?")
- The user has (or can provide) all three inputs: companion log, jinju log, and VQA report JSON for that query
- The goal is to **measure and quantify** latency stages, not to investigate why something went wrong

Specific valid use cases:
- Breaking down a single query's response latency into named pipeline stages
- Determining whether camera turn-on was triggered by TinyGemma or the server (as part of a latency breakdown)
- Correlating log-based timestamps with VQA report JSON metadata (`jinjuInvokeTs`, `questionAudioDuration`, `responseTime`) to produce a latency table

## When NOT to Use This Skill — Use `log_analysis` Instead

Do **NOT** activate this skill for any of the following. Use the **`log_analysis`** skill instead:
- **Root cause analysis** of a bug, failure, or unexpected behavior (e.g., "why did the agent not respond?", "why is there no audio?", "why did it hallucinate?")
- **Comparing a failing ("bad") case against passing ("good") case logs** to find differences
- **Investigating issues** like audio failures, visual hallucinations, connection drops, ANRs, crashes
- **General log analysis** — searching logs for errors, extracting tags, building timelines, finding correlations across devices or cases
- **Multi-device interlinked log analysis** (e.g., Jinju + companion phone logs analyzed together for root cause)

**Rule of thumb:** If the user is asking "what went wrong and why?" → `log_analysis`. If the user is asking "how long did each stage take for this query?" → `jinju_latency_breakdown`.

## CRITICAL: Execution Rules

> **Follow these rules strictly. Do not skip steps.**

1. **Execute steps in order.** Do not jump ahead.
2. **Each step has a deliverable.** Do not proceed until the deliverable is confirmed.
3. **Use the exact script path:** `.cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py`
4. **If the script fails, fix it before proceeding.** Common fixes: check paths exist, check Python is available, check JSON is valid.
5. **Always present the final tables to the user** with checkpoints and stages.
6. **Use the correct VQA report JSON:** `vqa_report_for_KPI_Visual_QA_TASK.json` for visual queries, `vqa_report_for_KPI_QA_TASK.json` for non-visual queries. The script auto-detects query type from the JSON filename.

---

## Steps

### Step 0: Gather Inputs from the User

**Before doing anything**, confirm you have all required inputs:

1. **companion_log_path** — companion device log file (e.g., `companion_log_00004.txt`)
2. **jinju_log_path** — jinju device log file (e.g., `jinju_log_00004.txt`)
3. **vqa_report_json_path** — VQA report JSON file (e.g., `vqa_report_for_KPI_Visual_QA_TASK.json` for visual, `vqa_report_for_KPI_QA_TASK.json` for non-visual)
4. **eval_id** *(optional)* — e.g., `q00004`. If not provided, auto-detected from log filenames.
5. **iteration** *(optional)* — iteration number. Defaults to first match.

**Query type is auto-detected from the VQA report JSON filename:**
- `Visual_QA_TASK` in filename → visual
- `QA_TASK` (without `Visual`) → non-visual

**GATE: Do not proceed to Step 1 until at least items 1-3 are confirmed.**

If any required input is missing, ask the user:
> "I need the following to begin latency analysis: (1) companion log path, (2) jinju log path, (3) VQA report JSON path. Optionally: (4) evalId (auto-detected from log filename), (5) iteration number. Please provide the missing items."

If the user has already provided all inputs, proceed immediately to Step 1.

---

### Step 1: Run the Latency Analyzer Script

**Goal:** Run `latency_analyzer.py` to extract all checkpoints, compute latencies, and determine camera source.

**Instructions:**

```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion <companion_log_path> \
    --jinju <jinju_log_path> \
    --vqa-report <vqa_report_json_path> \
    [--eval-id <eval_id>] \
    [--iteration <iteration>] \
    [--output <output_path>] \
    [--format markdown|json]
```

**Example (visual query):**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion data/results/jinju_daily_test_1008_withWifi/immersivesw/eval_set_1/assets/companion_log_00004.txt \
    --jinju data/results/jinju_daily_test_1008_withWifi/immersivesw/eval_set_1/assets/jinju_log_00004.txt \
    --vqa-report data/results/jinju_daily_test_1008_withWifi/immersivesw/vqa_report_for_KPI_Visual_QA_TASK.json \
    --format markdown
```

**Example (non-visual query):**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion data/results/jinju_daily_test_1008_withWifi/immersivesw/eval_set_1/assets/companion_log_00000.txt \
    --jinju data/results/jinju_daily_test_1008_withWifi/immersivesw/eval_set_1/assets/jinju_log_00000.txt \
    --vqa-report data/results/jinju_daily_test_1008_withWifi/immersivesw/vqa_report_for_KPI_QA_TASK.json \
    --format markdown
```

**To save output to a file:**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion <companion_log> --jinju <jinju_log> --vqa-report <vqa_json> \
    -o latency_breakdown.md --format markdown
```

**To get JSON output:**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion <companion_log> --jinju <jinju_log> --vqa-report <vqa_json> \
    -o latency_breakdown.json --format json
```

**Deliverable:** The script outputs a markdown report (or JSON) with:
- Metadata block (`reported_latency_start_time`, `calculated_user_speech_end_time`, `reported_latency_end_time`, `reported_latency`)
- Inferred Flow table (checkpoints with description, device, time, evidence, remark)
- Latency Stages table (stage, formula, duration, part of latency duration, remark)
- Camera turn-on source determination (TinyGemma vs server)

**Fallback (if script fails):** Manually search the logs using `grep` for each checkpoint pattern (see Checkpoint Reference below). Then manually compute latencies from the timestamps.

---

### Step 2: Review and Present Results

**Goal:** Review the script output and present it to the user.

**Instructions:**
1. Review the markdown output from the script.
2. Verify that all checkpoints were found (no "NOT FOUND" entries).
3. If any checkpoints are missing, investigate manually using `grep` on the logs.
4. Present the results to the user, highlighting:
   - The camera turn-on source (TinyGemma vs server)
   - The reported latency and its breakdown
   - The biggest bottleneck stage
   - Any speech duration discrepancy (actual vs log-based)
   - Any negative or unusual latencies (remarked in the tables)

**Deliverable:** The latency breakdown tables are presented to the user with all checkpoints, stages, and latencies.

---

## Checkpoint Reference

The script identifies 15 checkpoints from the logs:

| # | Checkpoint | Description | Device | Log Pattern | Match Strategy |
|---|---|---|---|---|---|
| 1 | SessionInvoke | Button press to invoke AI agent | companion | `ACTION_UP.*KEYCODE_FEATURED_APP_1` | first match |
| 2 | SessionReady | Agent session enters STARTING state | companion | `GC_AgentRequestHandlerI.*state=STARTING` | first match |
| 3 | SessionAudioStart | MCU begins audio capture | jinju | `PROJ_AUDIOCAP service.cc:505.*Begin audio capture` | first match |
| 4 | UserSpeechStart | VAD detects user speech onset | companion | `[Latency Tracing] User speech starts` | first match |
| 5 | UserSpeechEnd | VAD detects user speech end | companion | `[Latency Tracing] User speech ends` | first match |
| 6 | AudioEnhancementStart | SEANet model selection begins | companion | `Starting SEANet model selection` | first match |
| 7 | AudioEnhancementDumpStart | Denoised audio saved to WAV | companion | `Saving WAV file for stream DENOISED` | first match |
| 8 | CameraOpen | CameraService receives openStream request | jinju | `CameraService: openStream: received (LatencyMilestone)` | first match |
| 9 | CameraReady | CameraService finishes openStream | jinju | `CameraService: openStream(\d+) finished (LatencyMilestone)` | first match |
| 10 | TinyGemmaClassification | TinyGemma outputs classification | companion | `GC_TinyGemmaCommandReco.*[PRIMARY FC PROMPT] model output:` | **closest to calculated_user_speech_end_time** |
| 11 | GeminiProcessingStart | Agent enters PROCESSING state | companion | `GC_AgentRequestHandlerI.*state=PROCESSING` | first match |
| 12 | ServerVisualClassification | Server/ODA activates dynamic camera | companion | `ODA or server path activates dynamic camera` | first match |
| 13 | CameraStreamingStart | Camera stream starts (prewarmed) | companion | `Camera stream already prewarmed with same parameters, starting stream` | first match |
| 14 | ServerImageConfirmation | Server receives frames from camera | companion | `ODA or server path returning frames from camera` | first match |
| 15 | GeminiResponse | Agent enters RESPONDING state | companion | `GC_AgentRequestHandlerI.*state=RESPONDING` | first match |

**Important:** TinyGemmaClassification uses closest-match to `calculated_user_speech_end_time` because the pattern (`model output:`) appears multiple times in the log (e.g., "noise" outputs from background audio). Using the first match would give negative latencies.

**For non-visual queries**, checkpoints 8-9 and 12-14 show "-" (not applicable).

## Stage Reference

The script computes 7 latency stages:

| Stage | Formula | Visual | Non-visual |
|---|---|---|---|
| Session Start Latency | SessionReady - SessionInvoke | ✅ | ✅ |
| Camera PreWarm Duration | CameraReady - CameraOpen | ✅ | - |
| User Speech Duration | UserSpeechEnd - UserSpeechStart | ✅ | ✅ |
| TinyGemma Latency | TinyGemmaClassification - calculated_user_speech_end_time | ✅ | ✅ |
| Image Stream | CameraStreamingStart - TinyGemmaClassification | ✅ | - |
| Image Transmission Server | ServerImageConfirmation - CameraStreamingStart | ✅ | - |
| Gemini Response Latency | GeminiResponse - ServerImageConfirmation (visual) / GeminiResponse - TinyGemmaClassification (non-visual) | ✅ | ✅ |

**Note on Gemini Response Latency formula difference:**
- **Visual:** `GeminiResponse - ServerImageConfirmation` — measures server processing after receiving the image
- **Non-visual:** `GeminiResponse - TinyGemmaClassification` — covers server takeover (VAD finalization + state transitions) + processing + responding. This is parallel to the camera pipeline (Image Stream + Image Transmission) in visual queries. The small residual gap (RESPONDING → reported_latency_end_time) is TTS/audio streaming delay and is acceptable.

## Metadata Computation

```
reported_user_speech_start_time = jinjuInvokeTs (from JSON)
calculated_user_speech_end_time = jinjuInvokeTs + questionAudioDuration
reported_latency_end_time = calculated_user_speech_end_time + responseTime
reported_latency = responseTime
```


NOTE: Since the models stream the required input, latency here has been defined as the difference b/w input end time and model output.

## Camera Source Detection

- **TinyGemma**: `Direct inference command activates dynamic camera` found in companion log
- **Server**: `ODA or server path activates dynamic camera` found in companion log
- If both found and TinyGemma fires first → "TinyGemma (server also fired but camera already on)"
- If both found and server fires first → "server (TinyGemma also fired later)"
- For non-visual queries → "N/A (non-visual query)"

## Remark Logic

Remarks are only filled when a bug or uncommon number is detected:
- **UserSpeechEnd checkpoint**: If log-based end differs from `calculated_user_speech_end_time` by >500ms, remark about VAD/silence detection delay
- **User Speech Duration stage**: If log-based duration differs from `questionAudioDuration`, remark about the delta
- All other checkpoints/stages: empty remark (unless bugs are discovered)

## Part of Latency Duration (✅/❌)

- ✅ if the stage's time range overlaps with [reported_latency_start_time, reported_latency_end_time]
- ❌ otherwise

---

## Available Scripts

All scripts are located in `.cline/skills/jinju_latency_breakdown/scripts/`. Always use the full relative path.

| Script | Purpose | Usage |
|---|---|---|
| `latency_analyzer.py` | Extract checkpoints, compute latencies, determine camera source | `python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py --companion <log> --jinju <log> --vqa-report <json> [--eval-id q00004] [--iteration 1]` |

---

## Example Session

**User Input:**
> Analyze the latency for this Jinju query. Companion log: companion_log_00004.txt, Jinju log: jinju_log_00004.txt, VQA report: vqa_report_for_KPI_Visual_QA_TASK.json.

**Execution:**
1. **Step 0:** Confirm inputs — companion log, jinju log, VQA report JSON all provided. evalId will be auto-detected as `q00004`. Query type auto-detected as "visual" from JSON filename.
2. **Step 1:** Run the script:
   ```bash
   python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
       --companion data/results/jinju_daily_test_1008_withWifi/immersivesw/eval_set_1/assets/companion_log_00004.txt \
       --jinju data/results/jinju_daily_test_1008_withWifi/immersivesw/eval_set_1/assets/jinju_log_00004.txt \
       --vqa-report data/results/jinju_daily_test_1008_withWifi/immersivesw/vqa_report_for_KPI_Visual_QA_TASK.json \
       --format markdown
   ```
3. **Step 2:** Review output — all checkpoints found, camera source is TinyGemma, present tables to user.

---

*For detailed script usage, see `README.md`.*
