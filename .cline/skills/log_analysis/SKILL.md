---
name: log_analysis
description: Systematic iterative log analysis for Android QA. Use when analyzing device logs, identifying root causes, comparing failing vs. passing cases, or investigating issues like audio failures, visual hallucinations, connection problems, ANRs, crashes. Supports multi-device interlinked log analysis.
---

# Log Analysis Skill

A systematic, structured, and iterative approach to root cause analysis in Android device logs. Supports **multi-device interlinked log analysis** — multiple physical device logs (e.g., Jinju headset + S25 companion phone) can be merged into a single timeline-ordered log and analyzed together.

## Terminology

| Concept | Field | Description | Valid Values |
|---------|-------|-------------|-------------|
| AI agent/system under test | `agent` | One per case. The system being evaluated. | `Jinju-Gemini-Live`, `S25-Gemini-Live`, `S25-GPT-Live`, `Meta-Live`, `S25-Claude-Live` |
| Physical device a log came from | `device` | Multiple per case. Each has its own log file. | `Jinju`, `S25` |

A **case** (bad or good) = one agent + one or more device logs.

## When to Use This Skill

Activate this skill when:
- Analyzing Android logcat logs to find root causes of issues
- Comparing a failing ("bad") case against one or more passing ("good") case logs
- Investigating specific issues: audio failures, visual hallucinations, connection drops, ANRs, crashes
- Performing time-boxed deep investigation (up to 2 hours)
- Need reproducible analysis with documented evidence
- Analyzing multiple interlinked device logs (e.g., Jinju + companion phone)

## CRITICAL: Execution Rules

> **Follow these rules strictly. Do not skip steps. Do not substitute your own approach.**

1. **Execute steps in order.** Do not jump ahead. Do not skip.
2. **Each step has a deliverable.** Do not proceed to the next step until the deliverable is confirmed to exist.
3. **Use the exact script paths shown.** All scripts live in `.cline/skills/log_analysis/scripts/`. Always use the full relative path from the workspace root.
4. **If a script command fails, fix it before proceeding.** Do not abandon the workflow. Common fixes: check the path is correct, check the input file exists, check Python is available.
5. **If a referenced script does not exist**, fall back to the manual command provided in that step's "Fallback" section.
6. **Create all evidence files** in an `evidence/` directory that is a sibling of the folder containing the logs (i.e., `$EVIDENCE_DIR = "$(dirname "$LOGS_DIR")/evidence"`). The evidence directory is structured as `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/` where `qid` is provided by the user and `issue_brief` is a 2-3 word summary of the issue. The evidence path is therefore **relative to the logs being analyzed** — it changes depending on where the logs live. **Never** create the evidence folder at the workspace root unless the logs themselves are at the workspace root.

---

## Steps

### Step 0: Gather Inputs from the User

**Before doing anything**, confirm you have all required inputs:

1. **Issue description** — what is the problem being investigated?
2. **QID** — the question ID for this analysis (used to name the evidence directory).
3. **Agent** — the system under test. Valid: `Jinju-Gemini-Live`, `S25-Gemini-Live`, `S25-GPT-Live`, `Meta-Live`, `S25-Claude-Live`.
4. **Bad case** — one or more device logs, each labeled with a device name. Format: `device_name:log_path` (e.g., `Jinju:jinju_log.txt`, `S25:companion_log.txt`). Valid device names: `Jinju`, `S25`.
5. **Good case(s)** — one or more cases, each with one or more device logs labeled with device names.

**GATE: Do not proceed to Step 1 until all inputs are confirmed. At least one good case is required.**

If any input is missing, ask the user:
> "I need the following to begin analysis: (1) issue description, (2) QID (question ID for naming the evidence directory), (3) agent (Jinju-Gemini-Live, S25-Gemini-Live, S25-GPT-Live, Meta-Live, or S25-Claude-Live), (4) bad case device logs as device:path pairs (e.g., Jinju:jinju_log.txt S25:companion_log.txt — valid devices: Jinju, S25), (5) one or more good case device logs (same format). Please provide the missing items."

If the user has already provided all inputs, proceed immediately to Step 1.

---

### Step 1: Merge Multi-Device Logs

**Goal:** Merge all device logs for each case into a single timeline-ordered log with device annotations, and copy all concerned logs into the evidence directory created during skill execution.

**Instructions:**

