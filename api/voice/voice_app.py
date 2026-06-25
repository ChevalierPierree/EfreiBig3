"""Service vocal autonome de KiVendTout (FastAPI, port 8100).

Decouple du gros service data (port 8000) : on n'y touche pas. Le dashboard
(port 7600) appelle ce service pour la voix, et le service lit les KPIs du
data API pour la narration.

Lancer :
    uvicorn api.voice.voice_app:app --host 0.0.0.0 --port 8100
ou :
    python -m api.voice.voice_app

Pipeline /api/voice/command :
    audio -> transcribe (Whisper) -> classify (Ollama) -> [narrate (Ollama)]
"""
from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI, File, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import intent_service, narrate_service, stt_service, tts_service

app = FastAPI(title="KiVendTout Voice Layer", version="0.1.0")

# Le dashboard est servi sur :7600 (origine differente) -> CORS ouvert en local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextIn(BaseModel):
    text: str


class NarrateIn(BaseModel):
    view: str = "fraud"


@app.get("/health")
def health():
    return {"status": "ok", "service": "voice"}


async def _save_upload(audio: UploadFile) -> str:
    suffix = os.path.splitext(audio.filename or "rec.webm")[1] or ".webm"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(await audio.read())
    return path


@app.post("/api/voice/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    path = await _save_upload(audio)
    try:
        return stt_service.transcribe(path)
    finally:
        os.remove(path)


@app.post("/api/voice/intent")
def intent(body: TextIn):
    return intent_service.classify(body.text)


@app.post("/api/voice/narrate")
def narrate(body: NarrateIn):
    return narrate_service.narrate(body.view)


@app.get("/api/voice/tts/health")
def tts_health():
    """Le front interroge ceci : voix neuronale dispo ? sinon il retombe sur la voix navigateur."""
    return {"available": tts_service.available()}


@app.post("/api/voice/tts")
def tts(body: TextIn):
    """Texte -> audio WAV (voix neuronale locale Piper)."""
    try:
        audio = tts_service.synthesize(body.text)
    except FileNotFoundError:
        return Response(status_code=503, content=b"", media_type="audio/wav")
    return Response(content=audio, media_type="audio/wav")


@app.post("/api/voice/ask")
def ask(body: TextIn):
    """Repond a une question libre a partir des KPIs reels."""
    view = "fraud"
    return narrate_service.answer_question(body.text, view)


@app.post("/api/voice/command")
async def command(audio: UploadFile = File(...)):
    """Pipeline complet (non-stage) : audio -> texte -> intention -> reponse."""
    path = await _save_upload(audio)
    try:
        stt = stt_service.transcribe(path)
    finally:
        os.remove(path)

    intent = intent_service.classify(stt["text"])
    result = {"transcript": stt["text"], "intent": intent, "answer": None}

    if intent["action"] == "ask":
        result["answer"] = narrate_service.answer_question(stt["text"],
                                                           intent.get("view") or "fraud")["answer"]
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
