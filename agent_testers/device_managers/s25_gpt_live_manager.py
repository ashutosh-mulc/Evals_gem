from agent_testers.device_managers.device_manager import DeviceManagerTemplate
from utils.adb_client import AdbClient
import subprocess, os, shutil, time, signal

class DeviceManager(DeviceManagerTemplate):
    def __init__(self, gpt_device_id : str, log_dump_folder : str = "", config : dict = None):
        self.gpt_device = gpt_device_id
        self.log_procs = []
        self.log_folder = log_dump_folder
        self._adb = AdbClient()
        print(f"Make sure {self.gpt_device} is a rooted device and NULL Keyboard is installed on device!")
    
    @staticmethod
    def get_device_names():
        return ["s25_device_id"] # same order as the order of device ids in init
    
    def invoke(self, q_info):
        assert self._adb.is_device_online(self.gpt_device), f"Device {self.gpt_device} NOT online!"
        self._adb.unlock(self.gpt_device)

        invoke_type = q_info["eval_type"]
        print("----Invoking S25 GPT Live----")
        command = f"adb -s {self.gpt_device} shell am start -n \
            com.openai.chatgpt/.MainActivity" # starting ChatGPT on phone
        subprocess.run(command, shell=True)
        time.sleep(5)
        self._click_phone(self.gpt_device, 987, 2101)  # Taps on GPT Live
        time.sleep(10) # GPT live takes time to open up
        if invoke_type in ["Visual_QA_TASK", "Hallucination_TASK"]: #switch on camera for a visual question
            self._click_phone(self.gpt_device, 585, 2107) # Open Video
            time.sleep(2)
            print("S25 GPT invoked in video only mode!")
        else:
            print("S25 GPT invoked in audio only mode!")

    
    def terminate(self):
        command = f"adb -s {self.gpt_device} shell am force-stop com.openai.chatgpt"
        subprocess.run(command, shell=True)
        print(f"Terminated ChatGPT!")
    
    def logger(self):
        assert self._adb.is_device_online(self.gpt_device), "Devices NOT online!"
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
            for device_id in [self.gpt_device]:
                subprocess.run(["adb", "-s", device_id, "logcat", "-c"], check=True)
                log_file_name = "s25_gpt_live_log.txt"
                log_proc = subprocess.Popen(
                    ["timeout", "--kill-after=5", "50", "adb", "-s", device_id, "logcat",],
                    stdout=open(os.path.join(self.log_folder, log_file_name), "w"),
                    stderr=subprocess.STDOUT,
                    preexec_fn = os.setsid
                )
                self.log_procs.append(log_proc)

            self.__clear_s25_image_folder()
    
    def __pull_s25_query_image(self,):
        command = f"adb -s {self.gpt_device} shell screencap /sdcard/Pictures/screen.png" # click image
        subprocess.run(command, shell=True)
        print(command)

        command = (
            f"adb -s {self.gpt_device} pull"
            f' "/sdcard/Pictures/screen.png"'
            f" {self.log_folder}"
        )
        subprocess.run(command, shell=True)
        print(command)

        self.__clear_s25_image_folder()
    
    def __clear_s25_image_folder(self,):
        command = (
            f"adb -s {self.gpt_device} shell rm"
            f' "/sdcard/Pictures/screen.png"'
        )
        subprocess.run(command, shell=True)
        print(command)
