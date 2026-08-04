"""
Ultron entry point: boots the pywebview HUD window and runs the
listen -> transcribe -> think -> act -> speak loop in a background thread.

Push-to-talk key detection uses the `keyboard` library rather than
pywebview key events. Tradeoff: `keyboard` needs elevated/root permissions
on Linux (to read /dev/input) and can be flaky under some Wayland setups,
but it works globally (the HUD window doesn't need OS focus to hear you),
which matters for a "hold space to talk while doing other things" assistant.
pywebview key events would avoid the permissions issue but only fire while
the HUD window itself has focus — worse for the intended use case. If
`keyboard` fails to initialize (common in sandboxed/CI/headless
environments), we fall back to console input so the app still runs.
"""

from __future__ import annotations

import logging
import os
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

try:
    import keyboard as kb

    _KEYBOARD_AVAILABLE = True
except Exception as e:  # ImportError, or ImportError raised internally on unsupported platforms
    _KEYBOARD_AVAILABLE = False
    log.warning("`keyboard` library unavailable (%s) — falling back to console push-to-talk (Enter key).", e)


class Api:
    """Exposed to JS as `pywebview.api`. Currently the app is Python-driven
    (Python calls JS via evaluate_js), but this class exists so JS could call
    back into Python in the future without restructuring anything."""

    def ping(self):
        return "pong"


class UltronApp:
    def __init__(self):
        self.window: webview.Window | None = None
        self.history: list = []
        self._stop_event = threading.Event()

    # -- JS bridge helpers ----------------------------------------------

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
        import json

        self._call_js(f"showCard({card_type!r}, {title!r}, {json.dumps(content)})")

    def hide_card(self, card_type: str):
        self._call_js(f"hideCard({card_type!r})")

    def show_transcript(self, text: str):
        self._call_js(f"showTranscript({text!r})")

    # -- Tool result -> dashboard card mapping ----------------------------

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
            title = card_type.upper()
            self.show_card(card_type, title, call["result"])

    # -- Main loop ---------------------------------------------------------

    def _wait_for_wake_key_press(self) -> bool:
        """Block until the wake key goes down. Returns False if the app is stopping."""
        if _KEYBOARD_AVAILABLE:
            while not self._stop_event.is_set():
                if kb.is_pressed(config.WAKE_KEY):
                    return True
                time.sleep(0.05)
            return False
        else:
            try:
                input(f"\nPress ENTER to talk to Ultron (Ctrl+C to quit)... ")
                return not self._stop_event.is_set()
            except (EOFError, KeyboardInterrupt):
                return False

    def _still_holding_key(self) -> bool:
        if _KEYBOARD_AVAILABLE:
            return kb.is_pressed(config.WAKE_KEY) and not self._stop_event.is_set()
        return False  # console fallback: record_audio uses a fixed duration instead

    def run_loop(self):
        log.info("Ultron ready. Hold '%s' to talk.", config.WAKE_KEY)
        while not self._stop_event.is_set():
            try:
                self._one_cycle()
            except Exception:
                log.error("Unhandled error in main loop:\n%s", traceback.format_exc())
                self.set_status("idle")
                voice_output.speak("Something went wrong. Let's try that again.")
                time.sleep(1)

    def _one_cycle(self):
        if not self._wait_for_wake_key_press():
            return

        self.set_status("listening")
        audio_path = None
        try:
            if _KEYBOARD_AVAILABLE:
                audio_path = voice_input.record_audio(self._still_holding_key)
            else:
                # Console fallback: fixed-duration recording since there's no
                # key-release signal available.
                audio_path = voice_input.record_audio(self._make_timed_continue(4.0))
        except Exception as e:
            log.error("Recording failed: %s", e)
            self.set_status("idle")
            voice_output.speak("I couldn't hear anything just then.")
            return

        try:
            user_text = voice_input.transcribe(audio_path)
        except Exception as e:
            log.error("Transcription failed: %s", e)
            self.set_status("idle")
            voice_output.speak("I couldn't make that out.")
            return
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

        if not user_text:
            log.info("Empty transcription, ignoring.")
            self.set_status("idle")
            return

        log.info("Heard: %s", user_text)
        self.show_transcript(f"You: {user_text}")
        self.set_status("thinking")

        try:
            final_text, self.history, tool_calls = brain.send_message(user_text, self.history)
        except Exception as e:
            log.error("Brain error: %s", e)
            self.set_status("idle")
            voice_output.speak("My reasoning circuits hiccuped. Ask me again.")
            return

        self._render_tool_calls(tool_calls)

        self.set_status("speaking")
        self.show_transcript(f"Ultron: {final_text}")
        try:
            voice_output.speak(final_text)
        except Exception as e:
            log.error("Speech output failed: %s", e)

        self.set_status("idle")

    @staticmethod
    def _make_timed_continue(seconds: float):
        deadline = time.time() + seconds
        return lambda: time.time() < deadline

    def stop(self):
        self._stop_event.set()


def main():
    app = UltronApp()
    api = Api()

    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "index.html")

    app.window = webview.create_window(
        config.DASHBOARD_WINDOW_TITLE,
        url=dashboard_path,
        js_api=api,
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
