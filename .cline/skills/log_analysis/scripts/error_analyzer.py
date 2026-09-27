#!/usr/bin/env python3
"""
ErrorAnalyzer - Deep analysis of error patterns in Android logs
Usage: python error_analyzer.py <log_file> [output_dir]

This tool performs deep analysis of error patterns including:
- Error clustering
- Critical issue detection
- Timeline analysis
- Comprehensive reporting
"""

import re
import sys
import os
import json
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Tuple
import argparse
import hashlib

class ErrorAnalyzer:
    """Analyze error patterns in Android logs."""
    
    CRITICAL_PATTERNS = [
        (r'FATAL', 'Fatal Error'),
        (r'ANR', 'Application Not Responding'),
        (r'OutOfMemoryError', 'Memory Issue'),
        (r'StackOverflowError', 'Stack Overflow'),
        (r'NullPointerException', 'Null Pointer'),
        (r'IllegalStateException', 'Illegal State'),
        (r'RuntimeException', 'Runtime Exception'),
        (r'IOException', 'I/O Error'),
        (r'TimeoutException', 'Timeout'),
        (r'Connection.*[Ee]rror', 'Connection Error'),
        (r'Handler.*dead.*thread', 'Handler Dead Thread'),
        (r'Binder.*[Dd]ead', 'Binder Dead'),
        (r'Crash', 'Application Crash'),
        (r'Exception.*main', 'Main Thread Exception'),
    ]
    
    def __init__(self, log_entries: List[Dict]):
        self.entries = log_entries
        self.error_entries = [e for e in log_entries if e.get('level') in ['E', 'F', 'W']]
        self.clusters: Dict[str, List[Dict]] = defaultdict(list)
        self.timeline: List[Dict] = []
        
    def normalize_message(self, message: str, max_length: int = 100) -> str:
        """Normalize a message for clustering by removing variable parts."""
        # Remove numbers (often timestamps, IDs, etc.)
        normalized = re.sub(r'\d+', 'N', message)
        # Remove hex values
        normalized = re.sub(r'0x[0-9a-fA-F]+', 'HEX', normalized)
        # Remove UUIDs
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID', normalized)
        # Remove file paths
        normalized = re.sub(r'/[\w/.-]+', 'PATH', normalized)
        return normalized[:max_length]
    
    def cluster_errors(self) -> Dict[str, List[Dict]]:
        """Cluster similar errors together."""
        for entry in self.error_entries:
            # Create cluster key from tag and normalized message
            tag = entry.get('tag', 'Unknown')
            message = entry.get('message', '')
            normalized = self.normalize_message(message)
            cluster_key = f"{tag}::{hashlib.md5(normalized.encode()).hexdigest()[:12]}"
            
            self.clusters[cluster_key].append({
                **entry,
                'cluster_pattern': normalized
            })
        
        return self.clusters
    
    def get_cluster_summary(self) -> List[Dict]:
        """Get summary of all error clusters."""
        summaries = []
        for cluster_id, entries in self.clusters.items():
            first_entry = entries[0]
            # Collect unique devices that contributed to this cluster
            devices = list(set(e.get('device', '') for e in entries if e.get('device', '')))
            summaries.append({
                'cluster_id': cluster_id,
                'count': len(entries),
                'first_occurrence': entries[0]['timestamp'],
                'last_occurrence': entries[-1]['timestamp'],
                'tag': first_entry['tag'],
                'level': first_entry['level'],
                'pattern': first_entry.get('cluster_pattern', '')[:150],
                'sample_message': first_entry['message'][:200],
                'devices': devices
            })
        
        # Sort by count (most frequent first)
        return sorted(summaries, key=lambda x: x['count'], reverse=True)
    
    def detect_critical_issues(self) -> List[Dict]:
        """Detect critical issues based on known patterns."""
        critical_issues = []
        
        for entry in self.error_entries:
            message = entry.get('message', '')
            for pattern, issue_type in self.CRITICAL_PATTERNS:
                if re.search(pattern, message, re.IGNORECASE):
                    critical_issues.append({
                        **entry,
                        'issue_type': issue_type,
                        'matched_pattern': pattern
                    })
                    break
        
        return critical_issues
    
    def build_error_timeline(self, time_window_minutes: int = 5) -> List[Dict]:
        """Build timeline of error bursts."""
        if not self.error_entries:
            return []
        
        # Group errors by time window
        timeline = []
        current_window = []
        window_start = None
        
        for entry in sorted(self.error_entries, key=lambda x: x['timestamp']):
            try:
                entry_time = datetime.strptime(entry['timestamp'], '%m-%d %H:%M:%S.%f')
            except (ValueError, KeyError):
                continue
            
            if window_start is None:
                window_start = entry_time
                current_window = [entry]
            elif (entry_time - window_start).total_seconds() <= time_window_minutes * 60:
                current_window.append(entry)
            else:
                # Save current window and start new one
                if current_window:
                    devices_in_window = list(set(e.get('device', '') for e in current_window if e.get('device', '')))
                    timeline.append({
                        'window_start': window_start.strftime('%m-%d %H:%M:%S.%f'),
                        'window_end': current_window[-1]['timestamp'],
                        'error_count': len(current_window),
                        'unique_tags': len(set(e['tag'] for e in current_window)),
                        'levels': {l: sum(1 for e in current_window if e['level'] == l) 
                                   for l in ['F', 'E', 'W']},
                        'devices_involved': devices_in_window,
                        'sample_errors': [e['message'][:100] for e in current_window[:5]]
                    })
                window_start = entry_time
                current_window = [entry]
        
        # Don't forget the last window
        if current_window:
            devices_in_window = list(set(e.get('device', '') for e in current_window if e.get('device', '')))
            timeline.append({
                'window_start': window_start.strftime('%m-%d %H:%M:%S.%f'),
                'window_end': current_window[-1]['timestamp'],
                'error_count': len(current_window),
                'unique_tags': len(set(e['tag'] for e in current_window)),
                'levels': {l: sum(1 for e in current_window if e['level'] == l) 
                           for l in ['F', 'E', 'W']},
                'devices_involved': devices_in_window,
                'sample_errors': [e['message'][:100] for e in current_window[:5]]
            })
        
        return timeline
    
    def export_report(self, output_dir: str):
        """Export comprehensive analysis report."""
        os.makedirs(output_dir, exist_ok=True)
        
        # Cluster report
        cluster_summary = self.get_cluster_summary()
        with open(os.path.join(output_dir, 'error_clusters.json'), 'w') as f:
            json.dump(cluster_summary, f, indent=2)
        
        # Detailed clusters
        with open(os.path.join(output_dir, 'cluster_details.txt'), 'w') as f:
            for cluster_id, entries in self.clusters.items():
                devices = list(set(e.get('device', '') for e in entries if e.get('device', '')))
                f.write(f"\n{'='*80}\n")
                f.write(f"CLUSTER: {cluster_id}\n")
                f.write(f"Occurrences: {len(entries)}\n")
                if devices:
                    f.write(f"Devices: {', '.join(devices)}\n")
                f.write(f"Pattern: {entries[0].get('cluster_pattern', 'N/A')[:150]}\n")
                f.write(f"{'='*80}\n\n")
                for i, entry in enumerate(entries[:10], 1):
                    device_tag = f"[{entry.get('device', '')}] " if entry.get('device', '') else ""
                    f.write(f"[{i}] {device_tag}[{entry['timestamp']}] {entry['message']}\n\n")
        
        # Critical issues
        critical = self.detect_critical_issues()
        with open(os.path.join(output_dir, 'critical_issues.json'), 'w') as f:
            json.dump(critical, f, indent=2)
        
        # Timeline
        timeline = self.build_error_timeline()
        with open(os.path.join(output_dir, 'error_timeline.json'), 'w') as f:
            json.dump(timeline, f, indent=2)
        
        # Summary report
        all_devices = list(set(e.get('device', '') for e in self.error_entries if e.get('device', '')))
        with open(os.path.join(output_dir, 'analysis_summary.md'), 'w') as f:
            f.write("# Error Analysis Summary\n\n")
            f.write(f"**Total Entries Analyzed**: {len(self.entries)}\n")
            f.write(f"**Error/Warning Entries**: {len(self.error_entries)}\n")
            f.write(f"**Unique Error Clusters**: {len(self.clusters)}\n")
            f.write(f"**Critical Issues Found**: {len(critical)}\n")
            if all_devices:
                f.write(f"**Devices Analyzed**: {', '.join(all_devices)}\n")
            f.write(f"\n")
            
            f.write("## Top 10 Error Clusters\n\n")
            if all_devices:
                f.write("| Rank | Count | Tag | Devices | Pattern |\n")
                f.write("|------|-------|-----|---------|----------|\n")
                for i, summary in enumerate(cluster_summary[:10], 1):
                    dev_str = ', '.join(summary.get('devices', [])) if summary.get('devices') else '-'
                    f.write(f"| {i} | {summary['count']} | {summary['tag']} | {dev_str} | {summary['pattern'][:50]}... |\n")
            else:
                f.write("| Rank | Count | Tag | Pattern |\n")
                f.write("|------|-------|-----|----------|\n")
                for i, summary in enumerate(cluster_summary[:10], 1):
                    f.write(f"| {i} | {summary['count']} | {summary['tag']} | {summary['pattern'][:50]}... |\n")
            
            f.write("\n## Critical Issues\n\n")
            issue_types = defaultdict(int)
            for issue in critical:
                issue_types[issue['issue_type']] += 1
            for issue_type, count in issue_types.items():
                f.write(f"- **{issue_type}**: {count} occurrences\n")
        
        print(f"Report exported to {output_dir}", file=sys.stderr)


