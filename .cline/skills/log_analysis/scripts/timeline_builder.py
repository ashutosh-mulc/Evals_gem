#!/usr/bin/env python3
"""
TimelineBuilder - Reconstruct event timelines from Android logs
Usage: python timeline_builder.py <log_file> <keywords> [output_file]

This tool builds timelines of events matching specified keywords,
useful for understanding the sequence of events leading to failures.
"""

import re
import sys
import argparse
from datetime import datetime
from typing import List, Dict

class TimelineBuilder:
    """Build timelines from log entries."""
    
    def __init__(self, log_entries: List[Dict]):
        self.entries = log_entries
        
    def build_timeline(self, keywords: List[str], 
                       context_before: int = 0,
                       context_after: int = 0) -> List[Dict]:
        """
        Build a timeline of events matching keywords.
        
        Args:
            keywords: List of keywords to search for in tag and message
            context_before: Number of non-matching entries to include before each match
            context_after: Number of non-matching entries to include after each match
            
        Returns:
            List of timeline entries with context markers
        """
        timeline = []
        
        for i, entry in enumerate(self.entries):
            tag = entry.get('tag', '')
            message = entry.get('message', '')
            
            # Check if any keyword matches
            matched = any(
                kw.lower() in tag.lower() or kw.lower() in message.lower()
                for kw in keywords
            )
            
            if matched:
                timeline.append({
                    **entry,
                    'matched': True,
                    'matched_keywords': [kw for kw in keywords 
                                         if kw.lower() in tag.lower() or kw.lower() in message.lower()]
                })
            elif context_before > 0 or context_after > 0:
                # Check if this entry is within context range of a match
                include = False
                
                # Look forward for matches
                for j in range(1, context_after + 1):
                    if i + j < len(self.entries):
                        future = self.entries[i + j]
                        if any(kw.lower() in future.get('tag', '').lower() or 
                               kw.lower() in future.get('message', '').lower() 
                               for kw in keywords):
                            include = True
                            break
                
                # Look backward for matches
                if not include:
                    for j in range(1, context_before + 1):
                        if i - j >= 0:
                            past = self.entries[i - j]
                            if any(kw.lower() in past.get('tag', '').lower() or 
                                   kw.lower() in past.get('message', '').lower() 
                                   for kw in keywords):
                                include = True
                                break
                
                if include:
                    timeline.append({
                        **entry,
                        'matched': False,
                        'context': True
                    })
        
        return timeline
    
    def build_time_range_timeline(self, start_time: str, end_time: str) -> List[Dict]:
        """Build timeline for entries within a time range."""
        timeline = []
        for entry in self.entries:
            ts = entry.get('timestamp', '')
            if start_time <= ts <= end_time:
                timeline.append(entry)
        return timeline
    
    def build_error_timeline(self) -> List[Dict]:
        """Build timeline of only error and warning entries."""
        return [e for e in self.entries if e.get('level') in ['E', 'F', 'W']]
    
    def export_timeline(self, timeline: List[Dict], output_file: str, 
                        format: str = 'text'):
        """Export timeline to file."""
        if format == 'json':
            import json
            with open(output_file, 'w') as f:
                json.dump(timeline, f, indent=2)
        else:
            with open(output_file, 'w') as f:
                f.write("=" * 100 + "\n")
                f.write("EVENT TIMELINE\n")
                f.write("=" * 100 + "\n\n")
                
                for entry in timeline:
                    marker = "*" if entry.get('matched') else " "
                    level = entry.get('level', '?')
                    ts = entry.get('timestamp', 'Unknown')
                    tag = entry.get('tag', 'Unknown')
                    message = entry.get('message', '')[:150]
                    device = entry.get('device', '')
                    
                    device_prefix = f"[{device}] " if device else ""
                    f.write(f"[{marker}] {device_prefix}[{ts}] [{level}] {tag}: {message}\n")
                
                f.write("\n" + "=" * 100 + "\n")
                matched_count = sum(1 for e in timeline if e.get('matched'))
                f.write(f"Total entries: {len(timeline)}\n")
                f.write(f"Matched entries: {matched_count}\n")


def load_parsed_log(filepath: str) -> List[Dict]:
    """Load a previously parsed JSON log file."""
    import json
    with open(filepath, 'r') as f:
        return json.load(f)


