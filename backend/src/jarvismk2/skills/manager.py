"""SkillsManager — CRUD + execution + auto-match."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jarvismk2.core.config import get_config

# Executor signature:  (tool_name, args_dict) -> (ok: bool, result: Any)
Executor = Callable[[str, Dict[str, Any]], "tuple[bool, Any]"]


_DEFAULT_SKILLS: Dict[str, Dict[str, Any]] = {
    "routine_mattutina": {
        "descrizione": "Apre Mail e Calendar, mette musica per iniziare la giornata",
        "azioni": [
            {"tool": "apri_applicazione", "args": {"nome_app": "Mail"}},
            {"tool": "apri_applicazione", "args": {"nome_app": "Calendar"}},
            {"tool": "controllo_spotify", "args": {"azione": "play"}},
        ],
        "tag": ["routine", "mattutina"],
        "trigger_keywords": ["buongiorno", "iniziamo la giornata", "routine mattutina"],
        "auto": True,
    },
    "pausa_pranzo": {
        "descrizione": "Mette Spotify in pausa e blocca lo schermo",
        "azioni": [
            {"tool": "controllo_spotify", "args": {"azione": "pause"}},
            {"tool": "premi_tasto", "args": {"tasto": "cmd+ctrl+q"}},
        ],
        "tag": ["pausa", "pranzo"],
        "trigger_keywords": ["pausa pranzo", "vado a mangiare", "torno tra un po"],
        "auto": True,
    },
    "fine_lavoro": {
        "descrizione": "Abbassa il volume e saluta",
        "azioni": [
            {"tool": "gestisci_volume", "args": {"livello": 20}},
            {
                "tool": "notifica_sistema",
                "args": {"titolo": "JARVIS", "messaggio": "Buona serata, signore."},
            },
        ],
        "tag": ["fine", "sera"],
        "trigger_keywords": ["fine giornata", "stacco", "ho finito di lavorare"],
        "auto": True,
    },
    "modalita_focus": {
        "descrizione": "Volume al minimo, focus deep work",
        "azioni": [
            {"tool": "gestisci_volume", "args": {"livello": 5}},
            {
                "tool": "notifica_sistema",
                "args": {"titolo": "JARVIS", "messaggio": "Modalità focus attivata."},
            },
        ],
        "tag": ["focus", "deep_work"],
        "trigger_keywords": ["modalità focus", "deep work", "concentrazione"],
        "auto": True,
    },
}


class SkillsManager:
    """Persistent skill store with execution.

    Parameters
    ----------
    executor:
        A callable that resolves a ``(tool_name, args)`` pair to an
        ``(ok, result)`` tuple.  When ``None``, :meth:`esegui` will refuse to
        run anything (CRUD still works).
    """

    def __init__(
        self,
        executor: Optional[Executor] = None,
        storage: Optional[Path] = None,
        seed_defaults: bool = True,
    ) -> None:
        cfg = get_config()
        self._executor = executor
        self._storage = storage or (cfg.data_dir / "skills.json")
        self._storage.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._load()
        if seed_defaults and not self._skills:
            with self._lock:
                self._skills = {
                    k: {**v, "created_ts": time.time()} for k, v in _DEFAULT_SKILLS.items()
                }
            self._save()

    # ── executor ──────────────────────────────────────────────────────
    def set_executor(self, executor: Executor) -> None:
        self._executor = executor

    # ── persistence ───────────────────────────────────────────────────
    def _load(self) -> None:
        if not self._storage.exists():
            return
        try:
            self._skills = json.loads(self._storage.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Skills] load error: {e}")
            self._skills = {}

    def _save(self) -> None:
        tmp = self._storage.with_suffix(self._storage.suffix + ".tmp")
        try:
            with self._lock:
                tmp.write_text(
                    json.dumps(self._skills, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            tmp.replace(self._storage)
        except OSError as e:
            print(f"[Skills] save error: {e}")

    # ── CRUD ──────────────────────────────────────────────────────────
    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"nome": k, **v} for k, v in self._skills.items()]

    def get(self, nome: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._skills.get(nome) or {}) or None

    def create(
        self,
        nome: str,
        descrizione: str,
        azioni: List[Dict[str, Any]],
        tag: Optional[List[str]] = None,
        trigger_keywords: Optional[List[str]] = None,
        schedule_every_seconds: Optional[int] = None,
    ) -> bool:
        nome = nome.strip().lower().replace(" ", "_")
        if not nome or not azioni:
            return False
        with self._lock:
            self._skills[nome] = {
                "descrizione": descrizione,
                "azioni": azioni,
                "tag": list(tag or []),
                "trigger_keywords": list(trigger_keywords or []),
                "created_ts": time.time(),
                "auto": False,
                "schedule_every_seconds": schedule_every_seconds,
            }
        self._save()
        return True

    def get(self, nome: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._skills.get(nome) or {}) or None

    def delete(self, nome: str) -> bool:
        nome = nome.strip().lower()
        with self._lock:
            if nome not in self._skills:
                return False
            del self._skills[nome]
        self._save()
        return True

    def update(self, nome: str, **fields: Any) -> bool:
        nome = nome.strip().lower()
        with self._lock:
            if nome not in self._skills:
                return False
            allowed = {"descrizione", "azioni", "tag", "trigger_keywords"}
            for k, v in fields.items():
                if k in allowed:
                    self._skills[nome][k] = v
        self._save()
        return True

    # ── execution ─────────────────────────────────────────────────────
    def esegui(self, nome: str) -> Dict[str, Any]:
        nome = nome.strip().lower()
        with self._lock:
            skill = self._skills.get(nome)
            if not skill:
                for k in self._skills:
                    if nome in k or k in nome:
                        skill = self._skills[k]
                        nome = k
                        break
        if not skill:
            return {"ok": False, "error": f"skill '{nome}' non trovata"}

        results: List[Dict[str, Any]] = []
        successes = 0
        for i, step in enumerate(skill["azioni"], 1):
            tool = step.get("tool", "")
            args = step.get("args", {}) or {}
            if tool == "run_skill":
                sub_name = str(args.get("nome", "")).strip().lower()
                if sub_name:
                    sub = self.esegui(sub_name)
                    results.append({"step": i, "tool": tool, "ok": sub.get("ok"), "res": str(sub.get("risultati", sub))[:200]})
                    if sub.get("ok"):
                        successes += 1
                else:
                    results.append({"step": i, "tool": tool, "ok": False, "res": "nome skill mancante"})
                continue
            if not self._executor:
                results.append({"step": i, "tool": tool, "ok": False, "res": "nessun executor"})
                continue
            try:
                ok, res = self._executor(tool, args)
                results.append({"step": i, "tool": tool, "ok": ok, "res": str(res)[:200]})
                if ok:
                    successes += 1
            except Exception as e:
                results.append({"step": i, "tool": tool, "ok": False, "res": f"errore: {e}"})

        return {
            "ok": successes == len(skill["azioni"]),
            "skill": nome,
            "totali": len(skill["azioni"]),
            "successi": successes,
            "risultati": results,
        }

    def scheduled_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"nome": k, "every_seconds": v.get("schedule_every_seconds")}
                for k, v in self._skills.items()
                if v.get("schedule_every_seconds")
            ]

    # ── auto-match ────────────────────────────────────────────────────
    def match(self, user_request: str) -> Optional[str]:
        text = user_request.lower()
        with self._lock:
            for name, skill in self._skills.items():
                for trigger in skill.get("trigger_keywords", []) or []:
                    if trigger.lower() in text:
                        return name
        return None


# ── singleton ─────────────────────────────────────────────────────────
_manager: Optional[SkillsManager] = None


def get_skills_manager() -> SkillsManager:
    global _manager
    if _manager is None:
        _manager = SkillsManager()
    return _manager
