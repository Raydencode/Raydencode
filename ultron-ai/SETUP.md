# ULTRON — Full Setup Guide

This is the detailed, no-assumptions walkthrough: install, configure, and run
Ultron for the first time, plus a troubleshooting table for the errors you're
most likely to hit.

---

## 0. Prerequisites

- **Python 3.10 or newer** (`python3 --version` to check — 3.11 is a safe
  choice). Whisper, Piper, and pywebview all work best on recent Python.
- **A working microphone and speakers**, recognized by your OS.
- **~2GB free disk** (Whisper model + Piper voice model + Python deps add up).
- Accounts (all free-tier) at: Anthropic, NewsAPI, OpenWeatherMap, Tavily.
  You'll create API keys for each in Step 3.

---

## 1. Get the code into VS Code

1. Download the zip attached to this conversation and unzip it — you'll get
   an `ultron-ai/` folder.
2. Open VS Code → **File → Open Folder…** → select `ultron-ai/`.
3. Open a terminal inside VS Code: **Terminal → New Terminal** (it opens
   already rooted in `ultron-ai/`).
4. (Recommended) Install the **Python extension** for VS Code if you don't
   have it — Extensions panel, search "Python" (Microsoft), install. This
   gives you interpreter selection, linting, and debugging.

---

## 2. Install dependencies

### 2a. OS-level dependencies (do this first — pip can't install these)

**Linux (Debian/Ubuntu/Mint):**
```bash
sudo apt update
sudo apt install ffmpeg portaudio19-dev libwebkit2gtk-4.1-dev python3-gi
```
If `libwebkit2gtk-4.1-dev` isn't found on your distro version, try
`libwebkit2gtk-4.0-dev` instead.

**macOS:**
```bash
# Install Homebrew first if you don't have it: https://brew.sh
brew install ffmpeg portaudio
```
WebView is built into macOS (Cocoa/WebKit) — nothing extra to install there.

**Windows:**
1. Download ffmpeg from https://ffmpeg.org/download.html (or via
   `winget install ffmpeg`), and make sure `ffmpeg.exe` is on your PATH
   (test with `ffmpeg -version` in a new terminal).
2. PortAudio ships bundled inside the `sounddevice` pip wheel — no separate
   install needed.
3. WebView2 runtime is preinstalled on modern Windows 10/11. If
   `pywebview` complains it's missing, get it from
   https://developer.microsoft.com/microsoft-edge/webview2/.

### 2b. Python virtual environment + packages

In the VS Code terminal, inside `ultron-ai/`:

```bash
python -m venv .venv
```

Activate it:
```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd.exe)
.venv\Scripts\activate.bat
```

Your terminal prompt should now show `(.venv)` at the start of the line. In
VS Code, also select this interpreter: **Ctrl+Shift+P → "Python: Select
Interpreter" → pick the one under `.venv`** so the editor's linting/IntelliSense
matches what you actually run.

Now install everything:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will take a few minutes — `openai-whisper` pulls in PyTorch, which is
a large download. If `pip install` fails partway through with a compiler
error on `piper-tts` or `pyaudio`-adjacent packages, it almost always means
one of the OS-level deps from step 2a is missing — re-check that step.

---

## 3. Choose your LLM backend, then get your API keys

Ultron's "brain" is pluggable — pick ONE of these three for `LLM_PROVIDER`:

| Provider | Cost | Card required? | Notes |
|---|---|---|---|
| `anthropic` | Paid (small per-token cost) | Yes, eventually (small starting credit grant on new accounts) | Best quality/reliability |
| `gemini` | Free tier | **No** | Recommended free option — solid tool-use support |
| `ollama` | Free forever | **No**, no account at all | Fully offline/local; needs a capable PC; tool-use less reliable than the cloud options |

Regardless of which brain you pick, you still need three small free-tier
keys for news/weather/search (all no-card signups):

| Service | Used for | Where to get it | Free tier |
|---|---|---|---|
| NewsAPI | `get_news` tool | https://newsapi.org/register | 100 requests/day, dev tier |
| OpenWeatherMap | `get_weather` tool | https://home.openweathermap.org/users/sign_up → **API keys** tab | 1,000 calls/day. **New keys can take up to ~2 hours to activate** — if weather calls fail immediately after signup, this is why |
| Tavily | `web_search` tool | https://tavily.com → sign up → dashboard shows your key | 1,000 searches/month |

Then, depending on which brain you picked:

