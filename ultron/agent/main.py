#!/usr/bin/env python3
"""
main.py — ULTRON's HTTP server + API. Python standard library only.

Run: python3 main.py
Serves the UI and API on http://localhost:8420 by default.
"""

import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ULTRON_ROOT = AGENT_DIR.parent
UI_DIR = ULTRON_ROOT / "ui"

sys.path.insert(0, str(AGENT_DIR))

import data          # noqa: E402
import memory        # noqa: E402
import tools         # noqa: E402
import voice         # noqa: E402

PORT = int(os.environ.get("ULTRON_PORT", "8420"))
HISTORY_TURNS = 10


# ---------------------------------------------------------------------------
# .env loading — no third-party dotenv package, just a tiny parser.
# ---------------------------------------------------------------------------

def load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


load_dotenv(ULTRON_ROOT / ".env")


# ---------------------------------------------------------------------------
# LLM — optional. Everything must keep working if this is unreachable.
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def call_llm(system: str, messages: list[dict]) -> tuple[str | None, str | None]:
    """Returns (reply, error). Never raises."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None, "no ANTHROPIC_API_KEY configured"

    payload = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 400,
        "system": system,
        "messages": messages,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload, method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
            return text.strip() or None, None
    except urllib.error.HTTPError as e:
        return None, f"Anthropic API error {e.code}"
    except urllib.error.URLError as e:
        return None, f"Anthropic unreachable: {e.reason}"


# ---------------------------------------------------------------------------
# Routing — must work with zero LLM. Keyword + vault-overlap scoring.
# ---------------------------------------------------------------------------

GREETING_RE = re.compile(
    r"^(hi|hey|hello|yo|sup|good\s?(morning|afternoon|evening)|"
    r"can you hear me|are you there|you (there|awake)|test(ing)?|"
    r"what('?s| is) up|how('?s| is) it going|how are you)\b", re.I
)
FOLLOWUP_RE = re.compile(
    r"^(why\??|why is that\??|go on\.?|and\??|what about (it|that|the .+)\??|"
    r"what do you (mean|think)\??|really\??|tell me more\.?)$", re.I
)

REMEMBER_RE = re.compile(r"^\s*(remember|note)\b[:\s]+(that\s+)?(.+)$", re.I)
PLAN_RE = re.compile(r"\b(plan (my|the) day|what should i (work on|do)|priorit(y|ies) today)\b", re.I)
BRIEF_RE = re.compile(r"\b(brief me|catch me up|morning brief|what'?s going on|what slipped)\b", re.I)
INBOX_RE = re.compile(r"\b(inbox|unread|any (new )?emails?)\b", re.I)
WEB_RE = re.compile(r"\b(look up|search (the web|online)|google|what does .+ cost|how much (does|is|do))\b", re.I)


def classify(message: str, history: list[dict]) -> str | None:
    """Returns a tool name, or None for plain conversation."""
    msg = message.strip()
    if not msg:
        return None
    if GREETING_RE.search(msg) or FOLLOWUP_RE.match(msg) or len(msg.split()) <= 2:
        return None
    if REMEMBER_RE.match(msg):
        return "remember"
    if PLAN_RE.search(msg):
        return "plan_day"
    if BRIEF_RE.search(msg):
        return "brief_me"
    if INBOX_RE.search(msg):
        return "read_inbox"
    if WEB_RE.search(msg):
        return "research_web"

    # score against the vault: does this look like it's asking about
    # something that actually lives in the files?
    vault = data.get_vault()
    hits = vault.search(msg, limit=3)
    if hits and hits[0]["score"] >= 5:
        return "search_brain"

    # question-shaped but nothing in the vault, and not caught above ->
    # treat as conversation rather than guessing a tool.
    return None


def run_tool(name: str, message: str) -> dict:
    if name == "remember":
        m = REMEMBER_RE.match(message.strip())
        fact = m.group(3) if m else message
        return tools.remember(fact)
    if name == "plan_day":
        return tools.plan_day()
    if name == "brief_me":
        return tools.brief_me()
    if name == "read_inbox":
        return tools.read_inbox()
    if name == "research_web":
        return tools.research_web(message)
    if name == "search_brain":
        return tools.search_brain(message)
    raise ValueError(f"unknown tool {name}")


def conversational_reply(message: str, history: list[dict]) -> tuple[str, bool]:
    """Returns (speech, model_used)."""
    if not llm_available():
        if GREETING_RE.search(message.strip()):
            return "Yeah, I'm here.", False
        return ("No model connected, so I can't chat freely — set ANTHROPIC_API_KEY in .env. "
                "I can still search, brief, plan, or remember."), False

    claude_md = _read_claude_md()
    system_prompt = _read_prompt_md()
    system = f"{system_prompt}\n\n---\n\n{claude_md}"

    llm_messages = []
    for turn in history[-HISTORY_TURNS:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        content = turn.get("content", "")
        if content:
            llm_messages.append({"role": role, "content": content})
    llm_messages.append({"role": "user", "content": message})

    reply, err = call_llm(system, llm_messages)
    if err or not reply:
        return f"Model's unreachable right now ({err}).", False
    return reply, True


def _read_claude_md() -> str:
    path = ULTRON_ROOT / "CLAUDE.md"
    return path.read_text(encoding="utf-8") if path.exists() else "(no CLAUDE.md found)"


def _read_prompt_md() -> str:
    path = AGENT_DIR / "prompt.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[ultron] {self.address_string()} {fmt % args}\n")

    # -- helpers ----------------------------------------------------------

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return {}

    def _serve_static(self, rel_path: str):
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        file_path = (UI_DIR / rel_path).resolve()
        if UI_DIR not in file_path.parents and file_path != UI_DIR:
            self._send_json({"error": "forbidden"}, 403)
            return
        if not file_path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        ctype = STATIC_TYPES.get(file_path.suffix, mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
        self._send_bytes(file_path.read_bytes(), ctype)

    # -- GET ----------------------------------------------------------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            vault = data.get_vault()
            self._send_json({
                "mode": data.mode_label(),
                "llm_available": llm_available(),
                "elevenlabs_available": voice.is_configured(),
                "stats": vault.stats(),
            })
            return

        if path == "/api/graph":
            self._send_json(data.get_vault().graph_payload())
            return

        if path == "/api/note":
            qs = urllib.parse.parse_qs(parsed.query)
            note_id = (qs.get("id") or [""])[0]
            note = data.get_vault().get_note(note_id)
            if note is None:
                self._send_json({"error": "not found"}, 404)
            else:
                self._send_json(note)
            return

        if path == "/api/hubs":
            self._send_json({"hubs": data.get_vault().top_hubs(10)})
            return

        if path == "/api/memory":
            self._send_json({"memories": memory.list_memories()})
            return

        if path.startswith("/api/"):
            self._send_json({"error": "not found"}, 404)
            return

        self._serve_static(path)

    # -- POST ----------------------------------------------------------

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/chat":
            self._handle_chat()
            return

        if path == "/api/speak":
            self._handle_speak()
            return

        if path == "/api/listen":
            self._handle_listen()
            return

        if path == "/api/reload":
            data.get_vault(force_reload=True)
            self._send_json({"ok": True, "stats": data.get_vault().stats()})
            return

        self._send_json({"error": "not found"}, 404)

    def _handle_chat(self):
        body = self._read_json_body()
        message = (body.get("message") or "").strip()
        history = body.get("history") or []

        if not message:
            self._send_json({"error": "empty message"}, 400)
            return

        tool_name = classify(message, history)
        if tool_name:
            try:
                result = run_tool(tool_name, message)
            except Exception as e:
                self._send_json({
                    "speech": f"That tool hit an error: {e}",
                    "card": {"tool": tool_name, "error": str(e)},
                    "tool": tool_name,
                    "model_used": False,
                })
                return
            result["tool"] = tool_name
            result["model_used"] = False
            self._send_json(result)
            return

        speech, model_used = conversational_reply(message, history)
        self._send_json({
            "speech": speech,
            "card": None,
            "tool": None,
            "model_used": model_used,
        })

    def _handle_speak(self):
        body = self._read_json_body()
        text = (body.get("text") or "").strip()
        if not text:
            self._send_json({"error": "empty text"}, 400)
            return
        audio, err = voice.text_to_speech(text)
        if err:
            self._send_json({"error": err}, 503)
            return
        self._send_bytes(audio, "audio/mpeg")

    def _handle_listen(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send_json({"error": "empty audio"}, 400)
            return
        audio_bytes = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "audio/webm")
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".webm"
        transcript, err = voice.speech_to_text(audio_bytes, filename=f"audio{ext}")
        if err:
            self._send_json({"error": err}, 503)
            return
        self._send_json({"transcript": transcript})


def main():
    vault = data.get_vault()
    print(f"ULTRON — mode: {data.mode_label()}")
    vault.print_report()
    print(f"LLM: {'connected' if llm_available() else 'not configured (routing still works)'}")
    print(f"ElevenLabs voice: {'connected' if voice.is_configured() else 'not configured'}")
    print(f"\nServing on http://localhost:{PORT}\n")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
