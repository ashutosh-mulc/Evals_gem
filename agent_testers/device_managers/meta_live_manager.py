from agent_testers.device_managers.device_manager import DeviceManagerTemplate
from agent_testers.agent_tester import ARAPManager
from agent_testers.robopod_manager import RobopodManager
from utils.adb_client import AdbClient
import subprocess, os, shutil, time, signal, logging

class DeviceManager(DeviceManagerTemplate):
    def __init__(self, arap_config : dict, s25_device_id: str, log_dump_folder : str | None = "", config : dict = None):
        self._adb = AdbClient()
        if arap_config["use_robohead"]:
    '''
        Please note that the automated setup of Meta is unreliable as Meta might detect that its not a human speaking and might not respond.
    '''
    def __init__(self, arap_config : dict, s25_device_id: str, log_dump_folder : str | None = "", config : dict = None):
        if arap_config["use_robohead"]:
            self.arap_device = RobopodManager(arap_config["robopod_url"])
        elif arap_config["devices"]:
            arap_device = arap_config["devices"][0]
            self.arap_device = ARAPManager(arap_device)
        else:
            raise RuntimeWarning("No recording devices found!")
        
        self.meta_device = s25_device_id
        try:
            subprocess.run(
                        f"adb -s {self.meta_device} shell dumpsys package com.facebook.stella | grep versionName",
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True,
                        check=True
                    ).stdout.strip().split('\n')[-1].strip().split('=')[1]
        except:
            raise RuntimeError(f"Meta Device {self.meta_device} does not have Meta App installed!")
        
        # Invoke and terminate audio
        self.invoke_audio = "agent_testers/assets/invoke.wav"
        self.terminate_audio = "agent_testers/assets/close_session.wav"
        if not(os.path.exists(self.invoke_audio) and  os.path.exists(self.terminate_audio)):
            raise FileNotFoundError(f"{self.invoke_audio} or {self.terminate_audio} is missing!")

        self.log_procs = []
        self.log_folder = log_dump_folder
        print(f"Make sure {arap_config['devices'][0]}, {self.meta_device} is connected!")
    
    @staticmethod
    def get_device_names():
        return ["arap", "s25_device_id"] # same order as the order of device ids in init
    
    def invoke(self, q_info):
        assert self._adb.is_device_online(self.meta_device), f"Device {self.meta_device} NOT online!"

        self.arap_device.play_audio(self.invoke_audio)
        print("Started Meta Session!"); logging.info("Started meta session!")
        time.sleep(3)
    
    def terminate(self):
        assert self._adb.is_device_online(self.meta_device), f"Device {self.meta_device} NOT online!"

        self.arap_device.play_audio(self.terminate_audio)
        print("Terminated Meta Session!"); logging.info("Terminated meta session!")
        time.sleep(3)
    
    def logger(self):
        assert self._adb.is_device_online(self.meta_device), "Devices NOT online!"
            print("----Stopped & Dumped Logging----")
            
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
            for device_id in [self.meta_device]:
                subprocess.run(["adb", "-s", device_id, "logcat", "-c"], check=True)
                log_file_name = "meta_app_log.txt"
                log_proc = subprocess.Popen(
                    ["timeout", "--kill-after=5", "50", "adb", "-s", device_id, "logcat",],
                    stdout=open(os.path.join(self.log_folder, log_file_name), "w"),
                    stderr=subprocess.STDOUT,
                    preexec_fn = os.setsid
                )
                self.log_procs.append(log_proc)