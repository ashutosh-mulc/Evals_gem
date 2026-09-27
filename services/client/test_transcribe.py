import os
import sys
import requests

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils.file_utils import Base64Converter

URL = "http://107.99.236.212:8601"
def transcribe_audio(path):
    encoded_audio = Base64Converter.encode_to_base64(path)["file_base64"]
    response = requests.post(
            f"{URL}/transcribe/",
            json={"data": encoded_audio},
            timeout = 600  # long audios can take timess
        )
    response.raise_for_status()
    print(response.json())

def check_health():
    response = requests.get(
            f"{URL}/health/",
            timeout = 5  # long audios can take timess
        )
    response.raise_for_status()
    print(response.json())

if __name__ == '__main__':
    # transcribe_audio("/home/test/Amartya/work_2026/Gemini_Live_Evaluation/Evaluation_Framework/assets/temp.wav")
    check_health()