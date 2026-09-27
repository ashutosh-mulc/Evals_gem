#!/usr/bin/env python3
"""
CorrelationFinder - Find correlations across multiple log files
Usage: python correlation_finder.py <log1.json> <log2.json> ... [options]

This tool finds correlations between multiple log sources including:
- Time-correlated events
- Error cascades across components
- Common error tags across sources
"""

import json
import sys
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

class CorrelationFinder:
    """Find correlations across multiple log sources."""
    
    def __init__(self, log_sources: Dict[str, List[Dict]]):
        """
        Initialize with multiple log sources.
        
        Args:
            log_sources: Dict mapping source name to list of log entries
        """
        self.sources = log_sources
        self.correlations: List[Dict] = []
        # Caches for export_report so methods aren't recomputed
        self._cascades_cache = None
        self._common_tags_cache = None

    @staticmethod
    def _parse_ts(ts: str):
        """Parse a timestamp string once. Returns datetime or None."""
        try:
            return datetime.strptime(ts, '%m-%d %H:%M:%S.%f')
        except (ValueError, KeyError, TypeError):
            return None

    def _precompute_source(self, entries: List[Dict], levels_filter=None):
        """
        Pre-sort entries by timestamp and pre-parse timestamps ONCE.
        
        Returns a list of tuples (datetime, original_entry) sorted by datetime,
        optionally filtered to given log levels. Entries with unparseable
        timestamps are dropped.
        """
        parsed = []
        for entry in entries:
            if levels_filter and entry.get('level') not in levels_filter:
                continue
            dt = self._parse_ts(entry.get('timestamp'))
            if dt is None:
                continue
            parsed.append((dt, entry))
        parsed.sort(key=lambda x: x[0])
        return parsed

    def find_time_correlations(self, window_seconds: float = 1.0) -> List[Dict]:
        """Find events that occur within a time window across all pairs of sources."""
        correlations = []
        
        source_names = list(self.sources.keys())
        if len(source_names) < 2:
            return correlations
        
        # Pre-parse + sort each source ONCE (filter to E/F/W since only those
        # are correlated). This avoids calling strptime inside any loop.
        sorted_sources = {}
        for name, entries in self.sources.items():
            sorted_sources[name] = self._precompute_source(
                entries, levels_filter=('E', 'F', 'W')
            )
        
        # Find correlations between all pairs of sources using a two-pointer
        # merge (O(N+M) per pair) instead of the naive O(N*M) nested loop.
        for i in range(len(source_names)):
            for j in range(i + 1, len(source_names)):
                source1, source2 = source_names[i], source_names[j]
                list1 = sorted_sources[source1]  # sorted (dt, entry)
                list2 = sorted_sources[source2]  # sorted (dt, entry)
                
                correlations.extend(
                    self._correlate_pair(source1, source2, list1, list2, window_seconds)
                )
        
        self.correlations = correlations
        return correlations

    @staticmethod
    def _correlate_pair(source1, source2, list1, list2, window_seconds):
        """
        Two-pointer sweep over two time-sorted lists to find all pairs within
        `window_seconds` of each other. O(N + M) per pair.
        """
        results = []
        if not list1 or not list2:
            return results

        n2 = len(list2)
        # `right` only ever moves forward across list2, so total inner
        # advancement is bounded by len(list2) -> linear.
        right = 0

        for t1, e1 in list1:
            # Advance `right` until t2 >= t1 - window (left edge of window)
            while right < n2 and list2[right][0] < t1 - timedelta(seconds=window_seconds):
                right += 1

            # Scan the window [t1 - window, t1 + window]. Because list2 is sorted
            # we can break as soon as t2 exceeds t1 + window (early termination).
            k = right
            while k < n2:
                t2, e2 = list2[k]
                diff = (t2 - t1).total_seconds()
                if abs(diff) <= window_seconds:
                    results.append({
                        'source1': source1,
                        'entry1': {
                            'timestamp': e1.get('timestamp'),
                            'tag': e1.get('tag', 'Unknown'),
                            'level': e1.get('level', '?'),
                            'message': e1.get('message', '')[:200]
                        },
                        'source2': source2,
                        'entry2': {
                            'timestamp': e2.get('timestamp'),
                            'tag': e2.get('tag', 'Unknown'),
                            'level': e2.get('level', '?'),
                            'message': e2.get('message', '')[:200]
                        },
                        'time_diff_seconds': abs(diff)
                    })
                    k += 1
                elif diff > window_seconds:
                    # list2 is sorted ascending; no later entry can be in window.
                    break
                else:
                    k += 1

        return results
    
    def find_error_cascades(self, time_window_minutes: int = 2) -> List[Dict]:
        """Find cascading errors across sources."""
        cascades = []
        
        # Collect all errors with source info, pre-parsing timestamps ONCE.
        all_errors = []
        for source_name, entries in self.sources.items():
            for entry in entries:
                if entry.get('level') in ['E', 'F']:
                    dt = self._parse_ts(entry.get('timestamp'))
                    if dt is None:
                        continue
                    all_errors.append({
                        'source': source_name,
                        '_dt': dt,
                        **entry
                    })
        
        # Sort by parsed datetime (fast, no strptime in sort comparator)
        all_errors.sort(key=lambda x: x['_dt'])
        
        # Find cascades (errors from multiple sources in time window)
        i = 0
        while i < len(all_errors):
            cascade = [all_errors[i]]
            start_time = all_errors[i]['_dt']
            
            j = i + 1
            while j < len(all_errors):
                curr_time = all_errors[j]['_dt']
                if (curr_time - start_time).total_seconds() <= time_window_minutes * 60:
                    cascade.append(all_errors[j])
                    j += 1
                else:
                    break
            
            # Check if cascade involves multiple sources
            sources_in_cascade = set(e['source'] for e in cascade)
            if len(sources_in_cascade) > 1 and len(cascade) >= 2:
                cascades.append({
                    'start_time': cascade[0].get('timestamp'),
                    'end_time': cascade[-1].get('timestamp'),
                    'error_count': len(cascade),
                    'sources_involved': list(sources_in_cascade),
                    'errors': [{
                        'source': e['source'],
                        'timestamp': e.get('timestamp'),
                        'tag': e.get('tag', 'Unknown'),
                        'message': e.get('message', '')[:150]
                    } for e in cascade]
                })
            
            i = j if j > i + 1 else i + 1
        
        return cascades
    
    def find_common_tags(self, min_occurrences: int = 5) -> Dict[str, Dict]:
        """Find tags that appear in multiple sources."""
        tag_sources = defaultdict(lambda: defaultdict(int))
        
        for source_name, entries in self.sources.items():
            for entry in entries:
                if entry.get('level') in ['E', 'F', 'W']:
                    tag_sources[entry.get('tag', 'Unknown')][source_name] += 1
        
        # Filter to tags appearing in multiple sources
        common_tags = {}
        for tag, source_counts in tag_sources.items():
            if len(source_counts) > 1:
                total = sum(source_counts.values())
                if total >= min_occurrences:
                    common_tags[tag] = {
                        'sources': dict(source_counts),
                        'total_occurrences': total,
                        'source_count': len(source_counts)
                    }
        
        return dict(sorted(common_tags.items(), 
                          key=lambda x: x[1]['total_occurrences'], 
                          reverse=True))
    
    def export_report(self, output_file: str):
        """Export correlation report."""
        # Compute cascades/common tags ONCE and reuse for both the JSON and
        # the human-readable summary (previously these ran twice).
        cascades = self.find_error_cascades()
        common = self.find_common_tags()

        report = {
            'correlations': self.correlations,
            'cascades': cascades,
            'common_tags': common
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Also create human-readable summary
        summary_file = output_file.replace('.json', '_summary.txt')
        with open(summary_file, 'w') as f:
            f.write("=== Cross-Log Correlation Report ===\n\n")
            
            f.write(f"Sources analyzed: {list(self.sources.keys())}\n\n")
            
            f.write(f"Time-correlated events: {len(self.correlations)}\n")
            for corr in self.correlations[:10]:
                f.write(f"\n  [{corr['time_diff_seconds']:.3f}s apart]\n")
                f.write(f"  {corr['source1']}: [{corr['entry1']['tag']}] {corr['entry1']['message'][:80]}\n")
                f.write(f"  {corr['source2']}: [{corr['entry2']['tag']}] {corr['entry2']['message'][:80]}\n")
            
            f.write(f"\n\nError cascades: {len(cascades)}\n")
            for cascade in cascades[:5]:
                f.write(f"\n  Cascade at {cascade['start_time']}\n")
                f.write(f"  Sources: {', '.join(cascade['sources_involved'])}\n")
                f.write(f"  Errors: {cascade['error_count']}\n")
            
            f.write(f"\n\nCommon error tags across sources: {len(common)}\n")
            for tag, info in list(common.items())[:10]:
                f.write(f"  {tag}: {info['total_occurrences']} times across {info['source_count']} sources\n")
        
        print(f"Report exported to {output_file} and {summary_file}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='Cross-Log Correlation Finder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python correlation_finder.py log1.json log2.json -o correlation.json
  python correlation_finder.py jinju.json companion.json -n jinju companion -w 2.0
  python correlation_finder.py bad_merged.json --from-merged -o cross_device.json
        """
    )
    parser.add_argument('logfiles', nargs='+', help='JSON log files to analyze')
    parser.add_argument('--names', '-n', nargs='+', help='Names for each log source')
    parser.add_argument('--output', '-o', default='correlation_report.json',
                        help='Output file for report')
    parser.add_argument('--window', '-w', type=float, default=1.0,
                        help='Time window in seconds for correlation')
    parser.add_argument('--from-merged', action='store_true',
                        help='Split a single merged JSON by device field, then correlate across devices')
    
    args = parser.parse_args()
    
    # Load all log files
    sources = {}
    
    if args.from_merged:
        # --from-merged mode: load single merged JSON, split by device field
        if len(args.logfiles) != 1:
            print("Error: --from-merged requires exactly one merged JSON file", file=sys.stderr)
            sys.exit(1)
        
        merged_file = args.logfiles[0]
        print(f"Loading merged log file: {merged_file}...", file=sys.stderr)
        try:
            with open(merged_file, 'r') as f:
                all_entries = json.load(f)
        except Exception as e:
            print(f"  Error loading file: {e}", file=sys.stderr)
            sys.exit(1)
        
        print(f"  Loaded {len(all_entries)} entries", file=sys.stderr)
        
        # Split entries by device field
        device_entries = defaultdict(list)
        for entry in all_entries:
            device = entry.get('device', '')
            if device:
                device_entries[device].append(entry)
        
        sources = dict(device_entries)
        print(f"  Found {len(sources)} devices: {list(sources.keys())}", file=sys.stderr)
        for name, entries in sources.items():
            print(f"    {name}: {len(entries)} entries", file=sys.stderr)
    else:
        # Normal mode: load multiple JSON files as separate sources
        for i, logfile in enumerate(args.logfiles):
            name = args.names[i] if args.names and i < len(args.names) else f"source_{i+1}"
            print(f"Loading {logfile} as '{name}'...", file=sys.stderr)
            try:
                with open(logfile, 'r') as f:
                    sources[name] = json.load(f)
                print(f"  Loaded {len(sources[name])} entries", file=sys.stderr)
            except Exception as e:
                print(f"  Error loading file: {e}", file=sys.stderr)
                continue
    
    if len(sources) < 1:
        print("Error: No valid log sources loaded", file=sys.stderr)
        sys.exit(1)
    
    finder = CorrelationFinder(sources)
    
    print(f"\nFinding time correlations (window={args.window}s)...", file=sys.stderr)
    correlations = finder.find_time_correlations(args.window)
    print(f"  Found {len(correlations)} correlated event pairs", file=sys.stderr)
    
    print("Finding error cascades...", file=sys.stderr)
    cascades = finder.find_error_cascades()
    print(f"  Found {len(cascades)} cascades", file=sys.stderr)
    
    print("Finding common tags...", file=sys.stderr)
    common = finder.find_common_tags()
    print(f"  Found {len(common)} common error tags", file=sys.stderr)
    
    print(f"\nExporting report to {args.output}...", file=sys.stderr)
    finder.export_report(args.output)
    print("Done!", file=sys.stderr)


if __name__ == '__main__':
    main()
