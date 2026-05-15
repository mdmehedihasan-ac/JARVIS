"""Shared dataclasses used across modules.

These types are deliberately small and JSON-serializable so they can be sent
over WebSocket / REST to the frontend.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    """A single message in a conversation."""

    role: Role
    content: str
    ts: float = field(default_factory=time.time)
    name: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role, "content": self.content, "ts": self.ts}
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class BrainContext:
    """Context injected by the brain (cervello + episodic memory) into prompts."""

    lobo_attivato: str = ""
    neurons_snippets: List[str] = field(default_factory=list)
    episodes_block: str = ""

    def render(self) -> str:
        parts: List[str] = []
        if self.neurons_snippets:
            parts.append(
                f"[CERVELLO — lobo attivo: {self.lobo_attivato}]\n"
                + "\n".join(self.neurons_snippets)
            )
        if self.episodes_block:
            parts.append(self.episodes_block)
        return "\n\n".join(parts)


@dataclass
class AgentResponse:
    """Standardized output of an agent invocation."""

    text: str
    action: str = ""               # symbolic action / tool name
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = True
    latency_ms: int = 0
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "action": self.action,
            "tool_calls": self.tool_calls,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "metadata": self.metadata,
        }


class ChannelStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ChannelMessage:
    """An incoming message from an external channel (Telegram, web, etc.)."""

    channel: str                        # e.g. "telegram", "web"
    sender: str                         # platform-specific sender id
    content: str
    message_id: str = ""
    conversation_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "sender": self.sender,
            "content": self.content,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "metadata": self.metadata,
            "ts": self.ts,
        }