First, derive the evidence directory from the logs folder and create it:
```bash
EVIDENCE_DIR="$(dirname "$LOGS_DIR")/evidence"
mkdir -p "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis"
```

**Then, copy all concerned logs into a `raw_logs/` subfolder inside the evidence directory for reproducibility.** This preserves a copy of every input log (bad + all good cases) alongside the analysis artifacts so the analysis can be re-examined without depending on the original log locations. Create the folder and copy every device log there using the naming convention `{bad/good}_{actual_log_file_name}.txt`:
```bash
# Raw logs folder — a copy of every concerned input log lives here
RAW_LOGS_DIR="$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/raw_logs"
mkdir -p "$RAW_LOGS_DIR"

# Copy bad case logs (prefix with "bad_")
cp <bad_log_path_1> "$RAW_LOGS_DIR/bad_{actual_log_file_name_1}.txt"
cp <bad_log_path_2> "$RAW_LOGS_DIR/bad_{actual_log_file_name_2}.txt"

# Copy each good case log (prefix with "good_")
cp <good_log_path_1> "$RAW_LOGS_DIR/good_{actual_log_file_name_1}.txt"
cp <good_log_path_2> "$RAW_LOGS_DIR/good_{actual_log_file_name_2}.txt"
cp <good_log_path_3> "$RAW_LOGS_DIR/good_{actual_log_file_name_3}.txt"
# ... copy ALL bad and good case device logs
```
Example:
```bash
RAW_LOGS_DIR="$EVIDENCE_DIR/q14_audio_failure_analysis/raw_logs"
mkdir -p "$RAW_LOGS_DIR"
cp jinju_log.txt        "$RAW_LOGS_DIR/bad_jinju_log.txt"
cp companion_log.txt    "$RAW_LOGS_DIR/bad_companion_log.txt"
cp jinju_good_1.txt     "$RAW_LOGS_DIR/good_jinju_good_1.txt"
cp companion_good_1.txt "$RAW_LOGS_DIR/good_companion_good_1.txt"
cp jinju_good_2.txt     "$RAW_LOGS_DIR/good_jinju_good_2.txt"
```

> **Important:** Copy **every** input log the user provided for this analysis — all bad case device logs and all good case device logs across all good cases. Do not skip any. This copy is in addition to the merged/filtered artifacts produced later; it ensures the raw originals are preserved inside the evidence directory.

**If the bad case has multiple device logs**, merge them:
```bash
python .cline/skills/log_analysis/scripts/log_merger.py <device1:log1> <device2:log2> ... -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_merged" -f json
python .cline/skills/log_analysis/scripts/log_merger.py <device1:log1> <device2:log2> ... -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_merged" -f text
```
Example:
```bash
python .cline/skills/log_analysis/scripts/log_merger.py Jinju:jinju_log.txt S25:companion_log.txt -o "$EVIDENCE_DIR/q14_audio_failure_analysis/bad_merged" -f json
python .cline/skills/log_analysis/scripts/log_merger.py Jinju:jinju_log.txt S25:companion_log.txt -o "$EVIDENCE_DIR/q14_audio_failure_analysis/bad_merged" -f text
```

**If the bad case has only one device log**, SKIP the merge step. Use the raw log directly. Note the device name for the memory update later.

**For each good case**, repeat the merge if it has multiple device logs:
```bash
python .cline/skills/log_analysis/scripts/log_merger.py <device1:log1> <device2:log2> ... -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/good_merged_1" -f json
python .cline/skills/log_analysis/scripts/log_merger.py <device1:log1> <device2:log2> ... -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/good_merged_1" -f text
```
If a good case has only one device log, use the raw log directly.

**Deliverable:** `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_merged.json` exists (or raw bad log is used directly if single device). At least one good case log (merged or raw) is available. Additionally, `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/raw_logs/` exists and contains a copy of **every** input log (all bad + all good case device logs).

**Fallback (if script fails):** Manually merge using bash — prefix each line with `[DeviceName] `, concatenate, and sort by timestamp:
```bash
# Prefix and merge manually
sed 's/^/[Jinju] /' jinju_log.txt > /tmp/jinju_prefixed.txt
sed 's/^/[S25] /' companion_log.txt > /tmp/s25_prefixed.txt
cat /tmp/jinju_prefixed.txt /tmp/s25_prefixed.txt | sort -t' ' -k2,2 > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_merged.txt"
```