- **`anthropic`**: https://console.anthropic.com/ → **API Keys** → Create Key
- **`gemini`**: https://aistudio.google.com/apikey → Create API key (no card, just a Google account)
- **`ollama`**: no key — instead, install the app:
  1. Download and install from https://ollama.com
  2. It runs a local server automatically after install (or run `ollama serve` yourself)
  3. Pull a model that supports tool calling: `ollama pull llama3.1`
     (this downloads ~4.7GB — needs a reasonably capable PC, 8GB+ RAM minimum)

Copy each key somewhere safe as you create it — you'll paste them into
`.env` next.

---

## 4. Configure `.env`

In the terminal:
```bash
cp .env.example .env
```

Open `.env` in VS Code and set `LLM_PROVIDER` to your choice, then fill in
only the keys that provider needs, plus the three always-required ones:

```ini
LLM_PROVIDER=gemini

# only needed if LLM_PROVIDER=anthropic:
# ANTHROPIC_API_KEY=sk-ant-...your real key...

# only needed if LLM_PROVIDER=gemini:
GEMINI_API_KEY=...your real key...

# only needed if LLM_PROVIDER=ollama: nothing here, just OLLAMA_MODEL/OLLAMA_HOST
# defaults (llama3.1 @ localhost:11434) work if you followed step 3 as-is

NEWSAPI_KEY=...your real key...
OPENWEATHERMAP_KEY=...your real key...
TAVILY_API_KEY=tvly-...your real key...
```

Leave everything else commented out unless you want to change a default
(voice model path, window size, wake key, etc.).

**Do not commit `.env`** — it's already in `.gitignore`, but double check if
you're pushing this to your own repo.

