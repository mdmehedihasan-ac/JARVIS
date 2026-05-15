"""Token budget management — estimate, cap, and track token usage.

The goal: Kimi should NEVER receive more context than strictly necessary.
Brain + episodic memory replace the need for long context windows.

Strategy (inspired by Claude memory optimization — ~75% savings):
1. System prompt: compact, never repeated knowledge the brain already holds.
2. History: summarized to key points, not raw messages.
3. Brain context: only top-scored snippets within a token budget.
4. User message: always full (non-negotiable).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from jarvismk2.engine.base import Message


# ── Token estimation (4 chars ≈ 1 token for most models) ──────────────────
def estimate_tokens(text: str) -> int:
    """Fast heuristic token count (no tiktoken dep)."""
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: List[Message]) -> int:
    """Estimate total tokens across messages (including role overhead)."""
    total = 0
    for m in messages:
        total += estimate_tokens(m.content) + 4  # role + formatting overhead
    return total


# ── Budget config ──────────────────────────────────────────────────────────
@dataclass
class BudgetConfig:
    """Token budget allocation for a single Kimi call."""

    max_total: int = 2048           # max tokens sent to Kimi (input)
    max_system: int = 600           # system prompt (persona + brain + episodic)
    max_brain_context: int = 300    # brain snippets budget
    max_episodic: int = 200         # episodic memory budget
    max_history: int = 400          # conversation history budget
    max_output: int = 1024          # max_tokens for response
    reserve_user: int = 200         # reserved for user message


BUDGET_KIMI = BudgetConfig(
    max_total=1536,
    max_system=400,
    max_brain_context=200,
    max_episodic=100,
    max_history=250,
    max_output=512,
    reserve_user=150,
)

BUDGET_OLLAMA = BudgetConfig(
    max_total=3072,
    max_system=800,
    max_brain_context=400,
    max_episodic=200,
    max_history=600,
    max_output=1024,
    reserve_user=300,
)


def get_budget(engine_name: str) -> BudgetConfig:
    """Return appropriate budget based on engine."""
    if "kimi" in engine_name.lower():
        return BUDGET_KIMI
    return BUDGET_OLLAMA


# ── Text compression utilities ─────────────────────────────────────────────
def truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 12] + "\n[…troncato]"


def compress_history(
    messages: List[Message], max_tokens: int
) -> List[Message]:
    """Keep only the most recent messages that fit the budget.

    Strategy:
    - Keep last 1 exchange (2 messages) in full
    - Older messages → single ultra-compact summary line
    """
    if not messages:
        return []

    total = estimate_messages_tokens(messages)
    if total <= max_tokens:
        return messages

    # Keep last 2 messages (1 exchange)
    keep_tail = messages[-2:] if len(messages) >= 2 else messages
    tail_tokens = estimate_messages_tokens(keep_tail)

    remaining_budget = max_tokens - tail_tokens
    if remaining_budget <= 10 or len(messages) <= 2:
        return keep_tail

    # Summarize older messages: ultra-compact, 40 chars max each
    older = messages[:-2]
    parts = []
    for m in older:
        tag = "Q" if m.role == "user" else "R"
        parts.append(f"{tag}:{m.content[:40].replace(chr(10), ' ')}")

    summary = truncate_to_budget("|".join(parts), remaining_budget)
    return [Message(role="system", content=f"[ctx]{summary}")] + keep_tail


# ── Usage tracker ──────────────────────────────────────────────────────────
@dataclass
class UsageStats:
    """Track token usage per engine over time."""

    total_input: int = 0
    total_output: int = 0
    call_count: int = 0
    saved_by_cache: int = 0
    saved_by_compression: int = 0


class TokenTracker:
    """Thread-safe token usage tracker per engine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: Dict[str, UsageStats] = {}
        self._session_start = time.time()

    def record(
        self,
        engine: str,
        input_tokens: int,
        output_tokens: int,
        *,
        saved_cache: int = 0,
        saved_compression: int = 0,
    ) -> None:
        with self._lock:
            if engine not in self._stats:
                self._stats[engine] = UsageStats()
            s = self._stats[engine]
            s.total_input += input_tokens
            s.total_output += output_tokens
            s.call_count += 1
            s.saved_by_cache += saved_cache
            s.saved_by_compression += saved_compression

    def get_stats(self, engine: Optional[str] = None) -> Dict[str, any]:
        with self._lock:
            if engine:
                s = self._stats.get(engine, UsageStats())
                return {
                    "engine": engine,
                    "total_input": s.total_input,
                    "total_output": s.total_output,
                    "calls": s.call_count,
                    "saved_cache": s.saved_by_cache,
                    "saved_compression": s.saved_by_compression,
                    "efficiency": self._efficiency(s),
                }
            return {
                name: {
                    "total_input": s.total_input,
                    "total_output": s.total_output,
                    "calls": s.call_count,
                    "saved_cache": s.saved_by_cache,
                    "saved_compression": s.saved_by_compression,
                    "efficiency": self._efficiency(s),
                }
                for name, s in self._stats.items()
            }

    @staticmethod
    def _efficiency(s: UsageStats) -> str:
        total_would_have_been = s.total_input + s.saved_by_cache + s.saved_by_compression
        if total_would_have_been == 0:
            return "N/A"
        saved_pct = (s.saved_by_cache + s.saved_by_compression) / total_would_have_been * 100
        return f"{saved_pct:.0f}% risparmiato"


# ── singleton ──────────────────────────────────────────────────────────────
_tracker: Optional[TokenTracker] = None


def get_tracker() -> TokenTracker:
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker
