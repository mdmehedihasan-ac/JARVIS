"""FastAPI server: REST + WebSocket streaming used by the frontend."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from jarvismk2 import __version__
from jarvismk2.agents.auto_learning import AutoInternetLearningAgent
from jarvismk2.agents.orchestrator import get_orchestrator
from jarvismk2.brain.cervello import get_cervello
from jarvismk2.brain.episodic import get_episodic
from jarvismk2.brain.learning import LearningOrchestrator
from jarvismk2.connectors.obsidian import ObsidianConnector
from jarvismk2.connectors.webbridge import get_webbridge
from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus
from jarvismk2.core.scheduler import get_scheduler
from jarvismk2.core.types import ChatMessage
from jarvismk2.engine.router import get_router
from jarvismk2.skills.manager import get_skills_manager
from jarvismk2.voice.voce import Voce

logger = logging.getLogger(__name__)


# ── pydantic schemas ───────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    prefer: Optional[str] = None
    speak: bool = False
    msg_id: Optional[str] = None


class ChatResponse(BaseModel):
    text: str
    action: str
    success: bool
    latency_ms: int
    model: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SkillCreate(BaseModel):
    nome: str
    descrizione: str
    azioni: List[Dict[str, Any]]
    tag: List[str] = Field(default_factory=list)
    trigger_keywords: List[str] = Field(default_factory=list)
    schedule_every_seconds: Optional[int] = None


class SkillScheduleBody(BaseModel):
    every_seconds: int


class LearningQueueAdd(BaseModel):
    topic: str


# ── global cancel flags (msg_id → threading.Event) ────────────────────────
_cancel_flags: Dict[str, threading.Event] = {}


# ── app ────────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    cfg = get_config()
    app = FastAPI(
        title="JARVIS MK2",
        version=__version__,
        description="Personal AI Assistant — fusion of OpenJarvis and JARVIS.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.server.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    learning = LearningOrchestrator()
    learning.start()
    voce = Voce()

    scheduler = get_scheduler()

    def _register_scheduled_skills() -> None:
        sm = get_skills_manager()
        for item in sm.scheduled_skills():
            job_id = f"skill_{item['nome']}"
            scheduler.schedule(job_id, sm.esegui, args=(item["nome"],), every_seconds=item["every_seconds"])

    threading.Thread(target=_register_scheduled_skills, daemon=True).start()

    @app.on_event("shutdown")
    def _shutdown_voice() -> None:
        voce.stop()

    # ── basic ────────────────────────────────────────────────────────
    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        try:
            import whisper as _w  # noqa: F401
            _whisper_ok = True
        except ImportError:
            _whisper_ok = False
        return {
            "ok": True,
            "version": __version__,
            "engines": get_router().available(),
            "webbridge": get_webbridge().status(),
            "whisper": _whisper_ok,
            "persona": {
                "name": cfg.persona.name,
                "user_name": cfg.persona.user_name,
                "lang": cfg.persona.lang,
            },
        }

    @app.get("/api/config")
    def config_view() -> Dict[str, Any]:
        return {
            "persona": {
                "name": cfg.persona.name,
                "user_name": cfg.persona.user_name,
                "lang": cfg.persona.lang,
            },
            "ollama": {
                "host": cfg.ollama.host,
                "model_fast": cfg.ollama.model_fast,
                "model_heavy": cfg.ollama.model_heavy,
            },
            "voice": {
                "wake_words": cfg.voice.wake_words,
                "elevenlabs_voice_id": cfg.voice.elevenlabs_voice_id,
            },
            "obsidian": {
                "vault_path": cfg.obsidian.vault_path,
                "configured": cfg.obsidian.is_configured,
            },
            "telegram": {"configured": bool(cfg.telegram.bot_token)},
        }

    # ── chat ─────────────────────────────────────────────────────────
    @app.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        history = [
            ChatMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
            )
            for m in req.history
            if m.get("content")
        ]
        try:
            resp = get_orchestrator().run(req.message, history=history, prefer=req.prefer)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        if req.speak and resp.text.strip():
            voce.parla(resp.text, priority=True)
        return ChatResponse(
            text=resp.text,
            action=resp.action,
            success=resp.success,
            latency_ms=resp.latency_ms,
            model=resp.model,
            metadata=resp.metadata,
        )

    # ── WebSocket streaming chat ─────────────────────────────────────
    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                payload = await ws.receive_json()
                msg = payload.get("message", "")
                speak = bool(payload.get("speak", False))
                prefer = payload.get("prefer")
                msg_id = payload.get("msg_id", "")
                cancel_previous = bool(payload.get("cancel_previous", False))
                previous_msg_id = payload.get("previous_msg_id", "")
                history = [
                    ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
                    for m in payload.get("history", [])
                ]
                if not msg:
                    await ws.send_json({"type": "error", "error": "empty message"})
                    continue

                # cancel previous request if asked
                if cancel_previous and previous_msg_id and previous_msg_id in _cancel_flags:
                    _cancel_flags[previous_msg_id].set()
                    logger.info("Cancelled previous request %s", previous_msg_id)

                # register cancel flag for this request
                if msg_id:
                    _cancel_flags[msg_id] = threading.Event()

                try:
                    orchestrator = get_orchestrator()
                    loop = asyncio.get_event_loop()

                    queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
                    full_text = ""

                    def _produce(mid: str = "") -> None:
                        try:
                            for chunk in orchestrator.stream(msg, history=history, prefer=prefer):
                                if mid and mid in _cancel_flags and _cancel_flags[mid].is_set():
                                    logger.info("Stream cancelled for msg_id=%s", mid)
                                    break
                                loop.call_soon_threadsafe(
                                    queue.put_nowait,
                                    {"type": "token", "token": chunk},
                                )
                            if not (mid and mid in _cancel_flags and _cancel_flags[mid].is_set()):
                                loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})
                        except Exception as e:
                            loop.call_soon_threadsafe(
                                queue.put_nowait,
                                {"type": "error", "error": str(e)},
                            )

                    threading.Thread(target=_produce, args=(msg_id,), daemon=True).start()

                    while True:
                        item = await queue.get()
                        if item["type"] == "token":
                            chunk = item["token"]
                            full_text += chunk
                            await ws.send_json({"type": "token", "token": chunk})
                        elif item["type"] == "done":
                            if speak and full_text.strip():
                                voce.parla(full_text, priority=True)
                            await ws.send_json({"type": "done", "text": full_text})
                            break
                        else:
                            await ws.send_json({"type": "error", "error": item.get("error", "unknown error")})
                            break
                except Exception as e:
                    logger.exception("ws chat error")
                    await ws.send_json({"type": "error", "error": str(e)})
                finally:
                    if msg_id and msg_id in _cancel_flags:
                        del _cancel_flags[msg_id]
        except WebSocketDisconnect:
            return

    # ── WebSocket events fanout (brain / channels / voice) ────────────
    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        await ws.accept()
        bus = get_bus()
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _on_event(ev) -> None:  # noqa: ANN001 — internal event type
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": ev.type.value, "payload": ev.payload, "ts": ev.ts},
                )
            except Exception:
                pass

        unsubscribe = bus.subscribe(None, _on_event)
        try:
            while True:
                ev = await queue.get()
                await ws.send_json(ev)
        except WebSocketDisconnect:
            return
        finally:
            unsubscribe()

    # ── brain ────────────────────────────────────────────────────────
    @app.get("/api/brain/status")
    def brain_status() -> Dict[str, Any]:
        return get_cervello().stato()

    @app.get("/api/brain/graph")
    def brain_graph(max_per_lobo: int = 25) -> Dict[str, Any]:
        return get_cervello().grafo(max_per_lobo=max_per_lobo)

    @app.post("/api/brain/learn")
    def brain_learn(
        contenuto: str, tipo: str, lobo: str, tag: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        try:
            nid = get_cervello().impara(
                contenuto=contenuto, tipo=tipo, lobo=lobo, tag=tag or []
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"id": nid, "ok": True}

    @app.post("/api/brain/sync-obsidian")
    def brain_sync_obsidian() -> Dict[str, Any]:
        added = ObsidianConnector().sync_to_brain()
        return {"added": added}

    # ── episodic ─────────────────────────────────────────────────────
    @app.get("/api/episodic/stats")
    def episodic_stats() -> Dict[str, Any]:
        return get_episodic().stats()

    @app.get("/api/episodic/recent")
    def episodic_recent(n: int = 20) -> List[Dict[str, Any]]:
        return get_episodic().episodi_recenti(n=n)

    @app.get("/api/episodic/search")
    def episodic_search(q: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return get_episodic().cerca_simili(q, top_k=top_k)

    # ── skills ───────────────────────────────────────────────────────
    @app.get("/api/skills")
    def skills_list() -> List[Dict[str, Any]]:
        return get_skills_manager().list()

    @app.post("/api/skills")
    def skills_create(body: SkillCreate) -> Dict[str, Any]:
        ok = get_skills_manager().create(
            nome=body.nome,
            descrizione=body.descrizione,
            azioni=body.azioni,
            tag=body.tag,
            trigger_keywords=body.trigger_keywords,
            schedule_every_seconds=body.schedule_every_seconds,
        )
        if ok and body.schedule_every_seconds:
            sm = get_skills_manager()
            job_id = f"skill_{body.nome}"
            scheduler.schedule(job_id, sm.esegui, args=(body.nome,), every_seconds=body.schedule_every_seconds)
        return {"ok": ok}

    @app.delete("/api/skills/{nome}")
    def skills_delete(nome: str) -> Dict[str, Any]:
        return {"ok": get_skills_manager().delete(nome)}

    @app.post("/api/skills/{nome}/run")
    def skills_run(nome: str) -> Dict[str, Any]:
        return get_skills_manager().esegui(nome)

    # ── learning ─────────────────────────────────────────────────────
    @app.get("/api/learning/status")
    def learning_status() -> Dict[str, Any]:
        return learning.status()

    @app.get("/api/learning/export")
    def learning_export() -> Dict[str, Any]:
        return learning.export_knowledge()

    # ── obsidian search ─────────────────────────────────────────────
    @app.get("/api/obsidian/search")
    def obsidian_search(q: str, top_k: int = 10) -> List[Dict[str, Any]]:
        return ObsidianConnector().search(q, top_k=top_k)

    # ── token usage stats ─────────────────────────────────────────
    @app.get("/api/tokens/stats")
    def token_stats() -> Dict[str, Any]:
        from jarvismk2.engine.token_budget import get_tracker
        return get_tracker().get_stats()

    # ── STT / Whisper ─────────────────────────────────────────────
    def _whisper_available() -> bool:
        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @app.get("/api/stt/available")
    def stt_available() -> Dict[str, Any]:
        return {"available": _whisper_available()}

    @app.post("/api/stt/transcribe")
    async def stt_transcribe(request: Any) -> Dict[str, Any]:
        if not _whisper_available():
            raise HTTPException(status_code=503, detail="Whisper non disponibile. Installa con: pip install openai-whisper")
        try:
            import tempfile, os, whisper as _whisper  # type: ignore
            body = await request.body()
            suffix = ".webm"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(body)
                tmp_path = f.name
            model = _whisper.load_model("base")
            result = model.transcribe(tmp_path, language="it")
            os.unlink(tmp_path)
            return {"text": result.get("text", "").strip(), "ok": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── cancel active request ────────────────────────────────────
    @app.post("/api/cancel")
    def cancel_request(body: Dict[str, Any]) -> Dict[str, Any]:
        msg_id = body.get("msg_id", "")
        if msg_id and msg_id in _cancel_flags:
            _cancel_flags[msg_id].set()
            return {"ok": True, "cancelled": msg_id}
        return {"ok": False, "error": "no active request"}

    # ── brain search ─────────────────────────────────────────────
    @app.get("/api/brain/search")
    def brain_search(q: str, top: int = 8) -> List[Dict[str, Any]]:
        return get_cervello().cerca_fuzzy(q, top=top)

    # ── learning queue ───────────────────────────────────────────
    @app.get("/api/learning/queue")
    def queue_list() -> List[Dict[str, Any]]:
        return AutoInternetLearningAgent.get_instance().queue_list()

    @app.post("/api/learning/queue")
    def queue_add(body: LearningQueueAdd) -> Dict[str, Any]:
        AutoInternetLearningAgent.get_instance().queue_add(body.topic)
        q = AutoInternetLearningAgent.get_instance().queue_list()
        return {"ok": True, "queue_size": len(q)}

    @app.delete("/api/learning/queue/{idx}")
    def queue_remove(idx: int) -> Dict[str, Any]:
        ok = AutoInternetLearningAgent.get_instance().queue_remove(idx)
        return {"ok": ok}

    @app.delete("/api/learning/queue")
    def queue_clear() -> Dict[str, Any]:
        AutoInternetLearningAgent.get_instance().queue_clear()
        return {"ok": True}

    @app.get("/api/learning/continuous")
    def learning_continuous_status() -> Dict[str, Any]:
        agent = AutoInternetLearningAgent.get_instance()
        return {
            "running": agent._continuous_running,
            "stats": agent._stats,
        }

    @app.post("/api/learning/continuous/start")
    def learning_continuous_start() -> Dict[str, Any]:
        resp = AutoInternetLearningAgent.get_instance().start_continuous()
        return {"ok": resp.success, "text": resp.text}

    @app.post("/api/learning/continuous/stop")
    def learning_continuous_stop() -> Dict[str, Any]:
        resp = AutoInternetLearningAgent.get_instance().stop_continuous()
        return {"ok": resp.success, "text": resp.text}

    # ── skill scheduling ─────────────────────────────────────────
    @app.post("/api/skills/{nome}/schedule")
    def skill_schedule(nome: str, body: SkillScheduleBody) -> Dict[str, Any]:
        sm = get_skills_manager()
        ok = sm.update(nome, {"schedule_every_seconds": body.every_seconds})
        if ok:
            job_id = f"skill_{nome}"
            scheduler.schedule(job_id, sm.esegui, args=(nome,), every_seconds=body.every_seconds)
        return {"ok": ok}

    @app.delete("/api/skills/{nome}/schedule")
    def skill_unschedule(nome: str) -> Dict[str, Any]:
        sm = get_skills_manager()
        ok = sm.update(nome, {"schedule_every_seconds": None})
        scheduler.cancel(f"skill_{nome}")
        return {"ok": ok}

    @app.get("/api/scheduler/jobs")
    def scheduler_jobs() -> List[Dict[str, Any]]:
        return scheduler.list_jobs()

    # ── obsidian write note ───────────────────────────────────────
    @app.post("/api/obsidian/write")
    def obsidian_write(
        title: str,
        content: str,
        subdir: str = "web",
        source_url: str = "",
    ) -> Dict[str, Any]:
        return ObsidianConnector().write_note(title=title, content=content, subdir=subdir, source_url=source_url)

    return app


# Module-level app for `uvicorn jarvismk2.server:app`
app = create_app()
