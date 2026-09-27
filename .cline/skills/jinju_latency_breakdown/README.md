# Jinju Latency Breakdown Skill

Breaks down Jinju Gemini Live response latency into pipeline stages by analyzing companion log, jinju log, and VQA report JSON.

## Directory Structure

```
jinju_latency_breakdown/
├── SKILL.md                      # Main skill definition (metadata + instructions)
├── README.md                     # This file — navigation guide
└── scripts/
    └── latency_analyzer.py       # Python tool to extract milestones & compute latencies
```

## Quick Start

1. **Read the SKILL.md** — Contains the main skill definition with workflow and usage examples
2. **Use the script** — `latency_analyzer.py` does all the heavy lifting

## Script Usage

```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion <companion_log_path> \
    --jinju <jinju_log_path> \
    --vqa-report <vqa_report_json_path> \
    [--eval-id q00004] \
    [--iteration 1] \
    [--query-type visual|non-visual] \
    [--output <output_path>] \
    [--format markdown|json]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--companion` | Yes | Companion device log file path |
| `--jinju` | Yes | Jinju device log file path |
| `--vqa-report` | Yes | VQA report JSON file path |
| `--eval-id` | No | evalId (auto-detected from log filename if not provided) |
| `--iteration` | No | Iteration number (default: first match) |
| `--query-type` | No | `visual` or `non-visual` (auto-detected from TinyGemma output) |
| `--output`, `-o` | No | Output file path (prints to stdout if not provided) |
| `--format`, `-f` | No | `markdown` (default) or `json` |

### Examples

**Basic usage (auto-detect everything):**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion companion_log_00004.txt \
    --jinju jinju_log_00004.txt \
    --vqa-report vqa_report.json
```

**Save to file as JSON:**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion companion_log_00004.txt \
    --jinju jinju_log_00004.txt \
    --vqa-report vqa_report.json \
    -o latency_breakdown.json -f json
```

**Specify query type and evalId:**
```bash
python .cline/skills/jinju_latency_breakdown/scripts/latency_analyzer.py \
    --companion companion_log_00004.txt \
    --jinju jinju_log_00004.txt \
    --vqa-report vqa_report.json \
    --eval-id q00004 --query-type visual
```

## What It Analyzes

### Milestones Detected

**All query types:**
- Question ends (from JSON: `jinjuInvokeTs + questionAudioDuration`)
- End of speech detected (`[Latency Tracing] User speech ends` in companion log)
- TinyGemma decision (`GC_TinyGemmaCommandReco.*model output:` in companion log)
- TinyGemma command handled (`GC_GC_Agent_AIService: handleInferenceResult:` in companion log)
- RESPONDING state (`state=RESPONDING` in companion log)
- First caption received (`Live API: received captions:` in companion log)
- Response starts (from JSON: `Question end + responseTime`)

**Visual queries only:**
- Camera first frame RUNNING (in jinju log)
- First image sent to server (in companion log)

### Camera Source Detection

- Checks for `GeminiEnableCamera` mapped command from TinyGemma
- Checks all `ArResponse` messages for non-null `toolState` (server tool calls)
- Reports: `TinyGemma`, `server`, or `Unknown`

### Output Format

The script outputs a markdown table with columns:
- Stage name
- Start time (with log line)
- End time (with log line)
- Latency (ms)

Plus:
- JSON metadata summary
- Speech duration comparison (actual vs log-based)
- Camera source determination
- Detailed log lines for each stage

## When to Use

- Breaking down Jinju Gemini Live response latency into pipeline stages
- Determining camera turn-on source (TinyGemma vs server)
- Correlating log-based timestamps with VQA report JSON metadata
- Analyzing visual queries (camera pipeline) or non-visual queries
- Needing per-stage latency with exact log line evidence