---

### Step 2: Extract Tags and Assign Priorities (Bad Case Only)

**Goal:** Identify and prioritize all log tags from the bad case log.

**Instructions:**
1. Run `tag_extractor.py` on the **bad case log** (merged if multi-device, raw if single device):
   ```bash
   python .cline/skills/log_analysis/scripts/tag_extractor.py <bad_log_path> -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/tags_bad.txt" --sort errors --samples
   ```
   For multi-device logs, add `--by-device` to see per-device tag breakdown:
   ```bash
   python .cline/skills/log_analysis/scripts/tag_extractor.py <bad_merged.txt> -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/tags_bad.txt" --sort errors --samples --by-device
   ```
2. Review the extracted tags in `tags_bad.txt`.
3. Assign a priority (P0, P1, P2, P3) to each tag based on the issue type. **First, read `docs/tag_priority_memory.md`** — this is a living memory file of tag priorities from past verified analyses. **Filter entries by the current agent** — only use entries where the agent matches. If the issue type and agent match a previous entry, use those tag priorities as a starting point. Adjust as needed based on your judgment and the specific issue.
4. Write the prioritized tag list to `"$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/log_priority.txt"` in this format:
   ```
   P0: TagName1, TagName2
   P1: TagName3, TagName4
   P2: TagName5
   P3: (all remaining tags)
   ```

**Deliverable:** `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/log_priority.txt` exists and contains all tags with P0–P3 assignments.

**Fallback (if script fails):** Use bash to extract tags manually:
```bash
grep -oP '^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[VDEWIF]\s+\K[^:]+' <bad_log_path> | sort | uniq -c | sort -rn > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/tags_bad.txt"
```

---

### Step 3: Filter Both Logs by P0 Tags

**Goal:** Create filtered subsets of the bad log and all good logs containing only P0-priority tag entries.

**Instructions:**
1. Read the P0 tags from `log_priority.txt`.
2. Build a pipe-separated tag pattern (e.g., `AudioFlinger|MediaCodec|AudioRecord`).
3. Filter the **bad case log** by P0 tags:
   ```bash
   mkdir -p "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1"
   python .cline/skills/log_analysis/scripts/log_parser.py <bad_log_path> -t "Tag1|Tag2|Tag3" -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_p0.txt"
   ```
4. Filter **each good case log** by the same P0 tags. If there are multiple good cases, name them `good_p0_1.txt`, `good_p0_2.txt`, etc.:
   ```bash
   python .cline/skills/log_analysis/scripts/log_parser.py <good_log_path_1> -t "Tag1|Tag2|Tag3" -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_p0_1.txt"
   python .cline/skills/log_analysis/scripts/log_parser.py <good_log_path_2> -t "Tag1|Tag2|Tag3" -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_p0_2.txt"
   # ... repeat for each good case
   ```

**Deliverable:** `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_p0.txt` exists and is non-empty. At least one `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_p0_N.txt` exists and is non-empty.

**Fallback (if script fails):** Use bash grep:
```bash
mkdir -p "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1"
grep -E "Tag1|Tag2|Tag3" <bad_log_path> > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_p0.txt"
grep -E "Tag1|Tag2|Tag3" <good_log_path_1> > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_p0_1.txt"
# ... repeat for each good case
```

---

### Step 4: Compare Bad vs. Good

**Goal:** Identify differences between the filtered bad log and the filtered good log(s).

**Instructions:**
1. Compare `iteration_1/bad_p0.txt` against each `good_p0_N.txt` using diff:
   ```bash
   diff "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_p0_1.txt" "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_p0.txt" > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/comparison_1.txt"
   # If multiple good cases, diff against each:
   diff "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_p0_2.txt" "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_p0.txt" > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/comparison_2.txt"
   ```
2. Also run `error_analyzer.py` on the bad case to cluster errors and detect critical issues:
   ```bash
   # First, parse the bad log to JSON
   python .cline/skills/log_analysis/scripts/log_parser.py <bad_log_path> -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_parsed.json" -f json
   # Then analyze errors
   python .cline/skills/log_analysis/scripts/error_analyzer.py "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_parsed.json" "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/error_analysis/"
   ```
3. Document the following in `"$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/comparison.json"`:
   - Exact line numbers where differences occur
   - Log file paths for reference
   - Timestamp deltas between bad/good events
   - Missing/extra log entries in the bad case
   - Which good case(s) were compared
   - Which device(s) the differences came from (if multi-device)

