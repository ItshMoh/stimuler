import asyncio
import json
import os
from typing import Any
from urllib.parse import urlencode

from fastapi import WebSocket

from prompts import Prompt
from scoring import (
    build_reliability_warnings,
    score_accuracy,
    score_delivery,
    score_pronunciation,
)


def build_assessment_result(
    *,
    prompt: Prompt,
    transcript: str,
    confidence: float | None,
    words: list[dict[str, Any]],
    model: str,
) -> dict[str, Any]:
    accuracy_result = score_accuracy(prompt.text, transcript)
    delivery_result = score_delivery(words)
    pronunciation_result = score_pronunciation(prompt.text, transcript, words)

    return {
        "prompt_id": prompt.id,
        "target_text": prompt.text,
        "filename": "live-stream",
        "content_type": "audio/webm;codecs=opus",
        "size_bytes": 0,
        "transcript": transcript,
        "confidence": confidence,
        "words": words,
        "deepgram_model": model,
        "scores": {
            "accuracy": accuracy_result["accuracy"],
            "pronunciation": pronunciation_result["score"],
            **delivery_result["scores"],
        },
        "metrics": {
            **accuracy_result["metrics"],
            **delivery_result["metrics"],
            **pronunciation_result["metrics"],
        },
        "fillers": delivery_result["fillers"],
        "pauses": delivery_result["pauses"],
        "reliability_warnings": build_reliability_warnings(confidence, words),
        "word_feedback": accuracy_result["word_feedback"],
        "explanation": accuracy_result["explanation"],
        "fluency_explanation": delivery_result["explanation"],
        "pronunciation_explanation": pronunciation_result["explanation"],
        "message": "Live audio transcribed and compared with the target prompt.",
    }


async def stream_transcription(websocket: WebSocket, prompt: Prompt) -> None:
    api_key = os.getenv("DEEPGRAM_API_KEY")
    model = os.getenv("DEEPGRAM_MODEL", "nova-3")

    if not api_key:
        await websocket.send_json(
            {
                "type": "error",
                "detail": "DEEPGRAM_API_KEY is not configured on the backend",
            }
        )
        return

    try:
        import websockets
    except ImportError:
        await websocket.send_json(
            {
                "type": "error",
                "detail": "websockets is not installed in the backend environment",
            }
        )
        return

    params = urlencode(
        {
            "model": model,
            "smart_format": "true",
            "filler_words": "true",
            "interim_results": "true",
            "vad_events": "true",
            "utterance_end_ms": "1000",
        }
    )
    deepgram_url = f"wss://api.deepgram.com/v1/listen?{params}"
    final_segments: list[str] = []
    latest_interim = ""
    latest_confidence: float | None = None
    final_words: list[dict[str, Any]] = []
    stop_requested = asyncio.Event()

    try:
        async with _connect_deepgram(
            websockets,
            deepgram_url,
            {"Authorization": f"Token {api_key}"},
        ) as deepgram_socket:
            await websocket.send_json({"type": "ready"})

            async def receive_browser_audio() -> None:
                while True:
                    message = await websocket.receive()

                    if message.get("bytes") is not None:
                        await deepgram_socket.send(message["bytes"])
                        continue

                    if message.get("text") is not None:
                        data = json.loads(message["text"])

                        if data.get("type") == "stop":
                            await deepgram_socket.send(json.dumps({"type": "Finalize"}))
                            stop_requested.set()
                            return

            async def receive_deepgram_results() -> None:
                nonlocal latest_interim, latest_confidence, final_words

                async for raw_message in deepgram_socket:
                    data = json.loads(raw_message)

                    if data.get("type") != "Results":
                        continue

                    alternative = _first_live_alternative(data)
                    transcript = alternative.get("transcript", "")

                    if not transcript:
                        continue

                    latest_confidence = alternative.get("confidence")

                    if data.get("is_final"):
                        final_segments.append(transcript)
                        latest_interim = ""
                        final_words.extend(_format_live_words(alternative.get("words", [])))
                    else:
                        latest_interim = transcript

                    live_transcript = _combine_transcript(final_segments, latest_interim)
                    await websocket.send_json(
                        {
                            "type": "transcript",
                            "transcript": live_transcript,
                            "is_final": data.get("is_final", False),
                            "speech_final": data.get("speech_final", False),
                        }
                    )

            browser_task = asyncio.create_task(receive_browser_audio())
            deepgram_task = asyncio.create_task(receive_deepgram_results())
            stop_task = asyncio.create_task(stop_requested.wait())

            done, _pending = await asyncio.wait(
                {browser_task, deepgram_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not stop_requested.is_set():
                for task in done:
                    error = task.exception()

                    if error:
                        raise error

                raise RuntimeError("Live transcription stream closed before stop")

            await asyncio.sleep(float(os.getenv("STREAM_FINALIZE_WAIT_SECONDS", "1.2")))

            transcript = _combine_transcript(final_segments, latest_interim)
            result = build_assessment_result(
                prompt=prompt,
                transcript=transcript,
                confidence=latest_confidence,
                words=final_words,
                model=model,
            )
            await websocket.send_json({"type": "assessment", "result": result})

            for task in (browser_task, deepgram_task, stop_task):
                task.cancel()

            await deepgram_socket.send(json.dumps({"type": "CloseStream"}))
    except Exception as error:
        await websocket.send_json({"type": "error", "detail": str(error)})


def _connect_deepgram(websockets_module: Any, url: str, headers: dict[str, str]):
    try:
        return websockets_module.connect(url, additional_headers=headers)
    except TypeError:
        return websockets_module.connect(url, extra_headers=headers)


def _first_live_alternative(data: dict[str, Any]) -> dict[str, Any]:
    channel = data.get("channel", {})
    alternatives = channel.get("alternatives", [])

    if not alternatives:
        return {}

    return alternatives[0]


def _combine_transcript(final_segments: list[str], latest_interim: str) -> str:
    parts = [segment for segment in final_segments if segment]

    if latest_interim:
        parts.append(latest_interim)

    return " ".join(parts).strip()


def _format_live_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "word": word.get("word", ""),
            "punctuated_word": word.get("punctuated_word"),
            "start": word.get("start"),
            "end": word.get("end"),
            "confidence": word.get("confidence"),
        }
        for word in words
    ]
