import sys
import json
import numpy as np
from typing import Dict, List, Any
import re
import subprocess, os
from datetime import datetime
from copy import deepcopy

from automator.report_generator.utils.log_analyser import LogFile, check_gemini_audio_invoke, check_gemini_video_invoke
from utils.file_utils import *
# ------------------------------------------------------
# JSON CONFIGURATION
# ------------------------------------------------------
class JSONConfig:
    def __init__(self):
        self.kpi_type_list = ["jinju-gemini-live-kpi-audioqa", "jinju-gemini-live-kpi-vqa", "jinju-gemini-live-kpi-hallucination"]
        self.eval_type_to_kpi_id = {"AudioQA-per-query": 1, "VQA-per-query": 2, "Hallucination-per-query": 3} 
        self.json_dict = {
            "testId": "", 
            "userId": "rachit.a",
            "kpiType": "jinju-gemini-live-KPI-VQA", # jinju-gemini-live-KPI-audioQA, jinju-gemini-live-KPI-hallucination
            "companionPair": "",
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
                "datasets": "VQA_1.0.0", # QA_1.0.0, HQA_1.0.0
                "vlmJudgeName": "MiMo-VL-7B-RL"
            },
            "startTime": "", 
            "testState": "", 
            "isAutomation": True,
            "kpiResult": {
                "data": [
                    {

                    }
                ],
            },
            "kpiRaw": {
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


    def populate_json(self, raw_data: List, kpi_result: Dict) -> Dict:
        self.json_dict["kpiRaw"]["data"] = sorted(raw_data, key = lambda x: int(x["iteration"]))
        self.json_dict["kpiResult"]["data"] = kpi_result

        eval_type = raw_data[0]["eval_type"]
        test_type = self.kpi_type_list[self.eval_type_to_kpi_id[eval_type] - 1]
        self.json_dict["kpiType"] = test_type

        self.json_dict = self.__camel_case_keys(self.json_dict)



# ------------------------------------------------------
# KPI CONFIGURATION
# ------------------------------------------------------
class KPIConfig:
    def __init__(self):
        self.eval_type_to_kpi_name = {"QA_TASK": "AudioQA-per-query", "Visual_QA_TASK": "VQA-per-query", "Hallucination_TASK": "Hallucination-per-query"}
        self.kpi_result_format = {
                "category": "Overall", #category of the result
                "numOfQuestions": 0,
                "ratingMean": None,
                "ratingStd": None,
                "latencyMean": None,
                "latencyStd": None,
                "entropyMean": None,
                "entropyStd": None,
                "numFail": 0,
                "ratingZeroCount": 0,
                "ratingOneCount": 0,
                "ratingTwoCount": 0,
                "ratingThreeCount": 0,
                "ratingFourCount": 0,
                "ratingFiveCount": 0,
                "remarks": "",
                "relatedIssues": ""
            }
        self.kpi_result = []


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

    def read_and_group(self) -> Dict[str, Dict]: # grouped based on eval_type
        header, samples = self.read()
        grouped_samples = {}

        for count, line in enumerate(samples):
            assert "eval_type" in line[0], f"'eval_type' key is necessary in report and currently missing in line number {count + 1}"
            eval_type = line[0]["eval_type"]
            if eval_type in grouped_samples:
                grouped_samples[eval_type].append(line)
            else:
                grouped_samples[eval_type] = [line]
            

        return header, grouped_samples


# ------------------------------------------------------
# KPI AGGREGATOR
# ------------------------------------------------------
class KPIAggregator:
    def __init__(self, config: KPIConfig, json_config: JSONConfig):
        self.config = config
        self.json_config = json_config
        self.raw_data = []
        self.cumulative_metrics = {"category_wise": {}, "iteration_wise": {}}
        self.cumulative_metrics_format = {
                "category": "Overall", #category of the result
                "num_of_questions": 0,
                "ratings_list": [],
                "latency_list": [],
                "entropy_list": [],
                "num_fail": 0,
                "rating_zero_count": 0,
                "rating_one_count": 0,
                "rating_two_count": 0,
                "rating_three_count": 0,
                "rating_four_count": 0,
                "rating_five_count": 0,
            }
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

        if not self.cumulative_metrics["iteration_wise"]:
            for count in range(1, self.num_evaluations + 1):
                self.cumulative_metrics["iteration_wise"][f"Iteration-{count}"] = deepcopy(self.cumulative_metrics_format)

        filtered_list = self._sanitize_item(q_data)
        filtered_list = sorted(filtered_list, key = lambda x: int(x["iteration"]))
        filtered_item = filtered_list[0]
        # print('filterd_item', filtered_item)

        task_type = self.config.eval_type_to_kpi_name[filtered_item["eval_type"]]
        question_type = filtered_item.get("question_type", "")
        rating = float(filtered_item["rating"])
        response_time = float(filtered_item["response_time"]) if filtered_item["response_time"] is not None else None
        entropy = filtered_item["meta_info"]["entropy_metrics"]["entropy"]

        for itr, q_iter in enumerate(filtered_list):
            iter_rating = int(q_iter["rating"])
            assert iter_rating in range(6), f"Rating not in range for {filtered_item['eval_id']}"
            
            category = ""
            if int(q_iter["iteration"]) == 1:
                category = q_iter["question_type"]
            if category != "" and category not in self.cumulative_metrics["category_wise"]:
                self.cumulative_metrics["category_wise"][category] = deepcopy(self.cumulative_metrics_format)
                self.cumulative_metrics["category_wise"][category]["category"] = category
            
            iteration_name = f"Iteration-{int(q_iter['iteration'])}"
            if iteration_name not in self.cumulative_metrics["iteration_wise"]:
                self.cumulative_metrics["iteration_wise"][iteration_name] = deepcopy(self.cumulative_metrics_format)
                self.cumulative_metrics["iteration_wise"][iteration_name]["category"] = iteration_name
            
            rating_in_words = ""
            match iter_rating:
                case 5:
                    rating_in_words = "five"
                case 4:
                    rating_in_words = "four"
                case 3:
                    rating_in_words = "three"
                case 2:
                    rating_in_words = "two"
                case 1:
                    rating_in_words = "one"
                case 0:
                    if q_iter["error_type"] != "empty_response":
                        rating_in_words = "zero"
                    else:
                        rating_in_words = "fail"
                case _:
                    rating_in_words = "fail"

            
            for (catg_type, catg) in [("category_wise", category), ("iteration_wise", iteration_name)]:
                # print(catg_type, catg)
                if catg == "":
                    continue

                print("eval_id:", q_iter["eval_id"], catg_type, catg)

                for k in self.cumulative_metrics_format:
                    if rating_in_words in k:
                        self.cumulative_metrics[catg_type][catg][k] += 1

                self.cumulative_metrics[catg_type][catg]["num_of_questions"] += 1
                self.cumulative_metrics[catg_type][catg]["ratings_list"].append(int(q_iter["rating"]))
                if q_iter["response_time"]: self.cumulative_metrics[catg_type][catg]["latency_list"].append(float(q_iter["response_time"]))
                self.cumulative_metrics[catg_type][catg]["entropy_list"].append(float(q_iter["meta_info"]["entropy_metrics"]["entropy"]))
                    
                        
            filtered_list[itr]["image_path"] = filtered_list[itr]["meta_info"]["image_path"];filtered_list[itr]["meta_info"].pop("image_path")
            filtered_list[itr]["audioPathBeforeDenoising"] = filtered_list[itr]["meta_info"].get("audio_decoded_path", "");filtered_list[itr]["meta_info"].pop("audio_decoded_path") if "audio_decoded_path" in filtered_list[itr]["meta_info"] else ""
            filtered_list[itr]["audioPathDenoised"] = filtered_list[itr]["meta_info"].get("audio_denoised_path", "");filtered_list[itr]["meta_info"].pop("audio_denoised_path") if "audio_denoised_path" in filtered_list[itr]["meta_info"] else ""
            filtered_list[itr]["response"] = filtered_list[itr]["meta_info"]["response_path"];filtered_list[itr]["meta_info"].pop("response_path")
            filtered_list[itr]["screenPath"] =  filtered_list[itr]["meta_info"].get("device_view_image_path", "")
            filtered_list[itr]["eval_type"] = task_type
            filtered_list[itr]["rating"] = int(filtered_list[itr]["rating"])
            filtered_list[itr]["meta_info"]["responseTime"] = filtered_list[itr]["response_time"]
            filtered_list[itr]["manualVerification"] = filtered_list[itr].get("manual_verification", False)

            print(filtered_list[itr]["meta_info"].keys())
            filtered_list[itr]["meta_info"]["answerAudioDuration"] = filtered_list[itr]["response_duration"] if "response_duration" in filtered_list[itr] else filtered_list[itr]["meta_info"]["answer_audio_duration"] 
            

        self.raw_data.extend(filtered_list)

    def __get_result_from_cumulative_metrics(self, category_type, category):
        assert category_type in self.cumulative_metrics and category in self.cumulative_metrics[category_type], "Missing category or category_type"

        category_kpi_result = self.config.kpi_result_format.copy()
        category_kpi_result["category"] = category
        category_kpi_result["numOfQuestions"] = self.cumulative_metrics[category_type][category]["num_of_questions"]
        
        if self.cumulative_metrics[category_type][category]["ratings_list"]:
            category_kpi_result["ratingMean"] = round(np.mean(self.cumulative_metrics[category_type][category]["ratings_list"]), 2)
            category_kpi_result["ratingStd"] = round(np.std(self.cumulative_metrics[category_type][category]["ratings_list"]), 2)
        else:
            category_kpi_result["ratingMean"] = None
            category_kpi_result["ratingStd"] = None

        if self.cumulative_metrics[category_type][category]["latency_list"]:
            category_kpi_result["latencyMean"] = round(np.mean(self.cumulative_metrics[category_type][category]["latency_list"]), 2)
            category_kpi_result["latencyStd"] = round(np.std(self.cumulative_metrics[category_type][category]["latency_list"]), 2)
        else:
            category_kpi_result["latencyMean"] = None
            category_kpi_result["latencyStd"] = None
        
        if self.cumulative_metrics[category_type][category]["entropy_list"]:
            category_kpi_result["entropyMean"] = round(np.mean(self.cumulative_metrics[category_type][category]["entropy_list"]), 5)
            category_kpi_result["entropyStd"] = round(np.std(self.cumulative_metrics[category_type][category]["entropy_list"]), 5)
        else:
            category_kpi_result["entropyMean"] = None
            category_kpi_result["entropyStd"] = None
        
        category_kpi_result["numFail"] = self.cumulative_metrics[category_type][category]["num_fail"]
        category_kpi_result["ratingZeroCount"] = self.cumulative_metrics[category_type][category]["rating_zero_count"]
        category_kpi_result["ratingOneCount"] = self.cumulative_metrics[category_type][category]["rating_one_count"]
        category_kpi_result["ratingTwoCount"] = self.cumulative_metrics[category_type][category]["rating_two_count"]
        category_kpi_result["ratingThreeCount"] = self.cumulative_metrics[category_type][category]["rating_three_count"]
        category_kpi_result["ratingFourCount"] = self.cumulative_metrics[category_type][category]["rating_four_count"]
        category_kpi_result["ratingFiveCount"] = self.cumulative_metrics[category_type][category]["rating_five_count"]

        return category_kpi_result

    def finalize(self):
        # print(self.cumulative_metrics)
        print("Finalising...")
        self.cumulative_metrics["category_wise"]["Overall"] = deepcopy(self.cumulative_metrics_format)
        self.cumulative_metrics["iteration_wise"]["Overall"] = deepcopy(self.cumulative_metrics_format)

        for category_type in self.cumulative_metrics:
            for category in self.cumulative_metrics[category_type]:     
                if "Overall" in category:
                    continue

                self.config.kpi_result.append(self.__get_result_from_cumulative_metrics(category_type, category))

                for k in self.cumulative_metrics[category_type]["Overall"]:
                    v = self.cumulative_metrics[category_type][category][k]
                    if isinstance(v, int) :
                        self.cumulative_metrics[category_type]["Overall"][k] += self.cumulative_metrics[category_type][category][k]
                    elif isinstance(v, list):
                        self.cumulative_metrics[category_type]["Overall"][k].extend(self.cumulative_metrics[category_type][category][k])
        
        self.cumulative_metrics["iteration_wise"]["Overall(iteration1,2,3)"] = self.cumulative_metrics["iteration_wise"]["Overall"]
        self.cumulative_metrics["iteration_wise"].pop("Overall")
        for category_type in self.cumulative_metrics:
            for category in self.cumulative_metrics[category_type]:
                if "Overall" in category:
                    self.config.kpi_result.append(self.__get_result_from_cumulative_metrics(category_type, category))
        
        self.json_config.populate_json(self.raw_data, self.config.kpi_result)


# ------------------------------------------------------
# REPORT BUILDER
# ------------------------------------------------------
class KPIReportBuilder:
    def __init__(self, config: KPIConfig, json_config: JSONConfig):
        self.json_config = json_config
        self.aggregator = KPIAggregator(config, json_config)
        self.num_evaluations = -1
        
    def check_connection(self, device: str) -> bool:
        devices_list = subprocess.check_output(
                        ["adb", "devices"],
                        text=True
                    ).strip()
        
        if device in devices_list:
            return True

        return False
    
    def get_current_time(self):
        from datetime import datetime, timezone
        current_time_utc = datetime.now(timezone.utc)
        final_format_strftime = current_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        return final_format_strftime
        
    def populate_device_info(self, data_config: Dict):
        mobile_device = data_config["devices"]["s25_device_id"]
        self.num_evaluations = data_config["automator"]["num_evaluations"]
        companion_pair = data_config["automator"]["xr_board"]["companion_pair"]

        if companion_pair == "jinju/gemini-live-s25":
            jinju_device = data_config["devices"]["jinju_device_id"]
            isDeviceConnected = self.check_connection(mobile_device) and self.check_connection(jinju_device)

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
                "companionPair": data_config["automator"]["xr_board"]["companion_pair"],
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
        elif companion_pair == "s25/gemini-live":
            hwid = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.revision"],
                            text=True
                        ).strip()
            binaryVersion = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.build.version.incremental"],
                            text=True
                        ).strip()
            modelName = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.model"],
                            text=True
                        ).strip()
            mergeBuildId = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.omc.build.id"],
                            text=True,
                        ).strip()
            agsaVersion = subprocess.run(
                            f"adb -s {mobile_device} shell dumpsys package com.google.android.googlequicksearchbox | grep versionName",
                            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            check=True
                        ).stdout.strip().split('\n')[-1].strip().split('=')[1]
            aiAppVersion = subprocess.run(
                            f"adb -s {mobile_device} shell dumpsys package com.google.android.apps.bard | grep versionName",
                            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            check=True
                        ).stdout.strip().split('\n')[-1].strip().split('=')[1]
            meta_info = {
                "testId": datetime.now().strftime("%Y%m%d%H%M%S%f"),                                    
                "userId": data_config["automator"]["xr_board"]["user_id"],                                    # tester or uploader id : e.g. sy0514.jung
                "kpiType": data_config["automator"]["xr_board"]["kpi_type"],                                  # e.g. pass or fail
                "companionPair": data_config["automator"]["xr_board"]["companion_pair"],
                "aiAppVersion": aiAppVersion,
                "device": {
                    "deviceId": mobile_device,
                    "hwid": hwid,
                    "binaryVersion": binaryVersion,
                    "modelName": modelName,
                    "mergeBuildId": mergeBuildId,
                    "agsaVersion": agsaVersion
                },
                "testInformation": {
                    "datasets": data_config["automator"]["xr_board"]["dataset_name"],
                    "vlmJudgeName": data_config["automator"]["xr_board"]["judge_name"]
                },
                "startTime": self.get_current_time(),
                "testState": "Completed",
                "testResult":"pass",         
            }
            self.json_config.json_dict["device"].clear()
        
        elif companion_pair == "s25/gpt-4o-voice-mode":
            isDeviceConnected = self.check_connection(mobile_device)
            assert isDeviceConnected, "Devices used for evaluation are not connected"

            hwid = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.revision"],
                            text=True
                        ).strip()
            binaryVersion = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.build.version.incremental"],
                            text=True
                        ).strip()
            modelName = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.model"],
                            text=True
                        ).strip()
            mergeBuildId = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.omc.build.id"],
                            text=True,
                        ).strip()
            aiAppVersion = subprocess.run(
                            f"adb -s {mobile_device} shell dumpsys package com.openai.chatgpt | grep versionName",
                            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            check=True
                        ).stdout.strip().split('\n')[-1].strip().split('=')[1]
                        
            meta_info = {
                "testId": datetime.now().strftime("%Y%m%d%H%M%S%f"),                                    
                "userId": data_config["automator"]["xr_board"]["user_id"],                                    # tester or uploader id : e.g. sy0514.jung
                "kpiType": data_config["automator"]["xr_board"]["kpi_type"],                                  # e.g. pass or fail
                "companionPair": data_config["automator"]["xr_board"]["companion_pair"],
                "aiAppVersion" :  aiAppVersion,
                "device": {
                    "deviceId": mobile_device,
                    "hwid": hwid,
                    "binaryVersion": binaryVersion,
                    "modelName": modelName,
                    "mergeBuildId": mergeBuildId,
                },
                "testInformation": {
                    "datasets": data_config["automator"]["xr_board"]["dataset_name"],
                    "vlmJudgeName": data_config["automator"]["xr_board"]["judge_name"]
                },
                "startTime": self.get_current_time(),
                "testState": "Completed",
                "testResult":"pass",         
            }
            self.json_config.json_dict["device"].clear()
        
        elif companion_pair == "meta-wayfarer/meta-ai-live-s25":
            isDeviceConnected = self.check_connection(mobile_device)
            assert isDeviceConnected, "Devices used for evaluation are not connected"

            binaryVersion = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.build.version.incremental"],
                            text=True
                        ).strip()
            modelName = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.product.model"],
                            text=True
                        ).strip()
            mergeBuildId = subprocess.check_output(
                            ["adb", "-s", mobile_device, "shell", "getprop", "ro.omc.build.id"],
                            text=True,
                        ).strip()
            aiAppVersion = subprocess.run(
                            f"adb -s {mobile_device} shell dumpsys package com.facebook.stella | grep versionName",
                            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True,
                            check=True
                        ).stdout.strip().split('\n')[-1].strip().split('=')[1]
            
            
            meta_info = {
                "testId": datetime.now().strftime("%Y%m%d%H%M%S%f"),                                    
                "userId": data_config["automator"]["xr_board"]["user_id"],                                    # tester or uploader id : e.g. sy0514.jung
                "kpiType": data_config["automator"]["xr_board"]["kpi_type"],                                  # e.g. pass or fail
                "companionPair": data_config["automator"]["xr_board"]["companion_pair"],
                "aiAppVersion" :  aiAppVersion,
                "device": {
                    "deviceId": "", # needs to be changed manually after report generation with Meta glass "Serial number"
                    "binaryVersion": "", # needs to be changed manually after report generation with meta glass "Version"
                    "modelName": "Wayfarer",
                    "pairedDevice":{
                        "deviceId": mobile_device,
                        "binaryVersion": binaryVersion,
                        "modelName": modelName,
                        "mergeBuildId": mergeBuildId
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
            self.json_config.json_dict["device"].clear()
        else:
            print(companion_pair, "unknown companion pair")
            raise NotImplementedError

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
def KPI_Test_report_generator(eval_json_path, config_path, isVisualize=False):
    print("Eval Report Path:", eval_json_path)
    dump_path = eval_json_path.rsplit('.',1)[0] + "_for_XRBoard.json"; dump_path_list = []
    data_config = json.load(open(config_path, 'r'))

    reader = EvalFileReader(eval_json_path)

    _, eval_data = reader.read_and_group()

    for eval_type in eval_data:
        config = KPIConfig()
        json_config = JSONConfig()
        report_builder = KPIReportBuilder(config, json_config)
        report_builder.populate_device_info(data_config)

        updated_dump_path = dump_path.replace("XRBoard", f"KPI_{eval_type}")
        dump_path_list.append(updated_dump_path)

        print(f"Working on {eval_type}:Size ({len(eval_data[eval_type])})")
        report_builder.build(eval_data[eval_type])
        report_builder.save(updated_dump_path)
        del report_builder

    ### For Visualisation ###
    # if isVisualize:
    #     final_report = report_builder.get_report()
    #     final_report.pop("kpiResult")   # For visualisation removed "kpiResult" data
    #     print(json.dumps(final_report, indent=2))
    ### For Visualisation ###
    return dump_path_list


if __name__ == "__main__":
    eval_json_path = "/home/test/Shouvik/work_2026/Gemini_Live_Evaluation/Evaluation_Framework/data/vqa_report_sample.jsonl"
    KPI_Test_report_generator(eval_json_path)
