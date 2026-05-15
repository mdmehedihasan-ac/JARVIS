"""SimpleAgent — single-turn LLM call with aggressive token optimization.

Every token counts.  Optimization layers:
1. Brain cache: high-confidence neuron → instant reply, 0 LLM tokens.
2. Single pensa() call: result reused across cache check + prompt build.
3. Dedup: brain snippets already in episodic block are stripped.
4. Adaptive budget: Kimi gets a tight cap; Ollama gets more room.
5. Compact system prompt: brain already stores capabilities — don't repeat.
6. History compression: only last exchange kept full, rest → single summary line.
7. Smart episodic: only top-1, max 60 chars per field, no metadata bloat.
8. Gate impara: trivial interactions (<20 chars) don't pollute the brain.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterator, List, Optional

from jarvismk2.brain.cervello import get_cervello
from jarvismk2.brain.episodic import get_episodic
from jarvismk2.core.config import get_config
from jarvismk2.core.types import AgentResponse, ChatMessage
from jarvismk2.engine.base import Message
from jarvismk2.engine.router import get_router
from jarvismk2.engine.token_budget import (
    BudgetConfig,
    compress_history,
    estimate_tokens,
    estimate_messages_tokens,
    get_budget,
    get_tracker,
    truncate_to_budget,
)

logger = logging.getLogger(__name__)

_CACHE_CONFIDENCE = 0.82

# Words that signal a creative/complex request (never cache-hit)
_COMPLEX_WORDS = frozenset((
    "scrivi", "genera", "crea", "progetta", "spiega nel dettaglio",
    "analizza", "confronta", "sviluppa", "implementa", "elenca",
    "riassumi", "traduci", "correggi", "migliora", "converti",
    "write", "generate", "create", "explain", "analyze", "implement",
))

# Minimum interaction length worth learning (skip "ciao", "ok", etc.)
_MIN_LEARN_LEN = 25

_INSTANT_REPLIES = {
    "ciao": "Ciao Signore. Sono online.",
    "hey": "Sono qui, Signore.",
    "hei": "Sono qui, Signore.",
    "ok": "Ricevuto.",
    "okay": "Ricevuto.",
    "grazie": "Sempre a disposizione, Signore.",
    "thanks": "Sempre a disposizione, Signore.",
    "chi sei": "Sono JARVIS MK2, il tuo assistente personale locale.",
    "sei online": "Sì, sono online.",
    "ci sei": "Sì, Signore. Sono operativo.",
}


class SimpleAgent:
    """Token-optimized single-shot agent."""

    name = "simple"

    def __init__(self, prefer_engine: Optional[str] = None, heavy: bool = False) -> None:
        self._prefer = prefer_engine
        self._heavy = heavy

    # ── single pensa() + cache ────────────────────────────────────────
    def _think(self, user_input: str) -> Dict[str, Any]:
        """One pensa() call → reuse everywhere. Returns thought dict."""
        return get_cervello().pensa(user_input)

    @staticmethod
    def _is_cache_eligible(user_input: str) -> bool:
        """True if query is short/factual enough to serve from brain alone."""
        if len(user_input) > 100:
            return False
        low = user_input.lower()
        return not any(w in low for w in _COMPLEX_WORDS)

    @staticmethod
    def _try_instant_reply(user_input: str) -> Optional[str]:
        low = user_input.lower().strip(" \t\n\r.?!,;:")
        return _INSTANT_REPLIES.get(low)

    def _try_brain_cache(self, thought: Dict[str, Any], user_input: str) -> Optional[str]:
        if thought.get("top_forza", 0) < _CACHE_CONFIDENCE:
            return None
        if not thought["snippets"]:
            return None
        if not self._is_cache_eligible(user_input):
            return None

        snippet = thought["snippets"][0]
        # Strip the lobe prefix "[LOBO] " to return clean text
        if "] " in snippet:
            snippet = snippet.split("] ", 1)[1]

        logger.info("brain-cache HIT forza=%.2f len=%d", thought["top_forza"], len(snippet))
        get_tracker().record("brain-cache", 0, 0, saved_cache=estimate_tokens(snippet))
        return snippet

    # ── prompt assembly ───────────────────────────────────────────────
    def _build_messages(
        self,
        user_input: str,
        thought: Dict[str, Any],
        history: Optional[List[ChatMessage]] = None,
        budget: Optional[BudgetConfig] = None,
    ) -> List[Message]:
        cfg = get_config()
        episodic = get_episodic()
        b = budget or get_budget("ollama")

        # ── Brain snippets (capped, only novel info) ──
        brain_block = ""
        if thought["snippets"]:
            snippets_text = "\n".join(thought["snippets"])
            brain_block = truncate_to_budget(
                f"[{thought['lobo_attivato']}]\n{snippets_text}",
                b.max_brain_context,
            )

        # ── Episodic (top-1, ultra-compact) ──
        ep_block = episodic.render_prompt_block(user_input, top_k=1)
        if ep_block:
            ep_block = truncate_to_budget(ep_block, b.max_episodic)

        # ── Deduplicate: if brain already contains episodic content, drop episodic
        if brain_block and ep_block:
            brain_lower = brain_block.lower()
            ep_lines = [l for l in ep_block.split("\n") if l.strip()]
            # keep episodic only if it adds genuinely new info
            novel = [l for l in ep_lines if l[2:30].lower() not in brain_lower]
            ep_block = "\n".join(novel) if novel else ""

        # ── System prompt (compact) ──
        sys_parts = [cfg.persona.system_prompt]
        if brain_block:
            sys_parts.append(brain_block)
        if ep_block:
            sys_parts.append(ep_block)
        sys_content = truncate_to_budget("\n\n".join(sys_parts), b.max_system)

        out: List[Message] = [Message(role="system", content=sys_content)]

        # ── History (compressed) ──
        if history:
            hist_msgs = [
                Message(role=m.role, content=m.content)
                for m in history
                if m.role in ("user", "assistant")
            ]
            hist_msgs = compress_history(hist_msgs, b.max_history)
            out.extend(hist_msgs)

        out.append(Message(role="user", content=user_input))
        return out

    # ── run ──────────────────────────────────────────────────────────
    def run(
        self,
        user_input: str,
        history: Optional[List[ChatMessage]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AgentResponse:
        instant = self._try_instant_reply(user_input)
        if instant:
            return AgentResponse(
                text=instant,
                action="instant_reply",
                success=True,
                latency_ms=0,
                model="local",
                metadata={"engine": "instant"},
            )

        # Single brain query — reused everywhere
        thought = self._think(user_input)

        # 1) Brain cache → 0 tokens
        cached = self._try_brain_cache(thought, user_input)
        if cached:
            self._log_episode(user_input, cached)
            return AgentResponse(
                text=cached,
                action="brain_cache",
                success=True,
                latency_ms=0,
                model="cervello",
                metadata={"engine": "brain-cache", "tokens_saved": True},
            )

        # 2) LLM call with budget
        engine = get_router().pick(prefer=self._prefer, heavy=self._heavy)
        budget = get_budget(engine.name)
        messages = self._build_messages(user_input, thought, history, budget)

        # Scale max_tokens to query complexity
        effective_max = self._adaptive_max_tokens(user_input, max_tokens, budget)

        actual_tokens = estimate_messages_tokens(messages)
        raw_tokens = estimate_tokens(user_input) + sum(
            estimate_tokens(m.content) for m in (history or [])
        )
        saved = max(0, raw_tokens - actual_tokens)

        start = time.time()
        resp = engine.chat(messages, temperature=temperature, max_tokens=effective_max)
        elapsed = int((time.time() - start) * 1000)

        get_tracker().record(
            engine.name,
            input_tokens=resp.prompt_tokens or actual_tokens,
            output_tokens=resp.completion_tokens or estimate_tokens(resp.text),
            saved_compression=saved,
        )
        self._log_episode(user_input, resp.text)

        return AgentResponse(
            text=resp.text,
            action="simple_chat",
            success=True,
            latency_ms=elapsed,
            model=resp.model,
            metadata={"engine": engine.name, "tok_in": actual_tokens, "tok_saved": saved},
        )

    def stream(
        self,
        user_input: str,
        history: Optional[List[ChatMessage]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        instant = self._try_instant_reply(user_input)
        if instant:
            yield instant
            return

        thought = self._think(user_input)

        cached = self._try_brain_cache(thought, user_input)
        if cached:
            yield cached
            self._log_episode(user_input, cached)
            return

        engine = get_router().pick(prefer=self._prefer, heavy=self._heavy)
        budget = get_budget(engine.name)
        messages = self._build_messages(user_input, thought, history, budget)
        effective_max = self._adaptive_max_tokens(user_input, max_tokens, budget)

        accumulated: List[str] = []
        for chunk in engine.chat_stream(
            messages, temperature=temperature, max_tokens=effective_max
        ):
            accumulated.append(chunk)
            yield chunk

        full = "".join(accumulated)
        get_tracker().record(
            engine.name,
            input_tokens=estimate_messages_tokens(messages),
            output_tokens=estimate_tokens(full),
        )
        self._log_episode(user_input, full)

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _adaptive_max_tokens(user_input: str, requested: int, budget: BudgetConfig) -> int:
        """Short questions get shorter max_tokens → saves output tokens."""
        cap = budget.max_output
        input_len = len(user_input)
        if input_len < 30:
            cap = min(cap, 96)
        elif input_len < 80:
            cap = min(cap, 192)
        return min(requested, cap)

    @staticmethod
    def _log_episode(user_input: str, response: str) -> None:
        """Log to episodic memory — skip trivial interactions."""
        if len(user_input) < _MIN_LEARN_LEN and len(response) < _MIN_LEARN_LEN:
            return
        try:
            get_episodic().aggiungi(user_input, response)
        except Exception:
            pass
