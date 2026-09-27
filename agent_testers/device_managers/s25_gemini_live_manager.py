from agent_testers.device_managers.device_manager import DeviceManagerTemplate
from agent_testers.device_managers.mixins.app_tasks import AppTasksMixin
from agent_testers.device_managers.mixins.state_collect import StateCollectMixin
from utils.adb_client import AdbClient
import subprocess, os, shutil, time, signal

class DeviceManager(AppTasksMixin, StateCollectMixin, DeviceManagerTemplate):

    def __init__(self, gemini_device_id : str, log_dump_folder : str = "", config : dict = None):
        self.gemini_device = gemini_device_id
        self.live_device = gemini_device_id  # runs Gemini Live -> event-driven conversation loop
        self.log_procs = []
        self.log_folder = log_dump_folder
        self.state_collector = None
        self.xrclaw_collector = None  # backward-compat alias
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
        collect_fn = getattr(self, "_collect_state", None) or getattr(self, "_xrclaw_collect_state", None)
        collector = getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)
        if collect_fn and collector:
            collect_fn(collector, q_info)
            print(f"----XRClaw verification completed for {app_name}----")

        # ── Step 2: Execute app tasks from config (ALWAYS runs) ───
        # This opens the app, navigates, takes screenshot, and closes app.
        # Runs regardless of verification outcome so VLM judge has a screenshot.
        from apps import get_app_info, get_task_list

        app_info = get_app_info(q_type)
        task_list = get_task_list(q_type)
        if app_info and task_list:
            app_config = {
                "package_name": app_info["package_name"],
                "activity_name": app_info["activity_name"],
                "tasks": {app_eval_mode: task_list},
            }
            self._execute_app_tasks(q_type, app_config, app_eval_mode)
        else:
            print(f"App config not found for {q_type} (app_name={app_name}, mode={app_eval_mode})")
            self._pull_screenshot("/sdcard/Pictures/app_screenshot.png")

        # ── Step 3: Store screenshot path ───────────────────────────
        app_screenshot = os.path.join(self.log_folder, "app_screenshot.png")
        if os.path.exists(app_screenshot):
            q_info["metadata"]["app_screenshot_path"] = app_screenshot

    
    def terminate(self):

        # self._click_phone(self.gemini_device, 893, 2066) # Open Video
        command = f"adb -s {self.gemini_device} shell am force-stop com.google.android.googlequicksearchbox"
        subprocess.run(command, shell=True)
        print(f"Terminated Gemini!")
    
    def logger(self):
        assert self._adb.is_device_online(self.gemini_device), "Devices NOT online!"
        assert os.path.isdir(self.log_folder), f"log folder {self.log_folder} DOES NOT EXIST!"
        log_files = {}
        if len(self.log_procs) > 0:
            print("----Stopped & Dumped Logging----")
            # Log image query file
            self.__pull_s25_query_image()
            if len(os.listdir(self.log_folder)) > 0:
                for file_name in os.listdir(self.log_folder):
                    if "app_screenshot" in file_name:
                        shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "app_screenshot.png"))
                        log_files["app_screenshot_path"] = os.path.join(self.log_folder, "app_screenshot.png")
                        break
                    elif "screen.png" in file_name:
                        shutil.move(os.path.join(self.log_folder, file_name), os.path.join(self.log_folder, "device_view_image.png"))
                        log_files["device_view_image_path"] = os.path.join(self.log_folder, "device_view_image.png")
            
            # Kill log dump processes
            while len(self.log_procs) > 0:
                log_proc = self.log_procs.pop()

                os.killpg(os.getpgid(log_proc.pid), signal.SIGTERM)
                try:
                    log_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(log_proc.pid), signal.SIGKILL)
                    log_proc.wait()
        
        else:
            print("----Started Logging----")
            #Start log dump processes
            for device_id in [self.gemini_device]:
                subprocess.run(["adb", "-s", device_id, "logcat", "-c"], check=True)
                log_file_name = "s25_gemini_live_log.txt"
                log_proc = subprocess.Popen(
                    ["timeout", "--kill-after=5", "180", "adb", "-s", device_id, "logcat",],
                    stdout=open(os.path.join(self.log_folder, log_file_name), "w"),
                    stderr=subprocess.STDOUT,
                    preexec_fn = os.setsid
                )
                self.log_procs.append(log_proc)

            self.__clear_s25_image_folder()
    
    def __pull_s25_query_image(self, remote_path="/sdcard/Pictures/screen.png"):
        command = f"adb -s {self.gemini_device} shell screencap {remote_path}" # click image
        subprocess.run(command, shell=True)
        print(command)

        command = (
            f"adb -s {self.gemini_device} pull"
            f' {remote_path}'
            f" {self.log_folder}"
        )
        subprocess.run(command, shell=True)
        print(command)

        self.__clear_s25_image_folder(remote_path )
    
    def __clear_s25_image_folder(self, remote_path="/sdcard/Pictures/screen.png"):
        command = (
            f"adb -s {self.gemini_device} shell rm"
            f' {remote_path}'
        )
        subprocess.run(command, shell=True)
        print(command)

