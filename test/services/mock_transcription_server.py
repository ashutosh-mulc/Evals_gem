from fastapi import FastAPI
from pydantic import BaseModel
import whisper
import base64
import tempfile
import os
import uvicorn
import asyncio

app = FastAPI()

class StringRequest(BaseModel):
    data: str

@app.post("/transcribe/")
async def transcribe_audio(request: StringRequest):
    return {"language": "en", "text": "This is a dummy transcriber.", "start": 1.0, "end": 2.5}

@app.get("/health/", status_code = 200)
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    # Run with one worker process (important! so only one Whisper model loads)
    # uvicorn.run(app, host="0.0.0.0", port=8181)
    uvicorn.run(app, host="0.0.0.0", port=8080)
    # transcribe_file("/home/test/data/CODES/prompt_optimization/dev/tmp/Shouvik.m4a")