**Deliverable:** `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/comparison_N.txt` exists and contains diff output. `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/error_analysis/` contains error cluster reports (with device origin for multi-device logs).

**Fallback (if error_analyzer.py fails):** Manually grep for error-level entries:
```bash
grep -E "\s[EF]\s" <bad_log_path> > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_errors.txt"
grep -E "\s[EF]\s" <good_log_path_1> > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_errors_1.txt"
diff "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/good_errors_1.txt" "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/bad_errors.txt" > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/error_diff_1.txt"
```

---

### Step 5: Decision — Differences Found?

Review the comparison output from Step 4.

**If NO meaningful differences found → Expand Scope and iterate:**
1. Create a new iteration folder: `"$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_2/"`
2. Expand the tag filter to include P1 tags (in addition to P0)
3. Include thread IDs from the bad case errors
4. Re-run Steps 3 and 4 with the expanded scope
5. Repeat until differences are found or all priority levels are exhausted

**If YES, differences found → Proceed to Step 6**

---

### Step 6: Build Timeline and Formulate Root Cause Hypothesis

**Goal:** Reconstruct the event sequence around the failure and present a root cause hypothesis.

**Instructions:**
1. Build a timeline of events around the failure using the P0 tags and any error keywords:
   ```bash
   python .cline/skills/log_analysis/scripts/timeline_builder.py <bad_log_path> "keyword1,keyword2,Tag1" -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/timeline.txt" --context 5
   ```
   For multi-device logs, the timeline shows `[DeviceName]` per entry. To filter to a specific device:
   ```bash
   python .cline/skills/log_analysis/scripts/timeline_builder.py <bad_merged.txt> "keyword1,keyword2" -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/timeline_jinju.txt" --context 5 --device Jinju
   ```

2. **Cross-device correlation** (if multi-device bad case): Find correlated events across devices within the bad case:
   ```bash
   python .cline/skills/log_analysis/scripts/correlation_finder.py "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_merged.json" --from-merged -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/cross_device_correlation.json"
   ```
   This finds events that occurred close in time across different devices (e.g., Jinju error → S25 reaction 0.5s later).

3. **Cross-case correlation** (bad vs. good): Parse good case log(s) to JSON first, then run correlation:
   ```bash
   # Parse good case log(s) to JSON
   python .cline/skills/log_analysis/scripts/log_parser.py <good_log_path_1> -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/good_parsed_1.json" -f json
   # Run correlation between bad and good
   python .cline/skills/log_analysis/scripts/correlation_finder.py "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/bad_parsed.json" "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/good_parsed_1.json" -n bad good1 -o "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/correlation_report.json"
   ```

4. Write the root cause summary to `"$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/final_report.md"` including:
   - Issue description
   - Agent and devices analyzed
   - Root cause hypothesis
   - Supporting evidence (line numbers, timestamps, tag differences, device origin)
   - Cross-device correlations (if multi-device)
   - Comparison between bad and good case(s)
5. Present the hypothesis to the user and ask for validation.

**Deliverable:** `$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/final_report.md` exists with root cause summary. Hypothesis presented to user.

**Fallback (if timeline_builder.py fails):** Use bash to extract a time-ordered view:
```bash
grep -E "keyword1|keyword2|Tag1" <bad_log_path> > "$EVIDENCE_DIR/{qid}_{issue_brief}_analysis/iteration_1/timeline_manual.txt"
```

---

### Step 7: Update Tag Priority Memory (After User Verification)

**Goal:** Record the tags that led to the verified root cause so future analyses benefit from this experience.

**Instructions:**
1. **Only proceed if the user has confirmed the root cause hypothesis is correct.** If the user says the hypothesis is wrong, go back to Step 5 (expand scope) and iterate again. Do not write to the memory file for unverified hypotheses.
2. Read `docs/tag_priority_memory.md`.
3. Append a new entry under the matching issue type section (e.g., `### Audio`, `### Visual / Vision`, etc.) using the entry template from that file. **Include the agent** and **the devices used** in the analysis.
   ```
   #### [Issue Type] — [Date]

   - **Agent:** [agent name, e.g., Jinju-Gemini-Live]
   - **Devices:** [device names, e.g., Jinju, S25]
   - **Issue:** [one-line description of the problem investigated]
   - **Root cause:** [one-line summary]
   - **P0 tags:** [only the tags that directly led to the finding]
   ```
