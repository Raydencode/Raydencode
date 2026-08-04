"""
Text-to-speech via Piper (https://github.com/rhasspy/piper), a fast local
neural TTS engine.

Piper needs a voice model that is NOT bundled with this repo (they're
50-100MB+ each). To get one:

    1. pip install piper-tts
    2. Download a voice from https://huggingface.co/rhasspy/piper-voices
       e.g. for a decent US English voice:
       https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
       https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
       (you need BOTH the .onnx and the .onnx.json config file, same folder)
    3. Save them to ./models/ (or wherever) and point PIPER_VOICE_MODEL_PATH
       in .env at the .onnx file.

If the model file isn't present, `speak()` prints the text to the console
and logs a warning instead of crashing the app — voice output is a nice-to-
have, not something a missing download should take the whole assistant down
over.
"""

import io
import os
import sys
import wave

import sounddevice as sd
import numpy as np

from config import PIPER_VOICE_MODEL_PATH

_voice = None
_piper_available = False

_PIPER_CONFIG_PATH = PIPER_VOICE_MODEL_PATH + ".json"

try:
    from piper import PiperVoice

    if os.path.isfile(PIPER_VOICE_MODEL_PATH) and os.path.isfile(_PIPER_CONFIG_PATH):
        try:
            _voice = PiperVoice.load(PIPER_VOICE_MODEL_PATH)
            _piper_available = True
            print(f"[voice_output] Piper voice loaded from {PIPER_VOICE_MODEL_PATH}", file=sys.stderr)
        except Exception as e:
            print(
                f"[voice_output] WARNING: Failed to load Piper voice ({e}). "
                "Speech output will fall back to console printing.",
                file=sys.stderr,
            )
    else:
        missing = [
            p for p in (PIPER_VOICE_MODEL_PATH, _PIPER_CONFIG_PATH) if not os.path.isfile(p)
        ]
        print(
            f"[voice_output] WARNING: Piper voice file(s) not found: {', '.join(missing)}. "
            "Speech output will fall back to console printing. See voice_output.py header for "
            "download instructions.",
            file=sys.stderr,
        )
except ImportError:
    print(
        "[voice_output] WARNING: 'piper-tts' package not installed. "
        "Speech output will fall back to console printing. Run `pip install piper-tts` to enable it.",
        file=sys.stderr,
    )


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """Simple linear-interpolation resample — good enough for speech played
    back over speakers, avoids pulling in a new dependency (e.g. scipy)."""
    if orig_rate == target_rate or len(audio) == 0:
        return audio
    duration = len(audio) / orig_rate
    target_len = max(1, int(duration * target_rate))
    orig_x = np.linspace(0, len(audio) - 1, num=len(audio))
    target_x = np.linspace(0, len(audio) - 1, num=target_len)
    return np.interp(target_x, orig_x, audio.astype(np.float64)).astype(np.int16)


def speak(text: str) -> None:
    """Speak `text` aloud via Piper, or print it if Piper isn't configured."""
    if not text:
        return

    if not _piper_available:
        print(f"[ULTRON says]: {text}")
        return

    try:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            _voice.synthesize(text, wav_file)

        buffer.seek(0)
        with wave.open(buffer, "rb") as wav_file:
            audio_bytes = wav_file.readframes(wav_file.getnframes())
            piper_rate = wav_file.getframerate()
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)

        # Play at the output device's own native rate, resampling Piper's
        # audio to match, rather than forcing the device to open a stream
        # at Piper's rate directly — some drivers (older Windows MME in
        # particular) silently produce no/garbled audio instead of erroring
        # when opened at a rate they don't natively support. This mirrors
        # the same fix applied to microphone capture in voice_input.py.
        device_rate = int(sd.query_devices(kind="output")["default_samplerate"])
        playback_audio = _resample(audio_np, piper_rate, device_rate)

        sd.play(playback_audio, device_rate)
        sd.wait()

    except Exception as e:
        print(f"[voice_output] Speech synthesis failed ({e}); falling back to text.", file=sys.stderr)
        print(f"[ULTRON says]: {text}")
