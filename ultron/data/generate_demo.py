#!/usr/bin/env python3
"""
generate_demo.py — builds the fixtures under data/demo/.

Fixed random seed (see SEED below) so the graph looks identical every time
you run it. Safe to screen-record: nothing here is real. It's shaped like
a two-person Shopify studio because that's the example in the brief —
swap the CLIENTS/PROJECTS/INVOICES tables below for your own business if
you want the demo to look more like you, or just point ULTRON_DEMO=0 at
your real folders instead.

Run: python3 generate_demo.py
"""

import random
import shutil
from pathlib import Path

SEED = 20260804

HERE = Path(__file__).resolve().parent
OUT = HERE / "demo"

STUDIO_NAME = "Rayden Digital"

CLIENTS = [
    {
        "slug": "northfield-roasters",
        "name": "Northfield Roasters",
        "industry": "specialty coffee, D2C + wholesale",
        "since": "2024-11-02",
        "status": "active retainer",
    },
    {
        "slug": "marlowe-finch",
        "name": "Marlowe & Finch",
        "industry": "leather goods, small batch",
        "since": "2025-02-14",
        "status": "active retainer",
    },
    {
        "slug": "kestrel-outdoor",
        "name": "Kestrel Outdoor",
        "industry": "outdoor gear, seasonal",
        "since": "2025-05-20",
        "status": "build in progress",
    },
    {
        "slug": "bramble-co",
        "name": "Bramble & Co",
        "industry": "home fragrance",
        "since": "2024-06-10",
        "status": "lapsed",
    },
    {
        "slug": "vantage-fitness",
        "name": "Vantage Fitness",
        "industry": "gym equipment, B2B + D2C",
        "since": "2025-07-01",
        "status": "prospect",
    },
]

PROJECTS = [
    {"slug": "northfield-relaunch", "client": "northfield-roasters", "title": "Northfield Roasters — store relaunch",
     "kind": "store build", "budget": 7200, "start": "2024-11-10", "status": "shipped"},
    {"slug": "northfield-retainer", "client": "northfield-roasters", "title": "Northfield Roasters — monthly retainer",
     "kind": "retainer", "budget": 800, "start": "2025-01-01", "status": "ongoing"},
    {"slug": "marlowe-build", "client": "marlowe-finch", "title": "Marlowe & Finch — new store build",
     "kind": "store build", "budget": 5400, "start": "2025-02-20", "status": "shipped"},
    {"slug": "marlowe-retainer", "client": "marlowe-finch", "title": "Marlowe & Finch — monthly retainer",
     "kind": "retainer", "budget": 800, "start": "2025-03-01", "status": "ongoing"},
    {"slug": "kestrel-build", "client": "kestrel-outdoor", "title": "Kestrel Outdoor — store build",
     "kind": "store build", "budget": 8900, "start": "2025-05-25", "status": "in progress"},
    {"slug": "bramble-build", "client": "bramble-co", "title": "Bramble & Co — original store build",
     "kind": "store build", "budget": 4600, "start": "2024-06-15", "status": "shipped"},
]

# (client_slug, project_slug or None, amount, status, days_after_start)
INVOICES = [
    ("northfield-roasters", "northfield-relaunch", 3600, "paid", 0),
    ("northfield-roasters", "northfield-relaunch", 3600, "paid", 45),
    ("northfield-roasters", "northfield-retainer", 800, "paid", 210),
    ("northfield-roasters", "northfield-retainer", 800, "paid", 240),
    ("northfield-roasters", "northfield-retainer", 800, "unpaid", 270),
    ("marlowe-finch", "marlowe-build", 2700, "paid", 0),
    ("marlowe-finch", "marlowe-build", 2700, "partial", 60),
    ("marlowe-finch", "marlowe-retainer", 800, "paid", 150),
    ("kestrel-outdoor", "kestrel-build", 4450, "paid", 0),
    ("kestrel-outdoor", "kestrel-build", 4450, "unpaid", 70),
    ("bramble-co", "bramble-build", 4600, "paid", 5),
]

NOTES = [
    {
        "slug": "meeting-northfield-2025-06-12",
        "title": "Call with Northfield — wholesale portal ask",
        "client": "northfield-roasters",
        "date": "2025-06-12",
        "body": (
            "They want a login-gated wholesale price list bolted onto the existing store "
            "rather than a separate B2B platform. Quoted it informally as a retainer add-on, "
            "not a new build — keep it that way unless scope grows past ~10 hours.\n\n"
            "Related: [[Northfield Roasters]], [[Northfield Roasters — monthly retainer]]"
        ),
    },
    {
        "slug": "meeting-marlowe-2025-07-02",
        "title": "Marlowe & Finch — packaging photography delay",
        "client": "marlowe-finch",
        "date": "2025-07-02",
        "body": (
            "Photographer cancelled twice. Launch date is soft-blocked on new PDP imagery, "
            "not on anything we control. Flagged it back to them in writing.\n\n"
            "Related: [[Marlowe & Finch]], [[Marlowe & Finch — new store build]]"
        ),
    },
    {
        "slug": "idea-checkout-upsell",
        "title": "Idea — post-purchase upsell block for retainer clients",
        "client": None,
        "date": "2025-04-18",
        "body": (
            "Could roll this out as a standard retainer deliverable instead of one-off scope. "
            "Worth pricing separately before offering it — needs testing on one store first.\n\n"
            "Candidates: [[Northfield Roasters]], [[Marlowe & Finch]]"
        ),
    },
    {
        "slug": "meeting-kestrel-kickoff-2025-05-20",
        "title": "Kestrel Outdoor — kickoff notes",
        "client": "kestrel-outdoor",
        "date": "2025-05-20",
        "body": (
            "Seasonal inventory swings hard — needs a theme that handles sold-out states "
            "gracefully rather than hiding products. Budget agreed at £8,900, split 50/50.\n\n"
            "Related: [[Kestrel Outdoor]], [[Kestrel Outdoor — store build]]"
        ),
    },
    {
        "slug": "meeting-bramble-offboarding-2025-03-01",
        "title": "Bramble & Co — retainer lapsed",
        "client": "bramble-co",
        "date": "2025-03-01",
        "body": (
            "They paused the retainer to bring things in-house. Build itself is fully paid. "
            "No open scope, no chasing needed — just noting it so it doesn't look like a gap.\n\n"
            "Related: [[Bramble & Co]]"
        ),
    },
    {
        "slug": "prospect-vantage-2025-07-15",
        "title": "Vantage Fitness — inbound enquiry",
        "client": "vantage-fitness",
        "date": "2025-07-15",
        "body": (
            "B2B + D2C hybrid, larger than our usual build. Ballparked £9k-ish given the "
            "wholesale login logic alone. Proposal not sent yet.\n\n"
            "Related: [[Vantage Fitness]], [[Proposal — Vantage Fitness]]"
        ),
    },
]

