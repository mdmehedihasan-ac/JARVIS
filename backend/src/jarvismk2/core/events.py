"""Lightweight pub/sub event bus.

Used so the brain, channels, agents, and frontend (via WebSocket fanout) can
react to system-wide events without tight coupling.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Chat / agent
    CHAT_USER_MESSAGE = "chat.user_message"
    CHAT_ASSISTANT_MESSAGE = "chat.assistant_message"
    CHAT_TOKEN = "chat.token"                          # streaming token
    AGENT_STARTED = "agent.started"
    AGENT_FINISHED = "agent.finished"
    AGENT_ERROR = "agent.error"

    # Brain
    BRAIN_NEURON_ACTIVATED = "brain.neuron_activated"
    BRAIN_NEURON_LEARNED = "brain.neuron_learned"
    BRAIN_LOBO_LOAD_CHANGED = "brain.lobo_load_changed"

    # Channels
    CHANNEL_MESSAGE_RECEIVED = "channel.message_received"
    CHANNEL_MESSAGE_SENT = "channel.message_sent"
    CHANNEL_STATUS_CHANGED = "channel.status_changed"

    # Voice
    VOICE_WAKE_DETECTED = "voice.wake_detected"
    VOICE_TRANSCRIPT = "voice.transcript"
    VOICE_TTS_SPEAKING = "voice.tts_speaking"

    # Learning
    LEARNING_SKILL_ACQUIRED = "learning.skill_acquired"
    LEARNING_PATTERN_DETECTED = "learning.pattern_detected"


Handler = Callable[["Event"], None]


@dataclass
class Event:
    type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    """Thread-safe in-process bus."""

    def __init__(self) -> None:
        self._handlers: Dict[EventType, List[Handler]] = {}
        self._wildcards: List[Handler] = []
        self._lock = threading.RLock()

    def subscribe(
        self, event_type: Optional[EventType], handler: Handler
    ) -> Callable[[], None]:
        """Subscribe to a specific event type, or to **all** events when
        ``event_type`` is ``None``.  Returns an unsubscribe callable."""
        with self._lock:
            if event_type is None:
                self._wildcards.append(handler)
            else:
                self._handlers.setdefault(event_type, []).append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                if event_type is None:
                    if handler in self._wildcards:
                        self._wildcards.remove(handler)
                else:
                    lst = self._handlers.get(event_type, [])
                    if handler in lst:
                        lst.remove(handler)

        return _unsubscribe

    def publish(self, event_type: EventType, payload: Optional[Dict[str, Any]] = None) -> None:
        """Synchronously dispatch the event to all subscribers."""
        ev = Event(type=event_type, payload=payload or {})
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))
            wildcards = list(self._wildcards)

        for h in handlers + wildcards:
            try:
                h(ev)
            except Exception:
                logger.debug("event handler error for %s", event_type, exc_info=True)


# ── module-level singleton ─────────────────────────────────────────────────
_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    """Lazy singleton accessor."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus
