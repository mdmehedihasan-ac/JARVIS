"""Episodic memory — append-only log of every user/assistant turn.

Adapted from ``jarvis_episodic.py`` in mdmehedihasan-ac/JARVIS.  Embeddings are
optional: when ``GEMINI_API_KEY`` is set we vectorize via
``text-embedding-004``, otherwise we fall back to a keyword search.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvismk2.core.config import get_config

EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_DIM = 768


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    den_a = sum(x * x for x in a) ** 0.5
    den_b = sum(x * x for x in b) ** 0.5
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


class EpisodicMemory:
    """Persistent semantic+chronological log."""

    def __init__(
        self,
        episodes_path: Optional[Path] = None,
        embeddings_path: Optional[Path] = None,
        max_episodes: int = 5000,
    ) -> None:
        cfg = get_config()
        mem_dir = cfg.data_dir / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        self._episodes_path = episodes_path or (mem_dir / "episodes.jsonl")
        self._embeddings_path = embeddings_path or (mem_dir / "episodes_embeddings.json")
        self.max_episodes = max_episodes
        self._lock = threading.Lock()
        self._episodes: List[Dict[str, Any]] = []
        self._embeddings: Dict[str, List[float]] = {}
        self._api_key = cfg.cloud.gemini
        self._load()

    # ── persistence ────────────────────────────────────────────────────
    def _load(self) -> None:
        with self._lock:
            if self._episodes_path.exists():
                try:
                    with self._episodes_path.open("r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                self._episodes.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    pass
                if len(self._episodes) > self.max_episodes:
                    self._episodes = self._episodes[-self.max_episodes :]
            if self._embeddings_path.exists():
                try:
                    self._embeddings = json.loads(
                        self._embeddings_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    self._embeddings = {}

    def _append(self, ep: Dict[str, Any]) -> None:
        try:
            with self._episodes_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ep, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _save_embeddings(self) -> None:
        try:
            self._embeddings_path.write_text(
                json.dumps(self._embeddings), encoding="utf-8"
            )
        except OSError:
            pass

    # ── embeddings ─────────────────────────────────────────────────────
    def _embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip() or not self._api_key:
            return None
        try:
            from google import genai  # type: ignore
        except ImportError:
            return None
        try:
            client = genai.Client(api_key=self._api_key)
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text[:5000],
            )
            if result and getattr(result, "embeddings", None):
                first = result.embeddings[0]
                values = getattr(first, "values", None)
                if values:
                    return list(values)
        except Exception as e:  # pragma: no cover — network/auth
            print(f"[Episodic] embed error: {e}")
        return None

    @staticmethod
    def _episode_id(ep: Dict[str, Any]) -> str:
        text = (ep.get("user", "") + ep.get("jarvis", ""))[:200]
        h = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
        return f"{int(ep.get('ts', time.time()))}_{h}"

    # ── public API ─────────────────────────────────────────────────────
    def aggiungi(
        self,
        user_input: str,
        jarvis_output: str,
        tools: Optional[List[str]] = None,
        contesto: Optional[Dict[str, Any]] = None,
        generate_embedding: bool = True,
    ) -> str:
        ep: Dict[str, Any] = {
            "ts": time.time(),
            "user": user_input[:1500],
            "jarvis": jarvis_output[:1500],
            "tools": list(tools or []),
            "contesto": dict(contesto or {}),
        }
        eid = self._episode_id(ep)
        ep["id"] = eid

        with self._lock:
            self._episodes.append(ep)
            if len(self._episodes) > self.max_episodes:
                self._episodes = self._episodes[-self.max_episodes :]
        self._append(ep)

        if generate_embedding and self._api_key:
            def _gen() -> None:
                vec = self._embed(f"USER: {user_input}\nJARVIS: {jarvis_output}")
                if vec:
                    with self._lock:
                        self._embeddings[eid] = vec
                    self._save_embeddings()

            threading.Thread(target=_gen, daemon=True).start()

        return eid

    def cerca_simili(
        self, query: str, top_k: int = 5, min_score: float = 0.3
    ) -> List[Dict[str, Any]]:
        if not query:
            return []
        if not self._embeddings or not self._api_key:
            return self._keyword_search(query, top_k)

        qvec = self._embed(query)
        if not qvec:
            return self._keyword_search(query, top_k)

        out: List[Dict[str, Any]] = []
        with self._lock:
            for ep in self._episodes:
                vec = self._embeddings.get(ep["id"])
                if not vec:
                    continue
                score = _cosine(qvec, vec)
                if score >= min_score:
                    out.append({**ep, "score": score})
        out.sort(key=lambda x: -x["score"])
        return out[:top_k]

    def _keyword_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        q_low = query.lower()
        tokens = {w for w in q_low.split() if len(w) >= 3}
        if not tokens:
            return []
        scored: List[Dict[str, Any]] = []
        with self._lock:
            for ep in self._episodes:
                blob = (ep.get("user", "") + " " + ep.get("jarvis", "")).lower()
                score = sum(1 for t in tokens if t in blob)
                if score:
                    scored.append({**ep, "score": float(score)})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def episodi_recenti(self, n: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._episodes[-n:])

    def render_prompt_block(self, query: str, top_k: int = 3) -> str:
        eps = self.cerca_simili(query, top_k=top_k)
        if not eps:
            return ""
        lines = ["[MEM]"]
        for ep in eps:
            u = ep.get("user", "")[:60].replace("\n", " ")
            j = ep.get("jarvis", "")[:60].replace("\n", " ")
            lines.append(f"Q:{u} A:{j}")
        return "\n".join(lines)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "totale_episodi": len(self._episodes),
                "con_embedding": len(self._embeddings),
                "max": self.max_episodes,
            }


# ── singleton ─────────────────────────────────────────────────────────────

_episodic: Optional[EpisodicMemory] = None


def get_episodic() -> EpisodicMemory:
    global _episodic
    if _episodic is None:
        _episodic = EpisodicMemory()
    return _episodic
