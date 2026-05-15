"""Orchestrator — decides between skill / swarm / simple chat for each input.

Routing logic (in order):

1. **Skill match** — if the user input matches a skill's trigger keywords,
   execute it and return a short confirmation.
2. **Swarm trigger** — if the input asks for “scrivi codice”, “progetto”,
   “sviluppa”, route to the CrewAI swarm (if CrewAI is installed).
3. **Default** — :class:`SimpleAgent` with brain + episodic context.

Token optimization rules:
- Learning loop: ALWAYS uses Ollama (local), NEVER Kimi.
- Routing decisions: local keyword matching, no LLM call.
- Brain learning (impara): pure local write, no LLM call.
- Only user-facing chat uses Kimi (if configured and Ollama unavailable).
"""

from __future__ import annotations

import logging
import time
from typing import Iterator, List, Optional

from jarvismk2.agents.auto_learning import AutoInternetLearningAgent
from jarvismk2.agents.simple import SimpleAgent
from jarvismk2.agents.swarm import Swarm
from jarvismk2.agents.webbridge import KimiWebBridgeAgent
from jarvismk2.brain.cervello import get_cervello
from jarvismk2.brain.learning import LearningOrchestrator
from jarvismk2.core.config import get_config
from jarvismk2.core.events import EventType, get_bus
from jarvismk2.core.types import AgentResponse, ChatMessage
from jarvismk2.skills.manager import SkillsManager, get_skills_manager

logger = logging.getLogger(__name__)


_SWARM_HINTS = (
    "scrivi script",
    "scrivi codice",
    "sviluppa",
    "progetto python",
    "progetto in python",
    "scrivi una funzione",
    "scrivi un modulo",
    "implementa",
)

_SKILL_CREATE_HINTS = (
    "crea skill",
    "crea una skill",
    "crea nuova skill",
    "aggiungi skill",
    "definisci skill",
)

_LEARNING_QUEUE_HINTS = (
    "aggiungi alla coda",
    "metti in coda",
    "impara su",
    "coda di apprendimento",
    "aggiungi topic",
    "queue learning",
    "impara poi",
)


