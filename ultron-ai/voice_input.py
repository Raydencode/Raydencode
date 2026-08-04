"""
Microphone capture + local speech-to-text via Whisper.

The Whisper model is loaded once at import time (module-level), not inside
transcribe(), because loading it is the slow part (seconds, and real RAM) —
reloading per-call would make every single utterance sluggish.
"""

import queue
import sys
import tempfile
import wave

import numpy as np
import sounddevice as sd
import whisper

from config import WHISPER_MODEL_SIZE

SAMPLE_RATE = 16_000  # Whisper's native rate
CHANNELS = 1

print(f"[voice_input] Loading Whisper model '{WHISPER_MODEL_SIZE}'...", file=sys.stderr)
_whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
print("[voice_input] Whisper model loaded.", file=sys.stderr)


def record_audio(should_continue) -> str:
    """
    Record audio from the default microphone until `should_continue()` returns
    False (e.g. the push-to-talk key has been released). Saves to a temp WAV
    file and returns its path.

    `should_continue` is a zero-arg callable so the caller controls exactly
    when recording stops (typically "is the wake key still held down").
    """
    audio_queue: queue.Queue = queue.Queue()

    def _callback(indata, frames, time_info, status):
        if status:
            print(f"[voice_input] stream status: {status}", file=sys.stderr)
        audio_queue.put(indata.copy())

    frames = []
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", callback=_callback):
        while should_continue():
            try:
                frames.append(audio_queue.get(timeout=0.1))
            except queue.Empty:
                continue

    if not frames:
        raise RuntimeError("No audio captured — was the key held long enough?")

    audio_data = np.concatenate(frames, axis=0)

    tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp_file.name, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())

    return tmp_file.name


def transcribe(audio_path: str) -> str:
    """Transcribe a WAV file to text using the pre-loaded Whisper model."""
    result = _whisper_model.transcribe(audio_path, fp16=False)
    return result.get("text", "").strip()
