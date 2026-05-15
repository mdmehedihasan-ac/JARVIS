"""Abstract :class:`Engine` interface used by all backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional


@dataclass
class Message:
    role: str               # "system" | "user" | "assistant" | "tool"
    content: str
    name: Optional[str] = None


@dataclass
class EngineResponse:
    text: str
    model: str
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    raw: Dict[str, Any] = field(default_factory=dict)


class Engine(ABC):
    """Synchronous and streaming chat completion."""

    name: str = "abstract"
    default_model: str = ""

    @abstractmethod
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
        ...

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
        """Yield text chunks.  Default impl falls back to non-streaming."""
        resp = self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            **kwargs,
        )
        yield resp.text

    async def chat_stream_async(
        self,
        messages: List[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Default async wrapper around :meth:`chat_stream`."""
        for chunk in self.chat_stream(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            **kwargs,
        ):
            yield chunk

    def is_available(self) -> bool:  # pragma: no cover — overridden
        """Cheap check (e.g. ping endpoint, check env)."""
        return True
