"""
memory.py — writes to memory/ and nowhere else.

One dated markdown file per remembered fact. Never called silently: every
write is echoed back to the caller so it can be spoken out loud.
"""

import re
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
MEMORY_DIR = (AGENT_DIR.parent / "memory").resolve()
MEMORY_DIR.mkdir(exist_ok=True)


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "note"


def remember(fact: str) -> dict:
    fact = fact.strip()
    if not fact:
        return {"ok": False, "error": "nothing to remember"}

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    slug = _slugify(fact)
    filename = f"{date_str}-{slug}.md"
    path = MEMORY_DIR / filename

    # guard against writing outside memory/, and against overwriting a
    # same-day same-slug file by disambiguating with a counter
    counter = 2
    while path.exists():
        path = MEMORY_DIR / f"{date_str}-{slug}-{counter}.md"
        counter += 1
    path = path.resolve()
    if MEMORY_DIR not in path.parents and path != MEMORY_DIR:
        return {"ok": False, "error": "refused: path escaped memory/"}

    content = f"---\ndate: {now.isoformat(timespec='seconds')}\n---\n\n{fact}\n"
    path.write_text(content, encoding="utf-8")

    return {"ok": True, "path": str(path.relative_to(MEMORY_DIR.parent)), "fact": fact}


def list_memories(limit: int = 50) -> list[dict]:
    files = sorted(MEMORY_DIR.glob("*.md"), key=lambda p: p.name, reverse=True)
    out = []
    for p in files[:limit]:
        text = p.read_text(encoding="utf-8", errors="ignore")
        body = text.split("---\n", 2)[-1].strip() if text.startswith("---") else text.strip()
        out.append({"file": p.name, "fact": body})
    return out


def recent_context(limit: int = 5) -> str:
    mems = list_memories(limit)
    if not mems:
        return ""
    lines = [f"- {m['fact']} ({m['file']})" for m in mems]
    return "\n".join(lines)
