from agent_testers.device_managers.device_manager import DeviceManagerTemplate

class DeviceManager(DeviceManagerTemplate):
    def __init__(self, log_dump_folder : str = "", config : dict = None):
        self.log_folder = log_dump_folder
    
    @staticmethod
    def get_device_names():
        return [] # same order as the order of device ids in init
    
    def invoke(self, q_info):
        pass
    
    def terminate(self):
        pass
