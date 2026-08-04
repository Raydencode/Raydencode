"""
vault.py — turns a set of read-only folders into a searchable graph.

Every markdown/text/PDF file becomes a node. [[wikilinks]] between markdown
files become edges. Nothing in this file ever writes to the folders it reads.
"""

from __future__ import annotations

import re
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB — skip anything bigger
SKIP_DIR_NAMES = {"node_modules", ".git", ".svn", "__pycache__", ".DS_Store", ".obsidian"}
TEXT_EXTS = {".md", ".markdown", ".txt"}
PDF_EXTS = {".pdf"}
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FRONTMATTER_KV_RE = re.compile(r"^([A-Za-z0-9_\-]+):\s*(.*)$")
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass
class Node:
    id: str
    title: str
    type: str
    path: str
    root_label: str
    mtime: float
    size: int
    snippet: str = ""
    content: str = ""
    tags: list = field(default_factory=list)
    degree: int = 0

    def to_public_dict(self):
        # everything except full content — used for the graph payload
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "path": self.path,
            "root": self.root_label,
            "mtime": self.mtime,
            "size": self.size,
            "snippet": self.snippet,
            "tags": self.tags,
            "degree": self.degree,
        }


def _extract_pdf_text(raw: bytes) -> str:
    """
    Minimal, dependency-free PDF text extractor.

    Decompresses FlateDecode streams and pulls text out of Tj/TJ operators.
    This is not a full PDF parser — it will miss text in unusual encodings
    or scanned (image-only) PDFs — but it needs zero third-party packages.
    """
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.DOTALL):
        blob = m.group(1)
        try:
            blob = zlib.decompress(blob)
        except Exception:
            pass  # not flate-encoded (or already plain) — try as-is
        for tm in re.finditer(rb"\((.*?)(?<!\\)\)\s*Tj", blob, re.DOTALL):
            chunks.append(tm.group(1))
        for tm in re.finditer(rb"\[(.*?)\]\s*TJ", blob, re.DOTALL):
            parts = re.findall(rb"\((.*?)(?<!\\)\)", tm.group(1), re.DOTALL)
            chunks.append(b" ".join(parts))
    text = b" ".join(chunks).decode("latin-1", errors="ignore")
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return text


def _parse_frontmatter(text: str):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        kv = FRONTMATTER_KV_RE.match(line.strip())
        if kv:
            key, val = kv.group(1).lower(), kv.group(2).strip().strip('"\'')
            if key == "tags":
                meta[key] = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
            else:
                meta[key] = val
    body = text[m.end():]
    return meta, body


def _infer_type(root: Path, file_path: Path, frontmatter_type: str | None) -> str:
    if frontmatter_type:
        return frontmatter_type.lower()
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        rel = file_path
    parts = rel.parts
    if len(parts) > 1:
        # first subfolder under the indexed root, singular-ish
        label = parts[0].lower().rstrip("s")
        return label or "note"
    return "note"


