from fastapi import FastAPI, UploadFile, File, responses
from pydantic import BaseModel
import sounddevice as sd
import threading
import numpy as np
from pydub import AudioSegment
import tempfile
import os
import soundfile as sf
app = FastAPI()


class AudioHandler:
    def __init__(self, samplerate: int = 44100, channels: int = 1):
        self.samplerate = samplerate
        self.channels = channels
        self.recording = False
        self.frames = []
        self.thread = None
        self._play_lock = threading.Lock()     # serialize device access


    def _record_loop(self):
        """Internal loop to capture audio."""
        with sd.InputStream(samplerate = self.samplerate,
                            channels = self.channels,
                            device = 4,
                            callback = self._callback):
            while self.recording:
                sd.sleep(100)

    def _callback(self, indata, frames, time, status):
        if status:
            print("Recording error:", status)
        self.frames.append(indata.copy())

    def start_recording(self):
        """Start recording in background thread."""
        if self.recording:
            return "Already recording"
        self.frames = []
        self.recording = True
        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()
        return "Recording started"

    def stop_recording(self, filename: str):
        """Stop recording and save as MP3."""
        if not self.recording:
            return "Not recording"
        self.recording = False
        self.thread.join()

        audio_data = np.concatenate(self.frames, axis=0)

        # Save WAV temporarily
        tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        sf.write(tmp_wav.name, audio_data, self.samplerate)

        # Convert to MP3
        sound = AudioSegment.from_wav(tmp_wav.name)
        sound.export(filename, format="wav")
        os.remove(tmp_wav.name)

        return filename

    def play_audio(self, filename: str):
        """Play audio file (mp3/wav)."""
        sound = AudioSegment.from_file(filename)
        samples = np.array(sound.get_array_of_samples()).astype(np.float32)
        if sound.channels > 1:
            samples = samples.reshape((-1, sound.channels))
        samples = samples / (2 ** (8 * sound.sample_width - 1))
        with self._play_lock:                  # serialize device access
            sd.play(samples, samplerate=sound.frame_rate)
            sd.wait()                          # block until playback done, then release
        return f"Playback finished for {filename}"



# Global audio handler
audio_handler = AudioHandler()


class RecordRequest(BaseModel):
    filename: str

@app.get("/health_check")
async def health_check():
    return {"status": "OK"}

@app.post("/start_recording")
async def start_recording():
    return {"status": audio_handler.start_recording()}


@app.post("/stop_recording")
async def stop_recording(req: RecordRequest):
    result = audio_handler.stop_recording(req.filename)
    if result is None:
    	return {"message": "No record"}
    return responses.FileResponse(
    	path = result,
    	media_type = "audio/wav",
    	filename = os.path.basename(result)
    )


@app.post("/play")
async def play(req: RecordRequest):
    result = audio_handler.play_audio(req.filename)
    return {"status": result}


@app.post("/upload_and_play")
async def upload_and_play(file: UploadFile = File(...)):
    """Upload an mp3/wav file and play it."""
    tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}").name
    with open(tmp_path, "wb") as f:
        f.write(await file.read())
    result = audio_handler.play_audio(tmp_path)
    os.remove(tmp_path)
    return {"status": result}
    
    
    
import uvicorn

if __name__ == "__main__":
    uvicorn.run("arap_service:app", host="0.0.0.0", port=8000, reload=False)
        
