"""Wake-word listener with Italian STT.

Optional module — only imports ``speech_recognition`` lazily so the rest of
the system runs without it.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from typing import Callable, List, Optional

from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus

logger = logging.getLogger(__name__)


class Ascolto:
    """Continuous mic listener.

    Parameters
    ----------
    on_command:
        Callback invoked with the *post-wake-word* command text.
    wake_words:
        Override the wake words from config.
    """

    def __init__(
        self,
        on_command: Callable[[str], None],
        wake_words: Optional[List[str]] = None,
        language: str = "it-IT",
    ) -> None:
        self._on_command = on_command
        self._cfg = get_config()
        self._wake_words = [w.lower() for w in (wake_words or self._cfg.voice.wake_words)]
        self._language = language
        self._bus = get_bus()
        self._sr = None
        self._recognizer = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── lazy SR setup ──────────────────────────────────────────────────
    def _ensure_sr(self) -> None:
        if self._recognizer is not None:
            return
        try:
            import speech_recognition as sr  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "speech_recognition not installed. Run `uv sync --extra voice`."
            ) from e
        self._sr = sr
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = 300
        self._recognizer.dynamic_energy_threshold = True

    # ── lifecycle ──────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ensure_sr()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ascolto")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    # ── main loop ──────────────────────────────────────────────────────
    def _loop(self) -> None:
        sr = self._sr
        assert sr is not None and self._recognizer is not None
        try:
            mic = sr.Microphone()
        except OSError as e:
            logger.error("microphone not available: %s", e)
            return
        with mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=1)
            while not self._stop.is_set():
                try:
                    audio = self._recognizer.listen(
                        source, timeout=5, phrase_time_limit=15
                    )
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    logger.debug("listen error: %s", e)
                    continue

                text = self._transcribe(audio).strip()
                if not text:
                    continue
                logger.info("voice transcript: %s", text)
                self._bus.publish(EventType.VOICE_TRANSCRIPT, {"text": text})
                low = text.lower()
                for wake in self._wake_words:
                    if wake in low:
                        command = low.replace(wake, "", 1).strip(" ,.;:") or "ci sei"
                        logger.info("voice wake detected: wake=%s command=%s", wake, command)
                        self._bus.publish(
                            EventType.VOICE_WAKE_DETECTED,
                            {"wake": wake, "command": command},
                        )
                        if command:
                            try:
                                self._on_command(command)
                            except Exception:
                                logger.exception("on_command callback failed")
                        break

    # ── transcription with Groq → Google fallback ──────────────────────
    def _transcribe(self, audio) -> str:
        # Prefer Groq Whisper (very fast & Italian-friendly)
        groq_key = self._cfg.cloud.groq
        if groq_key:
            try:
                from groq import Groq  # type: ignore
            except ImportError:
                Groq = None  # type: ignore
            if Groq is not None:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(audio.get_wav_data())
                        tmp = f.name
                    try:
                        client = Groq(api_key=groq_key)
                        with open(tmp, "rb") as fh:
                            result = client.audio.transcriptions.create(
                                model="whisper-large-v3",
                                file=fh,
                                language=self._language.split("-")[0],
                            )
                        return getattr(result, "text", "") or ""
                    finally:
                        try:
                            os.unlink(tmp)
                        except OSError:
                            pass
                except Exception as e:
                    logger.debug("Groq STT failed, falling back: %s", e)

        # Local fallback: Google Web Speech (no key required, low quota)
        try:
            return self._recognizer.recognize_google(audio, language=self._language)  # type: ignore[attr-defined]
        except Exception:
            return ""
