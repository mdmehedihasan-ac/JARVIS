"""Kimi Code engine — local CLI wrapper (kimi -p --quiet).

Uses the locally-installed ``kimi`` binary (Kimi Code CLI) which authenticates
via OAuth stored in ``~/.kimi/``.  No API key required.

The binary is invoked in ``--quiet`` (non-interactive, print-mode) mode,
piping the prompt via ``-p`` and capturing stdout as the response.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Any, Iterator, List, Optional

from jarvismk2.engine.base import Engine, EngineResponse, Message

logger = logging.getLogger(__name__)

# Path discovery
_KIMI_BIN: Optional[str] = shutil.which("kimi")

# Timeout for a single CLI invocation (seconds)
_TIMEOUT = 120


class KimiEngine(Engine):
    """Kimi K2.6 via local Kimi Code CLI binary."""

    name = "kimi"
    default_model = "kimi-code/kimi-for-coding"

    def __init__(self, binary: Optional[str] = None) -> None:
        self._bin = binary or _KIMI_BIN
        self._avail_cache: Optional[bool] = None
        self._avail_ts: float = 0.0

    # ── availability (cached 60s) ─────────────────────────────────────
    def is_available(self) -> bool:
        now = time.time()
        if self._avail_cache is not None and (now - self._avail_ts) < 60:
            return self._avail_cache
        if not self._bin:
            self._avail_cache = False
            self._avail_ts = now
            return False
        try:
            r = subprocess.run(
                [self._bin, "--help"],
                capture_output=True, timeout=5,
            )
            self._avail_cache = r.returncode == 0
        except Exception:
            self._avail_cache = False
        self._avail_ts = now
        return self._avail_cache

    # ── prompt formatting ─────────────────────────────────────────────
    @staticmethod
    def _format_prompt(messages: List[Message]) -> str:
        """Flatten messages into a minimal prompt string for the CLI.

        Ultra-compact: short prefixes, no verbose separators.
        """
        parts: List[str] = []
        sys_text = ""

        for m in messages:
            if m.role == "system":
                sys_text = (sys_text + "\n" + m.content).strip() if sys_text else m.content
            elif m.role == "user":
                parts.append(f"U:{m.content}")
            elif m.role == "assistant":
                parts.append(f"A:{m.content}")

        out = ""
        if sys_text:
            out = sys_text + "\n---\n"
        out += "\n".join(parts)
        return out

    # ── chat (blocking) ───────────────────────────────────────────────
    def chat(
        self,
        messages: List[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> EngineResponse:
        if not self._bin:
            raise RuntimeError("kimi binary not found. Install with: curl -fsSL https://kimi.ai/install | sh")

        prompt = self._format_prompt(messages)
        cmd = [self._bin, "-p", prompt, "--quiet"]

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"kimi CLI timed out after {_TIMEOUT}s")

        elapsed = int((time.time() - start) * 1000)

        if result.returncode != 0:
            stderr = result.stderr.strip()[:500]
            raise RuntimeError(f"kimi CLI error (rc={result.returncode}): {stderr}")

        text = result.stdout.strip()

        return EngineResponse(
            text=text,
            model=self.default_model,
            latency_ms=elapsed,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=len(text) // 4,
            finish_reason="stop",
        )

    # ── streaming (line-by-line from subprocess) ──────────────────────
    def chat_stream(
        self,
        messages: List[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        if not self._bin:
            raise RuntimeError("kimi binary not found")

        prompt = self._format_prompt(messages)
        cmd = [self._bin, "-p", prompt, "--quiet"]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                yield line
        finally:
            proc.wait(timeout=10)
