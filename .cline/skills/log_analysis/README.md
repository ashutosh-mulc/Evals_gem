# Log Analysis Skill

Systematic iterative log analysis for Android QA engineers.

## Directory Structure

```
log_analysis/
├── SKILL.md                    # Main skill definition (metadata + instructions)
├── README.md                   # This file - navigation guide
├── docs/                       # Documentation
│   └── tag_priority_memory.md  # Living memory of verified tag priorities
└── scripts/                    # Python analysis tools
    ├── log_merger.py           # Merge multiple device logs into timeline-ordered log
    ├── log_parser.py           # Parse and filter Android logcat logs
    ├── error_analyzer.py       # Cluster errors, detect critical issues
    ├── timeline_builder.py     # Reconstruct event timelines
    ├── correlation_finder.py   # Cross-log correlation analysis
    └── tag_extractor.py        # Extract all tags with statistics
```

## Quick Start

1. **Read the SKILL.md** - Contains the main skill definition with workflow and usage examples
2. **Use scripts/** - Python tools for automated analysis

## Documentation Index

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | Main skill definition with YAML front matter |
| [docs/tag_priority_memory.md](docs/tag_priority_memory.md) | Living memory of verified tag priorities (read in Step 2, written in Step 7) |

## Scripts Index

| Script | Purpose | Example |
|--------|---------|---------|
| [log_merger.py](scripts/log_merger.py) | Merge device logs | `python log_merger.py Jinju:log1.txt S25:log2.txt -o out -f json` |
| [log_parser.py](scripts/log_parser.py) | Parse and filter logs | `python log_parser.py log.txt -t "Tag1\|Tag2" -o out.txt` |
| [error_analyzer.py](scripts/error_analyzer.py) | Cluster and analyze errors | `python error_analyzer.py parsed.json output/` |
| [timeline_builder.py](scripts/timeline_builder.py) | Build event timelines | `python timeline_builder.py log.txt "kw1,kw2" timeline.txt` |
| [correlation_finder.py](scripts/correlation_finder.py) | Cross-log correlation | `python correlation_finder.py log1.json log2.json -o report.json` |
| [tag_extractor.py](scripts/tag_extractor.py) | Extract tags with stats | `python tag_extractor.py log.txt -o tags.txt --sort errors` |

## Workflow Summary

```
1. Merge device logs (if multi-device) → log_merger.py
2. Copy concerned logs → raw_logs/ in evidence directory
3. Extract tags → tag_extractor.py
4. Assign priorities (P0, P1, P2, P3)
5. Filter logs → log_parser.py
6. Compare/Analyze → error_analyzer.py or correlation_finder.py
7. Build timeline → timeline_builder.py
8. Document findings
```

## When to Use

- Analyzing Android logcat logs for root cause analysis
- Comparing failing vs. passing case logs
- Investigating: audio failures, visual hallucinations, connection drops, ANRs, crashes
- Time-boxed deep investigation (up to 2 hours)
