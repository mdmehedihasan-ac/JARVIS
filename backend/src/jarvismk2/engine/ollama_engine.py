"""Ollama HTTP API client (no SDK dep — just httpx)."""

from __future__ import annotations

import json
import time
from typing import Any, Iterator, List, Optional

import httpx

from jarvismk2.core.config import get_config
from jarvismk2.engine.base import Engine, EngineResponse, Message


class OllamaEngine(Engine):
    """Talks to ``/api/chat`` on a local (or remote) Ollama instance.

    The ``keep_alive`` parameter is exposed so we can mimic the
    "qwen3:8b in RAM forever / qwen3.5:9b staffetta" trick from the source
    project — useful on a 16GB Apple Silicon laptop.
    """

    name = "ollama"

    def __init__(
        self,
        host: Optional[str] = None,
        default_model: Optional[str] = None,
        keep_alive: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        cfg = get_config()
        self.host = (host or cfg.ollama.host).rstrip("/")
        self.default_model = default_model or cfg.ollama.model_fast
        self.keep_alive = keep_alive if keep_alive is not None else cfg.ollama.keep_alive_fast
        self.timeout = timeout

    # ── availability ──────────────────────────────────────────────────
    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            if r.status_code != 200:
                return False
            models = {m.get("name", "") for m in r.json().get("models", [])}
            return self.default_model in models
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    # ── chat ──────────────────────────────────────────────────────────
    def _payload(
        self,
        messages: List[Message],
        *,
        model: Optional[str],
        temperature: float,
        max_tokens: int,
        stop: Optional[List[str]],
        stream: bool,
        **extra: Any,
    ) -> dict:
        return {
            "model": model or self.default_model,
            "messages": [
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in messages
            ],
            "stream": stream,
            "keep_alive": "30m" if self.keep_alive.strip() == "-1" else self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **({"stop": stop} if stop else {}),
                **(extra.pop("options", {}) if isinstance(extra.get("options"), dict) else {}),
            },
            **{k: v for k, v in extra.items() if k != "options"},
        }

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
        payload = self._payload(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=False,
            **kwargs,
        )
        start = time.time()
        r = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        elapsed = int((time.time() - start) * 1000)
        text = (data.get("message") or {}).get("content", "")
        return EngineResponse(
            text=text,
            model=data.get("model", payload["model"]),
            latency_ms=elapsed,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            finish_reason="stop" if data.get("done") else "length",
            raw=data,
        )

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
        payload = self._payload(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=True,
            **kwargs,
        )
        with httpx.stream(
            "POST", f"{self.host}/api/chat", json=payload, timeout=self.timeout
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = chunk.get("message") or {}
                content = msg.get("content")
                if content:
                    yield content
                if chunk.get("done"):
                    break
