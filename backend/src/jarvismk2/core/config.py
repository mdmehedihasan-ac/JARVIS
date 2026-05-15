"""Centralized configuration loaded from environment + optional ``.env`` file.

A single :class:`Config` instance is exposed via :func:`get_config`.  All other
modules should obtain it through this helper rather than reading ``os.environ``
directly — this keeps tests and overrides simple.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover — dotenv is a hard dep but be defensive
    def load_dotenv(*_args, **_kwargs) -> bool:  # type: ignore[no-redef]
        return False


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    raw = _env(name, "")
    if not raw:
        return list(default or [])
    return [x.strip() for x in raw.split(",") if x.strip()]


def _sanitize_keep_alive(val: str) -> str:
    """Ollama rejects '-1' as a duration string; treat it as 'keep in RAM forever'."""
    v = val.strip()
    if v == "-1":
        return "30m"
    return v


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(path))).resolve()


@dataclass
class PersonaConfig:
    """How JARVIS talks and presents itself."""

    lang: str = "it"
    name: str = "JARVIS"
    user_name: str = "Signore"

    @property
    def system_prompt(self) -> str:
        if self.lang.startswith("it"):
            return (
                f"Sei {self.name}, assistente AI di {self.user_name}. "
                "Rispondi in italiano, conciso e diretto."
            )
        return (
            f"You are {self.name}, AI assistant of {self.user_name}. "
            "Be concise and direct."
        )


@dataclass
class OllamaConfig:
    host: str = "http://localhost:11434"
    model_fast: str = "qwen2.5:7b"
    model_heavy: str = "qwen2.5:14b"
    keep_alive_fast: str = "30m"
    keep_alive_heavy: str = "0s"


@dataclass
class CloudKeys:
    openai: str = ""
    anthropic: str = ""
    gemini: str = ""
    groq: str = ""
    elevenlabs: str = ""
    # Kimi now runs locally via CLI binary — no API key needed


@dataclass
class VoiceConfig:
    wake_words: List[str] = field(default_factory=lambda: ["jarvis", "ehi jarvis"])
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"
    macos_voice_it: str = "Alice"
    macos_voice_en: str = "Daniel"


@dataclass
class ObsidianConfig:
    vault_path: str = ""
    subdir: str = "Jarvis"

    @property
    def is_configured(self) -> bool:
        return bool(self.vault_path) and _expand(self.vault_path).is_dir()


@dataclass
class TelegramConfig:
    bot_token: str = ""
    allowed_chat_ids: List[str] = field(default_factory=list)


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    frontend_origin: str = "http://localhost:5173"


@dataclass
class Config:
    """Top-level config aggregating all sub-configs."""

    persona: PersonaConfig
    ollama: OllamaConfig
    cloud: CloudKeys
    voice: VoiceConfig
    obsidian: ObsidianConfig
    telegram: TelegramConfig
    server: ServerConfig
    data_dir: Path
    log_level: str

    # ── factories ─────────────────────────────────────────────
    @classmethod
    def from_env(cls) -> Config:
        """Build a :class:`Config` from the current environment.

        Also calls :func:`load_dotenv` once so ``.env`` is read on first load.
        
        Data directory priority:
        1. JARVIS_DATA_DIR env var (explicit)
        2. Inside Obsidian vault at .jarvis/ (if vault configured)
        3. ~/.jarvismk2 (fallback)
        """
        load_dotenv(override=False)

        # Determine data directory priority:
        # 1. JARVIS_DATA_DIR env var (explicit override)
        # 2. Inside Obsidian vault at .jarvis/ (if vault configured)
        # 3. ~/.jarvismk2 (fallback)
        explicit_data_dir = _env("JARVIS_DATA_DIR", "").strip()
        obsidian_vault = _env("OBSIDIAN_VAULT_PATH", "").strip()
        
        if explicit_data_dir:
            # User explicitly set data directory
            data_dir = _expand(explicit_data_dir)
        elif obsidian_vault:
            # Use subdirectory inside Obsidian vault (hidden folder)
            data_dir = Path(obsidian_vault).expanduser() / ".jarvis"
        else:
            # Fallback to home directory
            data_dir = _expand("~/.jarvismk2")
        
        data_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            persona=PersonaConfig(
                lang=_env("JARVIS_PERSONA_LANG", "it"),
                name=_env("JARVIS_PERSONA_NAME", "JARVIS"),
                user_name=_env("JARVIS_USER_NAME", "Signore"),
            ),
            ollama=OllamaConfig(
                host=_env("OLLAMA_HOST", "http://localhost:11434"),
                model_fast=_env("OLLAMA_MODEL_FAST", "qwen2.5:7b"),
                model_heavy=_env("OLLAMA_MODEL_HEAVY", "qwen2.5:14b"),
                keep_alive_fast=_sanitize_keep_alive(_env("OLLAMA_KEEP_ALIVE_FAST", "30m")),
                keep_alive_heavy=_sanitize_keep_alive(_env("OLLAMA_KEEP_ALIVE_HEAVY", "0s")),
            ),
            cloud=CloudKeys(
                openai=_env("OPENAI_API_KEY"),
                anthropic=_env("ANTHROPIC_API_KEY"),
                gemini=_env("GEMINI_API_KEY"),
                groq=_env("GROQ_API_KEY"),
                elevenlabs=_env("ELEVENLABS_API_KEY"),
            ),
            voice=VoiceConfig(
                wake_words=_env_list("JARVIS_WAKE_WORDS", ["jarvis", "ehi jarvis"]),
                elevenlabs_voice_id=_env(
                    "ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB"
                ),
                macos_voice_it=_env("JARVIS_MACOS_VOICE_IT", "Alice"),
                macos_voice_en=_env("JARVIS_MACOS_VOICE_EN", "Daniel"),
            ),
            obsidian=ObsidianConfig(
                vault_path=_env("OBSIDIAN_VAULT_PATH"),
                subdir=_env("JARVIS_OBSIDIAN_SUBDIR", "Jarvis"),
            ),
            telegram=TelegramConfig(
                bot_token=_env("TELEGRAM_BOT_TOKEN"),
                allowed_chat_ids=_env_list("TELEGRAM_ALLOWED_CHAT_IDS"),
            ),
            server=ServerConfig(
                host=_env("JARVIS_HOST", "127.0.0.1"),
                port=_env_int("JARVIS_PORT", 8765),
                frontend_origin=_env(
                    "JARVIS_FRONTEND_ORIGIN", "http://localhost:5173"
                ),
            ),
            data_dir=data_dir,
            log_level=_env("JARVIS_LOG_LEVEL", "INFO"),
        )


# ── module-level singleton ─────────────────────────────────────────────────
_config: Optional[Config] = None


def get_config() -> Config:
    """Return the cached :class:`Config`, building it on first access."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config() -> Config:
    """Force a re-read from the environment (useful for tests)."""
    global _config
    _config = Config.from_env()
    return _config
