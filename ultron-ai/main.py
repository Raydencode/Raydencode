"""
Ultron entry point: boots the pywebview HUD window and runs a continuous
listen -> transcribe -> think -> act -> speak loop in a background thread.

Listening is always-on — there's no push-to-talk key. The HUD's mute button
(wired to `UltronApp.set_mute` below via pywebview's js_api) lets the user
pause the microphone entirely instead.

This project originally used the `keyboard` library for global push-to-talk
key detection. That approach was dropped: `keyboard` works by installing a
system-wide keyboard hook, which is the exact technique real keyloggers use,
and on some machines that gets flagged and blocked by antivirus/endpoint
security software. Always-on listening with an explicit mute button needs no
global hook at all, so it sidesteps that class of problem entirely — at the
cost of not being true push-to-talk.

Note this is fixed-length chunked listening, not real voice-activity
detection: each cycle records for LISTEN_CHUNK_SECONDS, transcribes, and
either acts on it or discards it if nothing intelligible came through (which
is the common case for a silent/quiet chunk — Whisper just returns an empty
string). Long sentences can get cut off at a chunk boundary; pausing briefly
between requests works better than talking continuously.

Wake-word gating: Ultron only engages the LLM after it transcribes a chunk
containing WAKE_WORD (default "ultron") — everything else is discarded
silently. There's no dedicated low-power wake-word engine here (that'd mean
a new always-on native dependency); instead every chunk is transcribed with
Whisper and checked for the wake word, which is heavier than a purpose-built
wake-word model but avoids adding one. If the wake word is heard with little
or nothing useful after it (e.g. just "hey Ultron"), one extra chunk is
recorded immediately to capture the actual request.

The wake-word check is fuzzy, not an exact match: a quiet mic + an uncommon
proper noun means Whisper regularly mishears "Ultron" as something close
but not identical ("Oltron", "Ultrone", ...). Each transcribed word (and
adjacent word-pairs, in case Whisper splits it into two tokens) is scored
against the wake word with difflib's similarity ratio; anything at or above
WAKE_WORD_FUZZY_THRESHOLD counts. The threshold is deliberately conservative
(0.6) — looser than that and ordinary words ("cutout", "python") start
scoring similarly to genuine near-misses, causing false activations.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import threading
import time
import traceback

import webview

import brain
import config
import voice_input
import voice_output

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("ultron")

LISTEN_CHUNK_SECONDS = float(os.getenv("LISTEN_CHUNK_SECONDS", "3.5"))
FOLLOWUP_CHUNK_SECONDS = float(os.getenv("FOLLOWUP_CHUNK_SECONDS", "6"))
WAKE_WORD_FUZZY_THRESHOLD = float(os.getenv("WAKE_WORD_FUZZY_THRESHOLD", "0.6"))


def _find_wake_word_end(text: str, wake_word: str, threshold: float) -> int | None:
    """Fuzzy-scan `text` for `wake_word`. Checks each word, and each pair of
    adjacent words joined together (covers Whisper splitting the wake word
    into two tokens). Returns the character index right after the match, or
    None if nothing scored high enough."""
    tokens = list(re.finditer(r"\S+", text))
    for i, tok in enumerate(tokens):
        word = tok.group().strip(".,!?;:\"'").lower()
        if difflib.SequenceMatcher(None, word, wake_word).ratio() >= threshold:
            return tok.end()
        if i + 1 < len(tokens):
            next_word = tokens[i + 1].group().strip(".,!?;:\"'").lower()
            combo = word + next_word
            if difflib.SequenceMatcher(None, combo, wake_word).ratio() >= threshold:
                return tokens[i + 1].end()
    return None


class UltronApp:
    """Also serves as the pywebview js_api object — the dashboard's mute
    button calls `pywebview.api.set_mute(bool)`, which lands on `set_mute`
    below directly."""

    def __init__(self):
        self.window: webview.Window | None = None
        self.history: list = []
        self.muted = False
        self._stop_event = threading.Event()

    # -- JS API (called from dashboard/script.js) ---------------------------

    def set_mute(self, muted: bool):
        self.muted = bool(muted)
        log.info("Microphone %s", "muted" if self.muted else "unmuted")
        if self.muted:
            self.set_status("muted")

    # -- JS bridge helpers (Python calling into the dashboard) --------------

    def _call_js(self, fn_call: str):
        if self.window is None:
            return
        try:
            self.window.evaluate_js(fn_call)
        except Exception as e:
            log.error("evaluate_js failed for %s: %s", fn_call, e)

    def set_status(self, state: str):
        self._call_js(f"setStatus({state!r})")

    def show_card(self, card_type: str, title: str, content) -> None:
        self._call_js(f"showCard({card_type!r}, {title!r}, {json.dumps(content)})")

    def hide_card(self, card_type: str):
        self._call_js(f"hideCard({card_type!r})")

    def show_transcript(self, text: str):
        self._call_js(f"showTranscript({text!r})")

    # -- Tool result -> dashboard card mapping -------------------------------

    TOOL_TO_CARD = {
        "get_news": "news",
        "get_weather": "weather",
        "web_search": "search",
        "get_system_info": "system",
    }

    def _render_tool_calls(self, tool_calls: list):
        for call in tool_calls:
            card_type = self.TOOL_TO_CARD.get(call["name"])
            if not card_type:
                continue  # open_app / run_command / list_files / read_file have no dedicated card
            self.show_card(card_type, card_type.upper(), call["result"])

    # -- Main loop ------------------------------------------------------------

    def run_loop(self):
        log.info("Ultron listening continuously. Use the dashboard's mute button to pause.")
        while not self._stop_event.is_set():
            try:
                self._one_cycle()
            except Exception:
                log.error("Unhandled error in main loop:\n%s", traceback.format_exc())
                time.sleep(1)

    def _record_and_transcribe(self, seconds: float) -> str | None:
        """One record+transcribe pass. Returns stripped text, or None on
        failure/empty/muted-mid-recording — callers just treat None as
        'nothing usable, keep listening'."""
        deadline = time.time() + seconds
        try:
            audio_path = voice_input.record_audio(lambda: time.time() < deadline and not self.muted)
        except Exception as e:
            log.error("Recording failed: %s", e)
            time.sleep(1)
            return None

        try:
            text = voice_input.transcribe(audio_path)
        except Exception as e:
            log.error("Transcription failed: %s", e)
            return None
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

        if self.muted or not text or not text.strip():
            return None
        return text.strip()

    def _one_cycle(self):
        if self.muted:
            self.set_status("muted")
            time.sleep(0.3)
            return

        self.set_status("listening")
        heard = self._record_and_transcribe(LISTEN_CHUNK_SECONDS)
        if heard is None:
            log.info("(heard nothing intelligible this chunk)")
            return  # silence, noise, or muted mid-chunk — keep passively listening

        log.info("Heard (passive): %s", heard)

        wake_end = _find_wake_word_end(heard, config.WAKE_WORD, WAKE_WORD_FUZZY_THRESHOLD)
        if wake_end is None:
            return  # wake word not heard — stay passive, don't react to it

        command = heard[wake_end:].strip(" ,.!?")
        if len(command) < 3:
            # Just the wake word alone ("hey Ultron") — capture the actual
            # request as a longer follow-up window than normal passive
            # chunks, since we now know engagement is real and want more
            # room for a pause-then-ask pattern instead of cutting it off.
            self.set_status("listening")
            command = self._record_and_transcribe(FOLLOWUP_CHUNK_SECONDS)
            if not command:
                return

        self._handle_command(command)

    def _handle_command(self, user_text: str):
        log.info("Heard: %s", user_text)
        self.show_transcript(f"You: {user_text}")
        self.set_status("thinking")

        try:
            final_text, self.history, tool_calls = brain.send_message(user_text, self.history)
        except Exception as e:
            log.error("Brain error: %s", e)
            self.set_status("listening")
            voice_output.speak("My reasoning circuits hiccuped. Ask me again.")
            return

        self._render_tool_calls(tool_calls)

        self.set_status("speaking")
        self.show_transcript(f"Ultron: {final_text}")
        try:
            voice_output.speak(final_text)
        except Exception as e:
            log.error("Speech output failed: %s", e)

    def stop(self):
        self._stop_event.set()


def main():
    app = UltronApp()

    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "index.html")

    app.window = webview.create_window(
        config.DASHBOARD_WINDOW_TITLE,
        url=dashboard_path,
        js_api=app,
        width=config.DASHBOARD_WIDTH,
        height=config.DASHBOARD_HEIGHT,
        on_top=config.DASHBOARD_ALWAYS_ON_TOP,
        frameless=config.DASHBOARD_FRAMELESS,
        background_color="#0a0a0a",
    )

    def _on_loaded():
        thread = threading.Thread(target=app.run_loop, daemon=True)
        thread.start()

    app.window.events.loaded += _on_loaded
    webview.start()
    app.stop()


if __name__ == "__main__":
    main()
