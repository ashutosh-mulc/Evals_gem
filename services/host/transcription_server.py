from fastapi import FastAPI
from pydantic import BaseModel
import whisper
import base64
import tempfile
import os
import uvicorn
import asyncio

app = FastAPI()

print("Loading Whisper model...")
model = whisper.load_model("large-v2")   # single shared GPU instance
# Second, faster model for in-run turn decisions (/transcribe_live/). Own lock, so it never
# queues behind large-v2 judge jobs. Use "small.en" if this whisper version predates "turbo".
LIVE_MODEL = "turbo"
live_model = whisper.load_model(LIVE_MODEL)
print("Models loaded!")

def transcribe_ts(audio_pth):
    return model.transcribe(
        audio_pth,
        language = 'en',
        word_timestamps = True,
        verbose = False,
        # task = 'translate' # leads to unceratinty in word timestamps and doesn't have accurate translation(atleast for Hindi)
    )

def detect_language(audio_pth):
    audio = whisper.load_audio(audio_pth)
    audio = whisper.pad_or_trim(audio)
    mel = whisper.log_mel_spectrogram(audio, n_mels = model.dims.n_mels).to(model.device)
    _, probs = model.detect_language(mel)
    
    return  max(probs, key = probs.get)

# A lock ensures only one transcription runs at a time
lock = asyncio.Lock()

class StringRequest(BaseModel):
    data: str


@app.post("/transcribe/")
async def transcribe_audio(request: StringRequest):
    # Decode base64 into a temporary MP3 file
    audio_bytes = base64.b64decode(request.data)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    print("----Recieved transcription request----", tmp_path)
    # Queue requests so Whisper never runs in parallel on GPU
    async with lock:
        # Offload blocking transcription to a thread executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, transcribe_ts, tmp_path)
        language = await loop.run_in_executor(None, detect_language, tmp_path)

    os.remove(tmp_path)  # cleanup
    
    print(f"{tmp_path} transcribed -> {result.get('segments', '')}")
    start_time = 25; end_time = 0; text = ""; words = []
    for segment in result["segments"]:
        # if segment["no_speech_prob"] > 0.45: # probability of the segment being empty
        #     continue
        for word in segment["words"]:
            if start_time > word['start']:
                start_time =  round(word['start'] , 2)
            if end_time < word['end']:
                end_time = round(word['end'], 2)
            words.append(word['word'])
    text = ''.join(words)

    return {"language": language, "text": text, "start": start_time, "end": end_time}

live_lock = asyncio.Lock()


@app.post("/transcribe_live/")
async def transcribe_live(request: StringRequest):
    """Low-latency text of one agent turn, used by the agent tester to pick its reply."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp.write(base64.b64decode(request.data))
        tmp_path = tmp.name
    try:
        async with live_lock:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: live_model.transcribe(tmp_path, language='en', condition_on_previous_text=False))
    finally:
        os.remove(tmp_path)
    return {"text": result["text"].strip()}

@app.get("/health/", status_code = 200)
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    # Run with one worker process (important! so only one Whisper model loads)
    # uvicorn.run(app, host="0.0.0.0", port=8181)
    uvicorn.run(app, host="0.0.0.0", port=8080)
    # transcribe_file("/home/test/data/CODES/prompt_optimization/dev/tmp/Shouvik.m4a")
