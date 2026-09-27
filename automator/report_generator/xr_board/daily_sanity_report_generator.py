import json
import numpy as np
from typing import Dict, List, Any
import re
import subprocess, os
from datetime import datetime

from automator.report_generator.utils.log_analyser import LogFile, check_gemini_audio_invoke, check_gemini_video_invoke
from utils.file_utils import *
# ------------------------------------------------------
# JSON CONFIGURATION
# ------------------------------------------------------
class JSONConfig:
    def __init__(self):
        self.json_dict = {
            "testId": "", 
            "userId": "rachit.a",
            "kpiType": "jinju-gemini-live-sanity",
            "companionPair": "",
            "testResult":"", # e.g. pass or fail
            "device": {
                "deviceId": "",
                "hwid": "",
                "binaryVersion": "",
                "modelName": "",
                "mergeBuildId": "",
                "pairedDevice": {
                    "deviceId": "",
                    "modelName": "",
                    "binaryVersion": "",
                    "glassCoreVersion": "",
                    "companionApkVersion": "",
                    "glassCoreExtensionVersion": "",
                    "agsaVersion": ""
                    }
            },
            "testInformation": {
                "datasets": "Sanity_QA_VQA_HQA_30",
                "vlmJudgeName": "MiMo-VL-7B-RL"
            },
            "startTime": "", 
            "testState": "Completed", 
            "isAutomation": True,
            "kpiResult": {
                "data": [
                    {

                    }
                ],
            },
            "kpiRaw": {
                "repeatedResultsOnFailureCases": {
                "audioQaPerQuerySession": [],
                "vqaPerQuerySession": [],
                "hallucinationPerQuerySession": [],
                "legend": [
                    "PASS in Iteration 1",
                    "PASS in Iteration 2",
                    "PASS in Iteration 3",
                    "Failed in all 3 iterations"
                ]
                },
                "data": [
                    {
                
                    }
                ]
            }
        }

    def __is_camel_case(self, key: str) -> bool:
        CAMEL_CASE_RE = re.compile(r'^[a-z][a-zA-Z0-9]*$')
        return bool(CAMEL_CASE_RE.match(key))

    def __to_camel_case(self, key: str) -> str:
        """
        Convert a string with spaces, snake_case, or mixed case
        into camelCase.
        """
        # Replace spaces and underscores with a single space
        key = re.sub(r'[_\s]+', ' ', key.strip())

        # Split into words
        parts = key.split(' ')

        # Lowercase first word, capitalize the rest
        return parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])


    def __camel_case_keys(self, obj: Any) -> Any:
        """
        Recursively convert all dictionary keys to camelCase.
        Works for nested dicts and lists.
        """
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                key_str = str(k)
                new_key = key_str if self.__is_camel_case(key_str) else self.__to_camel_case(key_str)
                new_dict[new_key] = self.__camel_case_keys(v)
            return new_dict
        elif isinstance(obj, list):
            return [self.__camel_case_keys(item) for item in obj]
        else:
            return obj

    def populate_json(self, kpi_result_data: List, kpi_list_data: Dict, failure_counts: Dict) -> Dict:
        self.json_dict["kpiRaw"]["data"] = sorted(kpi_result_data, key = lambda x: int(x["iteration"]))
        self.json_dict["kpiResult"]["data"] = kpi_list_data

        total_count = 0
        is_pass = True

        kpi_name_to_failure_log_name = {"AudioQA-per-query":"audioQaPerQuerySession", "VQA-per-query": "vqaPerQuerySession", "Hallucination-per-query": "hallucinationPerQuerySession"}
        for kpi_name in failure_counts:
            failure_log_name = kpi_name_to_failure_log_name[kpi_name]
            self.json_dict["kpiRaw"]["repeatedResultsOnFailureCases"][failure_log_name] = failure_counts[kpi_name]

            is_pass = is_pass and sum(failure_counts[kpi_name][1:]) == 0
            total_count = max(total_count, len(failure_counts[kpi_name]))

        self.json_dict["kpiRaw"]["repeatedResultsOnFailureCases"]["legend"] = [f"PASS in iteration {i}" for i in range(1, total_count)] + [f"Failed in all {total_count - 1} iterations"]            
        self.json_dict["testResult"] = "pass" if is_pass else "fail"
        self.json_dict = self.__camel_case_keys(self.json_dict)



