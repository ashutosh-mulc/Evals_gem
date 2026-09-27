"""
LogcatMixin — logcat capture, audio/image pull, and camera detection.

Extracted from JinjuGeminiManager so that the logger() logic (start/stop
logcat, process audio files, camera detection via logcat analysis, power
metrics) is reusable and not tangled with device-specific invoke/terminate.

Requires the host class to provide:
    - self.jinju_device: ADB serial of the Jinju glasses
    - self.companion_device: ADB serial of the companion phone
    - self.log_folder: Path to the log dump folder
    - self.log_procs: List of subprocess.Popen logcat processes
    - self.log_extra: Dict for extra log metadata
    - self.logcat_analyzer: LogcatAnalyzer instance
    - self.power_monitor: PowerMonitor instance
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import logging

from utils.log_analyzer import LogcatAnalyzer, BUILTIN_PROFILES

logger = logging.getLogger(__name__)


class LogcatMixin:
    """Mixin for logcat capture, audio/image file management, and camera detection.

    Host class must provide:
        - self.jinju_device
        - self.companion_device
        - self.log_folder
        - self.log_procs
        - self.log_extra
        - self.logcat_analyzer
        - self.power_monitor
    """

    def logger(self) -> dict:
        """Start or stop logging.

        When self.log_procs is empty: starts logcat capture + power measurement.
        When self.log_procs is non-empty: stops logcat, processes audio/image files,
        runs camera detection, collects power metrics, returns log_extra dict.
        """
        assert self._check_devices_online(), "Devices NOT online!"
        assert os.path.isdir(self.log_folder), f"log folder {self.log_folder} DOES NOT EXIST!"
        log_files = {}

        if len(self.log_procs) > 0:
            print("----Stopped & Dumped Logging----")
            # Log audio query files
            self._pull_jinju_query_audio()
            # Pull captured camera images from Jinju device
            self._pull_jinju_query_image()

            # --- Camera image capture detection via pulled files ---
            # _clear_jinju_image_folder() was called in the start phase, so any
            # image files now present were captured during this query.
            image_extensions = ('.jpg', '.jpeg', '.png')
            pulled_images = [
                f for f in os.listdir(self.log_folder)
                if f.lower().endswith(image_extensions)
                and 'app_screenshot' not in f
                and 'device_view_image' not in f
            ]
            if pulled_images:
                log_files["jinju_image_captured"] = True
                print(f"[CAMERA DEBUG] Image files pulled from device: {pulled_images}")
            else:
                log_files["jinju_image_captured"] = False
                print("[CAMERA DEBUG] No image files pulled from device.")

            # Process audio files from the pulled folder
            files_in_folder = os.listdir(self.log_folder)
            print(f"[LOGGER DEBUG] Files in log_folder before processing: {files_in_folder}")
            if len(files_in_folder) > 0:
                file_type_processed = {"denoised": False, "decoded": False, "image_view": False}
                for file_name in os.listdir(self.log_folder):
                    print(f"[LOGGER DEBUG] Processing file: {file_name!r}")

                    if "DECODED" in file_name:
                        if file_type_processed["decoded"]:
                            os.remove(os.path.join(self.log_folder, file_name))
                            continue
                        shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "audio_decoded.wav"))
                        log_files["audio_decoded_path"] = os.path.join(self.log_folder, "audio_decoded.wav")
                        file_type_processed["decoded"] = True
                    elif "DENOISED" in file_name:
                        if file_type_processed["denoised"]:
                            os.remove(os.path.join(self.log_folder, file_name))
                            continue
                        shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "audio_denoised.wav"))
                        log_files["audio_denoised_path"] = os.path.join(self.log_folder, "audio_denoised.wav")
                        file_type_processed["denoised"] = True
                    elif ".png" in file_name:
                        if os.path.exists(os.path.join(self.log_folder, file_name)):
                            if "app_screenshot" in file_name:
                                shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "app_screenshot.png"))
                                log_files["app_screenshot_path"] = os.path.join(self.log_folder, "app_screenshot.png")
                            elif "device_view_image" in file_name:
                                if not file_type_processed["image_view"]:
                                    shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "device_view_image.png"))
                                    log_files["device_view_image_path"] = os.path.join(self.log_folder, "device_view_image.png")
                                    file_type_processed["image_view"] = True
                                else:
                                    os.remove(os.path.join(self.log_folder, file_name))
                            else:
                                # Unknown PNG file, remove it
                                os.remove(os.path.join(self.log_folder, file_name))
                    elif file_name.lower().endswith(('.jpg', '.jpeg')):
                        # Camera photo — keep it (detection already done above)
                        continue
                    elif "power_log" in file_name:
                        continue
                    elif file_name.endswith(".txt"):
                        # Skip logcat files - they'll be analyzed below
                        continue
                    else:
                        # Handle both files and directories
                        full_path = os.path.join(self.log_folder, file_name)
                        if os.path.isdir(full_path):
                            # Remove directories recursively (e.g., assets/ with screenshots)
                            # Note: Screenshots are now saved directly to final assets folder,
                            # so tmp/assets/ should be empty or not exist
                            shutil.rmtree(full_path)
                        elif os.path.isfile(full_path):
                            os.remove(full_path)

            # --- Camera video capture detection via logcat analysis (jinju_log.txt) ---
            # Note: Photo capture is detected via pulled image files (see above).
            # Logcat analysis is kept only for video recording detection.
            jinju_log_path = os.path.join(self.log_folder, "jinju_log.txt")
            jinju_results = self.logcat_analyzer.analyze(jinju_log_path)
            print(f"[CAMERA DEBUG] Jinju logcat analysis results: {jinju_results}")

            if "camera" in jinju_results:
                cam = jinju_results["camera"]

                # --- Video recording results (from logcat) ---
                log_files["jinju_video_captured"] = cam.get("video_captured", False)
                log_files["jinju_video_recording_started"] = cam.get("video_recording_started", False)
                log_files["jinju_video_recording_stopped"] = cam.get("video_recording_stopped", False)
                if cam.get("video_uri"):
                    log_files["jinju_video_uri"] = cam["video_uri"]
                print(f"[VIDEO DEBUG] video_captured={cam.get('video_captured', False)}, "
                      f"video_recording_started={cam.get('video_recording_started', False)}, "
                      f"video_recording_stopped={cam.get('video_recording_stopped', False)}")
            else:
                log_files["jinju_video_captured"] = False
                print("[CAMERA DEBUG] No camera profile in jinju logcat results. video_captured=False")

            # --- MediaControl like/dislike detection via logcat analysis (companion_log.txt) ---
            companion_log_path = os.path.join(self.log_folder, "companion_log.txt")
            companion_results = self.logcat_analyzer.analyze(companion_log_path)
            print(f"[MEDIA DEBUG] Companion logcat analysis results: {companion_results}")

            if "mediacontrol" in companion_results:
                media = companion_results["mediacontrol"]
                log_files["liked"] = media.get("liked", False)
                log_files["disliked"] = media.get("disliked", False)
                if media.get("song_title"):
                    log_files["song_title"] = media["song_title"]
                print(f"[MEDIA DEBUG] liked={media.get('liked', False)}, disliked={media.get('disliked', False)}, song_title={media.get('song_title', 'N/A')}")

            # Kill log dump processes
            while len(self.log_procs) > 0:
                log_proc = self.log_procs.pop()

                os.killpg(os.getpgid(log_proc.pid), signal.SIGTERM)
                try:
                    log_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(log_proc.pid), signal.SIGKILL)
                    log_proc.wait()

            # Stop power measurement and collect metrics
            power_metrics = self.power_monitor.stop_and_collect(self.log_folder)
            if power_metrics.get("num_samples", 0) > 0:
                # Flatten power metrics into log_extra with consistent naming
                self.log_extra["avg_current_ma"] = power_metrics["avg_current_ma"]
                self.log_extra["avg_voltage_v"] = power_metrics["avg_voltage_v"]
                self.log_extra["avg_power_w"] = power_metrics["avg_power_w"]
                self.log_extra["power_num_samples"] = power_metrics["num_samples"]

            self.log_extra = {**self.log_extra, **log_files}
            return self.log_extra

        else:
            print("----Started Logging----")
            # Reconfigure logcat analyzer profiles based on current question type
            current_qt = getattr(self, 'current_question_type', '')
            if current_qt:
                profiles = self._select_profiles(current_qt)
                self.logcat_analyzer = LogcatAnalyzer(profiles)
                print(f"[LOGCAT] Analyzer profiles for '{current_qt}': {[p.app_name for p in profiles]}")

            # Start power measurement
            self.power_monitor.start()

            # Start log dump processes (logcat is captured for both devices)
            # The logcat is analyzed in the stop phase for camera capture detection
            for device_id in [self.jinju_device, self.companion_device]:
                subprocess.run(["adb", "-s", device_id, "logcat", "-c"], check=True)
                log_file_name = "jinju_log.txt" if device_id == self.jinju_device else "companion_log.txt"
                log_proc = subprocess.Popen(
                    ["timeout", "--kill-after=5", "180", "adb", "-s", device_id, "logcat",],
                    stdout=open(os.path.join(self.log_folder, log_file_name), "w"),
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid
                )
                self.log_procs.append(log_proc)

            self._clear_jinju_audio_folder()
            self._clear_jinju_image_folder()

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
        from utils.adb_client import AdbClient
        adb = AdbClient()
        return (adb.is_device_online(self.jinju_device) and
                adb.is_device_online(self.companion_device))

    def _clear_jinju_audio_folder(self):
        """Clear the Jinju audio debug folder on the companion device."""
        command = (
            f"adb -s {self.companion_device} shell rm"
            f' "/data/user/0/com.google.android.glasses.core/files/debug/*"'
        )
        print(command)
        subprocess.run(command, shell=True)

    def _pull_jinju_query_audio(self):
        """Pull Jinju query audio files from companion device and clear the folder."""
        command = (
            f"adb -s {self.companion_device} pull"
            f' "/data/user/0/com.google.android.glasses.core/files/debug/."'
            f" {self.log_folder}"
        )
        subprocess.run(command, shell=True)
        print(command)

        self._clear_jinju_audio_folder()

    def _pull_jinju_query_image(self):
        """Pull captured images from the Jinju device and clear the photos folder."""
        photos_path = "/data/data/com.android.microxr.blobstore/files/photos/"
        ls_command = f"adb -s {self.jinju_device} shell ls {photos_path}"
        ls_result = subprocess.check_output(ls_command, shell=True, text=True, stderr=subprocess.STDOUT).strip()
        print(f"[CAMERA DEBUG] Files on device in {photos_path}: {ls_result!r}")

        # Check if folder has any files (non-empty output that isn't an error)
        has_files = bool(ls_result) and "No such file" not in ls_result and "Permission denied" not in ls_result

        if has_files:
            print(f"[CAMERA DEBUG] Image files found on device! Files: {ls_result}")
        else:
            print(f"[CAMERA DEBUG] No image files found on device in photos folder.")

        command = (
            f"adb -s {self.jinju_device} pull"
            f' "/data/data/com.android.microxr.blobstore/files/photos/."'
            f" {self.log_folder}"
        )
        pull_result = subprocess.run(command, shell=True, capture_output=True, text=True)
        print(f"[CAMERA DEBUG] Pull command: {command}")
        print(f"[CAMERA DEBUG] Pull stdout: {pull_result.stdout.strip()!r}")
        print(f"[CAMERA DEBUG] Pull stderr: {pull_result.stderr.strip()!r}")
        print(f"[CAMERA DEBUG] Pull returncode: {pull_result.returncode}")

        # List files in log folder after pull
        files_after_pull = os.listdir(self.log_folder)
        print(f"[CAMERA DEBUG] Files in log_folder after pull: {files_after_pull}")

        self._clear_jinju_image_folder()

    def _clear_jinju_image_folder(self):
        """Clear the Jinju photos folder."""
        command = (
            f"adb -s {self.jinju_device} shell rm"
            f' "/data/data/com.android.microxr.blobstore/files/photos/*"'
        )
        subprocess.run(command, shell=True)
        print(command)

