#!/usr/bin/env python3
"""
Pre-run diagnostic checks for the evaluation framework.

Run this BEFORE starting the automator to catch common issues:
  - Device connectivity
  - ARAP app installed, launchable, and can play/record audio
  - XRClaw app running with privileged permissions
  - XRClaw app functions responding
  - Transcription service reachable
  - Judge model reachable
  - Config file valid with all required fields
  - Dataset file exists and is valid JSONL
  - Critical Python dependencies installed
  - FireRedVAD package installed and model files present
  - Display server reachable (required)
  - Rating rectifier reachable (optional, warning only)


Usage:
    python scripts/pre_run_checks.py configs/your_config.json
    python scripts/pre_run_checks.py configs/your_config.json --skip-arap  # skip ARAP tests
    python scripts/pre_run_checks.py configs/your_config.json --skip-xrclaw  # skip XRClaw tests
"""


import sys
import os
import json
import subprocess
import argparse
import tempfile
import time
import wave
import struct
import requests

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from agent_testers.device_managers import DEVICE_MANAGERS


# ── ANSI colors ──────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def pass_msg(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def fail_msg(msg, detail=""):
    print(f"  {RED}✗{RESET} {msg}")
    if detail:
        print(f"       {RED}{detail}{RESET}")

def warn_msg(msg, detail=""):
    print(f"  {YELLOW}⚠{RESET} {msg}")
    if detail:
        print(f"       {YELLOW}{detail}{RESET}")


def section(title):
    print(f"\n{BOLD}── {title} ──{RESET}")


# ── Helper functions ─────────────────────────────────────────────────

def run_adb(device_id, args, timeout=10):
    """Run an adb command and return (returncode, stdout, stderr)."""
    cmd = ["adb", "-s", device_id] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "ADB command timed out"
    except FileNotFoundError:
        return -1, "", "adb not found in PATH"


def run_adb_shell(device_id, shell_cmd, timeout=10):
    """Run an adb shell command."""
    return run_adb(device_id, ["shell"] + shell_cmd.split(), timeout=timeout)