# ------------------------------------------------------
# KPI CONFIGURATION
# ------------------------------------------------------
class KPIConfig:
    def __init__(self):
        self.eval_type_to_kpi_id = {"QA_TASK": 1, "Visual_QA_TASK": 2, "Hallucination_TASK": 3} 
        self.kpi_list = [
            {
                "Experiment": "Gemini-invoke",
                "Success Ratio": 0.75,
                "Total": 0,
                "Pass": 0,
                "Fail": 0,
                "Rating Mean": None,
                "Rating Std": None,
                "Latency Mean": None,
                "Latency Std": None,
                "Entropy Mean": None,
                "Entropy Std": None,
                "Session Duration": None,
                "Remarks": "", # Issues faced
                "Related Issues": "" #PLMs raised
            },
            {
                "Experiment": "AudioQA-per-query", #e.g. "audio QA: per-query session",
                "Success Ratio": 0.0, # It is expressed as a value between 0 and 1, not a percentage. It means Pass/Total.
                "Total": 0,  # Question number. Must match the number of PASS+FAIL.
                "Pass": 0, # It refers to the number of passes in the first iteration. (It does not refer to the maximum number of repetitions.) PASS means that the rating after manual verification is 3 or higher.
                "Fail": 0, # It means the number of ratings that received N/A, 0, 1, or 2 points in the first iteration.
                "Rating Mean": 0.0, # Average rating of each of the 10 questions. NULL values ​​are treated as 0 points
                "Rating Std": 0.0, # Standard deviation of rating of each of the 10 questions. NULL values ​​are treated as 0 points
                "Latency Mean": 0.0, # Average Response time
                "Latency Std": 0.0, # Standard Deviation Response time
                "Entropy Mean": 0.0, # Average Entropy
                "Entropy Std": 0.0, # Standard Deviation Entropy
                "Session Duration": None, # Used for long-lived sessions. It is null in this experiment.
                "Remarks": "", # Issues faced
                "Related Issues": "" #PLMs raised
            },
            {
                "Experiment": "VQA-per-query", #e.g. "audio QA: per-query session",
                "Success Ratio": 0.0, # It is expressed as a value between 0 and 1, not a percentage. It means Pass/Total.
                "Total": 0,  # Question number. Must match the number of PASS+FAIL.
                "Pass": 0, # It refers to the number of passes in the first iteration. (It does not refer to the maximum number of repetitions.) PASS means that the rating after manual verification is 3 or higher.
                "Fail": 0, # It means the number of ratings that received N/A, 0, 1, or 2 points in the first iteration.
                "Rating Mean": 0.0, # Average rating of each of the 10 questions. NULL values ​​are treated as 0 points
                "Rating Std": 0.0, # Standard deviation of rating of each of the 10 questions. NULL values ​​are treated as 0 points
                "Latency Mean": 0.0, # Average Response time
                "Latency Std": 0.0, # Standard Deviation Response time
                "Entropy Mean": 0.0, # Average Entropy
                "Entropy Std": 0.0, # Standard Deviation Entropy
                "Session Duration": None, # Used for long-lived sessions. It is null in this experiment.
                "Remarks": "", # Issues faced
                "Related Issues": "" #PLMs raised
            },
            {
                "Experiment": "Hallucination-per-query", #e.g. "audio QA: per-query session",
                "Success Ratio": 0.0, # It is expressed as a value between 0 and 1, not a percentage. It means Pass/Total.
                "Total": 0,  # Question number. Must match the number of PASS+FAIL.
                "Pass": 0, # It refers to the number of passes in the first iteration. (It does not refer to the maximum number of repetitions.) PASS means that the rating after manual verification is 3 or higher.
                "Fail": 0, # It means the number of ratings that received N/A, 0, 1, or 2 points in the first iteration.
                "Rating Mean": 0.0, # Average rating of each of the 10 questions. NULL values ​​are treated as 0 points
                "Rating Std": 0.0, # Standard deviation of rating of each of the 10 questions. NULL values ​​are treated as 0 points
                "Latency Mean": 0.0, # Average Response time
                "Latency Std": 0.0, # Standard Deviation Response time
                "Entropy Mean": 0.0, # Average Entropy
                "Entropy Std": 0.0, # Standard Deviation Entropy
                "Session Duration": None, # Used for long-lived sessions. It is null in this experiment.
                "Remarks": "", # Issues faced
                "Related Issues": "" #PLMs raised
            },
        ]


