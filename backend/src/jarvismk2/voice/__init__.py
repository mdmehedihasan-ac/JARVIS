"""Voice subsystem — Italian-first STT and TTS.

* :class:`Ascolto` — wake-word triggered microphone listener; Groq Whisper IT
  with Google STT fallback.
* :class:`Voce` — TTS queue.  ElevenLabs when configured, otherwise macOS
  ``say`` with the right voice for the detected language.
"""

from jarvismk2.voice.ascolto import Ascolto
from jarvismk2.voice.voce import Voce

__all__ = ["Ascolto", "Voce"]
