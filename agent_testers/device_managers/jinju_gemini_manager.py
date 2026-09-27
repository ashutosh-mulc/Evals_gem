import subprocess, time

from agent_testers.device_managers.device_manager import DeviceManagerTemplate
from agent_testers.device_managers.mixins.app_tasks import AppTasksMixin
from agent_testers.device_managers.mixins.state_collect import StateCollectMixin
from agent_testers.device_managers.mixins.logcat import LogcatMixin
from agent_testers.device_managers.mixins.device_info import DeviceInfoMixin
from agent_testers.device_managers.mixins.device_command import DeviceCommandMixin
from agent_testers.device_managers.mixins.app_meta_info import AppMetaInfoMixin
from utils.adb_client import AdbClient
from utils.log_analyzer import LogcatAnalyzer, BUILTIN_PROFILES
from agent_testers.power_monitor import PowerMonitor
from common.question_type import QuestionType

class DeviceManager(
    LogcatMixin,
    DeviceInfoMixin,
    DeviceCommandMixin,
    AppMetaInfoMixin,
    AppTasksMixin,
    StateCollectMixin,
    DeviceManagerTemplate,
):

    def __init__(self, companion_device_id : str, jinju_device_id : str, log_dump_folder : str = "", config : dict = None):
        self.companion_device = companion_device_id
        self.live_device = companion_device_id  # runs Gemini Live -> event-driven conversation loop
        self.jinju_device = jinju_device_id
        self.arap_speaker = None
        self.log_procs = []
        self.log_folder = log_dump_folder; self.log_extra = {}
        self.state_collector = None
        self.xrclaw_collector = None  # backward-compat alias
        self._adb = AdbClient()

        print(f"Make sure {self.companion_device} and {self.jinju_device} are rooted devices!")

        # --- power measurement (jinju only) ---
        config = config or {}
        power_cfg = config.get("power_measurement", {})
        self.power_monitor = PowerMonitor(
            device_id=self.jinju_device,
            script_path=power_cfg.get("script_path", ""),
            samples=power_cfg.get("samples", 100000),
            interval=power_cfg.get("interval", 2),
            enabled=power_cfg.get("enabled", False),
        )

        # --- logcat analyzer (pluggable, pattern-based) ---
        self.logcat_analyzer = LogcatAnalyzer([BUILTIN_PROFILES["camera"]])
    
    @staticmethod
    def get_device_names():
        return ["s25_device_id", "jinju_device_id"] # same order as the order of device ids in init

    def _get_companion_device(self) -> str:
        return self.companion_device

    def _get_jinju_device(self) -> str:
        return self.jinju_device

    def reset_device_to_default_state(self) -> dict:
        """Reset Jinju device to known default state before EVERY test case.
        
        Called once at the start of each test, before app-specific preconditions.
        This ensures consistent baseline state for all evaluations.
        
        Returns:
            dict with keys:
                - set: list of successful resets
                - failed: list of failed resets
        """
        report = {"set": [], "failed": []}
        
        # Reset screen to home
        self.reset_companion_screen()
        report["set"].append("Screen reset to home")
        
        # Reset volume to 100% on Jinju and companion device (all streams, percentage of each stream's max)
        self.reset_media_volume(self._get_jinju_device(), 100)
        self.reset_media_volume(self._get_companion_device(), 100)
        report["set"].append("Volume reset to 80%")
     
        ## Turn off DND/zen mode
        self._adb.set_dnd_mode(self.companion_device, False)
        report["set"].append("DND turned off")
        
        return report


    def set_connectivity(self, connectivity: str) -> None:
        """Setup companion device connectivity based on question type.

        OFFLINE:       Jinju is paired but no internet on companion device.
        DISCONNECTED:  Jinju is disconnected from companion device.
        ONLINE:        Jinju is paired and internet is also available.
        """
        if connectivity.lower() == "offline":
            self._adb.set_wifi(self.companion_device, False)
            self._adb.set_mobile_data(self.companion_device, False)
            self._adb.set_bluetooth(self.companion_device, True)
            print("Device state: OFFLINE (wifi off, mobile data off, bluetooth on)")

        elif connectivity.lower() == "disconnected":
            self._adb.set_wifi(self.companion_device, True)
            self._adb.set_mobile_data(self.companion_device, True)
            self._adb.set_bluetooth(self.companion_device, False)
            print("Device state: DISCONNECTED (wifi on, mobile data on, bluetooth off)")

        elif connectivity.lower() == "online":
            self._adb.set_wifi(self.companion_device, True)
            self._adb.set_mobile_data(self.companion_device, True)
            self._adb.set_bluetooth(self.companion_device, True)
            print("Device state: ONLINE (wifi on, mobile data on, bluetooth on)")
        else:
            print(f"Connectivity {connectivity} IS NOT VALID !\nContinuing in current state..,")

        time.sleep(1)

    def invoke(self, q_info):
        """
            Invokes gemini and performs the task for the given question.
            
            Note: State collectors gets invoked in agent_tester.py, this 
            function only handles execution of query on gemini live and start collecting logs
            Rest all including ARAP management is handled in agent_tester.py
            
            q_info: question info dictionary
            
            Execution steps:
             
             - Start services - Loggers, Power monitor(Future plan), etc.
             - Invoke gemini 
            
        """
        assert self._adb.is_device_online(self.jinju_device), f"Device {self.jinju_device} NOT online!"
        assert self._adb.is_device_online(self.companion_device), f"Device {self.companion_device} NOT online!"
        
        ## This makes noe 
        self._adb.unlock(self.companion_device)

        
        q_type = q_info.get("question_type", "").lower()

        # 4-part format: <connectivity>_<group>_<feature>_<action>
        parts = q_type.split("_") if q_type else []
        group = parts[1] if len(parts) >= 2 else ""
        feature = parts[2] if len(parts) >= 3 else ""

        invoke_type = q_info["eval_type"]
        qt = QuestionType.parse(q_info.get("question_type", ""))

        ## Step 2: Start Services 
        ## Logging has to be moved prior for detecting invokation and early stopping automation upon gemini-live session end
        # Logcat timestamp capture (complex pipeline - keep as subprocess)
        command = f"adb -s {self.jinju_device} logcat -v time -t 1 | grep -v \"^---\" | awk " + "'{print $1, $2}'"
        self.log_extra["jinju_invoke_ts"] = subprocess.check_output(command, shell= True, text=True).strip()
        
        print("----Invoking Jinju Gemini----")
        self._adb.press_key(self.jinju_device, "KEYCODE_FEATURED_APP_1")
        time.sleep(1.5)
        
          # Switch on camera for visual questions (VQA, Hallucination, or APP_EVAL with visual action)
        if invoke_type in ["Visual_QA_TASK", "Hallucination_TASK"] or qt.is_visual:
            self._adb.shell(self.jinju_device, "input keyevent --delay 200 KEYCODE_STEM_1 KEYCODE_STEM_1")
            time.sleep(0.5)
            print("Jinju invoked in video mode (camera on)!")
            return
        
        ## TODO: Move these in preconditions section for better control over invocation
        ## but the challenge is these apps have to be opened after invoking gemini to work
        ## TODO: Bigger plan is to change the verification processes for these, there are better ways
        ## Currently we rely on GEMINI to show the app function widgets and click on it but 
        ## this is not reliable, as gemini's ui is not very responsive and sometimes the widget's aren't 
        ## displayed live, after closing and reopening the session its visible
        
        if feature in ("message", "call") or group == "thirdparty" and feature == "whatsapp":
            self._adb.start_activity(
                self.companion_device,
                "com.google.android.apps.bard/com.google.android.apps.bard.shellapp.BardEntryPointActivity"
            )
            time.sleep(1)
            
            ## Close the keyboard pop-up/OR Use null keyboard while evaluation for these apps
            ## This is done to ensure taps works reliable as the locations are calibrated for 
            ## UI with keyboard closed.
            self._adb.reset_ime(self.companion_device)

        print("Jinju invoked in audio only mode!")

    
    def terminate(self):
        """Terminate the current session and reset the companion device screen.

        Sends multiple BACK presses to close any open menus/dialogs/sub-screens,
        then presses HOME to ensure the companion device returns to the home
        screen. This prevents stale app state from bleeding into the next test.

        Previously only a single BACK was sent, which left context menus,
        dialogs, and apps open — causing the companion device to stay stuck
        on a previous test's app (e.g., Samsung Notes with a context menu
        open) for dozens of subsequent test cases.
        """
        # Close any open context menus, dialogs, or sub-screens
        for _ in range(3):
            self._adb.press_back(self.companion_device)
            time.sleep(0.5)

        # Press HOME to ensure we're back at the home screen
        self._adb.press_key(self.companion_device, "KEYCODE_HOME")
        time.sleep(0.5)

        print(f"Terminated Gemini! Companion screen reset to home.")

    def reset_companion_screen(self):
        """Reset the companion device to a clean home-screen state.

        Call this at the START of each test case (before preconditions) to
        ensure no leftover app or menu state from a previous test interferes.
        This force-stops common test apps and presses HOME.
        """
        # Press HOME first to exit any foreground app
        self._adb.press_key(self.companion_device, "KEYCODE_HOME")
        time.sleep(0.5)

        # Send a couple of BACK presses to dismiss any lingering dialogs/menus
        for _ in range(2):
            self._adb.press_back(self.companion_device)
            time.sleep(0.3)

        # Press HOME again to ensure clean state
        self._adb.press_key(self.companion_device, "KEYCODE_HOME")
        time.sleep(0.5)

        print(f"Companion screen reset to home (pre-test cleanup).")


    def reset_media_volume(self, device_id: str, volume_pct: int = 80) -> None:
        """Reset volume on the specified device, setting ALL streams to a percentage of their max.

        Args:
            device_id: ADB device serial.
            volume_pct: Percentage of each stream's max range (0-100). Default 80%.
        """
        from agent_testers.device_managers.device_config import DeviceInfo

        di = DeviceInfo(device=device_id)
        vol_state = di.get_volume()
        all_streams = vol_state.get("all_streams", {})

        if not all_streams:
            # Fallback: set MUSIC only
            self._adb.shell(device_id, f"cmd media_session volume --stream 3 --set {volume_pct}")
            print(f"Reset media volume on {device_id} to {volume_pct}% (MUSIC only, no stream data)")
            return

        # Map stream name → stream ID for ADB command
        _STREAM_NAME_TO_ID = {
            "STREAM_VOICE_CALL": 0, "STREAM_SYSTEM": 1, "STREAM_RING": 2,
            "STREAM_MUSIC": 3, "STREAM_ALARM": 4, "STREAM_NOTIFICATION": 5,
            "STREAM_BLUETOOTH_SCO": 6, "STREAM_SYSTEM_ENFORCED": 7, "STREAM_DTMF": 8,
            "STREAM_TTS": 9, "STREAM_ACCESSIBILITY": 10, "STREAM_ASSISTANT": 11,
        }

        for sname, sinfo in all_streams.items():
            smax = sinfo.get("max")
            if smax is None or smax <= 0:
                continue
            target = int(volume_pct / 100 * smax)
            sid = _STREAM_NAME_TO_ID.get(sname)
            if sid is None:
                continue
            self._adb.shell(device_id, f"media volume --stream {sid} --set {target}")

        print(f"Reset volume on {device_id} to {volume_pct}% across {len(all_streams)} streams")
