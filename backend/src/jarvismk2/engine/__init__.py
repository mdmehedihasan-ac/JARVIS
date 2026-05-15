"""LLM engines and a thin :class:`EngineRouter` that picks the right one.

Inspired by OpenJarvis's ``engine/`` package but trimmed down.  We support:

* :class:`OllamaEngine` — local-first via the Ollama HTTP API.
* :class:`OpenAIEngine` — any OpenAI-compatible endpoint (incl. OpenAI proper).
* :class:`GroqEngine` — Groq for ultra-fast STT and chat.
* :class:`KimiEngine` — Moonshot AI Kimi K2.5 (OpenAI-compatible).
"""

from jarvismk2.engine.base import Engine, EngineResponse, Message
from jarvismk2.engine.ollama_engine import OllamaEngine
from jarvismk2.engine.openai_engine import OpenAIEngine
from jarvismk2.engine.groq_engine import GroqEngine
from jarvismk2.engine.kimi_engine import KimiEngine
from jarvismk2.engine.router import EngineRouter, get_router

__all__ = [
    "Engine",
    "EngineResponse",
    "EngineRouter",
    "GroqEngine",
    "KimiEngine",
    "Message",
    "OllamaEngine",
    "OpenAIEngine",
    "get_router",
]
