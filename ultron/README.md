# ULTRON

A voice-controlled assistant for one person's business, running entirely on
your own machine. Python standard library on the server, vanilla JS in the
browser. No frameworks, no build step, no package manager, nothing to
`npm install`.

It reads your files (read-only), turns them into a graph you can see, and
talks to you about them — search, web lookups grounded in your numbers, a
read-only inbox glance, a daily brief, a five-item plan, and a memory it
only writes to when you tell it to.

## Run it

```
cd ultron/agent
python3 main.py
```

Then open **http://localhost:8420**. That's the whole install. Python 3.10+
and a browser are the only requirements — nothing else gets installed
without asking you first.

By default you're looking at demo data: a fictional two-person Shopify
studio ("Rayden Digital") with invented clients, invoices, and notes. It's
safe to screen-record. Nothing in it is real.

## Turning on voice

The mic and spoken replies need an ElevenLabs API key. Everything else —
the graph, search, planning, remembering — works without one.

```
cp .env.example .env
chmod 600 .env
```

Open `.env` and set:

```
ELEVENLABS_API_KEY=sk_...
```

Get a key at https://elevenlabs.io. It never reaches the browser — the
page posts text to `/api/speak` and audio to `/api/listen`; only
`agent/voice.py`, on the server, ever sees the key. Restart `main.py`
after editing `.env`.

If you also want free-form conversation (not just the six tools), add:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without it, ULTRON still routes correctly — search/brief/plan/remember all
work via keyword and file matching — it just can't chat freely, and the UI
shows a `MODEL` badge as off so you know why.

## Making it yours

1. **`CLAUDE.md`** — who you are, how you want to be spoken to, what you
   sell. Loaded into every session. Fill in the `<placeholders>`.
2. **`.env`** — set `ULTRON_DEMO=0` and `ULTRON_FOLDERS=/path/one,/path/two`
   to point ULTRON at your real notes and client folders instead of the
   demo fixtures. You have to opt in — `ULTRON_DEMO` defaults to `1`.
3. Optional, both read-only, both leave-blank-to-skip:
   - `IMAP_HOST` / `IMAP_USER` / `IMAP_PASSWORD` — for `read_inbox` and
     `brief_me`. Headers only (who, subject), nothing gets sent.
   - `CALENDAR_ICS_PATH` — a local `.ics` export, for `brief_me`.

Regenerate the demo fixtures any time with:

```
cd ultron/data
python3 generate_demo.py
```

Fixed random seed, so the graph looks identical every run.

## What it costs

Everything here is pay-as-you-go, nothing is subscribed to on your behalf,
and ULTRON will never spend without asking first. Rough shape of the
costs — check each provider's current pricing page, these move:

- **ElevenLabs** — billed per character (speech out) and per minute
  (Scribe speech-to-text). A typical short exchange is a few hundred
  characters and a few seconds of audio; casual daily use is normally
  within ElevenLabs' free or starter tier.
- **Anthropic** (optional) — billed per token, only called for plain
  conversation turns, not for tool calls. Skip it entirely and ULTRON
  still does search/brief/plan/remember for free.
- **Web lookups** (`research_web`) — DuckDuckGo's instant-answer API, no
  key, no charge.
- Everything else — the graph, search, indexing, memory — is local and
  free.

## How it's built

```
ultron/
├── agent/
│   ├── main.py      HTTP server + API (stdlib http.server)
│   ├── vault.py      folders → searchable graph (wikilinks = edges)
│   ├── tools.py      search_brain, research_web, read_inbox, brief_me,
│   │                 remember, plan_day
│   ├── data.py       THE ONLY FILE THAT TOUCHES YOUR REAL DATA
│   ├── voice.py      ElevenLabs speech in and out — API key lives here only
│   ├── memory.py      writes to memory/ and nowhere else
│   └── prompt.md      the system prompt
├── ui/                index.html, app.js, graph.js, styles.css — no build step
├── data/              demo fixtures + generate_demo.py
├── memory/            one dated markdown file per remembered fact
├── CLAUDE.md          who you are — loaded every session
├── .env               keys, gitignored, chmod 600 (copy from .env.example)
└── README.md
```

**The graph** is hand-rolled force-directed layout on a `<canvas>`, not
SVG or a library — SVG needs a DOM node per element and stalls out past
roughly 1,500 nodes. Repulsion uses a spatial grid with a distance cutoff
so it stays close to linear cost. Labels are drawn most-connected-first
and skipped on collision, so hub clusters don't turn into a smear of text.

**Turn-taking** presses the mic once, then just talk — the browser watches
real mic level with a Web Audio `AnalyserNode` on a `setInterval` (not
`requestAnimationFrame`, which stops dead in a backgrounded tab and would
leave the mic silently deaf). Go quiet for ~900ms (`SILENCE_TIMEOUT_MS` at
the top of `ui/app.js`) and the turn ends and sends. The mic is explicitly
stopped while ULTRON is speaking, so it can't hear itself through your
speakers; barge in with the mic button, Space, or Esc.

**Routing works with no model at all.** If `ANTHROPIC_API_KEY` isn't set,
ULTRON scores your message against keyword patterns and against your own
files to decide conversation vs. a specific tool — never passing that off
as the model "understanding" anything. The UI shows a `MODEL` badge as off
so it's visible, not silent.

## Guardrails

These are enforced in code, not just prompted for:

- **Never sends anything.** No email, message, or calendar invite. There
  is no send path in this codebase.
- **Never writes to your real folders.** `vault.py` only ever reads.
  `memory.py` is the only module with write access, and it's hard-coded
  to `memory/` — it refuses a path that resolves outside that directory.
- **Never writes to memory silently.** Every `remember` call returns the
  exact text it wrote, spoken and shown, every time.
- **Never spends.** No paid API call happens outside the ones you've
  explicitly configured keys for; there's no purchasing path at all.
- **Never invents.** `search_brain` and `plan_day` only ever surface what's
  actually in your indexed files, with the source file named.

## Build order this was built in

1. Index the folders — `vault.py` + `data.py`, verified against the demo
   fixtures (`python3 -c "import data; data.get_vault().print_report()"`).
2. The graph UI against the real index, no voice.
3. Tools + conversation, text input only.
4. Voice in and out, and the reactor HUD.
5. `CLAUDE.md`, `memory/`, and the guardrails.

## Known limitations

- PDF text extraction is a small dependency-free regex-based extractor
  (no third-party PDF library, per the stdlib-only constraint). It handles
  normal text-layer PDFs; it won't get anything out of a scanned
  image-only PDF.
- `research_web` uses DuckDuckGo's instant-answer API, which doesn't
  cover everything a full search engine does — it's meant for quick facts
  to ground against your own numbers, not general research.
