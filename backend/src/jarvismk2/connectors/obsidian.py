"""Obsidian vault connector.

Combines:

* OpenJarvis-style **vault scanner** — walks ``.md`` files, parses simple
  frontmatter, emits ``Document``-like dicts.
* MHE Jarvis-style **brain sync** — maps the ``Jarvis/{clienti,errori_risolti,
  sessioni}`` convention into the right lobes of :class:`Cervello`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

from jarvismk2.brain.cervello import get_cervello
from jarvismk2.core.config import get_config

_TEXT_EXTS = {".md", ".markdown", ".txt"}
_SKIP_DIRS = {
    ".obsidian",
    ".git",
    ".trash",
    "__pycache__",
    "node_modules",
    ".venv",
}


@dataclass
class ObsidianDocument:
    doc_id: str
    title: str
    content: str
    rel_path: str
    timestamp: datetime
    url: str
    metadata: Dict[str, Any]


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Minimal YAML-frontmatter parser (no PyYAML)."""
    if not text.startswith("---"):
        return {}, text
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        return {}, text
    raw = rest[:end]
    body_start = end + len("\n---")
    if body_start < len(rest) and rest[body_start] == "\n":
        body_start += 1
    body = rest[body_start:]
    meta: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1]
            meta[k] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
        else:
            meta[k] = v.strip("'\"")
    return meta, body


class ObsidianConnector:
    """Scan a vault and sync notes into the cognitive brain."""

    def __init__(self, vault_path: Optional[str] = None, subdir: Optional[str] = None) -> None:
        cfg = get_config()
        self.vault_path = Path(
            os.path.expanduser(vault_path or cfg.obsidian.vault_path or "")
        )
        self.subdir = subdir or cfg.obsidian.subdir

    def is_configured(self) -> bool:
        return bool(self.vault_path) and self.vault_path.is_dir()

    # ── vault walk ────────────────────────────────────────────────────
    def iter_documents(
        self, since: Optional[datetime] = None
    ) -> Iterator[ObsidianDocument]:
        if not self.is_configured():
            return iter([])

        vault = self.vault_path
        vault_name = vault.name
        collected: List[Path] = []
        for root, dirs, files in os.walk(vault):
            dirs[:] = [
                d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")
            ]
            for fn in files:
                p = Path(root) / fn
                if p.suffix.lower() in _TEXT_EXTS:
                    collected.append(p)

        for p in collected:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if since and mtime < since:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, _body = _parse_frontmatter(text)
            title = meta.get("title") or p.stem
            rel = p.relative_to(vault)
            url = (
                f"obsidian://open?vault={quote(vault_name)}&file={quote(str(rel))}"
            )
            yield ObsidianDocument(
                doc_id=f"obsidian:{rel}",
                title=str(title),
                content=text,
                rel_path=str(rel),
                timestamp=mtime,
                url=url,
                metadata={k: v for k, v in meta.items() if k != "title"},
            )

    # ── brain sync ────────────────────────────────────────────────────
    def sync_to_brain(self) -> int:
        """Seed the cognitive brain's lobes from the Jarvis subdir convention.

        Returns the number of new neurons added.
        """
        if not self.is_configured():
            return 0
        return get_cervello().sync_obsidian(vault_path=str(self.vault_path))

    # ── write note ────────────────────────────────────────────────────
    def write_note(
        self,
        title: str,
        content: str,
        subdir: str = "web",
        tags: Optional[List[str]] = None,
        source_url: str = "",
    ) -> Dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "error": "vault non configurato"}
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title).strip()[:80] or "nota_web"
        folder = self.vault_path / subdir
        folder.mkdir(parents=True, exist_ok=True)
        note_path = folder / f"{safe_title}.md"
        tag_list = ", ".join(f'"{t}"' for t in (tags or ["web", "auto"]))
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        front = f"---\ntitle: {safe_title}\ndate: {ts}\ntags: [{tag_list}]\n"
        if source_url:
            front += f"source: {source_url}\n"
        front += "---\n\n"
        note_path.write_text(front + content, encoding="utf-8")
        return {"ok": True, "path": str(note_path), "title": safe_title}

    # ── incremental sync ──────────────────────────────────────────────
    def sync_to_brain_incremental(self, since_ts: Optional[float] = None) -> int:
        if not self.is_configured():
            return 0
        since = None
        if since_ts:
            from datetime import timezone as _tz
            since = datetime.fromtimestamp(since_ts, tz=timezone.utc)
        return get_cervello().sync_obsidian(vault_path=str(self.vault_path))

    # ── search ────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        if not self.is_configured() or not query:
            return []
        q = query.lower()
        out: List[Dict[str, Any]] = []
        for doc in self.iter_documents():
            blob = (doc.title + "\n" + doc.content).lower()
            score = blob.count(q)
            if score:
                snippet = doc.content[:240].replace("\n", " ")
                out.append(
                    {
                        "title": doc.title,
                        "rel_path": doc.rel_path,
                        "url": doc.url,
                        "snippet": snippet,
                        "score": score,
                    }
                )
        out.sort(key=lambda x: -x["score"])
        return out[:top_k]