# ------------------------------------------------------
# FILE READER
# ------------------------------------------------------
class EvalFileReader:
    def __init__(self, file_path: str, ignore_first: bool = True):
        self.file_path = file_path
        self.ignore_first = ignore_first

    def read(self) -> Dict | List:
        with open(self.file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        header = json.loads(lines[0])
        samples = [json.loads(line) for line in lines[1:]]
        return header, samples


# ------------------------------------------------------
# KPI AGGREGATOR
# ------------------------------------------------------
class KPIAggregator:
    def __init__(self, config: KPIConfig, json_config: JSONConfig):
        self.config = config
        self.json_config = json_config
        self.kpi_result_data = []
        self.failure_counts = {}
        self.cumulative_metrics = [dict() for _ in range(len(config.kpi_list))]
        self.num_evaluations = -1  
    
    @staticmethod
    def _sanitize_item(item: Dict) -> Dict:
        filtered_list = item.copy()
        for filtered in filtered_list:
            filtered.pop("image", None)
            filtered.pop("audio", None)
            filtered.pop("screen", None)
        return filtered_list

    def consume_sample(self, q_data: List):
        assert self.num_evaluations > 0, "Number of evaluations should be greater than 0"

        filtered_list = self._sanitize_item(q_data)
        filtered_list = sorted(filtered_list, key = lambda x: int(x["iteration"]))
        filtered_item = filtered_list[0]
        # print('filterd_item', filtered_item)

        task_type = filtered_item["eval_type"]
        question_type = filtered_item.get("question_type", "")
        rating = float(filtered_item["rating"])
        response_time = float(filtered_item["response_time"]) if filtered_item["response_time"] is not None else None
        entropy = filtered_item["meta_info"]["entropy_metrics"]["entropy"]

        if "audio_raw_path_copy" in filtered_item:
            base_audio_raw_path = filtered_item["audio_raw_path_copy"]
        else:
            base_audio_raw_path = filtered_item["meta_info"]["audio_raw_path"]
        companion_log_file = base_audio_raw_path.replace("audio","companion_log").replace("wav", "txt")
        companion_log = LogFile(companion_log_file)
        self.config.kpi_list[0]["Total"] += 1
        if task_type == "QA_TASK":
            print(check_gemini_audio_invoke(companion_log))
            self.config.kpi_list[0]["Pass"] += check_gemini_audio_invoke(companion_log)[0]
            self.config.kpi_list[0]["Fail"] += not check_gemini_audio_invoke(companion_log)[0]
        else:
            self.config.kpi_list[0]["Pass"] += check_gemini_video_invoke(companion_log)[0]
            self.config.kpi_list[0]["Fail"] += not check_gemini_video_invoke(companion_log)[0]
        print(check_gemini_audio_invoke(companion_log)[0], check_gemini_video_invoke(companion_log)[0])

        kpi_id = self.config.eval_type_to_kpi_id[task_type]; kpi_name = self.config.kpi_list[kpi_id]["Experiment"]
        self.config.kpi_list[kpi_id]["Total"] += 1
        self.config.kpi_list[kpi_id]["Pass"] += rating >= 3
        self.config.kpi_list[kpi_id]["Fail"] += rating < 3
        self.cumulative_metrics[kpi_id]["Rating"] = self.cumulative_metrics[kpi_id].get("Rating", [])+ [rating]
        self.cumulative_metrics[kpi_id]["Entropy"] = self.cumulative_metrics[kpi_id].get("Entropy", []) + [entropy]
        if response_time: self.cumulative_metrics[kpi_id]["Latency"] = self.cumulative_metrics[kpi_id].get("Latency", []) + [response_time]

        self.failure_counts[kpi_name] = self.failure_counts.get(kpi_name, [0] * self.num_evaluations)
        for itr, q_iter in enumerate(filtered_list):
            iter_rating = float(q_iter["rating"])
            if iter_rating >= 3:
                self.failure_counts[kpi_name][itr] += 1
            filtered_list[itr]["image_path"] = filtered_list[itr]["meta_info"]["image_path"];filtered_list[itr]["meta_info"].pop("image_path")
            filtered_list[itr]["audioPathBeforeDenoising"] = filtered_list[itr]["meta_info"].get("audio_decoded_path", "");filtered_list[itr]["meta_info"].pop("audio_decoded_path") if "audio_decoded_path" in filtered_list[itr]["meta_info"] else ""
            filtered_list[itr]["audioPathDenoised"] = filtered_list[itr]["meta_info"].get("audio_denoised_path", "");filtered_list[itr]["meta_info"].pop("audio_denoised_path") if "audio_denoised_path" in filtered_list[itr]["meta_info"] else ""
            filtered_list[itr]["response"] = filtered_list[itr]["meta_info"]["response_path"];filtered_list[itr]["meta_info"].pop("response_path")
            filtered_list[itr]["screenPath"] =  filtered_list[itr]["meta_info"].get("device_view_image_path", "")
            filtered_list[itr]["eval_type"] = kpi_name
            filtered_list[itr]["meta_info"]["responseTime"] = filtered_list[itr]["response_time"]
            filtered_list[itr]["meta_info"]["answerAudioDuration"] = filtered_list[itr]["response_duration"]
            filtered_list[itr]["manualVerification"] = filtered_list[itr].get("manual_verification", False)
            if "audio_raw_path_copy" in filtered_list[itr]:
                filtered_list[itr].pop("audio_raw_path_copy")

        self.kpi_result_data.extend(filtered_list)


    def finalize(self):
        # print(self.cumulative_metrics)
        for kpi_id, kpi_item in enumerate(self.config.kpi_list):
            if kpi_item["Total"] > 0: kpi_item["Success Ratio"] = round(kpi_item["Pass"] / kpi_item["Total"], 2)
            else: kpi_item["Success Ratio"] =  None

            if "Rating" in self.cumulative_metrics[kpi_id]:
                kpi_item["Rating Mean"] = round(np.mean(self.cumulative_metrics[kpi_id]["Rating"]), 2)
                kpi_item["Rating Std"] = round(np.std(self.cumulative_metrics[kpi_id]["Rating"]), 2)

            if "Entropy" in self.cumulative_metrics[kpi_id]:
                kpi_item["Entropy Mean"] = round(np.mean(self.cumulative_metrics[kpi_id]["Entropy"]), 5)
                kpi_item["Entropy Std"] = round(np.std(self.cumulative_metrics[kpi_id]["Entropy"]), 5)
            
            if "Latency" in self.cumulative_metrics[kpi_id] and len(self.cumulative_metrics[kpi_id]["Latency"]) > 0: 
                kpi_item["Latency Mean"] = round(np.mean(self.cumulative_metrics[kpi_id]["Latency"]), 2)
                kpi_item["Latency Std"] = round(np.std(self.cumulative_metrics[kpi_id]["Latency"]), 2)
            else:
                kpi_item["Latency Mean"] = None
                kpi_item["Latency Std"] = None

            if kpi_item["Total"] > 0 and kpi_item["Experiment"] != "Gemini-invoke":
                self.failure_counts[kpi_item["Experiment"]].append(kpi_item["Total"] - sum(self.failure_counts[kpi_item["Experiment"]]))
        
        self.json_config.populate_json(self.kpi_result_data, self.config.kpi_list, self.failure_counts)


# ------------------------------------------------------
# REPORT BUILDER
# ------------------------------------------------------
class KPIReportBuilder:
    def __init__(self, config: KPIConfig, json_config: JSONConfig):
        self.json_config = json_config
        self.aggregator = KPIAggregator(config, json_config)
        self.num_evaluations = -1
        
    def check_connection(self, jinju_device: str, mobile_device: str) -> bool:
        devices_list = subprocess.check_output(
                        ["adb", "devices"],
                        text=True
                    ).strip()
        
        if jinju_device in devices_list and mobile_device in devices_list:
            return True

        return False
    
    def get_current_time(self):
        from datetime import datetime, timezone
        current_time_utc = datetime.now(timezone.utc)
        final_format_strftime = current_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        return final_format_strftime
        
    def populate_device_info(self, data_config: Dict):
        
        jinju_device = data_config["devices"]["jinju_device_id"]
        mobile_device = data_config["devices"]["s25_device_id"]
        self.num_evaluations = data_config["automator"]["num_evaluations"]

        isDeviceConnected = self.check_connection(jinju_device, mobile_device)

        assert isDeviceConnected, "Devices used for evaluation are not connected"

        binaryVersion = subprocess.check_output(
                        ["adb", "-s", jinju_device, "shell", "getprop", "ro.product.build.version.incremental"],
                        text=True
                    ).strip()
        
        modelName = subprocess.check_output(
                        ["adb", "-s", jinju_device, "shell", "getprop", "ro.product.model"],
                        text=True
                    ).strip()
        
        hwid = subprocess.check_output(
                        ["adb", "-s", jinju_device, "shell", "getprop", "ro.revision"],
                        text=True
                    ).strip()
        
        jinjuMergeBuildId = subprocess.check_output(
                        ["adb", "-s", jinju_device, "shell", "getprop", "ro.omc.build.id"],
                        text=True,
                    ).strip()
        
        pairedDevice = subprocess.check_output(
                        ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.model"],
                        text=True
                    ).strip()
        
        mobileBinaryVersion = subprocess.check_output(
                        ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.build.version.incremental"],
                        text=True
                    ).strip()
        
        glasscoreVersion = subprocess.run(
                        f"adb -s {mobile_device} shell dumpsys package com.google.android.glasses.core | grep versionName=release",
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True,
                        check=True
                    ).stdout.strip().split('=')[1]
        
        companionApkVersion = subprocess.run(
                        f"adb -s {mobile_device} shell dumpsys package com.samsung.wearable.armanager | grep versionName",
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True,
                        check=True
                    ).stdout.strip().split('=')[1]
        
        try:
            glasscoreExtensionVersion = subprocess.run(
                            f"adb -s {mobile_device} shell dumpsys package com.samsung.android.glasses.core.ext | grep versionName",
                            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            check=True
                        ).stdout.strip().split('=')[1]
        except:
            glasscoreExtensionVersion = ""

        agsaVersion = subprocess.run(
                        f"adb -s {mobile_device} shell dumpsys package com.google.android.googlequicksearchbox | grep versionName",
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True,
                        check=True
                    ).stdout.strip().split('\n')[-1].strip().split('=')[1]

        meta_info = {
            "testId": datetime.now().strftime("%Y%m%d%H%M%S%f"),                                    
            "userId": data_config["automator"]["xr_board"]["user_id"],                                    # tester or uploader id : e.g. sy0514.jung
            "kpiType": data_config["automator"]["xr_board"]["kpi_type"],                                  # e.g. pass or fail
            "device": {
                "deviceId": jinju_device,
                "hwid": hwid,
                "binaryVersion": binaryVersion,
                "modelName": modelName,
                "mergeBuildId": jinjuMergeBuildId,
                "pairedDevice": {
                    "deviceId": mobile_device,
                    "modelName": pairedDevice,
                    "binaryVersion": mobileBinaryVersion,
                    "glassCoreVersion": glasscoreVersion,
                    "companionApkVersion": companionApkVersion,
                    "glassCoreExtensionVersion": glasscoreExtensionVersion,
                    "agsaVersion": agsaVersion
                    }
            },
            "testInformation": {
                "datasets": data_config["automator"]["xr_board"]["dataset_name"],
                "vlmJudgeName": data_config["automator"]["xr_board"]["judge_name"]
            },
            "startTime": self.get_current_time(),
            "testState": "Completed",
            "testResult":"pass",         
        }

        for key in meta_info:
            self.json_config.json_dict[key] = meta_info[key]


    def build(self, eval_data: List):
        self.aggregator.num_evaluations = self.num_evaluations
        for q_data in eval_data:
            self.aggregator.consume_sample(q_data = q_data)
        self.aggregator.finalize()

    
    def get_report(self) -> Dict:
        return self.json_config.json_dict
    
    def save(self, dump_path: str):
        # print(self.json_config.json_dict)
        with open(dump_path, 'w') as fp:
            fp.write(json.dumps(self.json_config.json_dict, indent=2))



# ------------------------------------------------------
# MAIN PIPELINE
# ------------------------------------------------------
def XR_Board_report_generator(eval_json_path, config_path, isVisualize=False):
    print("Eval Report Path:", eval_json_path)
    dump_path = eval_json_path.rsplit('.',1)[0] + "_for_XRBoard.json"
    data_config = JSONFileManager.load_file(config_path)


    config = KPIConfig()
    json_config = JSONConfig()
    reader = EvalFileReader(eval_json_path)
    report_builder = KPIReportBuilder(config, json_config)
    report_builder.populate_device_info(data_config)

    _, eval_data = reader.read()

    report_builder.build(eval_data)
    report_builder.save(dump_path)


    ### For Visualisation ###
    if isVisualize:
        final_report = report_builder.get_report()
        final_report.pop("kpiResult")   # For visualisation removed "kpiResult" data
        print(json.dumps(final_report, indent=2))
    ### For Visualisation ###

    return dump_path


if __name__ == "__main__":
    eval_json_path = "/home/test/Shouvik/work_2026/Gemini_Live_Evaluation/Evaluation_Framework/data/vqa_report_sample.jsonl"
    XR_Board_report_generator(eval_json_path)