def load_raw_log(filepath: str) -> List[Dict]:
    """Load a raw logcat format file. Handles both merged ([DeviceName] prefix) and raw formats."""
    entries = []
    log_pattern = re.compile(
        r'^(\d{2}-\d{2})\s+'
        r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'
        r'(\d+)\s+'
        r'(\d+)\s+'
        r'([VDEWIF])\s+'
        r'([^:]+):\s+'
        r'(.*)$'
    )
    
    # Pattern for merged logs with [DeviceName] prefix
    merged_pattern = re.compile(
        r'^\[([^\]]+)\]\s+'
        r'(\d{2}-\d{2})\s+'
        r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+'
        r'(\d+)\s+'
        r'(\d+)\s+'
        r'([VDEWIF])\s+'
        r'([^:]+):\s+'
        r'(.*)$'
    )
    
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            # Try merged format first
            match = merged_pattern.match(line)
            if match:
                device, date, time, pid, tid, level, tag, message = match.groups()
                entries.append({
                    'date': date,
                    'time': time,
                    'timestamp': f"{date} {time}",
                    'pid': int(pid),
                    'tid': int(tid),
                    'level': level,
                    'tag': tag,
                    'message': message,
                    'device': device
                })
                continue
            # Try raw format
            match = log_pattern.match(line)
            if match:
                date, time, pid, tid, level, tag, message = match.groups()
                entries.append({
                    'date': date,
                    'time': time,
                    'timestamp': f"{date} {time}",
                    'pid': int(pid),
                    'tid': int(tid),
                    'level': level,
                    'tag': tag,
                    'message': message,
                    'device': ''
                })
    
    return entries


def main():
    parser = argparse.ArgumentParser(
        description='Timeline Builder for Android Logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python timeline_builder.py log.txt "GC_Agent,MediaCodec" timeline.txt
  python timeline_builder.py log.json "Handler,Exception" --format json
  python timeline_builder.py log.txt "error,fail" --context 5
  python timeline_builder.py log.json --errors-only -o errors_timeline.txt
        """
    )
    parser.add_argument('logfile', help='Path to log file (JSON or raw logcat)')
    parser.add_argument('keywords', nargs='?', help='Comma-separated keywords to search for')
    parser.add_argument('--output', '-o', help='Output file (default: timeline.txt)')
    parser.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    parser.add_argument('--context', '-c', type=int, default=0,
                        help='Include N lines of context before/after matches')
    parser.add_argument('--errors-only', '-e', action='store_true',
                        help='Build timeline of errors only')
    parser.add_argument('--time-range', '-t', nargs=2, metavar=('START', 'END'),
                        help='Filter by time range (MM-DD HH:MM:SS.fff)')
    parser.add_argument('--device', '-d', help='Show only entries from this device (merged logs only, e.g., Jinju, S25)')
    
    args = parser.parse_args()
    
    # Load log file
    print(f"Loading log file: {args.logfile}", file=sys.stderr)
    if args.logfile.endswith('.json'):
        entries = load_parsed_log(args.logfile)
    else:
        entries = load_raw_log(args.logfile)
    print(f"Loaded {len(entries)} entries", file=sys.stderr)
    
    # Filter by device if specified
    if args.device:
        entries = [e for e in entries if e.get('device', '') == args.device]
        print(f"After device filter ({args.device}): {len(entries)} entries", file=sys.stderr)
    
    builder = TimelineBuilder(entries)
    
    # Build timeline based on options
    if args.errors_only:
        print("Building error timeline...", file=sys.stderr)
        timeline = builder.build_error_timeline()
    elif args.time_range:
        print(f"Building timeline for time range: {args.time_range}", file=sys.stderr)
        timeline = builder.build_time_range_timeline(args.time_range[0], args.time_range[1])
    elif args.keywords:
        keywords = [k.strip() for k in args.keywords.split(',')]
        print(f"Building timeline for keywords: {keywords}", file=sys.stderr)
        timeline = builder.build_timeline(keywords, args.context, args.context)
    else:
        print("Error: Must specify either keywords, --errors-only, or --time-range", file=sys.stderr)
        sys.exit(1)
    
    print(f"Timeline contains {len(timeline)} entries", file=sys.stderr)
    
    # Export
    output_file = args.output or 'timeline.txt'
    print(f"Exporting timeline to {output_file}...", file=sys.stderr)
    builder.export_timeline(timeline, output_file, args.format)
    print("Done!", file=sys.stderr)


if __name__ == '__main__':
    main()
