"""Voice adapters for servers that speak the OpenAI audio formats (OpenAI, Groq, faster-whisper-server, Kokoro-FastAPI and
similar). Configure `[voice] stt_url` / `tts_url` in config.toml; keys (if any) are `voice.stt_key` / `voice.tts_key`.

    transcribe(audio bytes, mime) -> text          POST {stt_url}/audio/transcriptions   (multipart, model=whisper-1)
    speak(text)                   -> (audio, mime) POST {tts_url}/audio/speech           (json, voice from config)
Audio is never stored. When no URL is set the console uses the browser's own speech features.
"""
from __future__ import annotations

import httpx

from .. import config, keystore

TRANSPORT: httpx.AsyncBaseTransport | None = None


class VoiceError(Exception):
    pass


def _headers(name: str) -> dict:
    key = keystore.get(name)
    return {"Authorization": f"Bearer {key}"} if key else {}


async def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    url = config.load()["voice"]["stt_url"].rstrip("/")
    if not url:
        raise VoiceError("server speech-to-text is not configured; the browser microphone is used instead")
    ext = "mp3" if "mpeg" in mime else "wav" if "wav" in mime else "ogg" if "ogg" in mime else "webm"
    try:
        async with httpx.AsyncClient(timeout=60, transport=TRANSPORT) as c:
            r = await c.post(f"{url}/audio/transcriptions", headers=_headers("voice.stt_key"), data={"model": "whisper-1"}, files={"file": (f"audio.{ext}", audio, mime)})
    except httpx.HTTPError:
        raise VoiceError("could not reach the speech-to-text server") from None
    if r.status_code != 200:
        raise VoiceError(f"speech-to-text failed (HTTP {r.status_code})")
    return str(r.json().get("text", "")).strip()


async def speak(text: str) -> tuple[bytes, str]:
    cfg = config.load()["voice"]
    url = cfg["tts_url"].rstrip("/")
    if not url or not text.strip():
        raise VoiceError("server text-to-speech is not configured; the browser voice is used instead")
    try:
        async with httpx.AsyncClient(timeout=60, transport=TRANSPORT) as c:
            r = await c.post(f"{url}/audio/speech", headers=_headers("voice.tts_key"), json={"model": "tts-1", "input": text, "voice": cfg["tts_voice"]})
    except httpx.HTTPError:
        raise VoiceError("could not reach the text-to-speech server") from None
    if r.status_code != 200:
        raise VoiceError(f"text-to-speech failed (HTTP {r.status_code})")
    return r.content, r.headers.get("content-type", "audio/mpeg")
