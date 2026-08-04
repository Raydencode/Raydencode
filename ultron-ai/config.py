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

# --- Required secrets -------------------------------------------------------
# Keys that Ultron cannot function without. Missing any of these raises at
# import time so the failure happens on startup, not mid-conversation.
REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "NEWSAPI_KEY",
    "OPENWEATHERMAP_KEY",
    "TAVILY_API_KEY",
]


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
    )

ANTHROPIC_API_KEY = _load_required("ANTHROPIC_API_KEY")
NEWSAPI_KEY = _load_required("NEWSAPI_KEY")
OPENWEATHERMAP_KEY = _load_required("OPENWEATHERMAP_KEY")
TAVILY_API_KEY = _load_required("TAVILY_API_KEY")

# --- Optional / tunable settings --------------------------------------------

# Whisper model size: tiny, base, small, medium, large. Bigger = more accurate
# but slower and more memory-hungry. "base" is a reasonable default on a
# laptop CPU.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

# Path to a downloaded Piper voice model (.onnx file). See voice_output.py
# and README instructions for how to obtain one. Left unset by default —
# voice_output.py degrades gracefully (console-only) if this doesn't exist.
PIPER_VOICE_MODEL_PATH = os.getenv("PIPER_VOICE_MODEL_PATH", "models/en_US-lessac-medium.onnx")

# Anthropic model used by brain.py.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Dashboard window
DASHBOARD_WINDOW_TITLE = "ULTRON"
DASHBOARD_WIDTH = int(os.getenv("DASHBOARD_WIDTH", "900"))
DASHBOARD_HEIGHT = int(os.getenv("DASHBOARD_HEIGHT", "900"))
DASHBOARD_ALWAYS_ON_TOP = os.getenv("DASHBOARD_ALWAYS_ON_TOP", "false").lower() == "true"
DASHBOARD_FRAMELESS = os.getenv("DASHBOARD_FRAMELESS", "false").lower() == "true"

# Push-to-talk key, as understood by the `keyboard` library (e.g. "space",
# "right ctrl", "f9").
WAKE_KEY = os.getenv("WAKE_KEY", "space")

# Conversation history trimming (see brain.py).
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))

if __name__ == "__main__":
    # Quick sanity check: `python config.py` prints what got loaded (secrets
    # masked) without importing the rest of the app.
    def _mask(v: str) -> str:
        return v[:4] + "..." + v[-4:] if len(v) > 8 else "***"

    print("Ultron config loaded OK", file=sys.stderr)
    for name in REQUIRED_ENV_VARS:
        print(f"  {name} = {_mask(os.getenv(name, ''))}")
    print(f"  WHISPER_MODEL_SIZE = {WHISPER_MODEL_SIZE}")
    print(f"  ANTHROPIC_MODEL = {ANTHROPIC_MODEL}")
    print(f"  WAKE_KEY = {WAKE_KEY}")
