import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from deepgram_client import transcribe_audio
from prompts import PROMPTS, get_prompt
from scoring import score_accuracy, score_delivery
from streaming import stream_transcription

load_dotenv()

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI(
    title="Stimuler Speech Assessment API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "stimuler-api"}


@app.get("/api/prompts")
def list_prompts():
    return {"prompts": PROMPTS}


@app.websocket("/api/transcribe/live/{prompt_id}")
async def live_transcription(websocket: WebSocket, prompt_id: str):
    await websocket.accept()

    prompt = get_prompt(prompt_id)

    if prompt is None:
        await websocket.send_json({"type": "error", "detail": "Prompt not found"})
        await websocket.close(code=1008)
        return

    await stream_transcription(websocket, prompt)


@app.post("/api/assess")
async def receive_audio(
    prompt_id: str = Form(...),
    audio: UploadFile = File(...),
):
    prompt = get_prompt(prompt_id)

    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")

    audio_bytes = await audio.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    transcription = transcribe_audio(audio_bytes)
    accuracy_result = score_accuracy(prompt.text, transcription["transcript"])
    delivery_result = score_delivery(transcription["words"])

    return {
        "prompt_id": prompt.id,
        "target_text": prompt.text,
        "filename": audio.filename,
        "content_type": audio.content_type,
        "size_bytes": len(audio_bytes),
        "transcript": transcription["transcript"],
        "confidence": transcription["confidence"],
        "words": transcription["words"],
        "deepgram_model": transcription["model"],
        "scores": {
            "accuracy": accuracy_result["accuracy"],
            **delivery_result["scores"],
        },
        "metrics": {
            **accuracy_result["metrics"],
            **delivery_result["metrics"],
        },
        "fillers": delivery_result["fillers"],
        "pauses": delivery_result["pauses"],
        "word_feedback": accuracy_result["word_feedback"],
        "explanation": accuracy_result["explanation"],
        "fluency_explanation": delivery_result["explanation"],
        "message": "Audio transcribed and compared with the target prompt.",
    }
