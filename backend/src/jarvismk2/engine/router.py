"""Engine router — picks the best engine for the task at hand.

Default strategy:

1. **Local first** — try Ollama if it's reachable.
2. **Kimi Code CLI** — local binary ``kimi`` (uses OAuth, no API key).
3. **Cloud fallback** — Groq → OpenAI, in that order, only if the right keys
   are configured.

You can also explicitly request an engine by name (``"ollama"``, ``"kimi"``,
``"openai"``, ``"groq"``).
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from jarvismk2.core.config import get_config
from jarvismk2.engine.base import Engine
from jarvismk2.engine.groq_engine import GroqEngine
from jarvismk2.engine.kimi_engine import KimiEngine
from jarvismk2.engine.ollama_engine import OllamaEngine
from jarvismk2.engine.openai_engine import OpenAIEngine

logger = logging.getLogger(__name__)


class EngineRouter:
    """Lazy-instantiate engines and pick one based on policy."""

    def __init__(self) -> None:
        cfg = get_config()
        self._cfg = cfg
        self._lock = threading.Lock()
        self._cache: Dict[str, Engine] = {}

    # ── engine factories ──────────────────────────────────────────────
    def _make(self, name: str) -> Engine:
        cfg = self._cfg
        if name == "ollama-fast":
            return OllamaEngine(
                default_model=cfg.ollama.model_fast,
                keep_alive=cfg.ollama.keep_alive_fast,
            )
        if name == "ollama-heavy":
            return OllamaEngine(
                default_model=cfg.ollama.model_heavy,
                keep_alive=cfg.ollama.keep_alive_heavy,
            )
        if name == "ollama":
            return OllamaEngine()
        if name == "groq":
            return GroqEngine()
        if name == "kimi":
            return KimiEngine()
        if name == "openai":
            return OpenAIEngine()
        raise KeyError(f"unknown engine '{name}'")

    def get(self, name: str) -> Engine:
        with self._lock:
            if name not in self._cache:
                self._cache[name] = self._make(name)
            return self._cache[name]

    # ── policy ────────────────────────────────────────────────────────
    def pick(
        self,
        *,
        prefer: Optional[str] = None,
        heavy: bool = False,
    ) -> Engine:
        """Return the engine to use.

        Order:
          1. explicit ``prefer`` (if available),
          2. local Ollama (heavy or fast variant),
          3. Groq if API key set,
          4. OpenAI if API key set,
          5. raise.
        """
        candidates: List[str] = []
        if prefer:
            candidates.append(prefer)
        # Kimi Code CLI first — faster responses (local binary, OAuth)
        candidates.append("kimi")
        candidates.append("ollama-heavy" if heavy else "ollama-fast")
        if self._cfg.cloud.groq:
            candidates.append("groq")
        if self._cfg.cloud.openai:
            candidates.append("openai")

        last_err: Optional[Exception] = None
        for name in candidates:
            try:
                engine = self.get(name)
                if engine.is_available():
                    logger.debug("router picked %s", name)
                    return engine
            except Exception as e:
                last_err = e
                continue

        # ── fallback: auto-discover any Ollama model ──────────────────
        if not (prefer and prefer not in ("ollama-fast", "ollama-heavy")):
            try:
                from jarvismk2.engine.ollama_engine import OllamaEngine
                probe = OllamaEngine()
                models = probe.list_models()
                if models:
                    first = models[0]
                    logger.info("auto-discovered Ollama model: %s", first)
                    engine = OllamaEngine(default_model=first)
                    if engine.is_available():
                        return engine
            except Exception:
                pass

        raise RuntimeError(
            "No engine available. Start Ollama (`ollama serve`) or set "
            "GROQ_API_KEY / OPENAI_API_KEY in your .env."
        ) from last_err

    def pick_local(self, *, heavy: bool = False) -> Engine:
        """Pick a LOCAL-only engine (Ollama qwen). NEVER returns Kimi/OpenAI/Groq.

        Used by learning loop, routing internals, and any operation that must
        NEVER consume cloud tokens.  Tries both qwen variants.
        """
        # Try preferred variant first, then the other
        first = "ollama-heavy" if heavy else "ollama-fast"
        second = "ollama-fast" if heavy else "ollama-heavy"
        for name in (first, second):
            try:
                engine = self.get(name)
                if engine.is_available():
                    logger.debug("pick_local → %s", name)
                    return engine
            except Exception:
                continue
        # fallback: auto-discover any Ollama model
        try:
            from jarvismk2.engine.ollama_engine import OllamaEngine
            probe = OllamaEngine()
            models = probe.list_models()
            if models:
                logger.info("pick_local auto-discovered: %s", models[0])
                return OllamaEngine(default_model=models[0])
        except Exception:
            pass
        raise RuntimeError(
            "No LOCAL engine available for learning. "
            "Start Ollama (`ollama serve`) with a qwen model."
        )

    def available(self) -> Dict[str, bool]:
        """For the frontend status panel."""
        out: Dict[str, bool] = {}
        for name in ("ollama-fast", "ollama-heavy", "kimi", "groq", "openai"):
            try:
                out[name] = self.get(name).is_available()
            except Exception:
                out[name] = False
        return out


# ── singleton ─────────────────────────────────────────────────────────
_router: Optional[EngineRouter] = None


def get_router() -> EngineRouter:
    global _router
    if _router is None:
        _router = EngineRouter()
    return _router
