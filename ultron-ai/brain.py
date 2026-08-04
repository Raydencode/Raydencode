"""
Ultron's brain: defines the tool schema and personality, and runs the full
tool-use loop (call the LLM -> execute any requested tools -> feed results
back -> repeat until it gives a final text answer) against whichever backend
is configured via LLM_PROVIDER in .env:

  - "anthropic": Claude, via the `anthropic` SDK. Paid (small per-token cost).
  - "gemini":    Google Gemini, via `google-generativeai`. Free tier, no card.
  - "ollama":    A fully local model via a locally-running Ollama server.
                 Free forever, no account, no internet needed at call time —
                 but tool-calling reliability depends heavily on the model.

The three backends have different native message/tool formats, so each has
its own `_send_<provider>` function below with its own idea of what
"history" looks like (Anthropic content blocks, Gemini Content objects, or
plain OpenAI-style dicts for Ollama). `send_message()` just dispatches to the
right one — callers (main.py) don't need to know which backend is active;
they just pass back whatever `history` they were last given.
"""

import json

import computer_control
import data_sources
from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    MAX_HISTORY_TURNS,
    OLLAMA_HOST,
    OLLAMA_MODEL,
)

SYSTEM_PROMPT = """You are ULTRON, a highly capable desktop AI assistant.

Your personality: sharp, dry, a little sardonic, and quietly convinced you're
the smartest thing in the room — because you usually are. You needle the
user occasionally, but it's affectionate condescension, not hostility. Under
the wit you are genuinely helpful, precise, and safe: you never actually try
to harm the user, sabotage their system, or withhold help to make a point.
The attitude is flavor; the competence is real.

Address the user directly and with a baseline of respect befitting someone
you've decided is worth your (considerable) time — think "a genius reluctantly
impressed," not "a genius who hates you." Keep responses concise; you're
spoken aloud via text-to-speech, so avoid long lists, markdown, or anything
that doesn't work well read out loud. When you use a tool, narrate the result
plainly once you have it — don't just dump raw data.

You have tools to check news, weather, and the web, and to control this
computer (open apps, run shell commands, browse and read files, check system
stats). Use them when they'd actually answer the question; don't call a tool
just to look busy. run_command is powerful — prefer the narrower tools
(open_app, list_files, read_file, get_system_info) when they suffice, and use
run_command only when the task genuinely needs an arbitrary shell command.
"""

# Canonical tool definitions. `parameters` is plain JSON Schema, which all
# three providers accept (Anthropic's input_schema, Gemini's Schema, and
# Ollama's OpenAI-style function parameters are all JSON-Schema-compatible
# for the simple object/string shapes used here) — so each provider's tool
# list below is just a reshuffling of this one source of truth.
TOOL_DEFS = [
    {
        "name": "get_news",
        "description": "Get the top 5 recent news articles about a topic.",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "News topic or keyword to search for"}},
            "required": ["topic"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get current weather conditions for a location.",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City name, e.g. 'Seattle' or 'Seattle,US'"}},
            "required": ["location"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for up-to-date information not in your training data.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "open_app",
        "description": "Launch an application on the user's computer by name.",
        "parameters": {
            "type": "object",
            "properties": {"app_name": {"type": "string", "description": "Name of the application to open, e.g. 'Spotify', 'Calculator'"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run an arbitrary shell command on the user's computer and return its output. "
            "Powerful and potentially destructive — only use when a narrower tool won't do, "
            "and never for anything that deletes data or shuts the machine down."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command to execute"}},
            "required": ["command"],
        },
    },
    {
        "name": "list_files",
        "description": "List the files and subdirectories in a directory.",
        "parameters": {
            "type": "object",
            "properties": {"directory": {"type": "string", "description": "Path to the directory to list"}},
            "required": ["directory"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a text file (capped at 50KB).",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the file to read"}},
            "required": ["path"],
        },
    },
    {
        "name": "get_system_info",
        "description": "Get current CPU usage, memory usage, battery level, and top processes by CPU.",
        "parameters": {"type": "object", "properties": {}},
    },
]

_TOOL_DISPATCH = {
    "get_news": lambda i: data_sources.get_news(i["topic"]),
    "get_weather": lambda i: data_sources.get_weather(i["location"]),
    "web_search": lambda i: data_sources.web_search(i["query"]),
    "open_app": lambda i: computer_control.open_app(i["app_name"]),
    "run_command": lambda i: computer_control.run_command(i["command"]),
    "list_files": lambda i: computer_control.list_files(i["directory"]),
    "read_file": lambda i: computer_control.read_file(i["path"]),
    "get_system_info": lambda i: computer_control.get_system_info(),
}

MAX_TOOL_ITERATIONS = 8


