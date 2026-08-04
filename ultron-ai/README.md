# ULTRON

A local desktop AI assistant: a cinematic animated HUD (pywebview), push-to-talk
voice input (Whisper), local voice output (Piper), computer control, and live
news/weather/search via Claude tool use.

## Project layout

```
ultron-ai/
├── main.py              # orchestration: HUD window + listen/think/act/speak loop
├── config.py             # env var loading + constants
├── brain.py               # Claude tool-use loop, Ultron's personality
├── voice_input.py         # mic capture + Whisper transcription
├── voice_output.py        # Piper text-to-speech
├── computer_control.py    # open_app, run_command, list_files, read_file, system info
├── data_sources.py        # NewsAPI, OpenWeatherMap, Tavily
├── requirements.txt
├── .env.example
└── dashboard/
    ├── index.html
    ├── style.css
    └── script.js
```

## 1. Install dependencies

### OS-level dependencies (install these first)

**Linux (Debian/Ubuntu):**
```bash
sudo apt install ffmpeg portaudio19-dev libwebkit2gtk-4.1-dev python3-gi
```

**macOS:**
```bash
brew install ffmpeg portaudio
```
(WebView is built into macOS — no extra install needed.)

**Windows:**
- Install [ffmpeg](https://ffmpeg.org/download.html) and add it to your PATH.
- PortAudio ships with the `sounddevice` wheel — nothing extra needed.
- WebView2 runtime is preinstalled on modern Windows 10/11.

### Python dependencies

```bash
cd ultron-ai
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Notes:
- `openai-whisper` downloads its model weights on first use (see step 4).
- The `keyboard` library needs elevated permissions on Linux (raw input
  access). If it can't initialize, Ultron automatically falls back to
  console push-to-talk (press Enter instead of holding Space).

## 2. Download and configure a Piper voice model

Piper needs a voice model that isn't bundled with this repo.

1. Pick a voice from the [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
   repo on Hugging Face. A solid default US English voice:
   - `en_US-lessac-medium.onnx`
   - `en_US-lessac-medium.onnx.json`
2. Download **both** files into a `models/` folder in the project root:
   ```bash
   mkdir -p models
   curl -L -o models/en_US-lessac-medium.onnx \
     https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
   curl -L -o models/en_US-lessac-medium.onnx.json \
     https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
   ```
3. Point `PIPER_VOICE_MODEL_PATH` in your `.env` at the `.onnx` file (the
   default already matches the path above).

If you skip this, Ultron still runs — it just prints its responses to the
console instead of speaking them.

## 3. Fill in `.env`

```bash
cp .env.example .env
```

Then edit `.env` and fill in:
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com/) → API Keys
- `NEWSAPI_KEY` — free key from [newsapi.org/register](https://newsapi.org/register)
- `OPENWEATHERMAP_KEY` — free key from [home.openweathermap.org](https://home.openweathermap.org/users/sign_up) (can take up to ~2 hours to activate)
- `TAVILY_API_KEY` — free key from [tavily.com](https://tavily.com)

## 4. Run it

```bash
python main.py
```

First run will download the Whisper model (`base` by default, ~150MB) —
this only happens once. The HUD window opens; hold **Space** (or press
Enter, if `keyboard` isn't available) and speak, then release to send.

## 5. What to test first

1. **Config loads** — run `python config.py` first; it prints masked keys
   and exits cleanly if everything is set.
2. **Silent smoke test** — launch `python main.py`, confirm the HUD renders
   (glowing core, rotating rings, "IDLE" status) before touching the mic.
3. **One voice round-trip** — hold the wake key, ask something simple like
   "what's the weather in Seattle", release, and confirm you see
   LISTENING → THINKING → SPEAKING → IDLE and a weather card appears.
4. **A tool call with no card** (e.g. "what's my CPU usage") to confirm
   `computer_control.py` works end to end.

### Common first-run errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `EnvironmentError: Missing required environment variable` | `.env` not filled in or not found | Confirm `.env` exists next to `main.py` and has all 4 keys |
| App exits immediately with an `ImportError` for `keyboard` on Linux | No permission to read raw input devices | Run with `sudo`, or add your user to the `input` group + a udev rule, or just let it fall back to console mode |
| Mic seems to record nothing / `RuntimeError: No audio captured` | Wrong default input device, or OS mic permission denied | Check `python -m sounddevice` lists your mic; on macOS grant Terminal/Python mic access in System Settings → Privacy |
| Long pause with no output on first launch | Whisper is downloading model weights | Wait it out once; it's cached under `~/.cache/whisper` after |
| `[voice_output] WARNING: Piper voice model not found` | Didn't download the `.onnx`/`.onnx.json` pair, or path is wrong | Re-check step 2; Ultron still works without it, just text-only |
| Blank/white HUD window on Linux | Missing WebKitGTK | Install `libwebkit2gtk-4.1-dev` (or `-4.0` on older distros) |
| `get_weather`/`get_news` returns an error card immediately | API key not yet active, or rate-limited | OpenWeatherMap keys can take ~2 hours to activate after signup; check your NewsAPI daily quota |
