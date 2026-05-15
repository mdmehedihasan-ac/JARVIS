"""OpenAI-compatible chat backend (works with OpenAI, Groq, OpenRouter, etc.)."""

from __future__ import annotations

import time
from typing import Any, Iterator, List, Optional

from jarvismk2.core.config import get_config
from jarvismk2.engine.base import Engine, EngineResponse, Message


class OpenAIEngine(Engine):
    """Thin wrapper around the ``openai`` Python SDK."""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        cfg = get_config()
        self._api_key = api_key if api_key is not None else cfg.cloud.openai
        self._base_url = base_url
        self.default_model = default_model
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "OpenAI SDK not installed. Run `uv sync --extra inference-cloud`."
            ) from e
        kwargs: dict = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url
        self._client = OpenAI(**kwargs)
        return self._client

    def is_available(self) -> bool:
        return bool(self._api_key) or bool(self._base_url)

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
        client = self._ensure_client()
        start = time.time()
        resp = client.chat.completions.create(
            model=model or self.default_model,
            messages=[
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in messages
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            **kwargs,
        )
        elapsed = int((time.time() - start) * 1000)
        choice = resp.choices[0]
        text = choice.message.content or ""
        usage = getattr(resp, "usage", None)
        return EngineResponse(
            text=text,
            model=resp.model,
            latency_ms=elapsed,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            finish_reason=choice.finish_reason or "stop",
            raw=resp.model_dump() if hasattr(resp, "model_dump") else {},
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
        client = self._ensure_client()
        stream = client.chat.completions.create(
            model=model or self.default_model,
            messages=[
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in messages
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except (IndexError, AttributeError):
                delta = None
            if delta:
                yield delta