def load_parsed_log(filepath: str) -> List[Dict]:
    """Load a previously parsed JSON log file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description='Error Analyzer for Android Logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python error_analyzer.py parsed_log.json output/
  python error_analyzer.py parsed_log.json analysis_results --timeline-window 10
        """
    )
    parser.add_argument('logfile', help='Path to parsed JSON log file')
    parser.add_argument('output_dir', nargs='?', default='analysis_output',
                        help='Output directory for reports')
    parser.add_argument('--timeline-window', type=int, default=5,
                        help='Time window in minutes for timeline analysis')
    
    args = parser.parse_args()
    
    print(f"Loading log file: {args.logfile}", file=sys.stderr)
    entries = load_parsed_log(args.logfile)
    print(f"Loaded {len(entries)} entries", file=sys.stderr)
    
    analyzer = ErrorAnalyzer(entries)
    print("Clustering errors...", file=sys.stderr)
    analyzer.cluster_errors()
    
    print(f"Found {len(analyzer.clusters)} unique error clusters", file=sys.stderr)
    print(f"Detecting critical issues...", file=sys.stderr)
    critical = analyzer.detect_critical_issues()
    print(f"Found {len(critical)} critical issues", file=sys.stderr)
    
    print(f"Exporting report to {args.output_dir}...", file=sys.stderr)
    analyzer.export_report(args.output_dir)
    
    print("\n=== Quick Summary ===", file=sys.stderr)
    print(f"Total error clusters: {len(analyzer.clusters)}", file=sys.stderr)
    print(f"Critical issues: {len(critical)}", file=sys.stderr)
    
    # Show top 5 clusters
    summary = analyzer.get_cluster_summary()
    print("\nTop 5 Error Clusters:", file=sys.stderr)
    for i, s in enumerate(summary[:5], 1):
        print(f"  {i}. [{s['count']}x] {s['tag']}: {s['pattern'][:60]}...", file=sys.stderr)


if __name__ == '__main__':
    main()
