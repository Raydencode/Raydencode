"""
Central configuration for Ultron.

Loads secrets and tunables from a .env file (via python-dotenv) and exposes
them as module-level constants that the rest of the app imports. Fails loudly
and early if a required key is missing, rather than letting some module
discover a blank string three calls deep at runtime.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# --- LLM backend selection ---------------------------------------------------
# Which brain to use. "anthropic" (Claude, paid), "gemini" (Google, free tier,
# no card required), or "ollama" (fully local, free forever, no account at
# all). See brain.py for the per-provider implementations.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
_VALID_PROVIDERS = {"anthropic", "gemini", "ollama"}
if LLM_PROVIDER not in _VALID_PROVIDERS:
    raise EnvironmentError(
        f"Invalid LLM_PROVIDER '{LLM_PROVIDER}' — must be one of {sorted(_VALID_PROVIDERS)}"
    )

# --- Required secrets -------------------------------------------------------
# Keys that Ultron cannot function without. Missing any of these raises at
# import time so the failure happens on startup, not mid-conversation.
# News/weather/search keys are needed regardless of which LLM backend you
# pick; the LLM key requirement depends on LLM_PROVIDER.
REQUIRED_ENV_VARS = ["NEWSAPI_KEY", "OPENWEATHERMAP_KEY", "TAVILY_API_KEY"]
if LLM_PROVIDER == "anthropic":
    REQUIRED_ENV_VARS.append("ANTHROPIC_API_KEY")
elif LLM_PROVIDER == "gemini":
    REQUIRED_ENV_VARS.append("GEMINI_API_KEY")
# ollama needs no API key — it talks to a local server instead.


def _load_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example to .env and fill in {name}, then restart Ultron."
        )
    return value


_missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
if _missing:
    raise EnvironmentError(
        "Ultron cannot start — missing required environment variable(s): "
        + ", ".join(_missing)
        + "\nCopy .env.example to .env and fill in the missing values."
        + ("\n(LLM_PROVIDER=" + LLM_PROVIDER + " — check that matches the key(s) you actually have.)")
    )

NEWSAPI_KEY = _load_required("NEWSAPI_KEY")
OPENWEATHERMAP_KEY = _load_required("OPENWEATHERMAP_KEY")
TAVILY_API_KEY = _load_required("TAVILY_API_KEY")

# Present but possibly empty depending on LLM_PROVIDER — brain.py only
# touches the one it actually needs.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- Optional / tunable settings --------------------------------------------

# Whisper model size: tiny, base, small, medium, large. Bigger = more accurate
# but slower and more memory-hungry. "small" trades a bit of latency for
# meaningfully better accuracy on short/uncommon words (e.g. a wake word
# like "Ultron") than "base" — worth it since misheard wake words are the
# single most common failure mode. Drop to "base" if it's too slow on your
# hardware, or "tiny" if you need it faster still and can live with more
# misses.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")

# Path to a downloaded Piper voice model (.onnx file). See voice_output.py
# and README instructions for how to obtain one. Left unset by default —
# voice_output.py degrades gracefully (console-only) if this doesn't exist.
PIPER_VOICE_MODEL_PATH = os.getenv("PIPER_VOICE_MODEL_PATH", "models/en_US-lessac-medium.onnx")

# Model IDs per provider.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Ollama: fully local LLM server. Install from https://ollama.com, run
# `ollama serve` (or it auto-starts on install), then `ollama pull <model>`
# once before first use. Tool-calling quality depends heavily on the model —
# llama3.1 and qwen2.5 are known to support it reasonably well; many smaller
# models don't support tool calling at all. Defaulting to a smaller model
# (llama3.2, ~3B) over llama3.1 (~8B) trades some accuracy for noticeably
# faster responses on CPU-only hardware — bump back up to llama3.1 if you
# have the hardware to spare and want the more capable model.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Wake word: Ultron ignores everything it hears until a transcribed chunk
# contains this word, then engages. Case-insensitive substring match.
WAKE_WORD = os.getenv("WAKE_WORD", "ultron").lower()

# Dashboard window
DASHBOARD_WINDOW_TITLE = "ULTRON"
DASHBOARD_WIDTH = int(os.getenv("DASHBOARD_WIDTH", "900"))
DASHBOARD_HEIGHT = int(os.getenv("DASHBOARD_HEIGHT", "900"))
DASHBOARD_ALWAYS_ON_TOP = os.getenv("DASHBOARD_ALWAYS_ON_TOP", "false").lower() == "true"
DASHBOARD_FRAMELESS = os.getenv("DASHBOARD_FRAMELESS", "false").lower() == "true"

# Conversation history trimming (see brain.py).
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))

if __name__ == "__main__":
    # Quick sanity check: `python config.py` prints what got loaded (secrets
    # masked) without importing the rest of the app.
    def _mask(v: str) -> str:
        return v[:4] + "..." + v[-4:] if len(v) > 8 else "***"

    print("Ultron config loaded OK", file=sys.stderr)
    print(f"  LLM_PROVIDER = {LLM_PROVIDER}", file=sys.stderr)
    for name in REQUIRED_ENV_VARS:
        print(f"  {name} = {_mask(os.getenv(name, ''))}")
    if LLM_PROVIDER == "gemini":
        print(f"  GEMINI_MODEL = {GEMINI_MODEL}")
    if LLM_PROVIDER == "ollama":
        print(f"  OLLAMA_MODEL = {OLLAMA_MODEL}")
        print(f"  OLLAMA_HOST = {OLLAMA_HOST}")
    print(f"  WHISPER_MODEL_SIZE = {WHISPER_MODEL_SIZE}")