PROPOSALS = [
    {
        "slug": "proposal-vantage-fitness",
        "title": "Proposal — Vantage Fitness",
        "client": "vantage-fitness",
        "date": "2025-07-20",
        "amount": 9000,
        "status": "draft",
        "body": (
            "Draft only — not sent. Store build + wholesale portal, £9,000, 8-week timeline.\n\n"
            "Related: [[Vantage Fitness]], [[Vantage Fitness — inbound enquiry]]"
        ),
    },
]


def w(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def frontmatter(**kv) -> str:
    lines = ["---"]
    for k, v in kv.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        elif v is not None:
            lines.append(f"{k}: {v}")
    lines.append("---\n")
    return "\n".join(lines)


def main():
    rng = random.Random(SEED)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    by_slug = {c["slug"]: c for c in CLIENTS}

    # studio overview note — a natural hub
    overview = frontmatter(type="note", tags=["studio"]) + (
        f"# {STUDIO_NAME}\n\n"
        "Two-person Shopify studio. Store builds run roughly £4,000-£9,000 depending on "
        "scope. Ongoing clients sit on an £800/month retainer for maintenance, small "
        "features and support.\n\n"
        "Clients:\n" +
        "\n".join(f"- [[{c['name']}]] — {c['industry']}, {c['status']}" for c in CLIENTS)
    )
    w(OUT / "notes" / "studio-overview.md", overview)

    # clients
    for c in CLIENTS:
        related_projects = [p for p in PROJECTS if p["client"] == c["slug"]]
        related_notes = [n for n in NOTES if n.get("client") == c["slug"]]
        body = frontmatter(type="client", tags=[c["status"].replace(" ", "-")]) + (
            f"# {c['name']}\n\n"
            f"- Industry: {c['industry']}\n"
            f"- Client since: {c['since']}\n"
            f"- Status: {c['status']}\n\n"
            "## Projects\n" +
            "\n".join(f"- [[{p['title']}]]" for p in related_projects) + "\n\n"
            "## Notes\n" +
            "\n".join(f"- [[{n['title']}]]" for n in related_notes)
        )
        w(OUT / "clients" / f"{c['slug']}.md", body)

    # projects
    for p in PROJECTS:
        client = by_slug[p["client"]]
        related_invoices = [i for i in INVOICES if i[1] == p["slug"]]
        body = frontmatter(type="project", tags=[p["kind"].replace(" ", "-"), p["status"].replace(" ", "-")]) + (
            f"# {p['title']}\n\n"
            f"- Client: [[{client['name']}]]\n"
            f"- Kind: {p['kind']}\n"
            f"- Budget: £{p['budget']:,}\n"
            f"- Start: {p['start']}\n"
            f"- Status: {p['status']}\n\n"
            "## Invoices\n" +
            "\n".join(f"- £{i[2]:,} — {i[3]}" for i in related_invoices)
        )
        w(OUT / "projects" / f"{p['slug']}.md", body)

    # invoices
    for idx, (client_slug, project_slug, amount, status, offset) in enumerate(INVOICES, start=1):
        client = by_slug[client_slug]
        project = next((p for p in PROJECTS if p["slug"] == project_slug), None)
        num = f"INV-{1000 + idx}"
        title = f"{num} — {client['name']}"
        body = frontmatter(type="invoice", tags=[status]) + (
            f"# {title}\n\n"
            f"- Client: [[{client['name']}]]\n"
            + (f"- Project: [[{project['title']}]]\n" if project else "") +
            f"- Amount: £{amount:,}\n"
            f"- Status: {status}\n"
        )
        w(OUT / "invoices" / f"{num.lower()}.md", body)

    # notes
    for n in NOTES:
        body = frontmatter(type="note", tags=["meeting"] if "meeting" in n["slug"] else ["idea"], date=n["date"]) + (
            f"# {n['title']}\n\n{n['body']}\n"
        )
        w(OUT / "notes" / f"{n['slug']}.md", body)

    # proposals
    for p in PROPOSALS:
        client = by_slug[p["client"]]
        body = frontmatter(type="proposal", tags=[p["status"]], date=p["date"]) + (
            f"# {p['title']}\n\n"
            f"- Client: [[{client['name']}]]\n"
            f"- Amount: £{p['amount']:,}\n"
            f"- Status: {p['status']}\n\n"
            f"{p['body']}\n"
        )
        w(OUT / "proposals" / f"{p['slug']}.md", body)

    total = sum(1 for _ in OUT.rglob("*.md"))
    print(f"Generated {total} demo files under {OUT} (seed={SEED})")


if __name__ == "__main__":
    main()
