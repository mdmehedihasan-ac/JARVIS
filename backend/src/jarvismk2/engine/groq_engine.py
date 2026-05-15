"""Groq — OpenAI-compatible chat + Whisper STT (super-fast)."""

from __future__ import annotations

from typing import Any, Optional

from jarvismk2.core.config import get_config
from jarvismk2.engine.openai_engine import OpenAIEngine


class GroqEngine(OpenAIEngine):
    """Groq exposes an OpenAI-compatible endpoint at ``api.groq.com/openai/v1``.

    Chat completion is identical to :class:`OpenAIEngine`; we also expose a
    ``transcribe`` helper for Whisper.
    """

    name = "groq"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "llama-3.3-70b-versatile",
    ) -> None:
        cfg = get_config()
        super().__init__(
            api_key=api_key if api_key is not None else cfg.cloud.groq,
            base_url="https://api.groq.com/openai/v1",
            default_model=default_model,
        )

    def is_available(self) -> bool:
        return bool(self._api_key)

    # ── Whisper STT (used by the voice layer) ─────────────────────────
    def transcribe(
        self,
        audio_path: str,
        *,
        model: str = "whisper-large-v3",
        language: Optional[str] = "it",
    ) -> str:
        """Transcribe ``audio_path`` and return the recognized text."""
        if not self._api_key:
            return ""
        try:
            from groq import Groq  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Groq SDK not installed. Run `uv sync --extra inference-groq`."
            ) from e
        client = Groq(api_key=self._api_key)
        with open(audio_path, "rb") as f:
            kwargs: dict[str, Any] = {"model": model, "file": f}
            if language:
                kwargs["language"] = language
            result = client.audio.transcriptions.create(**kwargs)
        return getattr(result, "text", "") or ""
