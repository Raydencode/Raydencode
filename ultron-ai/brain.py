"""
Ultron's brain: wraps the Anthropic SDK, defines the tool schema, and runs
the full tool-use loop (call Claude -> execute any requested tools -> feed
results back -> repeat until Claude gives a final text answer).
"""

import json

import anthropic

import computer_control
import data_sources
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, MAX_HISTORY_TURNS

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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

TOOLS = [
    {
        "name": "get_news",
        "description": "Get the top 5 recent news articles about a topic.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "News topic or keyword to search for"}},
            "required": ["topic"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get current weather conditions for a location.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City name, e.g. 'Seattle' or 'Seattle,US'"}},
            "required": ["location"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for up-to-date information not in your training data.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "open_app",
        "description": "Launch an application on the user's computer by name.",
        "input_schema": {
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
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command to execute"}},
            "required": ["command"],
        },
    },
    {
        "name": "list_files",
        "description": "List the files and subdirectories in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "description": "Path to the directory to list"}},
            "required": ["directory"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a text file (capped at 50KB).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the file to read"}},
            "required": ["path"],
        },
    },
    {
        "name": "get_system_info",
        "description": "Get current CPU usage, memory usage, battery level, and top processes by CPU.",
        "input_schema": {"type": "object", "properties": {}},
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


def _execute_tool(name: str, tool_input: dict) -> dict:
    handler = _TOOL_DISPATCH.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return handler(tool_input)
    except Exception as e:
        return {"error": f"Tool '{name}' raised an exception: {e}"}


def _trim_history(history: list) -> list:
    """Keep only the last MAX_HISTORY_TURNS user/assistant exchanges (2 messages per turn)."""
    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        return history[-max_messages:]
    return history


def send_message(user_text: str, history: list) -> tuple[str, list, list]:
    """
    Run one full conversational turn, including any tool-use round trips.

    Returns (final_text, updated_history, tool_calls_made) where tool_calls_made
    is a list of {"name": str, "input": dict, "result": dict} for the dashboard
    to render as cards.
    """
    messages = _trim_history(history) + [{"role": "user", "content": user_text}]
    tool_calls_made = []

    # Cap the loop so a misbehaving tool-use chain can't spin forever.
    for _ in range(8):
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
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

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return (
        "I chased that down a few too many rabbit holes and hit my tool-call limit. Try rephrasing?",
        messages,
        tool_calls_made,
    )