Sanity-check it loaded correctly:
```bash
python config.py
```
Expected output (example for `LLM_PROVIDER=gemini`):
```
Ultron config loaded OK
  LLM_PROVIDER = gemini
  NEWSAPI_KEY = 1234...5678
  OPENWEATHERMAP_KEY = abcd...wxyz
  TAVILY_API_KEY = tvly...9999
  GEMINI_API_KEY = AIza...xxxx
  GEMINI_MODEL = gemini-2.0-flash
  WHISPER_MODEL_SIZE = base
  WAKE_KEY = space
```
If instead you get `EnvironmentError: Missing required environment
variable`, one of the required keys for your chosen `LLM_PROVIDER` is still
blank, or the file isn't named exactly `.env` (not `.env.txt` — watch out
for Windows hiding extensions). If you picked `ollama`, also make sure the
Ollama app is actually running before you launch Ultron — `config.py` won't
catch that (there's no key to check), but `main.py` will error clearly if it
can't reach it.

---

## 5. Download a Piper voice model (for spoken output)

Piper (text-to-speech) needs a voice model that isn't bundled with this
project — it's a ~60MB download you fetch once.

```bash
mkdir -p models

# macOS/Linux
curl -L -o models/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o models/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

On Windows PowerShell, use `Invoke-WebRequest` instead:
```powershell
mkdir models
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" -OutFile "models/en_US-lessac-medium.onnx"
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" -OutFile "models/en_US-lessac-medium.onnx.json"
```

You need **both** files (the `.onnx` model and its `.onnx.json` config) in
the same folder. The default `PIPER_VOICE_MODEL_PATH` in `config.py` already
points at `models/en_US-lessac-medium.onnx`, so if you used the paths above
you don't need to change anything in `.env`.

Want a different voice/accent? Browse
https://huggingface.co/rhasspy/piper-voices — there are dozens (US/UK/AU
English, and many other languages). Download the matching `.onnx` +
`.onnx.json` pair and update `PIPER_VOICE_MODEL_PATH` in `.env` accordingly.

**This step is optional.** If you skip it, Ultron runs fine — it just
prints its replies to the terminal (`[ULTRON says]: ...`) instead of
speaking them, and logs a warning on startup telling you it's in that mode.

---

## 6. Run it

```bash
python main.py
```

What happens on first launch:
1. Whisper downloads its model weights (`base` size, ~150MB) to
   `~/.cache/whisper/` — one-time, can take a minute or two depending on
   your connection. Subsequent launches are instant.
2. The HUD window opens: black background, glowing red "ULTRON" core,
   rotating rings, status text reading `IDLE`.
3. In the terminal you'll see `Ultron ready. Hold 'space' to talk.`

**To talk to it:** press and hold **Space**, speak your request, then
release. Watch the status text cycle `LISTENING` → `THINKING` →
`SPEAKING` → `IDLE`. If `keyboard` couldn't get global key access (see
troubleshooting table), it instead prompts `Press ENTER to talk to
Ultron...` in the terminal — press Enter, then speak for up to ~4 seconds.

Try starting simple:
- "What's the weather in \[your city\]?" → should pop a weather card, top right.
- "Give me the latest news on \[topic\]" → news card, top left.
- "Search the web for \[something\]" → search card, bottom center.
- "What's my CPU usage?" → system card, bottom right.
- "Open \[some app you have installed\]" → launches it, no card (just a spoken confirmation).

To quit: close the HUD window, or `Ctrl+C` in the terminal.

---

## 7. Test order (recommended)

Do these in order — each isolates a different subsystem, so if something
breaks you know exactly where:

1. **`python config.py`** — confirms your `.env` is valid before touching
   anything else.
2. **Launch with mic untouched** — `python main.py`, just watch the HUD
   render (core, rings, IDLE status) and confirm no exceptions in the
   terminal. This isolates pywebview / dashboard issues from voice issues.
3. **One full voice round trip** — hold Space, ask for the weather
   somewhere real, release. Confirms mic capture → Whisper → Claude →
   OpenWeatherMap → Piper (or console fallback) all work together.
4. **A tool call with no card** — ask for CPU usage or to open an app, to
   confirm `computer_control.py` independently of the news/weather/search
   cards.
5. **A deliberately vague/conversational message** — "how's it going" —
   with no tool call, to confirm Claude's plain personality responses work
   without the tool-use loop.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `EnvironmentError: Missing required environment variable: X` | `.env` missing, misnamed, or that key left blank | Confirm the file is literally named `.env` in `ultron-ai/`, and every one of the 4 required keys has a real value |
| Crash on startup with `ImportError` related to `keyboard`, or push-to-talk never triggers | On Linux, `keyboard` needs raw `/dev/input` access, usually root | Run `sudo python main.py`, **or** add your user to the `input` group and set up a udev rule, **or** just accept the automatic console (Enter-key) fallback — it's fully functional, just less "hands-free" |
| `RuntimeError: No audio captured — was the key held long enough?` | Wrong default input device selected by the OS, mic muted, or OS denied mic access | Run `python -m sounddevice` to list devices and confirm your mic shows up; on macOS check **System Settings → Privacy & Security → Microphone** and allow your terminal/VS Code; on Windows check **Settings → Privacy → Microphone** |
| App hangs for a long time with no HUD window on first launch | Whisper is downloading its model in the background | Just wait — check your terminal for download progress; cached after this under `~/.cache/whisper/` |
| `[voice_output] WARNING: Piper voice model not found at ...` | Skipped or mis-pathed step 5 | Re-download the `.onnx` + `.onnx.json` pair into `models/`, or update `PIPER_VOICE_MODEL_PATH` in `.env` to match wherever you put them |
| `[voice_output] WARNING: 'piper-tts' package not installed` | `pip install -r requirements.txt` didn't fully succeed | Re-run `pip install piper-tts` inside your activated venv and check for errors |
| Blank white HUD window on Linux | Missing WebKitGTK runtime | Install `libwebkit2gtk-4.1-dev` (or `-4.0-dev` on older distros) and relaunch |
| `pywebview` fails to launch at all on Windows | Missing WebView2 runtime (rare on modern Windows) | Install from https://developer.microsoft.com/microsoft-edge/webview2/ |
| Weather/news/search card shows an error message immediately | API key not active yet, wrong key, or rate-limited | OpenWeatherMap keys can take ~2 hours after signup to start working; double-check you copied the whole key with no extra spaces; check your NewsAPI/Tavily dashboard for remaining quota |
| `pip install` fails building `piper-tts` or `sounddevice`/`pyaudio`-related package | Missing OS-level dev headers | Re-run step 2a for your OS — this is almost always a missing `portaudio`/build-tools issue |
| Claude responses feel cut off mid-sentence | Hit `max_tokens=1024` in `brain.py` | Bump `max_tokens` in the `client.messages.create(...)` call if you want longer replies (tradeoff: slower + costs more per call) |
| Ultron runs a shell command you didn't expect | `run_command` tool triggered by your phrasing | This is expected — Claude decides when to use `run_command`. The blocklist in `computer_control.py` only stops a short list of catastrophic patterns (`rm -rf /`, `shutdown`, etc.); it is **not** a full sandbox. Don't run Ultron with more system privilege than you're comfortable granting it |

---

## 9. Where to go from here

- Change personality/tone: edit `SYSTEM_PROMPT` in `brain.py`.
- Add a new tool: define it in `TOOLS` in `brain.py`, add a handler function
  (in `computer_control.py` or `data_sources.py`), and register it in
  `_TOOL_DISPATCH`.
- Change the wake key: set `WAKE_KEY` in `.env` (any key name the
  `keyboard` library understands, e.g. `right ctrl`, `f9`).
- Restyle the HUD: it's plain CSS in `dashboard/style.css` — no build step,
  just edit and reload.
