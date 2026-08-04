"""
voice.py — ElevenLabs speech in and out. The API key lives here and only
here on the server side; it never reaches the browser.

Speech out: POST /v1/text-to-speech/{voice_id}   -> mp3 bytes
Speech in:  POST /v1/speech-to-text (scribe_v1)   -> transcript
"""

import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid

API_BASE = "https://api.elevenlabs.io"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs' public "Rachel" voice


def _api_key() -> str | None:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    return key or None


def is_configured() -> bool:
    return _api_key() is not None


def text_to_speech(text: str) -> tuple[bytes | None, str | None]:
    """Returns (mp3_bytes, error). Exactly one of the two is set."""
    key = _api_key()
    if not key:
        return None, "ELEVENLABS_API_KEY not set — add it to .env"

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    url = f"{API_BASE}/v1/text-to-speech/{voice_id}"
    payload = json.dumps({
        "text": text,
        "model_id": os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_turbo_v2_5"),
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read(), None
    except urllib.error.HTTPError as e:
        return None, f"ElevenLabs TTS error {e.code}: {e.read().decode(errors='ignore')[:200]}"
    except urllib.error.URLError as e:
        return None, f"ElevenLabs unreachable: {e.reason}"


def speech_to_text(audio_bytes: bytes, filename: str = "audio.webm") -> tuple[str | None, str | None]:
    """Returns (transcript, error). Exactly one of the two is set."""
    key = _api_key()
    if not key:
        return None, "ELEVENLABS_API_KEY not set — add it to .env"

    url = f"{API_BASE}/v1/speech-to-text"
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "audio/webm"

    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="model_id"\r\n\r\nscribe_v1\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'.encode()
    )
    parts.append(audio_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return result.get("text", ""), None
    except urllib.error.HTTPError as e:
        return None, f"ElevenLabs STT error {e.code}: {e.read().decode(errors='ignore')[:200]}"
    except urllib.error.URLError as e:
        return None, f"ElevenLabs unreachable: {e.reason}"
