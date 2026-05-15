"""Cervello a 6 lobi — cognitive brain with Hebbian neurons.

Inspired by ``cervello_jarvis.py`` in mdmehedihasan-ac/JARVIS but adapted to:

* use the project-wide :class:`Config` for storage paths,
* publish events to the :class:`EventBus` instead of printing,
* expose async-safe ``thread.Lock``-guarded mutation,
* return frontend-friendly dicts for the brain graph view.

Each :class:`Neurone` is a small piece of declarative knowledge sitting inside
one of six lobes.  Activations reinforce the neuron (Hebb), inactivity decays
it.  An optional Obsidian vault sync thread keeps lobes populated from
markdown files.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Neurone:
    """A reinforcement-learning friendly piece of memory."""

    id: str
    contenuto: str
    tipo: str
    lobo: str
    forza: float = 0.5
    accessi: int = 1
    ultima_attivazione: str = ""
    fonte: str = "conversazione"
    tag: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def attiva(self) -> None:
        """Hebb's rule: cells that fire together, wire together."""
        self.accessi += 1
        self.forza = min(1.0, self.forza + 0.05)
        self.ultima_attivazione = datetime.now().isoformat()

    def decade(self) -> None:
        """Time-based forgetting curve."""
        self.forza = max(0.1, self.forza - 0.01)


@dataclass
class Lobo:
    nome: str
    funzione: str
    colore_hud: str
    neuroni: Dict[str, Neurone] = field(default_factory=dict)
    attivo: bool = True
    carico: float = 0.0

    def aggiungi(self, n: Neurone) -> None:
        self.neuroni[n.id] = n

    def cerca(self, query: str, top: int = 5) -> List[Neurone]:
        q = query.lower()
        hits: List[Neurone] = []
        for n in self.neuroni.values():
            if q in n.contenuto.lower() or any(q in t.lower() for t in n.tag):
                n.attiva()
                hits.append(n)
        return sorted(hits, key=lambda x: x.forza, reverse=True)[:top]


# ---------------------------------------------------------------------------
# Lobe definitions
# ---------------------------------------------------------------------------

_LOBE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "frontale": {
        "nome": "Lobo Frontale",
        "funzione": "Pianificazione, decisioni, task complessi, sviluppo software",
        "colore_hud": "#00d4ff",
    },
    "temporale": {
        "nome": "Lobo Temporale",
        "funzione": "Memoria clienti, conversazioni, linguaggio, nomi",
        "colore_hud": "#7b2fff",
    },
    "parietale": {
        "nome": "Lobo Parietale",
        "funzione": "Controllo sistema, spazio, file system, schermo",
        "colore_hud": "#ff6b35",
    },
    "occipitale": {
        "nome": "Lobo Occipitale",
        "funzione": "Visione, screenshot, riconoscimento UI",
        "colore_hud": "#00ff88",
    },
    "cerebellum": {
        "nome": "Cervelletto",
        "funzione": "Abitudini, sequenze automatiche, skill ricorrenti",
        "colore_hud": "#ffcc00",
    },
    "ippocampo": {
        "nome": "Ippocampo",
        "funzione": "Memoria a lungo termine, errori risolti, apprendimento",
        "colore_hud": "#ff2d55",
    },
}

_ROUTING_KEYWORDS: Dict[str, List[str]] = {
    "frontale": ["crea", "sviluppa", "pianifica", "sito", "codice", "progetto", "design", "app"],
    "temporale": ["cliente", "nome", "chi è", "ricorda", "parlami di", "preferenze", "storia"],
    "parietale": ["apri", "file", "cartella", "schermo", "clicca", "volume", "app", "sistema"],
    "occipitale": ["vedi", "guarda", "screenshot", "cosa c'è", "analizza immagine"],
    "ippocampo": ["errore", "problema", "fix", "debug", "risolvi", "non funziona"],
}


# ---------------------------------------------------------------------------
# Cervello
# ---------------------------------------------------------------------------


