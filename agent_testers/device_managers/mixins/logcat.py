"""
LogcatMixin — per-query Jinju log capture: logcat on both devices, pulled audio/photo
files, camera/video/media detection from logcat, power metrics.

start_logging() before the agent is invoked, stop_logging() after it answers.
"""

from __future__ import annotations

import os
import shutil
import logging

from utils.log_analyzer import LogcatAnalyzer, BUILTIN_PROFILES

logger = logging.getLogger(__name__)

JINJU_AUDIO_DIR = "/data/user/0/com.google.android.glasses.core/files/debug"  # on the companion
JINJU_PHOTOS_DIR = "/data/data/com.android.microxr.blobstore/files/photos"     # on the glasses


class LogcatMixin:
    """Mixin for logcat capture, audio/image file management, and camera detection.

    Host class must provide:
        - self.jinju_device, self.companion_device, self._adb
        - self.log_folder
        - self.log_procs (used by DeviceManagerTemplate._start_logcat/_stop_logcat)
        - self.logcat_analyzer
        - self.power_monitor
    """

    # Pulled files kept once under a canonical name: marker in filename → (canonical name, log_analysis key).
    # Later files with the same marker are duplicates and get deleted.
    _PULLED_FILES = {
        "DECODED": ("audio_decoded.wav", "audio_decoded_path"),
        "DENOISED": ("audio_denoised.wav", "audio_denoised_path"),
        "device_view_image": ("device_view_image.png", "device_view_image_path"),
    }

    def start_logging(self) -> None:
        """Start per-query capture: logcat on both devices, power sampling, cleared on-device dumps."""
        assert self._check_devices_online(), "Devices NOT online!"
        assert os.path.isdir(self.log_folder), f"log folder {self.log_folder} DOES NOT EXIST!"
        logger.info("----Started Logging----")
        self.log_extra = {}  # per query; invoke() adds jinju_invoke_ts

        current_qt = getattr(self, 'current_question_type', '')
        if current_qt:
            profiles = self._select_profiles(current_qt)
            self.logcat_analyzer = LogcatAnalyzer(profiles)
            logger.debug(f"[LOGCAT] Analyzer profiles for '{current_qt}': {[p.app_name for p in profiles]}")

        self.power_monitor.start()
        self._start_logcat({self.jinju_device: "jinju_log.txt", self.companion_device: "companion_log.txt"}, timeout_s=180)
        self._clear_jinju_audio_folder()
        self._clear_jinju_image_folder()

    def stop_logging(self) -> dict:
        """Stop capture and return what it found (stored as metadata["app_state"]["log_analysis"]):
        pulled audio/image paths, camera/video/media flags from logcat, power metrics.
        """
        assert self._check_devices_online(), "Devices NOT online!"
        assert os.path.isdir(self.log_folder), f"log folder {self.log_folder} DOES NOT EXIST!"
        logger.info("----Stopped & Dumped Logging----")
        log_files = {}

        self._pull_jinju_query_audio()
        self._pull_jinju_query_image()

        # Photo capture: the photos folder was cleared in start_logging(), so any
        # pulled image was taken during this query.
        pulled_images = [
            f for f in os.listdir(self.log_folder)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            and 'app_screenshot' not in f
            and 'device_view_image' not in f
        ]
        log_files["jinju_image_captured"] = bool(pulled_images)
        logger.debug(f"[CAMERA] Image files pulled from device: {pulled_images}")

        self._tidy_pulled_files(log_files)

        # Video capture: from the Jinju logcat (photos are detected from pulled files above)
        cam = self.logcat_analyzer.analyze(os.path.join(self.log_folder, "jinju_log.txt")).get("camera")
        log_files["jinju_video_captured"] = cam.get("video_captured", False) if cam is not None else False
        if cam is not None:
            log_files["jinju_video_recording_started"] = cam.get("video_recording_started", False)
            log_files["jinju_video_recording_stopped"] = cam.get("video_recording_stopped", False)
            if cam.get("video_uri"):
                log_files["jinju_video_uri"] = cam["video_uri"]
        logger.debug(f"[CAMERA] Jinju logcat camera results: {cam}")

        # Media like/dislike: from the companion logcat
        media = self.logcat_analyzer.analyze(os.path.join(self.log_folder, "companion_log.txt")).get("mediacontrol")
        if media is not None:
            log_files["liked"] = media.get("liked", False)
            log_files["disliked"] = media.get("disliked", False)
            if media.get("song_title"):
                log_files["song_title"] = media["song_title"]
        logger.debug(f"[MEDIA] Companion logcat mediacontrol results: {media}")

        self._stop_logcat()

        power_metrics = self.power_monitor.stop_and_collect(self.log_folder)
        if power_metrics.get("num_samples", 0) > 0:
            self.log_extra["avg_current_ma"] = power_metrics["avg_current_ma"]
            self.log_extra["avg_voltage_v"] = power_metrics["avg_voltage_v"]
            self.log_extra["avg_power_w"] = power_metrics["avg_power_w"]
            self.log_extra["power_num_samples"] = power_metrics["num_samples"]

        self.log_extra = {**self.log_extra, **log_files}
        return self.log_extra

    def _tidy_pulled_files(self, log_files: dict) -> None:
        """Rename the first pulled file of each kind (_PULLED_FILES) and delete everything
        else, keeping camera photos, logcat .txt dumps and the power log."""
        kept = set()
        for file_name in os.listdir(self.log_folder):
            path = os.path.join(self.log_folder, file_name)
            if "DECODED" in file_name:
                marker = "DECODED"
            elif "DENOISED" in file_name:
                marker = "DENOISED"
            elif ".png" in file_name and "device_view_image" in file_name:
                marker = "device_view_image"
            else:
                marker = None

            if marker:
                if marker in kept:
                    os.remove(path)
                    continue
                canonical, key = self._PULLED_FILES[marker]
                shutil.move(path, os.path.join(self.log_folder, canonical))
                log_files[key] = os.path.join(self.log_folder, canonical)
                kept.add(marker)
            elif file_name.lower().endswith(('.jpg', '.jpeg', '.txt')) or "power_log" in file_name:
                continue
            elif os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.isfile(path):
                os.remove(path)

    def _select_profiles(self, question_type: str) -> list:
        """Select logcat analyzer profiles based on question_type.

        Maps question_type keywords to the required BUILTIN_PROFILES entries.
        This ensures only relevant log patterns are analyzed per query, keeping
        the framework scalable as new app profiles are added.

        Args:
            question_type: The question type string (e.g., "online_device_mediacontrol_like").

        Returns:
            List of AppLogcatProfile objects to register with the LogcatAnalyzer.
        """
        qt_lower = (question_type or "").lower()

        profile_keys = set()

        # Camera/video queries need camera profile for image/video capture detection
        if "camera" in qt_lower or "video" in qt_lower:
            profile_keys.add("camera")

        # Media control queries (play/pause/like/dislike/skip/etc.) need mediacontrol profile
        if "mediacontrol" in qt_lower:
            profile_keys.add("mediacontrol")

        # Default: always include camera as baseline (covers general device queries)
        if not profile_keys:
            profile_keys.add("camera")

        return [BUILTIN_PROFILES[key] for key in profile_keys if key in BUILTIN_PROFILES]

    def _check_devices_online(self) -> bool:
        """Check if Jinju and companion devices are online."""
        return self._adb.is_device_online(self.jinju_device) and self._adb.is_device_online(self.companion_device)

    def _clear_jinju_audio_folder(self):
        """Clear the Jinju audio debug folder on the companion device."""
        self._adb.shell(self.companion_device, f"rm {JINJU_AUDIO_DIR}/*")

    def _pull_jinju_query_audio(self):
        """Pull Jinju query audio files from companion device and clear the folder."""
        self._adb.pull(self.companion_device, f"{JINJU_AUDIO_DIR}/.", self.log_folder, check=False)
        self._clear_jinju_audio_folder()

    def _pull_jinju_query_image(self):
        """Pull captured photos from the Jinju device and clear the photos folder."""
        self._adb.pull(self.jinju_device, f"{JINJU_PHOTOS_DIR}/.", self.log_folder, check=False)
        self._clear_jinju_image_folder()

    def _clear_jinju_image_folder(self):
        """Clear the Jinju photos folder."""
        self._adb.shell(self.jinju_device, f"rm {JINJU_PHOTOS_DIR}/*")
