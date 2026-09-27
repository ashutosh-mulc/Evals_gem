"""
Generalized Logcat Analyzer Utility

A pluggable, pattern-based logcat analysis framework. Each app registers its own
set of logcat patterns to detect specific events. The analyzer reads the captured
logcat file and returns structured results.

Usage:
    from utils.logcat_analyzer import LogcatAnalyzer, BUILTIN_PROFILES

    analyzer = LogcatAnalyzer([BUILTIN_PROFILES["camera"]])
    results = analyzer.analyze("/path/to/jinju_log.txt")
    # results = {"camera": {"image_captured": True, "photo_uri": "content://...", ...}}

To add a new app, define a new AppLogcatProfile and register it:
    BUILTIN_PROFILES["calendar"] = AppLogcatProfile(
        app_name="calendar",
        patterns=[
            LogcatPattern(
                name="event_created",
                patterns=[r"CalendarProvider.*insert.*events"],
                description="True if a calendar event was created"
            ),
        ]
    )
"""

import re
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LogcatPattern:
    """A single logcat pattern to match within a log file.

    Attributes:
        name: Identifier for the result key (e.g. "image_captured")
        patterns: List of regex patterns to search for. First match wins.
        description: Human-readable description of what this pattern detects.
        extract_group: 0 = boolean (found/not found), >0 = extract regex group N as value.
    """
    name: str
    patterns: list[str]
    description: str = ""
    extract_group: int = 0  # 0 = boolean, >0 = extract that group number


@dataclass
class AppLogcatProfile:
    """A profile for a specific app, containing all its logcat patterns.

    Attributes:
        app_name: Name of the app (e.g. "camera", "calendar")
        patterns: List of LogcatPattern definitions for this app
    """
    app_name: str
    patterns: list[LogcatPattern] = field(default_factory=list)


class LogcatAnalyzer:
    """Analyzes logcat files using registered app profiles.

    Supports multiple app profiles simultaneously. Each app's patterns are
    evaluated independently, and results are returned grouped by app name.
    """

    def __init__(self, profiles: list[AppLogcatProfile] = None):
        self.profiles = {p.app_name: p for p in (profiles or [])}

    def register_profile(self, profile: AppLogcatProfile):
        """Register or replace an app profile at runtime."""
        self.profiles[profile.app_name] = profile

    def analyze(self, log_file_path: str) -> dict:
        """Analyze a logcat file on disk.

        Args:
            log_file_path: Path to the captured logcat text file.

        Returns:
            Dict keyed by app_name, each containing a dict of pattern results.
            Example: {"camera": {"image_captured": True, "photo_uri": "content://..."}}
            Returns empty dict if file doesn't exist.
        """
        if not os.path.exists(log_file_path):
            print(f"[LogcatAnalyzer] Log file not found: {log_file_path}")
            return {}
        with open(log_file_path, 'r', errors='replace') as f:
            return self.analyze_text(f.read())

    def analyze_text(self, log_text: str) -> dict:
        """Analyze raw logcat text.

        Args:
            log_text: The full logcat content as a string.

        Returns:
            Dict keyed by app_name, each containing a dict of pattern results.
        """
        results = {}
        for app_name, profile in self.profiles.items():
            app_results = {}
            for pat in profile.patterns:
                matched = False
                for regex in pat.patterns:
                    match = re.search(regex, log_text)
                    if match:
                        if pat.extract_group > 0:
                            try:
                                app_results[pat.name] = match.group(pat.extract_group)
                            except IndexError:
                                app_results[pat.name] = None
                        else:
                            app_results[pat.name] = True
                        matched = True
                        break
                if not matched and pat.extract_group == 0:
                    app_results[pat.name] = False
            results[app_name] = app_results
        return results


# --- Built-in profiles ---

BUILTIN_PROFILES = {
    "camera": AppLogcatProfile(
        app_name="camera",
        patterns=[
            LogcatPattern(
                name="image_captured",
                patterns=[r"onPhotoCaptured"],
                description="True if a photo was captured and saved by the camera service"
            ),
            LogcatPattern(
                name="photo_uri",
                patterns=[r"onPhotoCaptured:\s*(content://\S+)"],
                description="URI of the captured photo (content:// URI)",
                extract_group=1
            ),
            LogcatPattern(
                name="capture_initiated",
                patterns=[r"capturePhoto", r"captureStarted.*PHOTO_IN_PROGRESS"],
                description="True if a photo capture was initiated"
            ),
            LogcatPattern(
                name="capture_completed",
                patterns=[r"PhotographyStateTransition.*PHOTO_IN_PROGRESS\s*->\s*IDLE"],
                description="True if capture completed (state transitioned back to IDLE)"
            ),
            # --- Video recording patterns ---
            LogcatPattern(
                name="video_recording_initiated",
                patterns=[r"captureVideoOrInterrupt", r"processStartRecordingVideo"],
                description="True if video recording was initiated"
            ),
            LogcatPattern(
                name="video_recording_started",
                patterns=[r"onVideoStarted", r"PhotographyStateTransition.*VIDEO_REQUESTED\s*->\s*VIDEO_IN_PROGRESS"],
                description="True if video recording actually started"
            ),
            LogcatPattern(
                name="video_recording_stopped",
                patterns=[r"onVideoStopped"],
                description="True if video recording was stopped"
            ),
            LogcatPattern(
                name="video_captured",
                patterns=[r"onVideoCaptured"],
                description="True if a video was captured and saved"
            ),
            LogcatPattern(
                name="video_uri",
                patterns=[r"onVideoCaptured:\s*(content://\S+)"],
                description="URI of the captured video (content:// URI)",
                extract_group=1
            ),
        ]
    ),
    "mediacontrol": AppLogcatProfile(
        app_name="mediacontrol",
        patterns=[
            LogcatPattern(
                name="liked",
                patterns=[r"Undo like"],
                description="True if user liked the current song"
            ),
            LogcatPattern(
                name="disliked",
                patterns=[r"Undo dislike"],
                description="True if user disliked the current song"
            ),
            # Note: song_title is not extractable from companion logcat —
            # the log only shows a hash reference (e.g. MediaMetadata@1861bcd5),
            # not the actual title string.
        ]
    ),
}