class Vault:
    def __init__(self, roots: list[str]):
        self.roots = [Path(r).expanduser() for r in roots]
        self.nodes: dict[str, Node] = {}
        self.edges: list[tuple[str, str]] = []
        self.title_index: dict[str, str] = {}  # lowercase title/stem -> node id
        self.skipped = {"too_big": 0, "unreadable": 0, "unsupported": 0, "missing_root": 0}
        self._build()

    # -- indexing ---------------------------------------------------------

    def _build(self):
        for root in self.roots:
            if not root.exists():
                self.skipped["missing_root"] += 1
                continue
            root_label = root.name or str(root)
            for path in root.rglob("*"):
                if path.is_dir():
                    if path.name in SKIP_DIR_NAMES:
                        # rglob has no prune; we filter matches inside skipped dirs below
                        continue
                    continue
                if any(part in SKIP_DIR_NAMES for part in path.parts):
                    continue
                self._index_file(root, root_label, path)
        self._link_wikilinks()
        self._compute_degrees()

    def _index_file(self, root: Path, root_label: str, path: Path):
        ext = path.suffix.lower()
        if ext not in TEXT_EXTS and ext not in PDF_EXTS:
            return
        try:
            size = path.stat().st_size
        except OSError:
            self.skipped["unreadable"] += 1
            return
        if size > MAX_FILE_BYTES:
            self.skipped["too_big"] += 1
            return

        try:
            if ext in PDF_EXTS:
                raw = path.read_bytes()
                text = _extract_pdf_text(raw)
                meta, body = {}, text
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
                meta, body = _parse_frontmatter(text)
        except OSError:
            self.skipped["unreadable"] += 1
            return

        node_id = str(path)
        h1 = H1_RE.search(body)
        title = meta.get("title") or (h1.group(1).strip() if h1 else None) or path.stem
        node_type = _infer_type(root, path, meta.get("type"))
        tags = meta.get("tags", [])
        snippet = " ".join(body.split())[:220]

        node = Node(
            id=node_id,
            title=title,
            type=node_type,
            path=str(path),
            root_label=root_label,
            mtime=path.stat().st_mtime,
            size=size,
            snippet=snippet,
            content=body,
            tags=tags,
        )
        self.nodes[node_id] = node
        self.title_index[title.lower()] = node_id
        self.title_index[path.stem.lower()] = node_id

    def _link_wikilinks(self):
        for node in self.nodes.values():
            if not node.content:
                continue
            for m in WIKILINK_RE.finditer(node.content):
                target_name = m.group(1).strip().lower()
                target_id = self.title_index.get(target_name)
                if target_id and target_id != node.id:
                    edge = (node.id, target_id)
                    if edge not in self.edges and (edge[1], edge[0]) not in self.edges:
                        self.edges.append(edge)

    def _compute_degrees(self):
        for a, b in self.edges:
            if a in self.nodes:
                self.nodes[a].degree += 1
            if b in self.nodes:
                self.nodes[b].degree += 1

    # -- reporting ----------------------------------------------------------

    def stats(self) -> dict:
        by_type: dict[str, int] = {}
        for n in self.nodes.values():
            by_type[n.type] = by_type.get(n.type, 0) + 1
        hubs = sorted(self.nodes.values(), key=lambda n: n.degree, reverse=True)[:10]
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "by_type": by_type,
            "top_hubs": [(n.title, n.degree, n.type) for n in hubs],
            "skipped": self.skipped,
            "roots": [str(r) for r in self.roots],
        }

    def print_report(self):
        s = self.stats()
        print(f"ULTRON vault index — {s['total_nodes']} notes, {s['total_edges']} links")
        print(f"  roots: {', '.join(s['roots'])}")
        for t, c in sorted(s["by_type"].items(), key=lambda kv: -kv[1]):
            print(f"  {t:>12}: {c}")
        if s["skipped"]["too_big"] or s["skipped"]["unreadable"] or s["skipped"]["missing_root"]:
            print(f"  skipped: {s['skipped']}")
        print("  top hubs:")
        for title, degree, t in s["top_hubs"]:
            print(f"    {degree:>3} links  [{t}]  {title}")

    # -- query ----------------------------------------------------------

    def graph_payload(self) -> dict:
        return {
            "nodes": [n.to_public_dict() for n in self.nodes.values()],
            "edges": [{"source": a, "target": b} for a, b in self.edges],
        }

    def get_note(self, node_id: str) -> dict | None:
        n = self.nodes.get(node_id)
        if not n:
            return None
        d = n.to_public_dict()
        d["content"] = n.content
        d["links_out"] = [b for a, b in self.edges if a == node_id]
        d["links_in"] = [a for a, b in self.edges if b == node_id]
        return d

    def search(self, query: str, limit: int = 8) -> list[dict]:
        query = query.strip().lower()
        if not query:
            return []
        terms = [t for t in re.split(r"\W+", query) if t]
        if not terms:
            return []
        scored = []
        for n in self.nodes.values():
            title_l = n.title.lower()
            content_l = n.content.lower()
            score = 0.0
            for t in terms:
                score += title_l.count(t) * 5
                score += content_l.count(t) * 1
            if score > 0:
                scored.append((score, n))
        scored.sort(key=lambda sn: sn[0], reverse=True)
        results = []
        for score, n in scored[:limit]:
            results.append({
                "id": n.id,
                "title": n.title,
                "type": n.type,
                "path": n.path,
                "root": n.root_label,
                "score": score,
                "snippet": _excerpt(n.content, terms),
            })
        return results

    def top_hubs(self, limit: int = 10) -> list[dict]:
        hubs = sorted(self.nodes.values(), key=lambda n: n.degree, reverse=True)[:limit]
        return [n.to_public_dict() for n in hubs]


def _excerpt(content: str, terms: list[str], width: int = 160) -> str:
    lc = content.lower()
    for t in terms:
        idx = lc.find(t)
        if idx != -1:
            start = max(0, idx - width // 2)
            end = min(len(content), idx + width // 2)
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(content) else ""
            return prefix + " ".join(content[start:end].split()) + suffix
    return " ".join(content.split())[:width]
