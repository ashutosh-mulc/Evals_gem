#!/usr/bin/env python3
"""
LogParser - Comprehensive Android Log Parser
Usage: python log_parser.py <log_file> [options]

This tool parses Android logcat format logs and provides filtering,
statistics, and export capabilities.
"""

import re
import sys
import json
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import argparse

@dataclass
class LogEntry:
    """Represents a single log entry."""
    date: str
    time: str
    timestamp: str
    pid: int
    tid: int
    level: str
    tag: str
    message: str
    raw_line: str
    device: str = ""  # Source device (e.g., Jinju, S25); empty for raw unmerged logs

class LogParser:
    """Parser for Android logcat format logs."""
    
    LOG_PATTERN = re.compile(
        r'^(\d{2}-\d{2})\s+'  # Date
        r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'  # Time
        r'(\d+)\s+'  # PID
        r'(\d+)\s+'  # TID
        r'([VDEWIF])\s+'  # Level
        r'([^:]+):\s+'  # Tag
        r'(.*)$'  # Message
    )

    # Pattern for merged logs with [DeviceName] prefix
    MERGED_LOG_PATTERN = re.compile(
        r'^\[([^\]]+)\]\s+'  # [DeviceName]
        r'(\d{2}-\d{2})\s+'  # Date
        r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'  # Time
        r'(\d+)\s+'  # PID
        r'(\d+)\s+'  # TID
        r'([VDEWIF])\s+'  # Level
        r'([^:]+):\s+'  # Tag
        r'(.*)$'  # Message
    )
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.entries: List[LogEntry] = []
        self.parse_errors: List[str] = []
        
    def parse(self) -> int:
        """Parse the log file and return number of entries."""
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line_num, line in enumerate(f, 1):
                entry = self._parse_line(line.strip())
                if entry:
                    self.entries.append(entry)
                elif line.strip():  # Non-empty line that didn't match
                    self.parse_errors.append(f"Line {line_num}: {line[:100]}")
        return len(self.entries)
    
    def _parse_line(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line. Tries merged format first, then raw format."""
        # Try merged format: [DeviceName] 07-17 10:23:45.123 ...
        match = self.MERGED_LOG_PATTERN.match(line)
        if match:
            device, date, time, pid, tid, level, tag, message = match.groups()
            return LogEntry(
                date=date,
                time=time,
                timestamp=f"{date} {time}",
                pid=int(pid),
                tid=int(tid),
                level=level,
                tag=tag,
                message=message,
                raw_line=line,
                device=device
            )
        # Try raw format: 07-17 10:23:45.123 ...
        match = self.LOG_PATTERN.match(line)
        if match:
            date, time, pid, tid, level, tag, message = match.groups()
            return LogEntry(
                date=date,
                time=time,
                timestamp=f"{date} {time}",
                pid=int(pid),
                tid=int(tid),
                level=level,
                tag=tag,
                message=message,
                raw_line=line
            )
        return None
    
    def filter_by_level(self, levels: List[str]) -> List[LogEntry]:
        """Filter entries by log level."""
        return [e for e in self.entries if e.level in levels]
    
    def filter_by_tag(self, pattern: str) -> List[LogEntry]:
        """Filter entries by tag pattern (regex)."""
        regex = re.compile(pattern, re.IGNORECASE)
        return [e for e in self.entries if regex.search(e.tag)]
    
    def filter_by_message(self, pattern: str) -> List[LogEntry]:
        """Filter entries by message content (regex)."""
        regex = re.compile(pattern, re.IGNORECASE)
        return [e for e in self.entries if regex.search(e.message)]
    
    def filter_by_time_range(self, start: str, end: str) -> List[LogEntry]:
        """Filter entries by time range."""
        return [e for e in self.entries if start <= e.timestamp <= end]
    
    def filter_by_device(self, device: str) -> List[LogEntry]:
        """Filter entries by source device (merged logs only)."""
        return [e for e in self.entries if e.device == device]
    
    def get_statistics(self) -> Dict:
        """Get statistics about the log file."""
        level_counts = defaultdict(int)
        tag_counts = defaultdict(int)
        pid_counts = defaultdict(int)
        
        for entry in self.entries:
            level_counts[entry.level] += 1
            tag_counts[entry.tag] += 1
            pid_counts[entry.pid] += 1
        
        return {
            'total_entries': len(self.entries),
            'parse_errors': len(self.parse_errors),
            'level_distribution': dict(level_counts),
            'top_tags': dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
            'top_processes': dict(sorted(pid_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        }
    
    def export_json(self, output_file: str, entries: Optional[List[LogEntry]] = None):
        """Export entries to JSON file."""
        entries = entries or self.entries
        with open(output_file, 'w') as f:
            json.dump([asdict(e) for e in entries], f, indent=2)
    
    def export_text(self, output_file: str, entries: Optional[List[LogEntry]] = None):
        """Export entries to text file."""
        entries = entries or self.entries
        with open(output_file, 'w') as f:
            for entry in entries:
                f.write(entry.raw_line + '\n')


def main():
    parser = argparse.ArgumentParser(
        description='Android Log Parser',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python log_parser.py logfile.txt --stats
  python log_parser.py logfile.txt -l E F -o errors.json
  python log_parser.py logfile.txt -t "MediaCodec" -o media.txt
  python log_parser.py logfile.txt -m "exception" --head 50
        """
    )
    parser.add_argument('logfile', help='Path to log file')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    parser.add_argument('--level', '-l', nargs='+', help='Filter by log levels (e.g., E W F)')
    parser.add_argument('--tag', '-t', help='Filter by tag pattern (regex)')
    parser.add_argument('--message', '-m', help='Filter by message pattern (regex)')
    parser.add_argument('--output', '-o', help='Output file')
    parser.add_argument('--format', '-f', choices=['json', 'text'], default='text')
    parser.add_argument('--head', type=int, help='Show only first N entries')
    parser.add_argument('--device', '-d', help='Filter by source device name (merged logs only, e.g., Jinju, S25)')
    
    args = parser.parse_args()
    
    log_parser = LogParser(args.logfile)
    count = log_parser.parse()
    print(f"Parsed {count} log entries", file=sys.stderr)
    
    entries = log_parser.entries
    
    # Apply filters
    if args.level:
        entries = log_parser.filter_by_level(args.level)
        print(f"After level filter: {len(entries)} entries", file=sys.stderr)
    
    if args.tag:
        entries = log_parser.filter_by_tag(args.tag)
        print(f"After tag filter: {len(entries)} entries", file=sys.stderr)
    
    if args.message:
        entries = log_parser.filter_by_message(args.message)
        print(f"After message filter: {len(entries)} entries", file=sys.stderr)
    
    if args.device:
        entries = log_parser.filter_by_device(args.device)
        print(f"After device filter ({args.device}): {len(entries)} entries", file=sys.stderr)
    
    if args.head:
        entries = entries[:args.head]
    
    # Output
    if args.stats:
        print(json.dumps(log_parser.get_statistics(), indent=2))
    elif args.output:
        if args.format == 'json':
            log_parser.export_json(args.output, entries)
        else:
            log_parser.export_text(args.output, entries)
        print(f"Output written to {args.output}", file=sys.stderr)
    else:
        # Print to console
        for entry in entries[:100]:  # Limit console output
            print(entry.raw_line)
        if len(entries) > 100:
            print(f"... and {len(entries) - 100} more entries")


if __name__ == '__main__':
    main()
