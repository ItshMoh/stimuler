import os
from typing import Any

from fastapi import HTTPException


def transcribe_audio(audio_bytes: bytes) -> dict[str, Any]:
    api_key = os.getenv("DEEPGRAM_API_KEY")
    model = os.getenv("DEEPGRAM_MODEL", "nova-3")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="DEEPGRAM_API_KEY is not configured on the backend",
        )

    try:
        from deepgram import DeepgramClient
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="deepgram-sdk is not installed in the backend environment",
        ) from error

    try:
        client = DeepgramClient(api_key=api_key)
        response = client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model=model,
            smart_format=True,
            filler_words=True,
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Deepgram transcription failed: {error}",
        ) from error

    payload = _response_to_dict(response)
    alternative = _first_alternative(payload)
    words = alternative.get("words") or []

    return {
        "model": model,
        "transcript": alternative.get("transcript", ""),
        "confidence": alternative.get("confidence"),
        "words": [_format_word(word) for word in words],
        "raw": payload,
    }


def _response_to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response

    if hasattr(response, "model_dump"):
        return response.model_dump()

    if hasattr(response, "to_dict"):
        return response.to_dict()

    if hasattr(response, "dict"):
        return response.dict()

    raise HTTPException(
        status_code=502,
        detail="Deepgram returned an unsupported response format",
    )


def _first_alternative(payload: dict[str, Any]) -> dict[str, Any]:
    channels = payload.get("results", {}).get("channels", [])

    if not channels:
        return {}

    alternatives = channels[0].get("alternatives", [])

    if not alternatives:
        return {}

    return alternatives[0]


def _format_word(word: dict[str, Any]) -> dict[str, Any]:
    return {
        "word": word.get("word", ""),
        "punctuated_word": word.get("punctuated_word"),
        "start": word.get("start"),
        "end": word.get("end"),
        "confidence": word.get("confidence"),
    }