4. Place the newest entry at the top of the section (below the section header).

**Deliverable:** `docs/tag_priority_memory.md` has been updated with a new verified entry.

---

## Evidence Organization

All analysis artifacts are organized in this structure (created during the steps above). The `evidence/` directory is a sibling of the logs folder (`$EVIDENCE_DIR`):

```
$EVIDENCE_DIR/
└── {qid}_{issue_brief}_analysis/
    ├── raw_logs/                       # Step 1: Copies of every concerned input log (bad + good)
    │   ├── bad_{actual_log_file_name}.txt
    │   └── good_{actual_log_file_name}.txt
    ├── bad_merged.txt / .json          # Step 1: Merged bad case (multi-device) — or raw log if single device
    ├── good_merged_1.txt / .json       # Step 1: Merged good case 1 — or raw log if single device
    ├── tags_bad.txt                    # Step 2: All extracted tags from bad log
    ├── log_priority.txt                # Step 2: Tags with P0–P3 priority assignments
    ├── bad_parsed.json                 # Step 4: Bad log parsed to JSON (for error_analyzer)
    ├── good_parsed_1.json              # Step 6: Good log(s) parsed to JSON (for correlation)
    ├── cross_device_correlation.json   # Step 6: Cross-device correlation (if multi-device)
    ├── correlation_report.json         # Step 6: Cross-case correlation (bad vs good)
    ├── iteration_1/
    │   ├── bad_p0.txt                  # Step 3: Filtered bad case (P0 tags)
    │   ├── good_p0_1.txt               # Step 3: Filtered good case 1 (P0 tags)
    │   ├── good_p0_2.txt               # Step 3: Filtered good case 2 (P0 tags) — if multiple
    │   ├── comparison_1.txt            # Step 4: Diff output (bad vs good 1)
    │   ├── comparison_2.txt            # Step 4: Diff output (bad vs good 2) — if multiple
    │   ├── comparison.json             # Step 4: Structured diff with line numbers
    │   ├── error_analysis/             # Step 4: Error cluster reports (with device origin)
    │   └── timeline.txt                # Step 6: Event timeline around failure (with device per entry)
    ├── iteration_2/                    # Created if expanding scope (Step 5)
    │   └── ...
    └── final_report.md                 # Step 6: Root cause summary
```

---

## Tag Priority Memory

Tag priorities are **not hardcoded** — they are learned from experience. The file `docs/tag_priority_memory.md` serves as a living memory of tag-to-priority assignments that have led to successful root cause analyses.

- **Step 2 (read):** Read `docs/tag_priority_memory.md` before assigning priorities. **Filter entries by the current agent** — only use entries where the agent matches. If the issue type and agent match a previous verified entry, use those tag priorities as a starting point.
- **Step 7 (write):** After the user confirms the root cause hypothesis, append the tags that led to the finding to this file, including the agent and devices. This ensures future analyses benefit from past experience.

See `docs/tag_priority_memory.md` for the full format and current entries.

---

## Available Scripts

All scripts are located in `.cline/skills/log_analysis/scripts/`. Always use the full relative path.

| Script | Purpose | Usage |
|---|---|---|
| `log_merger.py` | Merge multiple device logs into timeline-ordered log | `python .cline/skills/log_analysis/scripts/log_merger.py <log1:device1> <log2:device2> -o output -f json` |
| `tag_extractor.py` | Extract all tags with statistics | `python .cline/skills/log_analysis/scripts/tag_extractor.py <log> -o tags.txt --sort errors` |
| `log_parser.py` | Parse and filter Android logcat logs | `python .cline/skills/log_analysis/scripts/log_parser.py <log> -t "Tag1\|Tag2" -o output.txt` |
| `error_analyzer.py` | Cluster errors, detect critical issues | `python .cline/skills/log_analysis/scripts/error_analyzer.py <parsed.json> output_dir/` |
| `timeline_builder.py` | Reconstruct event timelines | `python .cline/skills/log_analysis/scripts/timeline_builder.py <log> "keyword1,keyword2" -o output.txt` |
| `correlation_finder.py` | Cross-log / cross-device correlation analysis | `python .cline/skills/log_analysis/scripts/correlation_finder.py log1.json log2.json -o report.json` |