class Orchestrator:
    """Top-level router used by CLI/server."""

    def __init__(
        self,
        skills: Optional[SkillsManager] = None,
        learning: Optional[LearningOrchestrator] = None,
    ) -> None:
        self._skills = skills or get_skills_manager()
        # Learning loop: ALWAYS Ollama, NEVER Kimi (saves 100% cloud tokens)
        self._learning = learning or LearningOrchestrator()
        self._learning.start()
        self._simple = SimpleAgent()
        self._auto_learning = AutoInternetLearningAgent.get_instance()
        self._webbridge = KimiWebBridgeAgent()
        self._swarm: Optional[Swarm] = None
        self._bus = get_bus()

    # ── public API ────────────────────────────────────────────────────
    def run(
        self,
        user_input: str,
        history: Optional[List[ChatMessage]] = None,
        prefer: Optional[str] = None,
    ) -> AgentResponse:
        cfg = get_config()
        self._bus.publish(EventType.CHAT_USER_MESSAGE, {"content": user_input})

        # 1) explicit "/swarm ..." escape
        text = user_input.strip()
        force_swarm = text.lower().startswith("/swarm ") or prefer == "swarm"
        if force_swarm:
            return self._run_swarm(text.split(" ", 1)[1] if " " in text else text)

        # 2) skill match
        skill_name = self._skills.match(text)
        if skill_name:
            return self._run_skill(skill_name, text)

        # 3) continuous learning control commands
        if AutoInternetLearningAgent.wants_continuous(text):
            return self._run_auto_learning_continuous(start=True)
        if AutoInternetLearningAgent.wants_stop(text):
            return self._run_auto_learning_continuous(start=False)
        if AutoInternetLearningAgent.wants_status(text):
            return self._run_auto_learning_status()

        # 4) single-shot internet learning command: WebBridge + Qwen only, no Kimi
        if AutoInternetLearningAgent.wants_auto_learning(text):
            return self._run_auto_learning(text)

        # 4b) skill creation from chat
        if any(h in text.lower() for h in _SKILL_CREATE_HINTS):
            return self._run_skill_create(text)

        # 4c) add to learning queue
        if any(h in text.lower() for h in _LEARNING_QUEUE_HINTS):
            return self._run_queue_add(text)

        # 4) browser/web intent via Kimi WebBridge (local browser, compact observations)
        if prefer == "webbridge" or KimiWebBridgeAgent.wants_webbridge(text):
            return self._run_webbridge(text)

        # 5) swarm by intent
        if prefer != "simple" and any(h in text.lower() for h in _SWARM_HINTS):
            try:
                return self._run_swarm(text)
            except Exception as e:
                logger.warning("swarm unavailable, falling back to simple: %s", e)

        # 6) default: simple chat
        start = time.time()
        resp = self._simple.run(text, history=history)
        elapsed = int((time.time() - start) * 1000)
        self._learning.on_interaction(
            user_input=text,
            action=resp.action,
            success=resp.success,
            latency_ms=elapsed,
            model=resp.model,
            task_type="conversation",
        )
        self._bus.publish(
            EventType.CHAT_ASSISTANT_MESSAGE,
            {"content": resp.text, "agent": "simple"},
        )
        # learn from interaction → temporal lobe (skip trivial exchanges)
        if len(text) >= 30 and len(resp.text) >= 30:
            try:
                get_cervello().impara(
                    contenuto=f"Q:{text[:80]}→A:{resp.text[:80]}",
                    tipo="fatto",
                    lobo="temporale",
                    fonte="conversazione",
                    tag=["chat"],
                )
            except Exception:
                pass
        return resp

    def stream(
        self,
        user_input: str,
        history: Optional[List[ChatMessage]] = None,
    ) -> Iterator[str]:
        """Stream-friendly path.  Skills/swarm fall back to non-streaming."""
        text = user_input.strip()
        self._bus.publish(EventType.CHAT_USER_MESSAGE, {"content": user_input})

        if text.lower().startswith("/swarm "):
            yield self._run_swarm(text[7:].strip()).text
            return

        skill = self._skills.match(text)
        if skill:
            yield self._run_skill(skill, text).text
            return

        if AutoInternetLearningAgent.wants_continuous(text):
            yield self._run_auto_learning_continuous(start=True).text
            return

        if AutoInternetLearningAgent.wants_stop(text):
            yield self._run_auto_learning_continuous(start=False).text
            return

        if AutoInternetLearningAgent.wants_status(text):
            yield self._run_auto_learning_status().text
            return

        if AutoInternetLearningAgent.wants_auto_learning(text):
            yield self._run_auto_learning(text).text
            return

        if any(h in text.lower() for h in _SKILL_CREATE_HINTS):
            yield self._run_skill_create(text).text
            return

        if any(h in text.lower() for h in _LEARNING_QUEUE_HINTS):
            yield self._run_queue_add(text).text
            return

        if KimiWebBridgeAgent.wants_webbridge(text):
            yield self._run_webbridge(text).text
            return

        if any(h in text.lower() for h in _SWARM_HINTS):
            try:
                yield self._run_swarm(text).text
                return
            except Exception:
                pass

        for chunk in self._simple.stream(text, history=history):
            yield chunk

    # ── helpers ───────────────────────────────────────────────────────
    def _run_skill(self, skill_name: str, user_input: str) -> AgentResponse:
        start = time.time()
        result = self._skills.esegui(skill_name)
        elapsed = int((time.time() - start) * 1000)
        ok = bool(result.get("ok"))
        if ok:
            text = (
                f"Eseguita skill '{result.get('skill', skill_name)}' "
                f"({result.get('successi', 0)}/{result.get('totali', 0)} step ok)."
            )
        else:
            text = (
                f"Skill '{skill_name}' fallita: "
                f"{result.get('error', 'errore sconosciuto')}"
            )
        self._learning.on_interaction(
            user_input=user_input,
            action=skill_name,
            success=ok,
            latency_ms=elapsed,
            model="local",
            task_type="skill",
            error="" if ok else str(result.get("error", "")),
        )
        return AgentResponse(
            text=text,
            action=skill_name,
            success=ok,
            latency_ms=elapsed,
            model="skill-runner",
            metadata={"result": result},
        )

    def _run_webbridge(self, user_input: str) -> AgentResponse:
        start = time.time()
        resp = self._webbridge.run(user_input)
        elapsed = int((time.time() - start) * 1000)
        self._learning.on_interaction(
            user_input=user_input,
            action=resp.action,
            success=resp.success,
            latency_ms=elapsed,
            model="kimi-webbridge",
            task_type="browser",
            error="" if resp.success else str(resp.metadata.get("error", "")),
        )
        self._bus.publish(
            EventType.CHAT_ASSISTANT_MESSAGE,
            {"content": resp.text, "agent": "kimi_webbridge"},
        )
        return resp

    def _run_auto_learning(self, user_input: str) -> AgentResponse:
        start = time.time()
        resp = self._auto_learning.run(user_input)
        elapsed = int((time.time() - start) * 1000)
        self._learning.on_interaction(
            user_input=user_input,
            action=resp.action,
            success=resp.success,
            latency_ms=elapsed,
            model=resp.model,
            task_type="auto_learning_web",
            error="" if resp.success else str(resp.metadata.get("error", "")),
        )
        self._bus.publish(
            EventType.CHAT_ASSISTANT_MESSAGE,
            {"content": resp.text, "agent": "auto_learning_qwen"},
        )
        return resp

    def _run_skill_create(self, user_input: str) -> AgentResponse:
        import re as _re
        text = user_input.strip()
        low = text.lower()
        nome = ""
        for h in _SKILL_CREATE_HINTS:
            if h in low:
                after = text[low.index(h) + len(h):].strip()
                nome = _re.split(r"\s+(?:che|con|che fa|che esegue)", after, maxsplit=1, flags=_re.I)[0].strip()
                break
        nome = _re.sub(r"[^a-z0-9_ ]", "", nome.lower()).strip()[:40].replace(" ", "_")
        if not nome:
            nome = f"skill_{int(time.time())}"
        trigger = [nome.replace("_", " ")]
        azioni = [{"tool": "notifica_sistema", "args": {"titolo": "JARVIS", "messaggio": f"Skill '{nome}' eseguita."}}]
        ok = self._skills.create(nome=nome, descrizione=text[:120], azioni=azioni, trigger_keywords=trigger)
        return AgentResponse(
            text=f"Skill '{nome}' creata. Trigger: '{trigger[0]}'. Modifica le azioni dalla pagina SKILLS.",
            action="skill_created",
            success=ok,
            model="local",
            metadata={"nome": nome, "trigger": trigger},
        )

    def _run_queue_add(self, user_input: str) -> AgentResponse:
        import re as _re
        text = user_input.strip()
        low = text.lower()
        agent = AutoInternetLearningAgent.get_instance()
        topic = text
        for h in _LEARNING_QUEUE_HINTS:
            if h in low:
                topic = text[low.index(h) + len(h):].strip()
                topic = _re.sub(r"^\s*(su|di|su)\s+", "", topic, flags=_re.I).strip()
                break
        if topic:
            agent.queue_add(topic)
            q = agent.queue_list()
            return AgentResponse(
                text=f"Topic '{topic}' aggiunto alla coda di apprendimento. "
                     f"Coda: {len(q)} topic in attesa.",
                action="learning_queue_add",
                success=True,
                model="local",
                metadata={"topic": topic, "queue_size": len(q)},
            )
        return AgentResponse(
            text="Specifica un topic da aggiungere alla coda, es. 'impara su python asyncio'.",
            action="learning_queue_add_failed",
            success=False,
            model="local",
        )

    def _run_auto_learning_continuous(self, start: bool) -> AgentResponse:
        """Gestisce start/stop apprendimento continuo."""
        agent = AutoInternetLearningAgent.get_instance()
        if start:
            resp = agent.start_continuous()
        else:
            resp = agent.stop_continuous()
        
        self._bus.publish(
            EventType.CHAT_ASSISTANT_MESSAGE,
            {
                "content": resp.text,
                "agent": "auto_learning_continuous",
                "status": "learning" if start else "completed",
            },
        )
        return resp
    
    def _run_auto_learning_status(self) -> AgentResponse:
        """Restituisce stato apprendimento continuo."""
        agent = AutoInternetLearningAgent.get_instance()
        return agent.get_status()

    def _ensure_swarm(self) -> Swarm:
        if self._swarm is None:
            self._swarm = Swarm()
        return self._swarm

    def _run_swarm(self, task: str) -> AgentResponse:
        swarm = self._ensure_swarm()
        start = time.time()
        try:
            result_text = swarm.run(task)
            elapsed = int((time.time() - start) * 1000)
            self._learning.on_interaction(
                user_input=task,
                action="swarm.crewai",
                success=True,
                latency_ms=elapsed,
                model="qwen2.5",
                task_type="swarm",
            )
            return AgentResponse(
                text=result_text,
                action="swarm.crewai",
                success=True,
                latency_ms=elapsed,
                model="swarm",
                metadata={"pipeline": ["architect", "developer", "reviewer"]},
            )
        except RuntimeError as e:
            # CrewAI not installed or local LLM not ready — fall back
            logger.info("swarm unavailable: %s", e)
            raise


# ── singleton ─────────────────────────────────────────────────────────
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
