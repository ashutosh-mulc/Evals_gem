#!/usr/bin/env python3
"""
Test script for the LogcatAnalyzer utility.

Usage:
  # Analyze an existing logcat file
  python -m utils.test_log_analyzer /path/to/logcat.txt

  # Live mode: capture logcat from device while you click camera, then analyze
  python -m utils.test_log_analyzer --live <device_id>

  # Live mode with custom duration (default 30s)
  python -m utils.test_log_analyzer --live <device_id> --duration 60
"""

import sys
import os
import re
import argparse
import subprocess
import tempfile
import signal

# Ensure parent dir is on path when run as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.log_analyzer import LogcatAnalyzer, BUILTIN_PROFILES


def print_results(results: dict, log_text: str = ""):
    """Pretty-print analyzer results and optionally show matched log lines."""
    print("\n" + "=" * 60)
    print("  Logcat Analyzer Results")
    print("=" * 60)

    if not results:
        print("  (no results — no profiles registered or empty log)")
        print("=" * 60)
        return

    for app_name, app_results in results.items():
        print(f"\n  App: {app_name}")
        for key, value in app_results.items():
            status_icon = "✅" if value else "❌" if value is False else "��"
            print(f"    {status_icon} {key}: {value}")

    # Show matched log lines if we have the raw text
    if log_text:
        print("\n" + "-" * 60)
        print("  Matched Log Lines")
        print("-" * 60)

        for app_name, profile in BUILTIN_PROFILES.items():
            for pat in profile.patterns:
                for regex in pat.patterns:
                    for match in re.finditer(regex, log_text):
                        # Find the full log line containing this match
                        line_start = log_text.rfind('\n', 0, match.start()) + 1
                        line_end = log_text.find('\n', match.end())
                        if line_end == -1:
                            line_end = len(log_text)
                        line = log_text[line_start:line_end].strip()
                        print(f"  [{pat.name}] {line}")

    print("\n" + "=" * 60)


def analyze_file(file_path: str):
    """Analyze a logcat file on disk."""
    print(f"Reading logcat file: {file_path}")

    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, 'r', errors='replace') as f:
        log_text = f.read()

    print(f"File size: {len(log_text)} bytes, {log_text.count(chr(10))} lines")

    analyzer = LogcatAnalyzer([BUILTIN_PROFILES["camera"]])
    results = analyzer.analyze_text(log_text)
    print_results(results, log_text)


def analyze_live(device_id: str, duration: int = 30):
    """Capture logcat from a device in real-time, then analyze."""
    print(f"Device: {device_id}")
    print(f"Capture duration: {duration}s (or press Ctrl+C to stop early)")

    # Verify device is connected
    check = subprocess.run(
        ["adb", "-s", device_id, "get-state"],
        capture_output=True, text=True
    )
    if check.returncode != 0 or "device" not in check.stdout.strip():
        print(f"ERROR: Device {device_id} not found or not ready.")
        print(f"  adb output: {check.stdout.strip()} {check.stderr.strip()}")
        sys.exit(1)

    # Clear logcat
    print("Clearing logcat...")
    subprocess.run(["adb", "-s", device_id, "logcat", "-c"], check=True)

    # Start capturing logcat to a temp file
    tmp_file = tempfile.NamedTemporaryFile(
        mode='w', suffix=".txt", delete=False, prefix="logcat_capture_"
    )
    tmp_path = tmp_file.name
    tmp_file.close()

    print(f"\nCapturing logcat to: {tmp_path}")
    print(">>> Click the camera button on the device now! <<<")
    print(f">>> (Auto-stopping in {duration}s, or press Ctrl+C to stop early)\n")

    log_proc = subprocess.Popen(
        ["adb", "-s", device_id, "logcat"],
        stdout=open(tmp_path, 'w'),
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid
    )

    try:
        log_proc.wait(timeout=duration)
    except subprocess.TimeoutExpired:
        print("Capture duration reached. Stopping...")
    except KeyboardInterrupt:
        print("\nStopped by user.")

    # Kill the logcat process
    try:
        os.killpg(os.getpgid(log_proc.pid), signal.SIGTERM)
        log_proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(log_proc.pid), signal.SIGKILL)
        except Exception:
            pass

    # Read and analyze the captured log
    with open(tmp_path, 'r', errors='replace') as f:
        log_text = f.read()

    print(f"Captured {len(log_text)} bytes, {log_text.count(chr(10))} lines")

    analyzer = LogcatAnalyzer([BUILTIN_PROFILES["camera"]])
    results = analyzer.analyze_text(log_text)
    print_results(results, log_text)

    # Clean up temp file
    try:
        os.unlink(tmp_path)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Test the LogcatAnalyzer utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze an existing logcat file
  python -m utils.test_log_analyzer /path/to/logcat.txt


  # Live capture from device, then analyze
  python -m utils.test_log_analyzer --live 4103d783bb2a9c00

  # Live capture with custom duration
  python -m utils.test_log_analyzer --live 4103d783bb2a9c00 --duration 60
        """
    )

    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to a logcat file to analyze"
    )
    parser.add_argument(
        "--live",
        metavar="DEVICE_ID",
        default=None,
        help="Capture logcat live from the specified device ID, then analyze"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration in seconds for live capture (default: 30)"
    )

    args = parser.parse_args()

    if args.live:
        analyze_live(args.live, args.duration)
    elif args.file:
        analyze_file(args.file)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
