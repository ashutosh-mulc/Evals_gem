"""
Power Monitor — On-device power measurement during evaluation.

Measures device power consumption by running a background sampling script
that reads current/voltage from sysfs nodes. The script runs with root
access via `su 0` and survives adb disconnection.

Supported Devices:
  - Jinju glasses (default script)
  - S25 (requires different script with appropriate sysfs paths)

The on-device script determines unit ranges and sysfs nodes, making
this manager device-agnostic — just provide the correct script path.
"""

import subprocess, os, re, time


class PowerMonitor:
    """
    Monitors device power consumption via on-device sampling script.

    Workflow:
      1. Push power measurement script to device
      2. Start background sampler (survives adb disconnect via nohup)
      3. After evaluation, kill sampler and pull log
      4. Parse log to extract average current, voltage, and power

    Args:
        device_id: ADB device serial.
        script_path: Local path to the power measurement shell script.
        remote_script: Destination path on device (default: /data/local/tmp/power_measure.sh).
        samples: Number of samples to collect (default: 100000).
        interval: Sampling interval in seconds (default: 2).
        enabled: Whether power measurement is enabled (default: True).
    """
    DEVICE_TMP_DIR = "/data/local/tmp/powertest"

    def __init__(self, device_id: str, script_path: str = "",
                 remote_script: str = "/data/local/tmp/power_measure.sh",
                 samples: int = 100000, interval: int = 2, enabled: bool = True):
        """Initialize PowerMonitor.

        Args:
            device_id: ADB device serial identifier.
            script_path: Path to local power measurement script.
            remote_script: Remote destination path on device.
            samples: Number of samples to collect.
            interval: Time between samples in seconds.
            enabled: Enable/disable power measurement.
        """
        self.device = device_id
        self.script_path = script_path
        self.remote_script = remote_script
        self.samples = samples
        self.interval = interval
        self.enabled = bool(enabled) and bool(script_path) and os.path.exists(script_path)
        self.pid = None
        self.remote_log = f"{self.DEVICE_TMP_DIR}/power_current.log"
        self._pushed = False
        if enabled and not self.enabled:
            print(f"WARNING: power measurement requested but script not found: '{script_path}'. Disabled.")

    def _adb(self, args: list, **kw) -> subprocess.CompletedProcess:
        """Run an ADB command on the target device.

        Args:
            args: List of ADB arguments (e.g., ["shell", "ls"]).
            **kw: Additional kwargs for subprocess.run.

        Returns:
            subprocess.CompletedProcess with command result.
        """
        return subprocess.run(["adb", "-s", self.device] + args, **kw)

    def push_script(self):
        """Push the power measurement script to the device.

        Creates the temp directory, pushes the script, and makes it executable.
        No-op if power measurement is disabled.
        """
        if not self.enabled:
            return
        self._adb(["shell", "mkdir", "-p", self.DEVICE_TMP_DIR])
        self._adb(["push", self.script_path, self.remote_script])
        self._adb(["shell", "chmod", "755", self.remote_script])
        self._pushed = True
        print(f"----Power script pushed to {self.device}----")

    def start(self):
        """Start the background power sampling process.

        Runs the power measurement script with root access using nohup so it
        survives adb disconnection. Stores the PID for later termination.
        """
        if not self.enabled:
            return
        if not self._pushed:
            self.push_script()
        self._adb(["shell", "rm", "-f", self.remote_log])
        remote = (f"SAMPLES={self.samples} INTERVAL={self.interval} LOG={self.remote_log} "
                  f"nohup su 0 sh {self.remote_script} >/dev/null 2>&1 & echo $!")
        try:
            out = subprocess.check_output(["adb", "-s", self.device, "shell", remote], text=True).strip()
            m = re.findall(r"\d+", out)
            self.pid = m[-1] if m else None
        except subprocess.SubprocessError as e:
            print(f"Power start failed: {e}")
            self.pid = None
        print(f"----Power measurement started (pid={self.pid})----")

    def stop_and_collect(self, local_folder: str, log_name: str = "power_log.txt") -> dict:
        """Stop the sampler, pull the log, and return parsed power metrics.

        Args:
            local_folder: Local directory to save the pulled log file.
            log_name: Filename for the saved log (default: "power_log.txt").

        Returns:
            Dict with keys:
              - avg_current_ma: Average current in milliamps (or None)
              - avg_voltage_v: Average voltage in volts (or None)
              - avg_power_w: Average power in watts (or None)
              - num_samples: Number of valid samples collected
        """
        if not self.enabled:
            return {}
        if self.pid:
            self._adb(["shell", "su", "0", "kill", self.pid], stderr=subprocess.DEVNULL)
        # defensive wakelock release (the script's TERM trap normally does this)
        self._adb(["shell", "su", "0", "sh", "-c", "echo powertest > /sys/power/wake_unlock"],
                  stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1)
        local_log = os.path.join(local_folder, log_name)
        self._adb(["pull", self.remote_log, local_log], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._adb(["shell", "rm", "-f", self.remote_log])
        self.pid = None
        return self._parse_log(local_log)

    @staticmethod
    def _parse_log(local_log: str) -> dict:
        """Parse the power log file and extract metrics.

        Parses lines matching the pattern:
          I=<current>mA ... V=<voltage>V ... (<power>mW)

        Args:
            local_log: Path to the local log file.

        Returns:
            Dict with keys:
              - avg_current_ma: Average current in milliamps
              - avg_voltage_v: Average voltage in volts
              - avg_power_w: Average power in watts
              - num_samples: Number of valid samples
        """
        metrics = {"avg_current_ma": None, "avg_voltage_v": None,
                   "avg_power_w": None, "num_samples": 0}
        if not os.path.exists(local_log):
            return metrics
        sample_re = re.compile(r"I=(-?\d+)\s*mA.*?V=(-?\d+\.\d+)\s*V.*?\((-?\d+)\s*mW\)")
        cur, volt, pw = [], [], []
        with open(local_log, "r", errors="replace") as f:
            for line in f:
                m = sample_re.search(line)
                if m:
                    cur.append(int(m.group(1)))
                    volt.append(float(m.group(2)))
                    pw.append(int(m.group(3)))
        n = len(pw)
        metrics["num_samples"] = n
        if n:
            metrics["avg_current_ma"] = round(sum(cur) / n, 2)
            metrics["avg_voltage_v"] = round(sum(volt) / n, 3)
            metrics["avg_power_w"] = round(sum(pw) / n / 1000.0, 3)
        return metrics