**Note:** `error_analyzer.py` and `correlation_finder.py` require JSON input. Use `log_parser.py` with `-f json` to convert raw logs to JSON first. `correlation_finder.py` with `--from-merged` takes a single merged JSON and splits by device field automatically.

---

## Documentation

| File | Content |
|---|---|
| `docs/tag_priority_memory.md` | **Living memory** of verified tag priorities (read in Step 2, written in Step 7) |

---

## Iteration Structure

Analysis follows iterative refinement. Each iteration expands scope if no differences are found.

| Iteration | Focus | Duration |
|---|---|---|
| 1 | Error identification (P0 tags only) | 5 min |
| 2 | Pattern recognition (P0+P1 tags, clustering) | 10 min |
| 3 | Timeline reconstruction | 5 min |
| 4 | Cross-component / cross-device correlation | 15 min |
| 5 | Root cause hypothesis | 30 min |
| 6+ | Validation & refinement | As needed |

---

## Example Session

**User Input:**
> Analyze this audio invoke failure. QID: q14. Agent: Jinju-Gemini-Live. Bad case: Jinju:jinju_log.txt, S25:companion_log.txt. Good case 1: Jinju:jinju_good_1.txt, S25:companion_good_1.txt. Good case 2: Jinju:jinju_good_2.txt. Focus on audio pipeline components.

**Execution:**
1. **Step 0:** Confirm inputs — issue: "audio invoke failure", QID: `q14`, agent: `Jinju-Gemini-Live`, bad: `Jinju:jinju_log.txt` + `S25:companion_log.txt` (2 devices), good 1: `Jinju:jinju_good_1.txt` + `S25:companion_good_1.txt` (2 devices), good 2: `Jinju:jinju_good_2.txt` (1 device). ✅ All provided.
2. **Step 1:** Derive `EVIDENCE_DIR` from the logs folder, then create `$EVIDENCE_DIR/q14_audio_failure_analysis/`. **Copy all concerned logs into the evidence directory's `raw_logs/` subfolder:** `mkdir -p "$EVIDENCE_DIR/q14_audio_failure_analysis/raw_logs"` → copy `jinju_log.txt`→`bad_jinju_log.txt`, `companion_log.txt`→`bad_companion_log.txt`, `jinju_good_1.txt`→`good_jinju_good_1.txt`, `companion_good_1.txt`→`good_companion_good_1.txt`, `jinju_good_2.txt`→`good_jinju_good_2.txt`. Merge bad case: `log_merger.py Jinju:jinju_log.txt S25:companion_log.txt -o "$EVIDENCE_DIR/q14_audio_failure_analysis/bad_merged" -f json` (and text). Merge good case 1 similarly → `good_merged_1`. Good case 2 is single device → use raw log directly.
3. **Step 2:** Run `tag_extractor.py --by-device` on `bad_merged.txt` → extract tags → assign P0: GC_AgentRequestHandlerI, GC_GC_Agent_AIService, DeliQueue → write `log_priority.txt`. Read memory, filter by agent `Jinju-Gemini-Live`.
4. **Step 3:** Filter bad merged log by P0 tags → `iteration_1/bad_p0.txt`. Filter each good case → `good_p0_1.txt`, `good_p0_2.txt`.
5. **Step 4:** Diff bad vs each good → `comparison_1.txt`, `comparison_2.txt`. Run `error_analyzer.py` on bad merged JSON → `iteration_1/error_analysis/` (clusters show device origin).
6. **Step 5:** Differences found → proceed to Step 6.
7. **Step 6:** Build timeline with `timeline_builder.py` on `bad_merged.txt` → shows `[Jinju]` / `[S25]` per entry. Run cross-device correlation: `correlation_finder.py bad_merged.json --from-merged` → finds Jinju error → S25 reaction. Run cross-case correlation: `correlation_finder.py bad_parsed.json good_parsed_1.json`. Write `final_report.md` → present root cause hypothesis to user.
8. **Step 7:** User confirms hypothesis is correct → append verified entry (agent: `Jinju-Gemini-Live`, devices: `Jinju, S25`, P0 tags: GC_AgentRequestHandlerI, GC_GC_Agent_AIService, DeliQueue) to `docs/tag_priority_memory.md` under the Audio section.

---

*For detailed commands, templates, and examples, see the `docs/` directory.*