def generate_test_wav(filepath, duration_sec=1.0, freq=440, sample_rate=44100):
    """Generate a short test WAV file with a sine wave."""
    n_samples = int(duration_sec * sample_rate)
    with wave.open(filepath, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        for i in range(n_samples):
            sample = int(32767 * 0.5 * __import__('math').sin(2 * __import__('math').pi * freq * i / sample_rate))
            f.writeframes(struct.pack('<h', sample))


# ── Check functions ──────────────────────────────────────────────────

def check_device_online(device_id, label=""):
    """Check if a device is connected and online via adb."""
    rc, out, _ = run_adb(device_id, ["get-state"])
    if rc == 0 and out.strip() == "device":
        pass_msg(f"Device {label or device_id} is online")
        return True
    else:
        fail_msg(f"Device {label or device_id} is not online", f"adb get-state returned: {out}")
        return False


def check_arap_app_installed(device_id):
    """Check if com.ss.arap is installed on the device."""
    rc, out, _ = run_adb_shell(device_id, "pm list packages com.ss.arap")
    if rc == 0 and "com.ss.arap" in out:
        pass_msg("com.ss.arap is installed")
        return True
    else:
        fail_msg("com.ss.arap is NOT installed", "Install the ARAP APK on the device")
        return False


def check_arap_app_launch(device_id):
    """Check if com.ss.arap can be launched."""
    rc, out, _ = run_adb_shell(
        device_id,
        "am start com.ss.arap/com.ss.arap.MainActivity"
    )
    if rc == 0:
        time.sleep(2)
        # Verify it's running
        rc2, out2, _ = run_adb_shell(device_id, "pidof com.ss.arap")
        if rc2 == 0 and out2.strip():
            pass_msg(f"com.ss.arap launched (PID: {out2.strip()})")
            return True
        else:
            fail_msg("com.ss.arap launched but process not found", "App may have crashed")
            return False
    else:
        fail_msg("Failed to launch com.ss.arap", out)
        return False


def check_arap_play_audio(device_id):
    """Test audio playback: push a test wav and broadcast PLAY_AUDIO."""
    # Generate a test wav
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        test_wav = tmp.name
    generate_test_wav(test_wav, duration_sec=1.0)

    # Push to device
    # Use external app data dir (world-accessible via adb) instead of the
    # private /data/data/ dir which adb push can't write to without root.
    # This matches the path used by check_arap_recording() below.
    arap_root = "/storage/emulated/0/Android/data/com.ss.arap/files/"
    remote_path = os.path.join(arap_root, "pre_run_check_test.wav")

    # Ensure the directory exists on the device before pushing
    run_adb_shell(device_id, f"mkdir -p {arap_root}")

    # Push to the full remote_path (not just the directory) so the file
    # gets the expected name. Pushing to a directory preserves the source
    # temp filename, which causes the ls check below to fail.
    rc, out, _ = run_adb(device_id, ["push", test_wav, remote_path])
    os.unlink(test_wav)

    if rc != 0:
        fail_msg("Failed to push test audio to device", out)
        return False

    # Verify file exists on device
    rc, out, _ = run_adb_shell(device_id, f"ls {remote_path}")
    if rc != 0 or "No such file" in out:
        fail_msg("Test audio not found on device after push", f"Expected at {remote_path}")
        return False

    # Clear logcat
    run_adb_shell(device_id, "logcat -c")

    # Broadcast PLAY_AUDIO
    rc, out, _ = run_adb_shell(
        device_id,
        f'am broadcast -a com.ss.arap.PLAY_AUDIO --es filePath "{remote_path}"'
    )

    if rc != 0:
        fail_msg("PLAY_AUDIO broadcast failed", out)
        return False

    # Wait a moment for playback
    time.sleep(2)

    # Check logcat for errors
    rc, out, _ = run_adb_shell(device_id, "logcat -d -t 30 | grep -i 'arap\\|error\\|exception'")
    has_error = any(kw in out.lower() for kw in ["error", "exception", "failed"]) if out else False

    if has_error:
        fail_msg("PLAY_AUDIO broadcast sent but logcat shows errors", out[:200])
        return False

    pass_msg("ARAP play_audio: broadcast sent, no errors in logcat")
    return True


def check_arap_recording(device_id):
    """Test recording: start, stop, and pull the recording file."""
    rec_name = "pre_run_check_rec.wav"

    # Start recording
    rc, out, _ = run_adb_shell(
        device_id,
        f'am broadcast -a com.ss.arap.START_RECORDING --es fileName "{rec_name}"'
    )
    if rc != 0:
        fail_msg("START_RECORDING broadcast failed", out)
        return False

    # Record for 2 seconds
    time.sleep(2)

    # Stop recording
    rc, out, _ = run_adb_shell(device_id, "am broadcast -a com.ss.arap.STOP_RECORDING")
    if rc != 0:
        fail_msg("STOP_RECORDING broadcast failed", out)
        return False

    # Pull the recording
    remote_rec = f"/storage/emulated/0/Android/data/com.ss.arap/files/{rec_name}"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        local_rec = tmp.name

    rc, out, _ = run_adb(device_id, ["pull", remote_rec, local_rec])

    if rc != 0:
        fail_msg("Failed to pull recording from device", out)
        return False

    # Check file is non-empty
    size = os.path.getsize(local_rec)
    os.unlink(local_rec)

    if size < 100:
        fail_msg(f"Recording file is too small ({size} bytes)", "Recording may not be working")
        return False

    pass_msg(f"ARAP recording works (file size: {size} bytes)")
    return True


def check_xrclaw_app_running(device_id):
    """Check if XRClaw app is running with ShellIdentityInstrumentation."""
    rc, out, _ = run_adb_shell(device_id, "dumpsys activity processes | grep claw")
    if rc == 0 and "com.samsung.xr.claw.client" in out:
        # Check for instrumentation
        rc2, out2, _ = run_adb_shell(device_id, "dumpsys activity processes | grep -i instrument")
        if rc2 == 0 and "ShellIdentityInstrumentation" in out2:
            pass_msg("XRClaw app is running with ShellIdentityInstrumentation")
            return True
        else:
            warn_msg("XRClaw app is running but ShellIdentityInstrumentation not found")
            warn_msg(f"Relaunch with: adb -s {device_id} shell am instrument -w com.samsung.xr.claw.client/.ShellIdentityInstrumentation")
            return False
    else:
        fail_msg("XRClaw app is not running", f"Launch with: adb -s {device_id} shell am instrument -w com.samsung.xr.claw.client/.ShellIdentityInstrumentation")
        return False


def check_xrclaw_app_functions(python_automation_path, device_id):
    """Test XRClaw app functions by querying device info."""
    if not os.path.isdir(python_automation_path):
        fail_msg("XRClaw python_automation_path not found", python_automation_path)
        return False

    parent_dir = os.path.dirname(python_automation_path)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    try:
        from python_automation import DeviceManager
        dm = DeviceManager(adb_path="adb", device=device_id)

        # Test 1: Device info
        info = dm.device_info.get_all()
        d = info.to_dict()
        battery = d.get("battery", {}).get("level", "?")
        pass_msg(f"XRClaw device_info works (battery: {battery}%)")

        # Test 2: Notes query
        notes = dm.notes.find_notes()
        pass_msg(f"XRClaw notes.find_notes() works ({len(notes)} notes)")

        return True
    except Exception as e:
        fail_msg("XRClaw app function test failed", str(e))
        return False


def check_service_url(url, name, path="/health_check"):
    """Check if a service is reachable via HTTP."""
    full_url = url.rstrip("/") + path
    try:
        resp = requests.get(full_url, timeout=5)
        if resp.status_code == 200:
            pass_msg(f"{name} is reachable at {url}")
            return True
        else:
            fail_msg(f"{name} returned status {resp.status_code}", full_url)
            return False
    except requests.exceptions.ConnectionError:
        fail_msg(f"{name} is not reachable", f"Connection refused at {url}")
        return False
    except requests.exceptions.Timeout:
        fail_msg(f"{name} timed out", f"Timeout at {url}")
        return False
    except Exception as e:
        fail_msg(f"{name} check failed", str(e))
        return False


def check_judge_model(url):
    """Check if the judge model API is reachable."""
    full_url = url.rstrip("/") + "/models"
    try:
        resp = requests.get(full_url, timeout=5)
        if resp.status_code == 200:
            models = resp.json()
            model_count = len(models.get("data", []))
            pass_msg(f"Judge model is reachable ({model_count} models available)")
            return True
        else:
            fail_msg(f"Judge model returned status {resp.status_code}", full_url)
            return False
    except Exception as e:
        fail_msg("Judge model check failed", str(e))
        return False


# ── Known device manager types ────────────────────────────────────────
VALID_DEVICE_MANAGER_TYPES = set(DEVICE_MANAGERS)


def _diagnose_dataset_path(dataset_file):
    """Provide actionable diagnostics when a dataset file is not found."""
    detail_lines = [f"Configured path: {dataset_file}"]

    resolved = os.path.abspath(dataset_file)
    detail_lines.append(f"Resolved path:  {resolved}")

    # Check for double-prefix (e.g., maire/maire/data/...)
    normalized = dataset_file.replace("\\", "/")
    parts = normalized.split("/")
    for i in range(len(parts) - 1):
        if parts[i] and parts[i] == parts[i + 1]:
            detail_lines.append(
                f"⚠ Path contains repeated segment '{parts[i]}/{parts[i]}' — "
                f"possible double-prefix error."
            )
            # Suggest a corrected path by collapsing the duplicate
            corrected = "/".join(
                parts[:i] + [parts[i]] + parts[i + 2:]
            )
            if os.path.isfile(corrected):
                detail_lines.append(f"  Did you mean: {corrected}")
            break

    # Check if the file exists relative to the project root
    relative_to_root = os.path.join(PROJECT_ROOT, dataset_file)
    if os.path.isfile(relative_to_root):
        detail_lines.append(
            f"File exists relative to project root: {relative_to_root}\n"
            f"  Consider using an absolute path or a path relative to the project root."
        )

    # Check if the file exists relative to CWD
    if not os.path.isabs(dataset_file):
        cwd_relative = os.path.join(os.getcwd(), dataset_file)
        if os.path.isfile(cwd_relative):
            detail_lines.append(f"File exists relative to CWD: {cwd_relative}")

    # Search for similarly-named files in the project
    basename = os.path.basename(dataset_file)
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip hidden dirs and common non-data dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
        if basename in files:
            found_path = os.path.join(root, basename)
            if found_path != resolved:
                detail_lines.append(f"Similar file found at: {found_path}")
                break

    return "\n       ".join(detail_lines)


def check_config(config_path):
    """Validate the config file has all required fields."""
    if not os.path.isfile(config_path):
        fail_msg("Config file not found", config_path)
        return False, None

    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        fail_msg("Config file is not valid JSON", str(e))
        return False, None

    # ── Pydantic schema validation (first-pass) ──
    try:
        from common.schema import AppConfig
        app_config = AppConfig.from_dict(config)
        app_config.validate_runtime()
        pass_msg("Pydantic schema validation passed")
    except Exception as e:
        fail_msg("Pydantic schema validation failed", str(e))
        # Continue with manual checks — they may provide more specific errors

    required_sections = ["device_manager_type", "dataset_start_index", "dataset_end_index",
                         "logger", "paths", "devices", "urls", "message_service",
                         "judge_worker", "automator"]
    missing = [k for k in required_sections if k not in config]
    if missing:
        fail_msg("Config missing required sections", f"Missing: {', '.join(missing)}")
        return False, None

    # ── Validate device_manager_type ──
    dm_type = config.get("device_manager_type", "")
    if not dm_type:
        fail_msg("device_manager_type is empty", "Must be one of: " + ", ".join(sorted(VALID_DEVICE_MANAGER_TYPES)))
        return False, None
    if dm_type not in VALID_DEVICE_MANAGER_TYPES:
        warn_msg(
            f"Unknown device_manager_type: '{dm_type}'",
            "Known types: " + ", ".join(sorted(VALID_DEVICE_MANAGER_TYPES))
        )

    # ── Check paths ──
    paths = config.get("paths", {})
    dataset_file = paths.get("dataset_file", "")
    if not dataset_file:
        fail_msg("paths.dataset_file is empty", "The automator will crash without a dataset file.")
        return False, None
    if not os.path.isfile(dataset_file):
        detail = _diagnose_dataset_path(dataset_file)
        fail_msg("Dataset file not found", detail)
        return False, None
    else:
        pass_msg(f"Dataset file exists: {dataset_file}")

    root_folder = paths.get("root_folder", "")
    if root_folder:
        os.makedirs(root_folder, exist_ok=True)
        pass_msg(f"Root folder exists: {root_folder}")
    else:
        fail_msg("paths.root_folder is empty", "The automator needs a root folder for results.")
        return False, None

    # ── Check queue_file parent directory ──
    queue_file = paths.get("queue_file", "")
    if queue_file:
        queue_parent = os.path.dirname(queue_file)
        if queue_parent and not os.path.isdir(queue_parent):
            try:
                os.makedirs(queue_parent, exist_ok=True)
                pass_msg(f"Queue file directory created: {queue_parent}")
            except OSError as e:
                fail_msg("Cannot create queue_file directory", f"{queue_parent}: {e}")
                return False, None

    # ── Check device IDs ──
    devices = config.get("devices", {})

    if "s25" in dm_type:
        s25_id = devices.get("s25_device_id", "")
        if not s25_id:
            fail_msg("s25_device_id is empty", "Required for " + dm_type)
            return False, None

    if "jinju" in dm_type:
        jinju_id = devices.get("jinju_device_id", "")
        if not jinju_id:
            fail_msg("jinju_device_id is empty", "Required for " + dm_type)
            return False, None

    # ── Check ARAP config ──
    arap = devices.get("arap", {})
    use_robohead = arap.get("use_robohead", True)
    if not use_robohead:
        arap_devices = arap.get("devices", [])
        if len(arap_devices) < 1:
            fail_msg("ARAP devices list is empty", "Required when use_robohead=false")
            return False, None
        if len(arap_devices) > 2:
            fail_msg("Too many ARAP devices", f"Expected 1-2, got {len(arap_devices)}")
            return False, None
        record_duration = arap.get("record_duration", 0)
        if record_duration <= 0:
            fail_msg("arap.record_duration must be > 0", f"Got: {record_duration}")
            return False, None
    else:
        robopod_url = arap.get("robopod_url", "")
        if not robopod_url:
            fail_msg("robopod_url is empty", "Required when use_robohead=true")
            return False, None

    # ── Check URLs ──
    urls = config.get("urls", {})
    display_port = urls.get("display_port", 0)
    if display_port <= 0:
        warn_msg("urls.display_port is 0 or not set", "Display client may not connect")

    # ── Check judge_worker prompt versions ──
    judge_worker = config.get("judge_worker", {})
    prompt_fields = ["qa_prompt_version", "vqa_prompt_version", "hqa_prompt_version", "appEval_prompt_version"]
    for field in prompt_fields:
        val = judge_worker.get(field, [])
        if not val:
            warn_msg(f"judge_worker.{field} is empty", "Judge may not have a prompt to use for this eval type")

    # ── Check XRClaw config ──
    xrclaw_config = config.get("xrclaw", {})
    if xrclaw_config.get("enabled", False):
        xrclaw_path = xrclaw_config.get("python_automation_path", "")
        if not xrclaw_path:
            fail_msg("xrclaw.python_automation_path is empty", "Required when xrclaw.enabled=true")
            return False, None
        if not os.path.isdir(xrclaw_path):
            fail_msg("xrclaw.python_automation_path not found", xrclaw_path)
            return False, None

    pass_msg("Config file is valid")
    return True, config


def check_fireredvad():
    """Check that FireRedVAD Python package is installed and model files exist."""
    # 1. Check Python package import
    try:
        import fireredvad  # noqa: F401
        pass_msg("fireredvad Python package is importable")
    except ImportError:
        fail_msg(
            "fireredvad Python package is NOT installed",
            "pip install fireredvad==0.0.2  (see README §4 FireRedVAD)"
        )
        return False

    # 2. Check model directory exists
    model_dir = os.path.join(
        PROJECT_ROOT, "data", "models", "fireredvad",
        "pretrained_models", "FireRedVAD", "VAD"
    )
    if not os.path.isdir(model_dir):
        fail_msg(
            "FireRedVAD model directory not found",
            f"Expected at: {model_dir}\n"
            "Download/Clone from: https://huggingface.co/FireRedTeam/FireRedVAD/tree/main \n"
            "See README §4: FireRedVAD (speech detection)"
        )
        return False

    # 3. Check key model files are present
    required_files = ["cmvn.ark", "model.pth.tar"]
    missing_files = [f for f in required_files if not os.path.isfile(os.path.join(model_dir, f))]
    if missing_files:
        fail_msg(
            "FireRedVAD model directory is incomplete",
            f"Missing files in {model_dir}: {', '.join(missing_files)}\n"
            "Re-download the model from HuggingFace"
        )
        return False

    pass_msg(f"FireRedVAD model files present ({model_dir})")
    return True


def check_python_dependencies():
    """Check that critical Python dependencies are installed."""
    critical_deps = [
        ("requests", "HTTP client for service checks"),
        ("openai", "OpenAI-compatible API client for judge"),
        ("numpy", "Numerical computing (used by VAD, entropy)"),
        ("dateutil", "Date/time parsing (python-dateutil)"),
    ]
    all_ok = True
    for module_name, description in critical_deps:
        try:
            __import__(module_name)
            pass_msg(f"{module_name} installed ({description})")
        except ImportError:
            pkg_name = "python-dateutil" if module_name == "dateutil" else module_name
            fail_msg(f"{module_name} is NOT installed", f"pip install {pkg_name} — {description}")
            all_ok = False
    return all_ok


def check_display_client(config):
    """Check if the display client process is running (required).

    The display server is started automatically by the automator (agent_tester.py)
    as a background thread. But the display CLIENT is a separate GUI process that
    must be started manually on the monitor host.
    Two variants are available:
      - display_client.py          (landscape mode)
      - display_client_portrait.py (portrait mode, rotated 90°)
    This check verifies that at least one client process is running.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "display_client"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            pass_msg(f"Display client is running (PID: {', '.join(pids)})")
            return True
        else:
            fail_msg(
                "Display client is NOT running",
                "Start with either:\n"
                "  Landscape: python services/client/display_client.py http://<server_ip>:<display_port>\n"
                "  Portrait:  python services/client/display_client_portrait.py http://<server_ip>:<display_port>"
            )
            return False
    except FileNotFoundError:
        # pgrep not available, try ps + grep as fallback
        try:
            result = subprocess.run(
                "ps aux | grep display_client | grep -v grep",
                shell=True, capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                pass_msg("Display client is running")
                return True
            else:
                fail_msg(
                    "Display client is NOT running",
                    "Start with either:\n"
                    "  Landscape: python services/client/display_client.py http://<server_ip>:<display_port>\n"
                    "  Portrait:  python services/client/display_client_portrait.py http://<server_ip>:<display_port>"
                )
                return False
        except Exception as e:
            fail_msg("Display client check failed", str(e))
            return False
    except Exception as e:
        fail_msg("Display client check failed", str(e))
        return False



def check_rating_rectifier(config):
    """Check if the rating rectifier service is reachable (if configured)."""
    rectifier_url = config.get("urls", {}).get("rating_rectifier_url", "")
    if not rectifier_url:
        warn_msg("rating_rectifier_url not set — skipping (optional)")
        return True

    try:
        resp = requests.get(rectifier_url.rstrip("/") + "/models", timeout=5)
        if resp.status_code == 200:
            pass_msg(f"Rating rectifier reachable at {rectifier_url}")
            return True
        else:
            warn_msg(f"Rating rectifier returned status {resp.status_code}", rectifier_url)
            return True  # Warning, not failure
    except requests.exceptions.ConnectionError:
        warn_msg(
            f"Rating rectifier not reachable at {rectifier_url}",
            "Service is optional — pipeline will work without it"
        )
        return True
    except Exception as e:
        warn_msg(f"Rating rectifier check failed: {e}")
        return True


def check_dataset(config):
    """Check the dataset file is valid JSONL."""

    dataset_file = config["paths"]["dataset_file"]
    if not dataset_file or not os.path.isfile(dataset_file):
        detail = _diagnose_dataset_path(dataset_file) if dataset_file else "dataset_file is empty in config"
        fail_msg("Dataset file not found", detail)
        return False

    try:
        with open(dataset_file) as f:
            lines = f.readlines()
        if not lines:
            fail_msg("Dataset file is empty", dataset_file)
            return False

        # Validate first and last lines are JSON
        json.loads(lines[0])
        json.loads(lines[-1])

        start_idx = config.get("dataset_start_index", 0)
        end_idx = config.get("dataset_end_index", len(lines))
        num_questions = (min(end_idx, len(lines)-1) - start_idx) + 1

        if num_questions <= 0:
            fail_msg(
                "No questions to evaluate",
                f"dataset_start_index={start_idx}, dataset_end_index={end_idx}, "
                f"dataset has {len(lines)} lines. Check your index range."
            )
            return False

        pass_msg(f"Dataset valid: {len(lines)} lines, {num_questions} questions to evaluate")
        return True
    except json.JSONDecodeError as e:
        fail_msg("Dataset contains invalid JSON", str(e))
        return False


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pre-run diagnostic checks for the evaluation framework")
    parser.add_argument("config", help="Path to the config JSON file")
    parser.add_argument("--skip-arap", action="store_true", help="Skip ARAP device checks")
    parser.add_argument("--skip-xrclaw", action="store_true", help="Skip XRClaw checks")
    args = parser.parse_args()

    print(f"{BOLD}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║   Pre-Run Diagnostic Checks                      ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════╝{RESET}")

    all_passed = True

    # ── 1. Config validation ──
    section("1. Config Validation")
    config_ok, config = check_config(args.config)
    if not config_ok:
        print(f"\n{RED}Config validation failed. Fix the above errors before continuing.{RESET}")
        sys.exit(1)
    all_passed = all_passed and config_ok

    # ── 2. Dataset validation ──
    section("2. Dataset Validation")
    dataset_ok = check_dataset(config)
    all_passed = all_passed and dataset_ok

    # ── 3. Device connectivity ──
    section("3. Device Connectivity")
    devices = config["devices"]
    dm_type = config["device_manager_type"]

    device_ids_to_check = []
    if "s25" in dm_type:
        device_ids_to_check.append((devices.get("s25_device_id", ""), "S25 (companion)"))
    if "jinju" in dm_type:
        device_ids_to_check.append((devices.get("jinju_device_id", ""), "Jinju"))

    arap = devices.get("arap", {})
    if not arap.get("use_robohead", True):
        for i, dev_id in enumerate(arap.get("devices", [])):
            label = f"ARAP speaker" if i == 0 else f"ARAP recorder"
            device_ids_to_check.append((dev_id, label))

    for dev_id, label in device_ids_to_check:
        if dev_id:
            ok = check_device_online(dev_id, label)
            all_passed = all_passed and ok
        else:
            fail_msg(f"{label} device ID is empty")
            all_passed = False

    # ── 4. ARAP checks ──
    if not args.skip_arap and not arap.get("use_robohead", True):
        section("4. ARAP App Checks")

        arap_devices = arap.get("devices", [])
        speaker_id = arap_devices[0] if arap_devices else ""

        if speaker_id:
            installed = check_arap_app_installed(speaker_id)
            all_passed = all_passed and installed

            if installed:
                launched = check_arap_app_launch(speaker_id)
                all_passed = all_passed and launched

                if launched:
                    play_ok = check_arap_play_audio(speaker_id)
                    all_passed = all_passed and play_ok

                    rec_ok = check_arap_recording(speaker_id)
                    all_passed = all_passed and rec_ok
        else:
            fail_msg("No ARAP speaker device configured")
            all_passed = False
    elif arap.get("use_robohead", True):
        section("4. ARAP (Robopod mode)")
        robopod_url = arap.get("robopod_url", "")
        if robopod_url:
            ok = check_service_url(robopod_url, "Robopod server")
            all_passed = all_passed and ok
        else:
            fail_msg("robopod_url is empty")
            all_passed = False

    # ── 5. XRClaw checks ──
    xrclaw_config = config.get("xrclaw", {})
    if xrclaw_config.get("enabled", False) and not args.skip_xrclaw:
        section("5. XRClaw Checks")

        xrclaw_device = devices.get("s25_device_id", "")
        if xrclaw_device:
            running = check_xrclaw_app_running(xrclaw_device)
            all_passed = all_passed and running

            if running:
                python_automation_path = xrclaw_config.get("python_automation_path", "")
                if python_automation_path:
                    af_ok = check_xrclaw_app_functions(python_automation_path, xrclaw_device)
                    all_passed = all_passed and af_ok
                else:
                    fail_msg("xrclaw.python_automation_path is empty in config")
                    all_passed = False
        else:
            fail_msg("No s25_device_id for XRClaw target device")
            all_passed = False
    elif not xrclaw_config.get("enabled", False):
        section("5. XRClaw Checks")
        warn_msg("XRClaw is disabled in config — skipping")

    # ── 6. Service checks ──
    section("6. Service Checks")

    urls = config.get("urls", {})
    transcription_url = urls.get("transcription_url", "")
    judge_url = urls.get("judge_url", "")

    if transcription_url:
        ok = check_service_url(transcription_url, "Transcription service", path="/health/")
        all_passed = all_passed and ok
    else:
        fail_msg("transcription_url is empty")
        all_passed = False

    if judge_url:
        ok = check_judge_model(judge_url)
        all_passed = all_passed and ok
    else:
        fail_msg("judge_url is empty")
        all_passed = False

    display_ok = check_display_client(config)

    all_passed = all_passed and display_ok

    # ── 7. Python dependencies ──

    section("7. Python Dependencies")
    deps_ok = check_python_dependencies()
    all_passed = all_passed and deps_ok

    # ── 8. FireRedVAD checks ──
    section("8. FireRedVAD (Speech Detection)")
    vad_ok = check_fireredvad()
    all_passed = all_passed and vad_ok

    # ── 9. Optional service checks ──
    section("9. Optional Services (Rating Rectifier)")
    rectifier_ok = check_rating_rectifier(config)
    # This is a warning, not a failure

    # ── Summary ──

    print(f"\n{BOLD}╔══════════════════════════════════════════════════╗{RESET}")
    if all_passed:
        print(f"{BOLD}║  {GREEN}All checks passed ✓{RESET}{BOLD}                                ║{RESET}")
        print(f"{BOLD}║  Ready to run: python -m automator.automator    ║{RESET}")
        print(f"{BOLD}║      {args.config}              ║{RESET}")
    else:
        print(f"{BOLD}║  {RED}Some checks failed ✗{RESET}{BOLD}                            ║{RESET}")
        print(f"{BOLD}║  Fix the issues above before running the pipeline║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════╝{RESET}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
