"""
Local machine control: launch apps, run shell commands, browse files, and
report system stats. This is the module with the most blast radius in the
whole project — run_command() executes arbitrary shell input from the LLM,
so it carries a (best-effort, not bulletproof) blocklist. Treat it as a
convenience feature for a trusted single user, not a sandbox.
"""

import os
import platform
import re
import subprocess

import psutil

READ_FILE_MAX_BYTES = 50_000  # 50KB cap so we never dump a huge file into context

# Patterns that block obviously destructive commands. This is NOT a security
# boundary — a determined user (or a sufficiently creative LLM) can still
# construct something harmful. It only exists to stop the most common
# catastrophic footguns (wiping a disk, formatting a drive, shutting the
# machine down) from being triggered by an offhand voice command.
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\brm\s+-rf\s+~",
    r"\brm\s+-rf\s+\*",
    r"\bmkfs\b",
    r"\bformat\s+[a-zA-Z]:",
    r"\bdel\s+/f\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r">\s*/dev/sd[a-z]",
    r":(){:|:&};:",  # fork bomb
    r"\bdiskpart\b",
]
_DANGEROUS_RE = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)


def open_app(app_name: str) -> dict:
    """Launch an application by name, cross-platform."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(app_name)  # noqa: S606 - user-directed app launch
        elif system == "Darwin":
            subprocess.run(["open", "-a", app_name], check=True, timeout=10)
        else:  # Linux and friends
            try:
                subprocess.run(["xdg-open", app_name], check=True, timeout=10)
            except (subprocess.CalledProcessError, FileNotFoundError):
                subprocess.Popen([app_name])  # fall back to treating it as a binary name

        return {"status": "ok", "message": f"Launched '{app_name}'"}

    except Exception as e:
        return {"error": f"Could not open '{app_name}': {e}"}


def run_command(command: str) -> dict:
    """Run a shell command and return its output. Blocks an obvious-danger denylist first."""
    if _DANGEROUS_RE.search(command):
        return {"error": f"Refused to run '{command}': matches a destructive-command pattern."}

    try:
        result = subprocess.run(
            command,
            shell=True,  # noqa: S602 - intentional: this tool exists to run arbitrary shell commands
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "status": "ok",
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
        }

    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after 30s: '{command}'"}
    except Exception as e:
        return {"error": f"Failed to run command: {e}"}


def list_files(directory: str) -> dict:
    """List entries in a directory."""
    try:
        expanded = os.path.expanduser(directory)
        if not os.path.isdir(expanded):
            return {"error": f"'{directory}' is not a valid directory"}

        entries = os.listdir(expanded)
        files, dirs = [], []
        for entry in entries:
            full_path = os.path.join(expanded, entry)
            (dirs if os.path.isdir(full_path) else files).append(entry)

        return {"directory": expanded, "directories": sorted(dirs), "files": sorted(files)}

    except PermissionError:
        return {"error": f"Permission denied reading '{directory}'"}
    except Exception as e:
        return {"error": f"Failed to list '{directory}': {e}"}


def read_file(path: str) -> dict:
    """Read a text file's contents, capped at READ_FILE_MAX_BYTES."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.isfile(expanded):
            return {"error": f"'{path}' is not a valid file"}

        size = os.path.getsize(expanded)
        with open(expanded, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(READ_FILE_MAX_BYTES)

        truncated = size > READ_FILE_MAX_BYTES
        return {
            "path": expanded,
            "content": content,
            "truncated": truncated,
            "size_bytes": size,
        }

    except PermissionError:
        return {"error": f"Permission denied reading '{path}'"}
    except UnicodeDecodeError:
        return {"error": f"'{path}' does not look like a text file"}
    except Exception as e:
        return {"error": f"Failed to read '{path}': {e}"}


def get_system_info() -> dict:
    """CPU %, memory %, battery %, and top 5 processes by CPU usage."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()

        battery_info = None
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if battery is not None:
            battery_info = {"percent": battery.percent, "plugged_in": battery.power_plugged}

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        top_processes = sorted(processes, key=lambda p: p.get("cpu_percent") or 0, reverse=True)[:5]

        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "battery": battery_info,
            "top_processes": [
                {"pid": p["pid"], "name": p["name"], "cpu_percent": p.get("cpu_percent")}
                for p in top_processes
            ],
        }

    except Exception as e:
        return {"error": f"Failed to get system info: {e}"}
