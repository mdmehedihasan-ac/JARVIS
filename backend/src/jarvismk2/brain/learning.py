"""Brain v2 — self-learning subsystem.

Condensed from ``jarvis_brain_v2/`` in mdmehedihasan-ac/JARVIS.  We keep:

* :class:`LearningMemory` — JSON-backed store for skills, interactions,
  user-profile preferences, routing/prompt stats, detected patterns.
* :class:`LearningOrchestrator` — wires it all together, runs a background
  loop that periodically prunes/optimizes/regenerates routing weights, and
  exposes ``on_interaction`` / ``on_failure`` / ``on_correction`` callbacks.

We deliberately drop the heavier ``SkillAcquisition`` / ``SelfOptimizer`` /
``BehavioralLearning`` classes from the original into a single, simpler
implementation tuned for the new architecture.  Plug-in points are clearly
marked so they can be extended later.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus


class LearningMemory:
    """Thread-safe JSON-backed storage for learning state."""

    def __init__(self, path: Optional[Path] = None) -> None:
        cfg = get_config()
        self.path = path or (cfg.data_dir / "learning_state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = self._load()

    # ── persistence ────────────────────────────────────────────────────
    def _default(self) -> Dict[str, Any]:
        return {
            "acquired_skills": {},
            "interaction_log": [],
            "user_profile": {
                "preferences": {},
                "routines": {},
                "corrections": [],
            },
            "optimization_state": {
                "model_stats": {},
                "prompt_stats": {},
                "routing_weights": {},
            },
            "detected_patterns": [],
        }

    def _load(self) -> Dict[str, Any]:
        with self._lock:
            if self.path.exists():
                try:
                    return json.loads(self.path.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"[LearningMemory] load error: {e}")
            return self._default()

    def _save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with self._lock:
                tmp.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            os.replace(tmp, self.path)
        except OSError as e:
            print(f"[LearningMemory] save error: {e}")

    # ── skills ─────────────────────────────────────────────────────────
    def add_skill(
        self,
        name: str,
        code: str,
        description: str,
        tool_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._data["acquired_skills"][name] = {
                "code": code,
                "description": description,
                "tool_schema": tool_schema or {},
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success_count": 0,
                "fail_count": 0,
                "last_used": None,
            }
        self._save()

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data["acquired_skills"].get(name)

    def all_skills(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._data["acquired_skills"])

    def incr_skill(self, name: str, *, success: bool) -> None:
        with self._lock:
            skill = self._data["acquired_skills"].get(name)
            if not skill:
                return
            key = "success_count" if success else "fail_count"
            skill[key] = skill.get(key, 0) + 1
            if success:
                skill["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save()

    # ── interactions (capped log) ──────────────────────────────────────
    def log_interaction(
        self,
        user_input: str,
        action: str,
        success: bool,
        latency_ms: int = 0,
        model: str = "",
        task_type: str = "",
        error: str = "",
    ) -> None:
        entry = {
            "ts": int(time.time()),
            "input": user_input[:200],
            "action": action,
            "success": success,
            "latency_ms": latency_ms,
            "model": model,
            "task_type": task_type,
            "error": error[:200],
        }
        with self._lock:
            log = self._data["interaction_log"]
            log.append(entry)
            if len(log) > 1000:
                self._data["interaction_log"] = log[-1000:]
            # Save every 10 entries to limit IO
            n = len(self._data["interaction_log"])
        if n % 10 == 0:
            self._save()

    def recent_interactions(self, n: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data["interaction_log"][-n:])

    # ── corrections ────────────────────────────────────────────────────
    def add_correction(self, wrong_action: str, correct_action: str, context: str) -> None:
        with self._lock:
            self._data["user_profile"].setdefault("corrections", []).append(
                {
                    "wrong": wrong_action,
                    "correct": correct_action,
                    "context": context[:200],
                    "ts": int(time.time()),
                }
            )
        self._save()

    def corrections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data["user_profile"].get("corrections", []))

    # ── preferences ────────────────────────────────────────────────────
    def set_pref(
        self, category: str, key: str, value: Any, confidence: float = 1.0
    ) -> None:
        with self._lock:
            cat = self._data["user_profile"].setdefault("preferences", {}).setdefault(
                category, {}
            )
            cat[key] = {
                "value": value,
                "confidence": float(confidence),
                "updated": time.strftime("%Y-%m-%d"),
            }
        self._save()

    def get_pref(self, category: str, key: str) -> Any:
        with self._lock:
            cat = self._data["user_profile"].get("preferences", {}).get(category, {})
            entry = cat.get(key)
            return entry["value"] if entry else None

    # ── optimization stats ─────────────────────────────────────────────
    def record_model_stat(
        self, model: str, task_type: str, success: bool, latency_ms: int
    ) -> None:
        key = f"{model}|{task_type}"
        with self._lock:
            stats = self._data["optimization_state"].setdefault("model_stats", {})
            entry = stats.setdefault(
                key, {"success": 0, "fail": 0, "total_latency_ms": 0, "count": 0}
            )
            entry["count"] += 1
            entry["total_latency_ms"] += int(latency_ms)
            entry["success" if success else "fail"] += 1
        self._save()

    def model_stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._data["optimization_state"].get("model_stats", {}))

    def set_routing_weights(self, weights: Dict[str, float]) -> None:
        with self._lock:
            self._data["optimization_state"]["routing_weights"] = dict(weights)
        self._save()

    def routing_weights(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._data["optimization_state"].get("routing_weights", {}))

    # ── patterns ───────────────────────────────────────────────────────
    def add_pattern(self, pattern_type: str, description: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._data["detected_patterns"].append(
                {
                    "type": pattern_type,
                    "description": description,
                    "data": data,
                    "ts": int(time.time()),
                }
            )
        self._save()

    def patterns(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data["detected_patterns"])

    def prune_old_patterns(self, days: int = 30) -> None:
        cutoff = int(time.time()) - days * 86400
        with self._lock:
            self._data["detected_patterns"] = [
                p for p in self._data["detected_patterns"] if p.get("ts", 0) >= cutoff
            ]
        self._save()

    def export_all(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "acquired_skills": dict(self._data["acquired_skills"]),
                "user_profile": dict(self._data["user_profile"]),
                "optimization_state": dict(self._data["optimization_state"]),
                "detected_patterns": list(self._data["detected_patterns"]),
                "interaction_count": len(self._data["interaction_log"]),
            }


class LearningOrchestrator:
    """Coordinates :class:`LearningMemory` updates and a background loop.

    The background loop:
      * recomputes routing weights from collected ``model_stats``;
      * prunes old patterns and stale interactions;
      * runs every ``interval_sec`` seconds (default 5 minutes).

    CRITICAL: This class uses EXCLUSIVELY Ollama (qwen models) for any LLM
    call.  Kimi, OpenAI, Groq are ABSOLUTELY FORBIDDEN here.  All operations
    are local: JSON writes, heuristics, and Ollama-only calls.
    """

    # Engine names that are NEVER allowed for learning operations
    _BLOCKED_ENGINES = frozenset({"kimi", "openai", "groq"})

    def __init__(
        self,
        memory: Optional[LearningMemory] = None,
        interval_sec: int = 300,
        skill_acquire_fn: Optional[Callable[[str, str, str], Optional[Dict[str, Any]]]] = None,
    ) -> None:
        self.memory = memory or LearningMemory()
        self.interval_sec = interval_sec
        self.skill_acquire_fn = skill_acquire_fn
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._bus = get_bus()

    # ── background loop ────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="learning")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._recompute_routing_weights()
                self.memory.prune_old_patterns(days=30)
            except Exception as e:  # pragma: no cover
                print(f"[LearningOrchestrator] loop error: {e}")
            # interruptible sleep
            for _ in range(self.interval_sec):
                if self._stop.is_set():
                    break
                time.sleep(1)

    def _recompute_routing_weights(self) -> None:
        """Simple heuristic: weight = success / (success + fail + ε).

        Stored as a flat ``{ "model|task_type": weight }`` dict.  Real routing
        can read these and rank models per task.
        """
        stats = self.memory.model_stats()
        weights: Dict[str, float] = {}
        for key, s in stats.items():
            total = s.get("success", 0) + s.get("fail", 0)
            weights[key] = round(s.get("success", 0) / (total + 1e-3), 3)
        if weights:
            self.memory.set_routing_weights(weights)

    # ── hooks (call from agent runtime) ────────────────────────────────
    def on_interaction(
        self,
        *,
        user_input: str,
        action: str,
        success: bool,
        latency_ms: int = 0,
        model: str = "",
        task_type: str = "",
        error: str = "",
    ) -> None:
        # Guard: never let blocked engines influence routing weights
        model_lower = (model or "").lower()
        is_blocked = any(b in model_lower for b in self._BLOCKED_ENGINES)

        self.memory.log_interaction(
            user_input,
            action,
            success,
            latency_ms=latency_ms,
            model=model,
            task_type=task_type,
            error=error,
        )

        # Only update routing stats for LOCAL engines (qwen/ollama)
        if not is_blocked:
            self.memory.record_model_stat(
                model or "unknown",
                task_type or "default",
                success,
                latency_ms,
            )

        if action and self.memory.get_skill(action):
            self.memory.incr_skill(action, success=success)

    def _get_local_engine(self):
        """Return an Ollama engine for learning tasks. NEVER Kimi/cloud."""
        from jarvismk2.engine.router import get_router
        return get_router().pick_local()

    def on_failure(
        self, user_input: str, failed_action: str, error: str
    ) -> Optional[Dict[str, Any]]:
        """Attempt skill acquisition when an action fails.

        Uses ONLY local Ollama (qwen) — never Kimi or cloud engines.
        ``skill_acquire_fn`` receives (user_input, failed_action, error)
        and should return a new skill dict or None.
        """
        if not self.skill_acquire_fn:
            return None
        try:
            new_skill = self.skill_acquire_fn(user_input, failed_action, error)
        except Exception as e:  # pragma: no cover
            print(f"[LearningOrchestrator] skill_acquire_fn error: {e}")
            return None
        if new_skill:
            self.memory.add_skill(
                name=new_skill.get("name", failed_action),
                code=new_skill.get("code", ""),
                description=new_skill.get("description", ""),
                tool_schema=new_skill.get("tool_schema"),
            )
            self._bus.publish(
                EventType.LEARNING_SKILL_ACQUIRED,
                {"name": new_skill.get("name"), "trigger": failed_action},
            )
        return new_skill

    def on_correction(
        self, wrong_action: str, correct_action: str, context: str
    ) -> None:
        self.memory.add_correction(wrong_action, correct_action, context)
        self._bus.publish(
            EventType.LEARNING_PATTERN_DETECTED,
            {"type": "correction", "wrong": wrong_action, "correct": correct_action},
        )

    # ── dashboard ──────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "skills_acquired": len(self.memory.all_skills()),
            "patterns_detected": len(self.memory.patterns()),
            "interactions_logged": len(self.memory.recent_interactions(n=1)) > 0,
            "routing_weights": self.memory.routing_weights(),
            "background_running": bool(self._thread and self._thread.is_alive()),
        }

    def export_knowledge(self) -> Dict[str, Any]:
        return self.memory.export_all()