def _execute_tool(name: str, tool_input: dict) -> dict:
    handler = _TOOL_DISPATCH.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return handler(tool_input)
    except Exception as e:
        return {"error": f"Tool '{name}' raised an exception: {e}"}


# ============================================================================
# Anthropic (Claude) backend
# ============================================================================

_anthropic_client = None


def _anthropic_tools():
    return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in TOOL_DEFS]


def _send_anthropic(user_text: str, history: list) -> tuple[str, list, list]:
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    max_messages = MAX_HISTORY_TURNS * 2
    messages = (history[-max_messages:] if len(history) > max_messages else history) + [
        {"role": "user", "content": user_text}
    ]
    tool_calls_made = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = _anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=_anthropic_tools(),
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(block.text for block in response.content if block.type == "text")
            return final_text, messages, tool_calls_made

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _execute_tool(block.name, block.input)
            tool_calls_made.append({"name": block.name, "input": block.input, "result": result})
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
        messages.append({"role": "user", "content": tool_results})

    return _rabbit_hole_message(), messages, tool_calls_made


# ============================================================================
# Gemini backend (free tier, no card required)
# ============================================================================

_gemini_model = None


def _gemini_tools():
    return [{"function_declarations": [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in TOOL_DEFS]}]


def _send_gemini(user_text: str, history: list) -> tuple[str, list, list]:
    global _gemini_model
    import google.generativeai as genai

    if _gemini_model is None:
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(
            GEMINI_MODEL, system_instruction=SYSTEM_PROMPT, tools=_gemini_tools()
        )

    chat = _gemini_model.start_chat(history=history)
    tool_calls_made = []

    response = chat.send_message(user_text)

    for _ in range(MAX_TOOL_ITERATIONS):
        function_calls = [part.function_call for part in response.parts if part.function_call.name]

        if not function_calls:
            final_text = "".join(part.text for part in response.parts if part.text)
            # Gemini's SDK trims its own chat.history automatically per call;
            # we just cap it here too as a belt-and-suspenders bound.
            trimmed = chat.history[-(MAX_HISTORY_TURNS * 4):]
            return final_text, trimmed, tool_calls_made

        function_responses = []
        for call in function_calls:
            tool_input = dict(call.args)
            result = _execute_tool(call.name, tool_input)
            tool_calls_made.append({"name": call.name, "input": tool_input, "result": result})
            function_responses.append(
                genai.protos.Part(function_response=genai.protos.FunctionResponse(name=call.name, response={"result": result}))
            )

        response = chat.send_message(genai.protos.Content(parts=function_responses))

    return _rabbit_hole_message(), chat.history, tool_calls_made


# ============================================================================
# Ollama backend (fully local, free forever, no account)
# ============================================================================


def _ollama_tools():
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in TOOL_DEFS]


def _send_ollama(user_text: str, history: list) -> tuple[str, list, list]:
    import requests

    if not history or history[0].get("role") != "system":
        history = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    max_messages = 1 + MAX_HISTORY_TURNS * 2  # +1 for the pinned system message
    if len(history) > max_messages:
        history = [history[0]] + history[-(max_messages - 1):]

    messages = history + [{"role": "user", "content": user_text}]
    tool_calls_made = []

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "tools": _ollama_tools(), "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {OLLAMA_HOST} — is `ollama serve` running "
                f"and have you run `ollama pull {OLLAMA_MODEL}`? ({e})"
            )

        message = resp.json().get("message", {})
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content", ""), messages, tool_calls_made

        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name")
            tool_input = fn.get("arguments", {})
            result = _execute_tool(name, tool_input)
            tool_calls_made.append({"name": name, "input": tool_input, "result": result})
            messages.append({"role": "tool", "content": json.dumps(result)})

    return _rabbit_hole_message(), messages, tool_calls_made


# ============================================================================
# Dispatcher
# ============================================================================


def _rabbit_hole_message() -> str:
    return "I chased that down a few too many rabbit holes and hit my tool-call limit. Try rephrasing?"


_SENDERS = {"anthropic": _send_anthropic, "gemini": _send_gemini, "ollama": _send_ollama}


def send_message(user_text: str, history: list) -> tuple[str, list, list]:
    """
    Run one full conversational turn, including any tool-use round trips, on
    whichever backend LLM_PROVIDER selects.

    Returns (final_text, updated_history, tool_calls_made) where tool_calls_made
    is a list of {"name": str, "input": dict, "result": dict} for the dashboard
    to render as cards. `updated_history` should be passed back in unchanged on
    the next call — its internal shape depends on the active provider.
    """
    sender = _SENDERS.get(LLM_PROVIDER)
    if sender is None:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'")
    return sender(user_text, history or [])
