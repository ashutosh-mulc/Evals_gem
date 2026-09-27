#!/usr/bin/env python3
"""
TagExtractor - Extract all unique tags from Android log files
Usage: python tag_extractor.py <log_file> [options]

This tool extracts all unique tags from a log file along with statistics,
helping analysts manually assign priorities for comparative analysis.
"""

import re
import sys
import json
import argparse
from collections import defaultdict
from typing import Dict, List

class TagExtractor:
    """Extract and analyze tags from Android logcat format logs."""
    
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
        self.tag_stats: Dict[str, Dict] = defaultdict(lambda: {
            'total': 0,
            'V': 0, 'D': 0, 'I': 0, 'W': 0, 'E': 0, 'F': 0,
            'error_sample': None
        })
        self.device_tag_stats: Dict[str, Dict[str, Dict]] = defaultdict(
            lambda: defaultdict(lambda: {
                'total': 0,
                'V': 0, 'D': 0, 'I': 0, 'W': 0, 'E': 0, 'F': 0,
                'error_sample': None
            })
        )
        self.devices_found: List[str] = []
        self.total_lines = 0
        self.parsed_lines = 0
        
    def extract(self) -> int:
        """Extract tags from log file and return count."""
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                self.total_lines += 1
                line = line.strip()
                device = ''
                
                # Try merged format first: [DeviceName] ...
                match = self.MERGED_LOG_PATTERN.match(line)
                if match:
                    device, date, time, pid, tid, level, tag, message = match.groups()
                else:
                    # Try raw format: 07-17 10:23:45.123 ...
                    match = self.LOG_PATTERN.match(line)
                    if match:
                        date, time, pid, tid, level, tag, message = match.groups()
                
                if match:
                    self.parsed_lines += 1
                    
                    self.tag_stats[tag]['total'] += 1
                    self.tag_stats[tag][level] += 1
                    
                    # Keep sample of error messages
                    if level in ['E', 'F'] and not self.tag_stats[tag]['error_sample']:
                        self.tag_stats[tag]['error_sample'] = message[:200]
                    
                    # Track per-device stats if device is set (merged log)
                    if device:
                        if device not in self.devices_found:
                            self.devices_found.append(device)
                        self.device_tag_stats[device][tag]['total'] += 1
                        self.device_tag_stats[device][tag][level] += 1
                        if level in ['E', 'F'] and not self.device_tag_stats[device][tag]['error_sample']:
                            self.device_tag_stats[device][tag]['error_sample'] = message[:200]
        
        return len(self.tag_stats)
    
    def get_sorted_tags(self, sort_by: str = 'total') -> List[tuple]:
        """Get tags sorted by specified criteria."""
        if sort_by == 'total':
            return sorted(self.tag_stats.items(), key=lambda x: x[1]['total'], reverse=True)
        elif sort_by == 'errors':
            return sorted(self.tag_stats.items(), 
                         key=lambda x: x[1]['E'] + x[1]['F'], reverse=True)
        elif sort_by == 'warnings':
            return sorted(self.tag_stats.items(), key=lambda x: x[1]['W'], reverse=True)
        else:
            return list(self.tag_stats.items())
    
    def export_text(self, output_file: str, sort_by: str = 'total', 
                    include_samples: bool = False, by_device: bool = False):
        """Export tag list to text file."""
        with open(output_file, 'w') as f:
            f.write(f"Tag Extraction Report\n")
            f.write(f"=====================\n")
            f.write(f"File: {self.filepath}\n")
            f.write(f"Total lines: {self.total_lines}\n")
            f.write(f"Parsed lines: {self.parsed_lines}\n")
            f.write(f"Unique tags: {len(self.tag_stats)}\n")
            if self.devices_found:
                f.write(f"Devices found: {', '.join(self.devices_found)}\n")
            f.write(f"\n")
            
            f.write(f"{'Rank':<6} {'Tag':<40} {'Total':<10} {'E':<6} {'W':<6} {'I':<6}\n")
            f.write("-" * 80 + "\n")
            
            for i, (tag, stats) in enumerate(self.get_sorted_tags(sort_by), 1):
                error_count = stats['E'] + stats['F']
                f.write(f"{i:<6} {tag:<40} {stats['total']:<10} {error_count:<6} {stats['W']:<6} {stats['I']:<6}\n")
                
                if include_samples and stats['error_sample']:
                    f.write(f"       Sample: {stats['error_sample']}\n")
            
            # Per-device breakdown
            if by_device and self.devices_found:
                for device in self.devices_found:
                    f.write(f"\n{'=' * 80}\n")
                    f.write(f"Device: {device}\n")
                    f.write(f"{'=' * 80}\n")
                    f.write(f"{'Rank':<6} {'Tag':<40} {'Total':<10} {'E':<6} {'W':<6} {'I':<6}\n")
                    f.write("-" * 80 + "\n")
                    
                    device_tags = self.device_tag_stats[device]
                    sorted_device_tags = sorted(device_tags.items(), 
                                               key=lambda x: x[1]['total'], reverse=True)
                    for i, (tag, stats) in enumerate(sorted_device_tags, 1):
                        error_count = stats['E'] + stats['F']
                        f.write(f"{i:<6} {tag:<40} {stats['total']:<10} {error_count:<6} {stats['W']:<6} {stats['I']:<6}\n")
                        
                        if include_samples and stats['error_sample']:
                            f.write(f"       Sample: {stats['error_sample']}\n")
    
    def export_json(self, output_file: str, sort_by: str = 'total'):
        """Export tag statistics to JSON file."""
        export_data = {
            'file': self.filepath,
            'total_lines': self.total_lines,
            'parsed_lines': self.parsed_lines,
            'unique_tags': len(self.tag_stats),
            'tags': {}
        }
        
        for tag, stats in self.get_sorted_tags(sort_by):
            export_data['tags'][tag] = {
                'total': stats['total'],
                'verbose': stats['V'],
                'debug': stats['D'],
                'info': stats['I'],
                'warning': stats['W'],
                'error': stats['E'],
                'fatal': stats['F'],
                'error_sample': stats['error_sample']
            }
        
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='Tag Extractor for Android Logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tag_extractor.py logfile.txt -o tag_list.txt
  python tag_extractor.py logfile.txt --sort errors -o error_tags.txt
  python tag_extractor.py logfile.txt --json -o tags.json
  python tag_extractor.py logfile.txt --samples
        """
    )
    parser.add_argument('logfile', help='Path to log file')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--sort', '-s', choices=['total', 'errors', 'warnings'], 
                        default='total', help='Sort criteria')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    parser.add_argument('--samples', action='store_true', 
                        help='Include error message samples')
    parser.add_argument('--by-device', action='store_true',
                        help='Include per-device tag breakdown (merged logs only)')
    
    args = parser.parse_args()
    
    extractor = TagExtractor(args.logfile)
    count = extractor.extract()
    
    print(f"Extracted {count} unique tags from {extractor.parsed_lines} parsed lines", 
          file=sys.stderr)
    
    if args.json:
        if args.output:
            extractor.export_json(args.output, args.sort)
            print(f"JSON exported to {args.output}", file=sys.stderr)
        else:
            import json
            print(json.dumps({
                'total_lines': extractor.total_lines,
                'parsed_lines': extractor.parsed_lines,
                'unique_tags': count,
                'tags': {tag: stats['total'] for tag, stats in extractor.tag_stats.items()}
            }, indent=2))
    else:
        if args.output:
            extractor.export_text(args.output, args.sort, args.samples, args.by_device)
            print(f"Tag list exported to {args.output}", file=sys.stderr)
        else:
            # Print to console
            extractor.export_text('/dev/stdout', args.sort, args.samples, args.by_device)


if __name__ == '__main__':
    main()
