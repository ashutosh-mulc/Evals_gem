from datetime import datetime
import re
import numpy as np
class LogFile:
    def __init__(self, path: str):
        self.path = path
        self.log = []
        with open(self.path, 'r', encoding='utf-8', errors = 'replace') as f:
            for idx, line in enumerate(f.readlines()):
                log_line_split = list(filter(lambda x: x != "", line.strip().split(' ',)))
                log_line = dict()
                try:
                    log_line["date"] = log_line_split[0]
                    log_line["time"] = datetime.strptime(log_line_split[1], "%H:%M:%S.%f").time()
                    log_line["processId"] = int(log_line_split[2])
                    log_line["threadId"] = int(log_line_split[3])
                    log_line["logType"] = log_line_split[4]
                    log_line["logStr"] = ' '.join(log_line_split[5:])

                    self.log.append(log_line)
                except Exception as e:
                    # print(e)
                    # print(log_line_split)
                    continue
        # print(self.log)
    
    def search_all(self, key: str):
        ans = []
        for x in self.log:
            if key in x['logStr']:
                ans.append(x)
        return ans

def check_gemini_audio_invoke(companion_log: LogFile):
    # print(f"LogSize:{len(companion_log.log)}")
    error_log = "GC_AgentRequestHandlerI: Received ERROR state, errorType: GENERIC_ERROR"
    invoke_log = re.compile(
                    r'^GC_AgentRequestHandlerI: Received agent response with updated state: '
                    r'ArResponse\(state=LISTENING, audioLevel=\d+(?:\.\d+)?'
                )
    start_log = "GC_AgentRequestHandlerI: #agent# startInternal CONVERSATION_MODE_START"
    relevant_logs = companion_log.search_all("GC_AgentRequestHandlerI")

    ret = False; meta_info = {}
    for log in relevant_logs:
        if error_log in log['logStr']:
            meta_info['failure_time'] = log['time']
            return False, relevant_logs, meta_info
        elif re.match(invoke_log, log['logStr']):
            meta_info['success_time'] = log['time']
            ret = True
        elif start_log in log['logStr']:
            meta_info['start_time'] = log['time']
    
    return ret, relevant_logs, meta_info

def check_gemini_video_invoke(companion_log: LogFile):
    audio_invoke, relevant_logs, meta_info = check_gemini_audio_invoke(companion_log)
    relevant_logs += companion_log.search_all("CameraManagerGlobal")
    # video_invoke_log = "GC_AgentRequestHandlerI: #agent# sendRequestIfConnectionEstablished CAMERA_STATE_TOGGLE"
    camera_invoke_log = re.compile(r"CameraManagerGlobal: Camera \d+ facing CAMERA_FACING_BACK state now CAMERA_STATE_ACTIVE for client com\.google\.android\.googlequicksearchbox API Level \d+ User Id \d+Device Id \d+")
    tc_pass = [True, False]
    if audio_invoke:
        for log in relevant_logs:
            # if (video_invoke_log in log['logStr'] and log['time'] >= meta_info['start_time']):
            #     meta_info['video_toggle_time'] = log['time']
            #     tc_pass [0] = True
            if (re.match(camera_invoke_log, log['logStr']) and log['time'] >= meta_info['start_time']):
                meta_info['camera_invoke_time'] = log['time']
                tc_pass [1] = True
    return bool(np.all(tc_pass)), relevant_logs, meta_info


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m automator.report_generator.utils.log_analyser <logcat_file>")
        sys.exit(1)
    l = LogFile(sys.argv[1])
    print(check_gemini_video_invoke(l)[0], check_gemini_audio_invoke(l)[0])

