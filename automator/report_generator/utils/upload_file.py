import requests
import warnings
from pathlib import Path
import json
import os

def upload(file_path: str, use_actual_url):
    if use_actual_url:
        API_URL = "http://xr.sec.samsung.net/api/v3/file/upload?saveFile=true"
    else:
        API_URL = "http://xr.sec.samsung.net/api/v3/file/upload?saveFile=false"
    path = Path(file_path)

    if not path.is_file():
        warning_str = f"{file_path} does not exist or has already been uploaded!"
        warnings.warn(warning_str, RuntimeWarning)
        return file_path
    print(f"{file_path} is file")

    with path.open("rb") as f:
        assert path.suffix in ['.wav', '.png', '.mp3'], 'Unknown extension'
        if path.suffix == '.wav':
            files = {
                "file": (path.name, f, "audio/wav")
            }
        elif path.suffix == '.mp3':
            files = {
                "file": (path.name, f, "audio/mp3")
            }
        elif path.suffix == '.png':
            files = {
                "file": (path.name, f, "image/png")
            }

        response = requests.post(
            API_URL,
            files=files,
            timeout=60
        )

    print("Status:", response.status_code)

    try:
        print("Response JSON:", response.json())
        return response.json()["url"]
    except ValueError:
        print("Response Text:", response.text)
        return file_path

def scan_and_upload_file(json_file, use_actual_url, upload_keys = ["audioPathDenoised", "audioPathBeforeDenoising", "imagePath", "response", "screenPath", "audioRawPath"], uploaded_files = {}):
    try:
        if not os.path.exists(json_file):
            return {}
        else:
            print(json_file)
        with open(json_file, 'r') as file:
            data = json.load(file)
        if use_actual_url:
            print("Uploading files to XR_BOARD!!")
        
        for data_point in data["kpiRaw"]["data"]:
            for k in upload_keys:
                if k in data_point:
                    path = data_point[k]
                    if path not in uploaded_files:
                        data_point[k] = upload(path, use_actual_url)
                        uploaded_files[path] = data_point[k]
                    else:
                        data_point[k] = uploaded_files[path]
                elif k in data_point["metaInfo"]:
                    path = data_point["metaInfo"][k]
                    if path not in uploaded_files:
                        data_point["metaInfo"][k] = upload(path, use_actual_url)
                        uploaded_files[path] = data_point["metaInfo"][k]
                    else:
                        data_point["metaInfo"][k] = uploaded_files[path]
                else:
                    raise Exception("Missing key!")
                    
        
        with open(json_file, 'w') as fp:
            fp.write(json.dumps(data, indent=2))
        
        return uploaded_files

    except FileNotFoundError:
        print(f"Error: The file {json_file} was not found.")
    except json.JSONDecodeError as e:
        print(f"Error: Failed to decode JSON from the file: {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m automator.report_generator.utils.upload_file <results_dir>")
        sys.exit(1)
    results_dir = sys.argv[1]
    uploaded_files = scan_and_upload_file(os.path.join(results_dir, "vqa_report_for_XRBoard.json"), True)
    uploaded_files = scan_and_upload_file(os.path.join(results_dir, "vqa_report_for_KPI_Visual_QA_TASK.json"), True, uploaded_files)
    uploaded_files = scan_and_upload_file(os.path.join(results_dir, "vqa_report_for_KPI_QA_TASK.json"), True, uploaded_files)
    uploaded_files = scan_and_upload_file(os.path.join(results_dir, "vqa_report_for_KPI_Hallucination_TASK.json"), True, uploaded_files)

