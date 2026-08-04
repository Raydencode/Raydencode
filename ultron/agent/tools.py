"""
tools.py — the six things ULTRON can actually do.

Every tool returns exactly two things:
  speech: one or two sentences, meant to be spoken out loud
  card:   a dict of structured detail, meant to be read on screen

The two are never the same text. Tools only read; nothing here sends
anything, writes to your real folders, or spends money.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path

import data
import memory

MONEY_RE = re.compile(r"[£$€]\s?[\d,]+(?:\.\d+)?")
MONEY_KEYWORDS = ("invoice", "unpaid", "overdue", "proposal", "retainer", "budget", "£", "$")


def _vault():
    return data.get_vault()


# -- 1. search_brain ---------------------------------------------------------

def search_brain(query: str) -> dict:
    results = _vault().search(query, limit=5)
    if not results:
        return {
            "speech": f"Nothing in your files matches \"{query}\".",
            "card": {"tool": "search_brain", "query": query, "results": []},
        }

    top = results[0]
    if len(results) == 1:
        speech = f"{top['title']}, from {Path(top['path']).name}: {top['snippet'][:140]}"
    else:
        files = ", ".join(Path(r["path"]).name for r in results[:3])
        speech = f"Found it across {len(results)} files ({files})."

    return {
        "speech": speech,
        "card": {"tool": "search_brain", "query": query, "results": results},
    }


# -- 2. research_web ----------------------------------------------------------

def _fetch_duckduckgo(query: str) -> dict | None:
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query, "format": "json", "no_html": 1, "skip_disambig": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "ULTRON/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def research_web(query: str) -> dict:
    data_json = _fetch_duckduckgo(query)
    if data_json is None:
        return {
            "speech": "Couldn't reach the web to look that up.",
            "card": {"tool": "research_web", "query": query, "error": "network unavailable"},
        }

    answer = data_json.get("AbstractText") or ""
    if not answer and data_json.get("RelatedTopics"):
        first = data_json["RelatedTopics"][0]
        answer = first.get("Text", "") if isinstance(first, dict) else ""

    if not answer:
        return {
            "speech": f"Nothing useful came back for \"{query}\".",
            "card": {"tool": "research_web", "query": query, "result": None},
        }

    # try to land it on your own numbers: does the query name a client/
    # project that has a known budget in the vault?
    grounding = None
    price_matches = MONEY_RE.findall(answer)
    if price_matches:
        for r in _vault().search(query, limit=3):
            note = _vault().get_note(r["id"])
            if note and MONEY_RE.search(note["content"]):
                vault_amount = MONEY_RE.search(note["content"]).group(0)
                grounding = f"Your file on {note['title']} shows {vault_amount} — compare against that."
                break

    speech = answer[:200]
    if grounding:
        speech = f"{answer[:140]} {grounding}"

    return {
        "speech": speech,
        "card": {
            "tool": "research_web",
            "query": query,
            "answer": answer,
            "source": data_json.get("AbstractURL") or "duckduckgo.com",
            "grounded_against": grounding,
        },
    }


# -- 3. read_inbox --------------------------------------------------------

def read_inbox() -> dict:
    host = os.environ.get("IMAP_HOST")
    user = os.environ.get("IMAP_USER")
    password = os.environ.get("IMAP_PASSWORD")

    if not (host and user and password):
        return {
            "speech": "Inbox isn't connected — no IMAP settings in your .env.",
            "card": {
                "tool": "read_inbox",
                "configured": False,
                "missing": [k for k, v in
                            {"IMAP_HOST": host, "IMAP_USER": user, "IMAP_PASSWORD": password}.items()
                            if not v],
            },
        }

    import imaplib
    import email
    from email.header import decode_header

    try:
        conn = imaplib.IMAP4_SSL(host)
        conn.login(user, password)
        conn.select("INBOX", readonly=True)
        status, msg_ids = conn.search(None, "UNSEEN")
        ids = msg_ids[0].split()[:10] if status == "OK" else []
        items = []
        for mid in ids:
            status, msg_data = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject, enc = decode_header(msg.get("Subject", ""))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(enc or "utf-8", errors="ignore")
            sender = msg.get("From", "unknown")
            items.append({"from": sender, "subject": subject})
        conn.logout()
    except Exception as e:
        return {
            "speech": "Inbox is configured but I couldn't read it.",
            "card": {"tool": "read_inbox", "configured": True, "error": str(e)},
        }

    known = []
    for item in items:
        name_guess = re.sub(r"<.*?>", "", item["from"]).strip(' "')
        hits = _vault().search(name_guess, limit=1) if name_guess else []
        item["known_contact"] = bool(hits)
        if hits:
            known.append(name_guess)

    if not items:
        speech = "Inbox is clean — nothing unread."
    else:
        known_count = sum(1 for i in items if i["known_contact"])
        speech = f"{len(items)} unread. {known_count} from people already in your files."

    return {
        "speech": speech,
        "card": {"tool": "read_inbox", "configured": True, "unread": items},
    }


# -- 4. brief_me --------------------------------------------------------

def _calendar_events_today() -> list[dict]:
    ics_path = os.environ.get("CALENDAR_ICS_PATH")
    if not ics_path or not Path(ics_path).exists():
        return []
    text = Path(ics_path).read_text(encoding="utf-8", errors="ignore")
    today = date.today().strftime("%Y%m%d")
    events = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        summary_m = re.search(r"SUMMARY:(.*)", block)
        start_m = re.search(r"DTSTART[^:]*:(\d{8})", block)
        if start_m and start_m.group(1) == today:
            events.append({"summary": summary_m.group(1).strip() if summary_m else "(untitled)"})
    return events


def brief_me() -> dict:
    inbox = read_inbox()
    events = _calendar_events_today()

    pieces = []
    if inbox["card"].get("configured"):
        unread = inbox["card"].get("unread", [])
        pieces.append(f"{len(unread)} unread" if unread else "inbox clean")
    else:
        pieces.append("inbox not connected")

    if os.environ.get("CALENDAR_ICS_PATH"):
        pieces.append(f"{len(events)} on today's calendar" if events else "nothing on today's calendar")
    else:
        pieces.append("calendar not connected")

    speech = ", ".join(pieces) + "."

    return {
        "speech": speech,
        "card": {
            "tool": "brief_me",
            "inbox": inbox["card"],
            "calendar": {
                "configured": bool(os.environ.get("CALENDAR_ICS_PATH")),
                "events_today": events,
            },
        },
    }


# -- 5. remember --------------------------------------------------------

def remember(fact: str) -> dict:
    result = memory.remember(fact)
    if not result.get("ok"):
        return {
            "speech": f"Couldn't save that — {result.get('error', 'unknown error')}.",
            "card": {"tool": "remember", "ok": False, "error": result.get("error")},
        }
    return {
        "speech": f"Wrote it down: \"{result['fact']}\" — saved to {result['path']}.",
        "card": {"tool": "remember", "ok": True, "path": result["path"], "fact": result["fact"]},
    }


# -- 6. plan_day --------------------------------------------------------

def plan_day() -> dict:
    vault = _vault()
    candidates = []
    for node in vault.nodes.values():
        text = (node.title + " " + node.content).lower()
        score = 0
        if node.type == "invoice" and "unpaid" in text:
            score += 10
        if node.type == "invoice" and "partial" in text:
            score += 6
        if node.type == "proposal" and "draft" in text:
            score += 7
        if "overdue" in text:
            score += 8
        if any(k in text for k in MONEY_KEYWORDS):
            score += 2
        score += min(node.degree, 5) * 0.5
        if score > 0:
            candidates.append((score, node))

    candidates.sort(key=lambda sn: sn[0], reverse=True)
    top = candidates[:5]

    if not top:
        return {
            "speech": "Nothing in your files is flagged as urgent right now.",
            "card": {"tool": "plan_day", "items": []},
        }

    items = [{
        "title": n.title,
        "type": n.type,
        "why": _why(n),
        "path": n.path,
    } for _, n in top]

    speech = f"Top of the list: {items[0]['title']}. {len(items)} items total, ranked by what moves money."

    return {
        "speech": speech,
        "card": {"tool": "plan_day", "items": items},
    }


def _why(node) -> str:
    text = node.content.lower()
    if node.type == "invoice" and "unpaid" in text:
        return "unpaid invoice"
    if node.type == "invoice" and "partial" in text:
        return "partially paid"
    if node.type == "proposal" and "draft" in text:
        return "proposal still in draft"
    if "overdue" in text:
        return "overdue"
    return "flagged in your files"


TOOLS = {
    "search_brain": search_brain,
    "research_web": research_web,
    "read_inbox": read_inbox,
    "brief_me": brief_me,
    "remember": remember,
    "plan_day": plan_day,
}
