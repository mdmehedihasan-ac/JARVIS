"""Telegram bot adapter.

Adapted from OpenJarvis's ``channels/telegram.py``: long-polling listener,
send-only mode if ``python-telegram-bot`` isn't installed, allow-list of chat
ids, event bus integration.
"""

from __future__ import annotations

import logging
import textwrap
import threading
from typing import Callable, List, Optional

import httpx

from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus
from jarvismk2.core.types import ChannelMessage, ChannelStatus

logger = logging.getLogger(__name__)

Handler = Callable[[ChannelMessage], None]
_TELEGRAM_MAX_LEN = 4096


class TelegramChannel:
    """Long-polling Telegram bot wrapping :class:`Orchestrator` calls."""

    channel_id = "telegram"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        allowed_chat_ids: Optional[List[str]] = None,
        parse_mode: str = "Markdown",
    ) -> None:
        cfg = get_config()
        self._token = bot_token if bot_token is not None else cfg.telegram.bot_token
        self._allowed = list(
            allowed_chat_ids if allowed_chat_ids is not None else cfg.telegram.allowed_chat_ids
        )
        self._parse_mode = parse_mode
        self._handlers: List[Handler] = []
        self._status = ChannelStatus.DISCONNECTED
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._bus = get_bus()

    # ── lifecycle ─────────────────────────────────────────────────────
    def on_message(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def status(self) -> ChannelStatus:
        return self._status

    def start(self) -> None:
        """Start the long-polling listener (or send-only if SDK missing)."""
        if not self._token:
            logger.warning("Telegram bot token not configured")
            self._status = ChannelStatus.ERROR
            return
        self._stop.clear()
        self._status = ChannelStatus.CONNECTING

        try:
            from telegram.ext import ApplicationBuilder  # noqa: F401
        except ImportError:
            logger.info(
                "python-telegram-bot not installed; running in send-only mode"
            )
            self._status = ChannelStatus.CONNECTED
            return

        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="telegram")
        self._thread.start()
        self._status = ChannelStatus.CONNECTED
        logger.info("Telegram channel connected (long polling)")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._status = ChannelStatus.DISCONNECTED

    # ── send ──────────────────────────────────────────────────────────
    def send(self, chat_id: str, content: str) -> bool:
        if not self._token:
            return False
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        chunks = textwrap.wrap(
            content,
            width=_TELEGRAM_MAX_LEN,
            break_long_words=True,
            replace_whitespace=False,
        )
        if not chunks:
            chunks = [""]
        try:
            for chunk in chunks:
                payload = {"chat_id": chat_id, "text": chunk}
                if self._parse_mode:
                    payload["parse_mode"] = self._parse_mode
                r = httpx.post(url, json=payload, timeout=10.0)
                if r.status_code >= 300:
                    logger.warning(
                        "Telegram send error %d: %s", r.status_code, r.text[:200]
                    )
                    return False
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_SENT,
                {"channel": "telegram", "chat_id": chat_id, "content": content},
            )
            return True
        except Exception:
            logger.debug("Telegram send failed", exc_info=True)
            return False

    # ── poll loop (PTB) ───────────────────────────────────────────────
    def _poll_loop(self) -> None:
        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters

            app = ApplicationBuilder().token(self._token).build()

            async def _handle(update, _ctx):  # noqa: ANN001 — PTB API
                msg = update.message
                if not msg:
                    return
                cm = ChannelMessage(
                    channel="telegram",
                    sender=str(msg.from_user.id) if msg.from_user else "",
                    content=msg.text or "",
                    message_id=str(msg.message_id),
                    conversation_id=str(msg.chat.id),
                )
                if self._allowed and cm.conversation_id not in self._allowed:
                    logger.debug("ignoring chat %s", cm.conversation_id)
                    return
                self._bus.publish(
                    EventType.CHANNEL_MESSAGE_RECEIVED,
                    cm.to_dict(),
                )
                for h in self._handlers:
                    try:
                        h(cm)
                    except Exception:
                        logger.exception("Telegram handler error")

            app.add_handler(MessageHandler(filters.TEXT, _handle))
            app.run_polling(stop_signals=None, drop_pending_updates=True)
        except Exception:
            logger.debug("Telegram poll loop error", exc_info=True)
            self._status = ChannelStatus.ERROR


def make_telegram_bot_orchestrator_glue() -> Optional[TelegramChannel]:
    """Convenience: build a TelegramChannel that routes every message through
    the orchestrator and replies back on the same chat.

    Returns ``None`` if no Telegram token is configured.
    """
    cfg = get_config()
    if not cfg.telegram.bot_token:
        return None

    from jarvismk2.agents.orchestrator import get_orchestrator

    chan = TelegramChannel()
    orch = get_orchestrator()

    def _handler(msg: ChannelMessage) -> None:
        try:
            resp = orch.run(msg.content)
            chan.send(msg.conversation_id, resp.text or "(nessuna risposta)")
        except Exception as e:
            logger.exception("orchestrator failed for telegram message")
            chan.send(
                msg.conversation_id, f"Errore interno: {type(e).__name__}: {e}"
            )

    chan.on_message(_handler)
    return chan
