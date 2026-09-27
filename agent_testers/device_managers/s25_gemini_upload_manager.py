from agent_testers.device_managers.device_manager import DeviceManagerTemplate
from utils.adb_client import AdbClient
import subprocess, os, shutil, time, signal

class DeviceManager(DeviceManagerTemplate):
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
    
    def _upload_image(self, image_path: str, eval_id: str) -> None:
        print("----Uploading image to S25----")
        command = f'adb -s {self.gemini_device} shell "rm -rf /sdcard/DCIM/Camera/*"'
        print(command)
        subprocess.run(command, shell=True)

        image_name = f"temp_{eval_id}.png"
        command = f"adb -s {self.gemini_device} push {image_path} /sdcard/DCIM/Camera/{image_name}"
        print(command)
        subprocess.run(command, shell=True)

        command = f"adb -s {self.gemini_device} shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/DCIM/Camera/{image_name}"
        print(command)
        subprocess.run(command, shell=True)
        time.sleep(2)

        self._click_phone(self.gemini_device, 75, 2103) # click on +
        time.sleep(1)
        self._click_phone(self.gemini_device, 240, 1640) # click on camera
        time.sleep(1)
        self._click_phone(self.gemini_device, 164, 1769) # select first image
        time.sleep(1)
        self._click_phone(self.gemini_device, 887, 2131) # click on 'Done'
        time.sleep(10) # wait for image to upload
        self._click_phone(self.gemini_device, 90, 1968) # click on 'Ask Gemini' to activate input
        time.sleep(0.5) # wait for image to upload
        command = ["adb", "-s", f"{self.gemini_device}", "shell", "input", "text", "Understand%sthe%scontent%sin%sthe%simage,%sbut%sdont%ssay%sanything"]
        subprocess.run(command, shell = False)
        time.sleep(2)

        self._click_phone(self.gemini_device, 976, 2104) # upload the image
        time.sleep(100) # wait for the gemini analysis

    
    def invoke(self, q_info):
        assert self._adb.is_device_online(self.gemini_device), f"Device {self.gemini_device} NOT online!"
        self._adb.unlock(self.gemini_device)

        invoke_type = q_info["eval_type"]
        print("----Invoking S25 Gemini Live----")
        command = f"adb -s {self.gemini_device} shell am start -n \
            com.google.android.apps.bard/com.google.android.apps.bard.shellapp.BardEntryPointActivity" # starting gemini on phone
        subprocess.run(command, shell=True)
        time.sleep(2)

        image_path  = q_info["metadata"]["image_path"]
        eval_id = q_info["eval_id"]
        
        if invoke_type in ["Visual_QA_TASK", "Hallucination_TASK"]: #switch off camera if not a visual question
            self._upload_image(image_path, eval_id)
            time.sleep(2)
            print("S25 Gemini invoked in video only mode!")
        
        self._click_phone(self.gemini_device, 976, 2104)  # Taps on Gemini Live

        time.sleep(5) # Gemini live takes time to open up

    
    def terminate(self):
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
                    if "screen.png" in file_name:
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
    
    def __pull_s25_query_image(self,):
        command = f"adb -s {self.gemini_device} shell screencap /sdcard/Pictures/screen.png" # click image
        subprocess.run(command, shell=True)
        print(command)

        command = (
            f"adb -s {self.gemini_device} pull"
            f' "/sdcard/Pictures/screen.png"'
            f" {self.log_folder}"
        )
        subprocess.run(command, shell=True)
        print(command)

        self.__clear_s25_image_folder()
    
    def __clear_s25_image_folder(self,):
        command = (
            f"adb -s {self.gemini_device} shell rm"
            f' "/sdcard/Pictures/screen.png"'
        )
        subprocess.run(command, shell=True)
        print(command)