import os
import requests
import warnings
import json

def post_json(api_url_type: str, payload: dict, timeout: int = 30):
    """
    Sends a POST request with a raw JSON body.

    :param api_url: Endpoint URL
    :param payload: Dictionary to be sent as JSON
    :param timeout: Request timeout in seconds
    :return: requests.Response or None
    """
    if api_url_type == "sanity":
        api_url = "http://xr.sec.samsung.net/api/v2/vision/jinju/test/gemini"
    elif api_url_type == "audio":
        api_url = "http://xr.sec.samsung.net/api/v2/vision/jinju/kpi/gemini/audio-qa"
    elif api_url_type == "visual":
        api_url = "http://xr.sec.samsung.net/api/v2/vision/jinju/kpi/gemini/visual-qa"
    elif api_url_type == "hallucination":
        api_url = "http://xr.sec.samsung.net/api/v2/vision/jinju/kpi/gemini/hallucination"
    else:
        raise(f"{api_url_type} Unknown api_url_type!")
        return

    assert isinstance(payload, dict),"Payload must be a dictionary."

    try:
        response = requests.post(
            api_url,
            json=payload,   # Automatically sets Content-Type: application/json
            timeout=timeout
        )
    except requests.RequestException as e:
        warnings.warn(f"Request failed: {e}", RuntimeWarning)
        return None

    print("Status:", response.status_code)

    try:
        print("Response JSON:", response.json())
    except ValueError:
        print("Response Text:", response.text)

    return response.json()['message']

if __name__=="__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m automator.report_generator.utils.upload_reports <results_dir>")
        sys.exit(1)
    path = sys.argv[1]

    #kpi_file_type = {"vqa_report_for_XRBoard": "sanity", "vqa_report_for_KPI_QA_TASK": "audio", "vqa_report_for_KPI_Visual_QA_TASK": "visual", "vqa_report_for_KPI_Hallucination_TASK": "hallucination"}
    kpi_file_type = {"vqa_report_for_KPI_Visual_QA_TASK": "visual"}
    for f_name_ext in os.listdir(path):
        f_name = f_name_ext.split('.')[0]
        if f_name in kpi_file_type:
            file_path = os.path.join(path, f_name_ext)
            with open(file_path, "r") as f:
                payload = json.load(f)
                print(post_json(kpi_file_type[f_name], payload))