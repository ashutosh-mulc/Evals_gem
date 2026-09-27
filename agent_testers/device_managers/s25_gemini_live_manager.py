from agent_testers.device_managers.device_manager import DeviceManagerTemplate
from agent_testers.device_managers.mixins.app_tasks import AppTasksMixin
from agent_testers.device_managers.mixins.state_collect import StateCollectMixin
from utils.adb_client import AdbClient
import os, shutil, subprocess, time

class DeviceManager(AppTasksMixin, StateCollectMixin, DeviceManagerTemplate):

    def __init__(self, gemini_device_id : str, log_dump_folder : str = "", config : dict = None):
        self.gemini_device = gemini_device_id
        self.live_device = gemini_device_id  # runs Gemini Live -> event-driven conversation loop
        self.log_procs = []
        self.log_folder = log_dump_folder
        self._adb = AdbClient()

        print(f"Make sure {self.gemini_device} is a rooted device!")

    
    @staticmethod
    def get_device_names():
        return ["s25_device_id"] # same order as the order of device ids in init

    def _get_companion_device(self) -> str:
        return self.gemini_device

    def invoke(self, q_info):

        assert self._adb.is_device_online(self.gemini_device), f"Device {self.gemini_device} NOT online!"
        self._adb.unlock(self.gemini_device)

        
        print("----Invoking S25 Gemini Live----")
        command = f"adb -s {self.gemini_device} shell am start -n \
            com.google.android.apps.bard/com.google.android.apps.bard.shellapp.BardEntryPointActivity" # starting gemini on phone
        subprocess.run(command, shell=True)
        time.sleep(2)
        # self._click_phone(self.gemini_device, 982, 2097)  # Taps on Gemini Live
        self._click_phone(self.gemini_device, 893, 1200)  # Taps on Gemini Live

        time.sleep(5) # Gemini live takes time to open up
        invoke_type = q_info["eval_type"]
        if invoke_type in ["Visual_QA_TASK", "Hallucination_TASK"]: #switch off camera if not a visual question
            self._click_phone(self.gemini_device, 185, 2069) # Open Video
            time.sleep(2)
            print("S25 Gemini invoked in video only mode!")

    
    def capture_app_meta_info(self, q_info):
        assert self._adb.is_device_online(self.gemini_device), f"Device {self.gemini_device} NOT online!"
        self._adb.unlock(self.gemini_device)

        q_type = q_info["question_type"]
        # Parse question_type using the shared parser
        from common.question_type import QuestionType
        qt = QuestionType.parse(q_type)
        app_name = qt.app_key or ""
        app_eval_mode = qt.action

        # ── Step 1: XRClaw verification (if available) ──────────────
        # Runs first, stores result in metadata["app_state"].
        # Does NOT return early — app tasks always run after this.
        self._collect_state(q_info)

        # ── Step 2: Execute app tasks from config (ALWAYS runs) ───
        # This opens the app, navigates, takes screenshot, and closes app.
        # Runs regardless of verification outcome so VLM judge has a screenshot.
        if not self._run_app_tasks(qt.group, qt.feature, q_type, app_eval_mode,
                                    fallback_screenshot=True, mode_fallback=qt.action_with_suffix):
            print(f"App config not found for {q_type} (app_name={app_name}, mode={app_eval_mode})")

        # ── Step 3: Store screenshot path ───────────────────────────
        app_screenshot = os.path.join(self.log_folder, "app_screenshot.png")
        if os.path.exists(app_screenshot):
            q_info["metadata"]["post_state_screenshots"] = [app_screenshot]

    
    def terminate(self):

        # self._click_phone(self.gemini_device, 893, 2066) # Open Video
        command = f"adb -s {self.gemini_device} shell am force-stop com.google.android.googlequicksearchbox"
        subprocess.run(command, shell=True)
        print(f"Terminated Gemini!")
    
    def start_logging(self) -> None:
        assert self._adb.is_device_online(self.gemini_device), "Devices NOT online!"
        assert os.path.isdir(self.log_folder), f"log folder {self.log_folder} DOES NOT EXIST!"
        self._start_logcat({self.gemini_device: "s25_gemini_live_log.txt"}, timeout_s=180)
        self._clear_s25_image_folder()

    def stop_logging(self) -> dict:
        assert self._adb.is_device_online(self.gemini_device), "Devices NOT online!"
        log_files = {}
        self._pull_s25_query_image()
        for file_name in os.listdir(self.log_folder):
            if "screen.png" in file_name:
                shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "device_view_image.png"))
                log_files["device_view_image_path"] = os.path.join(self.log_folder, "device_view_image.png")
        self._stop_logcat()
        return log_files

    def _pull_s25_query_image(self, remote_path="/sdcard/Pictures/screen.png"):
        self._adb.screencap(self.gemini_device, remote_path)
        self._adb.pull(self.gemini_device, remote_path, self.log_folder, check=False)
        self._clear_s25_image_folder(remote_path)

    def _clear_s25_image_folder(self, remote_path="/sdcard/Pictures/screen.png"):
        self._adb.delete_file(self.gemini_device, remote_path)