class Cervello:
    """Six-lobe cognitive brain with persistence, decay, and an Obsidian hook."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        vault_path: Optional[str] = None,
        autosave: bool = True,
    ) -> None:
        cfg = get_config()
        self._storage = storage_path or (cfg.data_dir / "cervello.json")
        self._storage.parent.mkdir(parents=True, exist_ok=True)
        self._vault: Optional[Path] = None
        if vault_path:
            p = Path(vault_path).expanduser()
            if p.is_dir():
                self._vault = p
        self._autosave = autosave
        self._lock = threading.RLock()
        self._bus = get_bus()

        self.lobi: Dict[str, Lobo] = {
            name: Lobo(
                nome=meta["nome"],
                funzione=meta["funzione"],
                colore_hud=meta["colore_hud"],
            )
            for name, meta in _LOBE_DEFAULTS.items()
        }

        self._load()

    # ── routing ────────────────────────────────────────────────────────
    def quale_lobo(self, query: str) -> str:
        q = query.lower()
        for lobo, kws in _ROUTING_KEYWORDS.items():
            if any(k in q for k in kws):
                return lobo
        return "cerebellum"

    # ── pensa ──────────────────────────────────────────────────────────
    def pensa(self, query: str, max_snippets: int = 8) -> Dict[str, Any]:
        """Run the routing + lobe activation; return context for the prompt.

        Returns dict with keys: lobo_attivato, snippets, top_forza.
        top_forza is the confidence of the best matching neuron (0..1).
        """
        lobo_primario = self.quale_lobo(query)
        snippets: List[str] = []
        top_forza: float = 0.0

        with self._lock:
            self.lobi[lobo_primario].carico = min(
                1.0, self.lobi[lobo_primario].carico + 0.3
            )

            # Primary lobe first, then the others
            order = [lobo_primario] + [n for n in self.lobi if n != lobo_primario]
            for name in order:
                for neurone in self.lobi[name].cerca(query, top=2):
                    snippets.append(f"[{name.upper()}] {neurone.contenuto}")
                    top_forza = max(top_forza, neurone.forza)
                    if len(snippets) >= max_snippets:
                        break
                if len(snippets) >= max_snippets:
                    break

            # Gentle decay of all lobe loads
            for lobo in self.lobi.values():
                lobo.carico = max(0.0, lobo.carico - 0.1)

        self._bus.publish(
            EventType.BRAIN_LOBO_LOAD_CHANGED,
            {"lobo": lobo_primario, "carico": self.lobi[lobo_primario].carico},
        )
        return {"lobo_attivato": lobo_primario, "snippets": snippets, "top_forza": top_forza}

    # ── learn ──────────────────────────────────────────────────────────
    def impara(
        self,
        contenuto: str,
        tipo: str,
        lobo: str,
        fonte: str = "conversazione",
        tag: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if lobo not in self.lobi:
            raise ValueError(f"Unknown lobo '{lobo}'. Valid: {list(self.lobi)}")
        hash_key = self._norm_hash(contenuto)
        with self._lock:
            for l in self.lobi.values():
                for n in l.neuroni.values():
                    if self._norm_hash(n.contenuto) == hash_key:
                        n.attiva()
                        if self._autosave:
                            self._save()
                        return n.id
        nid = f"{lobo}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        n = Neurone(
            id=nid,
            contenuto=contenuto,
            tipo=tipo,
            lobo=lobo,
            forza=0.5,
            accessi=1,
            ultima_attivazione=datetime.now().isoformat(),
            fonte=fonte,
            tag=list(tag or []),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self.lobi[lobo].aggiungi(n)
        if self._autosave:
            self._save()
        self._bus.publish(
            EventType.BRAIN_NEURON_LEARNED,
            {"id": nid, "lobo": lobo, "contenuto": contenuto[:120]},
        )
        return nid

    @staticmethod
    def _norm_hash(text: str) -> str:
        import re as _re
        return _re.sub(r"[^a-z0-9]", "", text.lower().strip())[:120]

    def cerca_fuzzy(self, query: str, top: int = 8) -> List[Dict[str, Any]]:
        q = query.lower()
        hits: List[tuple] = []
        with self._lock:
            for lobo in self.lobi.values():
                for n in lobo.neuroni.values():
                    score = 0
                    if q in n.contenuto.lower():
                        score += 3
                    for t in n.tag:
                        if q in t.lower():
                            score += 1
                    if score:
                        hits.append((score, n))
        hits.sort(key=lambda x: (-x[0], -x[1].forza))
        return [
            {
                "id": n.id,
                "contenuto": n.contenuto[:200],
                "lobo": n.lobo,
                "forza": round(n.forza, 2),
                "fonte": n.fonte,
                "tag": list(n.tag or []),
            }
            for _, n in hits[:top]
        ]

    # ── persistence ────────────────────────────────────────────────────
    def _save(self) -> None:
        try:
            with self._lock:
                data = {
                    name: {
                        "neuroni": {k: asdict(v) for k, v in lobo.neuroni.items()},
                        "carico": lobo.carico,
                    }
                    for name, lobo in self.lobi.items()
                }
            tmp = self._storage.with_suffix(self._storage.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._storage)
        except Exception as e:  # pragma: no cover — best-effort persistence
            print(f"[Cervello] save error: {e}")

    def _load(self) -> None:
        if not self._storage.exists():
            return
        try:
            raw = json.loads(self._storage.read_text(encoding="utf-8"))
            for name, lobo_data in raw.items():
                if name not in self.lobi:
                    continue
                for nid, nd in (lobo_data.get("neuroni") or {}).items():
                    try:
                        self.lobi[name].neuroni[nid] = Neurone(**nd)
                    except TypeError:
                        # legacy / malformed entry — skip
                        continue
                self.lobi[name].carico = float(lobo_data.get("carico", 0.0) or 0.0)
        except Exception as e:  # pragma: no cover
            print(f"[Cervello] load error: {e}")

    # ── periodic decay (run by background thread on demand) ─────────────
    def decay_all(self) -> None:
        with self._lock:
            for lobo in self.lobi.values():
                for neurone in lobo.neuroni.values():
                    neurone.decade()
        self._save()

    # ── views ──────────────────────────────────────────────────────────
    def stato(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "lobi": {
                    nome: {
                        "nome": lobo.nome,
                        "funzione": lobo.funzione,
                        "colore": lobo.colore_hud,
                        "neuroni": len(lobo.neuroni),
                        "carico": round(lobo.carico, 2),
                        "attivo": lobo.attivo,
                        "top": [
                            {"contenuto": n.contenuto[:80], "forza": round(n.forza, 2)}
                            for n in sorted(
                                lobo.neuroni.values(), key=lambda x: x.forza, reverse=True
                            )[:3]
                        ],
                    }
                    for nome, lobo in self.lobi.items()
                },
                "totale_neuroni": sum(len(l.neuroni) for l in self.lobi.values()),
                "ultimo_aggiornamento": datetime.now().isoformat(),
            }

    def grafo(self, max_per_lobo: int = 25) -> Dict[str, Any]:
        """Return force-directed graph payload for the frontend HUD."""
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        flat: List[tuple] = []

        with self._lock:
            for name, lobo in self.lobi.items():
                nodes.append(
                    {
                        "id": f"lobo:{name}",
                        "label": lobo.nome.upper(),
                        "type": "lobo",
                        "color": lobo.colore_hud,
                        "size": 22,
                        "lobo": name,
                        "carico": round(lobo.carico, 2),
                        "neuroni_count": len(lobo.neuroni),
                        "funzione": lobo.funzione[:60],
                    }
                )
                top = sorted(lobo.neuroni.values(), key=lambda x: x.forza, reverse=True)[
                    :max_per_lobo
                ]
                for n in top:
                    node_id = f"n:{n.id}"
                    nodes.append(
                        {
                            "id": node_id,
                            "label": n.contenuto[:40],
                            "type": "neurone",
                            "color": lobo.colore_hud,
                            "size": round(n.forza * 8 + 2, 1),
                            "lobo": name,
                            "tipo": n.tipo,
                            "forza": round(n.forza, 2),
                            "accessi": n.accessi,
                            "fonte": n.fonte,
                            "contenuto": n.contenuto[:200],
                            "tags": list(n.tag or []),
                        }
                    )
                    edges.append(
                        {
                            "source": f"lobo:{name}",
                            "target": node_id,
                            "type": "membership",
                            "weight": n.forza,
                        }
                    )
                    flat.append((node_id, set(n.tag or [])))

        # Synaptic edges between neurons that share a tag (max 2 per neuron)
        seen: set = set()
        for i, (id_a, tags_a) in enumerate(flat):
            if not tags_a:
                continue
            count = 0
            for j, (id_b, tags_b) in enumerate(flat):
                if i >= j or count >= 2:
                    continue
                shared = tags_a & tags_b
                if not shared:
                    continue
                pair = tuple(sorted((id_a, id_b)))
                if pair in seen:
                    continue
                seen.add(pair)
                edges.append(
                    {
                        "source": id_a,
                        "target": id_b,
                        "type": "synapse",
                        "weight": 0.4,
                        "shared_tags": list(shared)[:3],
                    }
                )
                count += 1

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "totale_nodi": len(nodes),
                "totale_archi": len(edges),
                "totale_lobi": len(self.lobi),
                "totale_neuroni": sum(len(l.neuroni) for l in self.lobi.values()),
            },
        }

    # ── Obsidian sync (called by connector or scheduler) ────────────────
    def sync_obsidian(self, vault_path: Optional[str] = None) -> int:
        """Read an Obsidian vault's Jarvis subdir and seed lobes.

        Returns the number of neurons added.  Designed to be idempotent: each
        markdown file maps to a deterministic neuron id.
        """
        cfg = get_config()
        vault: Optional[Path] = self._vault
        if vault_path:
            cand = Path(vault_path).expanduser()
            if cand.is_dir():
                vault = cand
        if vault is None:
            return 0

        root = vault / cfg.obsidian.subdir
        if not root.exists():
            return 0

        added = 0
        mapping = [
            ("clienti", "temporale", "cliente"),
            ("errori_risolti", "ippocampo", "errore"),
            ("sessioni", "frontale", "fatto"),
        ]
        for subdir, lobo, tipo in mapping:
            d = root / subdir
            if not d.exists():
                continue
            for md in d.glob("*.md"):
                stem = md.stem
                nid = f"obsidian_{subdir}_{stem}"
                with self._lock:
                    if nid in self.lobi[lobo].neuroni:
                        continue
                try:
                    text = md.read_text(encoding="utf-8")[:800]
                except OSError:
                    continue
                with self._lock:
                    self.lobi[lobo].neuroni[nid] = Neurone(
                        id=nid,
                        contenuto=f"{subdir.upper()} {stem}: {text}",
                        tipo=tipo,
                        lobo=lobo,
                        forza=0.6,
                        accessi=1,
                        ultima_attivazione=datetime.now().isoformat(),
                        fonte="obsidian",
                        tag=[subdir, stem],
                    )
                added += 1
        if added and self._autosave:
            self._save()
        return added


# ---------------------------------------------------------------------------
# Singleton helper + background decay
# ---------------------------------------------------------------------------

_cervello: Optional[Cervello] = None
_decay_thread: Optional[threading.Thread] = None
_decay_lock = threading.Lock()


def get_cervello() -> Cervello:
    global _cervello
    if _cervello is None:
        cfg = get_config()
        _cervello = Cervello(
            storage_path=cfg.data_dir / "cervello.json",
            vault_path=cfg.obsidian.vault_path or None,
        )
        _start_decay_thread()
    return _cervello


def _start_decay_thread(interval_sec: int = 3600) -> None:
    """Start a daemon thread that decays neurons once an hour."""
    global _decay_thread
    with _decay_lock:
        if _decay_thread and _decay_thread.is_alive():
            return

        def _loop() -> None:
            while True:
                time.sleep(interval_sec)
                try:
                    get_cervello().decay_all()
                except Exception:
                    pass

        _decay_thread = threading.Thread(target=_loop, daemon=True, name="cervello-decay")
        _decay_thread.start()
