"""TTS with a queue. ElevenLabs preferred, macOS ``say`` as fallback."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import tempfile
import threading
from queue import Empty, Queue
from typing import Optional

from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus

logger = logging.getLogger(__name__)

_ENG_HINT_WORDS = (
    "the",
    "and",
    "for",
    "with",
    "you",
    "your",
    "this",
    "that",
    "have",
    "please",
)


def _looks_english(text: str) -> bool:
    """Cheap heuristic — used only to pick a macOS voice."""
    low = f" {text.lower()} "
    return sum(1 for w in _ENG_HINT_WORDS if f" {w} " in low) >= 2


class Voce:
    """Threaded TTS player.

    Use :meth:`parla` to enqueue text.  Set ``priority=True`` to flush the
    queue first (interrupts current speech).
    """

    def __init__(self) -> None:
        cfg = get_config()
        self._cfg = cfg
        self._queue: Queue[Optional[str]] = Queue()
        self._stop = threading.Event()
        self._bus = get_bus()
        self._worker = threading.Thread(target=self._loop, daemon=True, name="voce")
        self._worker.start()

    # ── public API ────────────────────────────────────────────────────
    def parla(self, testo: str, priority: bool = False) -> None:
        if not testo or not testo.strip():
            return
        if priority:
            self._flush()
        self._queue.put(testo)

    def stop(self) -> None:
        self._stop.set()
        self._flush()
        self._queue.put(None)

    def _flush(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Empty:
            pass

    # ── worker ────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if text is None:  # poison pill
                break
            self._bus.publish(EventType.VOICE_TTS_SPEAKING, {"text": text[:80], "state": "start"})
            try:
                self._synthesize(text)
            except Exception as e:  # pragma: no cover
                logger.debug("TTS error: %s", e)
            finally:
                self._bus.publish(
                    EventType.VOICE_TTS_SPEAKING, {"text": text[:80], "state": "end"}
                )

    # ── synthesizers ──────────────────────────────────────────────────
    def _synthesize(self, text: str) -> None:
        # 1) ElevenLabs if configured
        if self._cfg.cloud.elevenlabs and self._tts_elevenlabs(text):
            return
        # 2) macOS `say` as fallback (rich voices on macOS)
        if platform.system() == "Darwin":
            self._tts_macos_say(text)
            return
        # 3) Last resort: print
        logger.info("[Voce] (no TTS backend) %s", text)

    def _tts_elevenlabs(self, text: str) -> bool:
        try:
            import httpx
        except ImportError:  # pragma: no cover — httpx is a hard dep
            return False
        try:
            r = httpx.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self._cfg.voice.elevenlabs_voice_id}",
                headers={
                    "xi-api-key": self._cfg.cloud.elevenlabs,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.7, "similarity_boost": 0.8},
                },
                timeout=30.0,
            )
            if r.status_code != 200:
                logger.debug("ElevenLabs error %s: %s", r.status_code, r.text[:200])
                return False
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(r.content)
                tmp = f.name
            try:
                if platform.system() == "Darwin":
                    subprocess.run(["afplay", tmp], capture_output=True, check=False)
                else:
                    # Linux fallback: aplay or paplay
                    for player in ("paplay", "aplay", "mpg123", "ffplay"):
                        try:
                            subprocess.run(
                                [player, tmp], capture_output=True, check=False
                            )
                            break
                        except FileNotFoundError:
                            continue
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return True
        except Exception as e:
            logger.debug("ElevenLabs synth failed: %s", e)
            return False

    def _tts_macos_say(self, text: str) -> None:
        voice = self._cfg.voice.macos_voice_en if _looks_english(text) else self._cfg.voice.macos_voice_it
        try:
            subprocess.run(
                ["say", "-v", voice, "-r", "180", text],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            logger.debug("`say` command not found")
