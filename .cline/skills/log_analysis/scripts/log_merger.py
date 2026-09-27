#!/usr/bin/env python3
"""
LogMerger - Merge multiple device logs into a single timeline-ordered log
Usage: python log_merger.py <log1:device1> <log2:device2> ... [options]

This tool merges logs from multiple physical devices (e.g., Jinju, S25) into
a single timeline-ordered log. Each entry is annotated with its source device.

Valid device names: Jinju, S25

Examples:
  python log_merger.py jinju_log.txt:Jinju companion_log.txt:S25 -o bad_merged -f json
  python log_merger.py jinju_log.txt:Jinju s25_log.txt:S25 -o merged.txt
"""

import re
import sys
import json
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

# Valid physical device names
VALID_DEVICES = {'Jinju', 'S25'}

# Standard Android logcat pattern (raw, unmerged)
LOG_PATTERN = re.compile(
    r'^(\d{2}-\d{2})\s+'  # Date
    r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'  # Time
    r'(\d+)\s+'  # PID
    r'(\d+)\s+'  # TID
    r'([VDEWIF])\s+'  # Level
    r'([^:]+):\s+'  # Tag
    r'(.*)$'  # Message
)


@dataclass
class MergedEntry:
    """Represents a single log entry with device origin."""
    device: str
    date: str
    time: str
    timestamp: str
    pid: int
    tid: int
    level: str
    tag: str
    message: str
    raw_line: str


def parse_log_file(filepath: str, device: str) -> List[MergedEntry]:
    """Parse a single log file and return entries annotated with device name."""
    entries = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            match = LOG_PATTERN.match(line.strip())
            if match:
                date, time, pid, tid, level, tag, message = match.groups()
                entries.append(MergedEntry(
                    device=device,
                    date=date,
                    time=time,
                    timestamp=f"{date} {time}",
                    pid=int(pid),
                    tid=int(tid),
                    level=level,
                    tag=tag,
                    message=message,
                    raw_line=line.strip()
                ))
    return entries


def merge_entries(all_entries: List[MergedEntry]) -> List[MergedEntry]:
    """Sort all entries by timestamp. Stable sort preserves original order for ties."""
    return sorted(all_entries, key=lambda e: e.timestamp)


def export_text(entries: List[MergedEntry], output_file: Optional[str] = None):
    """Export merged entries as text with [DeviceName] prefix per line."""
    lines = []
    for entry in entries:
        lines.append(f"[{entry.device}] {entry.raw_line}")
    content = '\n'.join(lines) + '\n'
    if output_file:
        with open(output_file, 'w') as f:
            f.write(content)
    else:
        sys.stdout.write(content)


def export_json(entries: List[MergedEntry], output_file: Optional[str] = None):
    """Export merged entries as JSON with device field per entry."""
    data = [asdict(e) for e in entries]
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
    else:
        print(json.dumps(data, indent=2))


def parse_device_log_arg(arg: str) -> Tuple[str, str]:
    """Parse a 'path:device' argument. Split on the last ':' to handle Windows paths."""
    if ':' not in arg:
        raise ValueError(f"Argument '{arg}' is missing ':device' suffix. Expected format: path:DeviceName")
    filepath, device = arg.rsplit(':', 1)
    device = device.strip()
    if device not in VALID_DEVICES:
        raise ValueError(f"Invalid device name '{device}'. Valid devices: {', '.join(sorted(VALID_DEVICES))}")
    return filepath, device


def main():
    parser = argparse.ArgumentParser(
        description='Merge multiple device logs into a single timeline-ordered log',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python log_merger.py jinju_log.txt:Jinju s25_log.txt:S25 -o bad_merged -f json
  python log_merger.py jinju_log.txt:Jinju s25_log.txt:S25 -o merged.txt
  python log_merger.py jinju_log.txt:Jinju -o single_merged -f json

Valid device names: Jinju, S25
        """
    )
    parser.add_argument('logs', nargs='+', help='Log files as path:DeviceName (e.g., log.txt:Jinju)')
    parser.add_argument('--output', '-o', help='Output file (without extension; .txt or .json appended based on format)')
    parser.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                        help='Output format (default: text)')

    args = parser.parse_args()

    # Parse all path:device arguments
    parsed_logs = []
    for log_arg in args.logs:
        try:
            filepath, device = parse_device_log_arg(log_arg)
            parsed_logs.append((filepath, device))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Parse each log file
    all_entries = []
    device_counts = {}
    for filepath, device in parsed_logs:
        print(f"Parsing {filepath} (device: {device})...", file=sys.stderr)
        entries = parse_log_file(filepath, device)
        device_counts[device] = len(entries)
        all_entries.extend(entries)
        print(f"  Parsed {len(entries)} entries", file=sys.stderr)

    if not all_entries:
        print("Error: No log entries parsed from any file", file=sys.stderr)
        sys.exit(1)

    # Merge (sort by timestamp)
    print(f"\nMerging {len(all_entries)} total entries...", file=sys.stderr)
    merged = merge_entries(all_entries)

    # Print summary
    print(f"\nMerge summary:", file=sys.stderr)
    for device, count in device_counts.items():
        print(f"  {device}: {count} entries", file=sys.stderr)
    print(f"  Total merged: {len(merged)} entries", file=sys.stderr)

    # Determine output
    if args.output:
        if args.format == 'json':
            output_file = args.output if args.output.endswith('.json') else f"{args.output}.json"
            export_json(merged, output_file)
        else:
            output_file = args.output if args.output.endswith('.txt') else f"{args.output}.txt"
            export_text(merged, output_file)
        print(f"\nOutput written to {output_file}", file=sys.stderr)
    else:
        if args.format == 'json':
            export_json(merged)
        else:
            export_text(merged)


if __name__ == '__main__':
    main()
