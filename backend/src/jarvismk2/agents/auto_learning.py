from __future__ import annotations

import json
import re
import threading
import time
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

from jarvismk2.brain.cervello import get_cervello
from jarvismk2.connectors.webbridge import WebBridgeConnector, get_webbridge
from jarvismk2.core.events import EventType, get_bus
from jarvismk2.core.types import AgentResponse
from jarvismk2.engine.base import Engine, Message
from jarvismk2.engine.ollama_engine import OllamaEngine
from jarvismk2.engine.token_budget import (
    estimate_messages_tokens,
    estimate_tokens,
    get_tracker,
    truncate_to_budget,
)

# ── LearningQueue ─────────────────────────────────────────────────

class LearningQueue:
    """Persistent queue of topics to learn, backed by JSON."""

    def __init__(self, path: Optional[str] = None) -> None:
        from jarvismk2.core.config import get_config
        cfg = get_config()
        self._path = path or str(cfg.data_dir / "learning_queue.json")
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        import os
        if not os.path.exists(self._path):
            self._items: List[Dict[str, Any]] = []
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._items = json.load(f)
        except Exception:
            self._items = []

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, topic: str) -> None:
        with self._lock:
            self._items.append({"topic": topic, "ts": time.time()})
            self._save()

    def add_many(self, topics: List[str]) -> None:
        with self._lock:
            for t in topics:
                self._items.append({"topic": t, "ts": time.time()})
            self._save()

    def pop(self) -> Optional[str]:
        with self._lock:
            if not self._items:
                return None
            item = self._items.pop(0)
            self._save()
            return str(item.get("topic", ""))

    def peek(self) -> Optional[str]:
        with self._lock:
            if not self._items:
                return None
            return str(self._items[0].get("topic", ""))

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._items)

    def remove(self, idx: int) -> bool:
        with self._lock:
            if 0 <= idx < len(self._items):
                self._items.pop(idx)
                self._save()
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._save()


# Trigger singolo ciclo
_TRIGGERS = (
    "avvia apprendimento automatico",
    "inizia apprendimento automatico",
    "fai apprendimento automatico",
    "fai apprendimento autonomo",
    "impara automaticamente",
    "auto apprendimento",
    "autoapprendimento",
    "apprendimento autonomo su",
    "apprendimenro autonomo",
)

# Trigger continuo
_TRIGGERS_CONTINUOUS = (
    "avvia apprendimento automatico",
    "inizia apprendimento automatico",
    "attiva apprendimento automatico",
    "inizia apprendimento continuo",
    "avvia apprendimento continuo",
    "inizia auto apprendimento",
    "avvia auto apprendimento",
    "avvia apprendimento autonomo",
    "inizia apprendimento autonomo",
    "attiva apprendimento autonomo",
    "apprendimento autonomo continuo",
    "apprendimento infinito",
    "impara continuamente",
)

# Trigger stop
_TRIGGERS_STOP = (
    "ferma apprendimento",
    "stop apprendimento",
    "smetti di imparare",
    "pausa apprendimento",
    "interrompi apprendimento",
)

# Trigger status
_TRIGGERS_STATUS = (
    "stato apprendimento",
    "status apprendimento",
    "stato auto apprendimento",
    "stato apprendimento autonomo",
    "come sta imparando",
    "progresso apprendimento",
)

_VALID_LOBI = {"frontale", "temporale", "parietale", "occipitale", "cerebellum", "ippocampo"}
_DEFAULT_TOPIC = "novità utili su AI locale, automazione browser, sviluppo software e assistenti personali"

# Topic tecnici predefiniti per apprendimento continuo
_TECH_TOPICS = [
    # Ingegneria
    "ingegneria software best practices",
    "system design patterns",
    "architettura microservizi",
    " DevOps CI/CD pipelines",
    "kubernetes best practices",
    "docker containerization",
    "cloud architecture AWS Azure GCP",
    "infrastructure as code terraform",
    "monitoring observability prometheus grafana",
    
    # Informatica / CS
    "algoritmi e strutture dati avanzate",
    "complessità computazionale",
    "distributed systems",
    "database design SQL NoSQL",
    "caching strategies redis",
    "message queues kafka rabbitmq",
    "API design REST GraphQL",
    "security best practices OWASP",
    "cryptography basics",
    "blockchain smart contracts",
    
    # Coding / Programming
    "python best practices 2024",
    "javascript typescript patterns",
    "rust programming memory safety",
    "go golang concurrency",
    "C++ performance optimization",
    "functional programming Haskell Scala",
    "clean code principles",
    "test driven development TDD",
    "refactoring techniques",
    "code review best practices",
    
    # AI / ML
    "machine learning algorithms explained",
    "deep learning neural networks",
    "natural language processing NLP",
    "computer vision techniques",
    "LLM large language models architecture",
    "prompt engineering best practices",
    "RAG retrieval augmented generation",
    "vector databases embeddings",
    "fine tuning LLMs",
    "AI agents autonomous systems",
    "multi-modal AI models",
    "AI safety alignment",
    
    # Scrivere / Copywriting
    "technical writing best practices",
    "documentation as code",
    "API documentation standards",
    "copywriting persuasivo",
    "content marketing strategy",
    "SEO content optimization",
    "storytelling techniques",
    "UX writing microcopy",
    "accessibility writing a11y",
    
    # Prompt Engineering
    "prompt engineering techniques",
    "chain of thought prompting",
    "few shot prompting",
    "zero shot prompting",
    "role prompting strategies",
    "system prompt design",
    "prompt injection prevention",
    "LLM context window optimization",
    "token efficiency techniques",
    
    # Tools & Workflow
    "git advanced workflows",
    "GitHub actions automation",
    "vim neovim productivity",
    "IDE tips tricks vscode",
    "terminal productivity zsh",
    "tmux session management",
    "Makefile automation",
    "just command runner",
    "task runners comparison",
    
    # Soft skills tech
    "agile methodologies scrum kanban",
    "tech lead responsibilities",
    "code review etiquette",
    "technical debt management",
    "incident response postmortem",
    "on-call best practices",
    "remote work productivity",
    "async communication",
]


class AutoInternetLearningAgent:
    name = "auto_internet_learning"
    
    _instance: Optional["AutoInternetLearningAgent"] = None
    _lock = threading.Lock()

    def __init__(self, bridge: Optional[WebBridgeConnector] = None) -> None:
        self._bridge = bridge or get_webbridge()
        self._continuous_running = False
        self._continuous_thread: Optional[threading.Thread] = None
        self._stats = {"total_learned": 0, "sessions": 0, "current_topic": "", "errors": 0}
        self._stop_event = threading.Event()
        self._bus = get_bus()
        self._queue = LearningQueue()
    
    @classmethod
    def get_instance(cls) -> "AutoInternetLearningAgent":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @staticmethod
    def wants_auto_learning(text: str) -> bool:
        low = text.lower()
        return any(t in low for t in _TRIGGERS)
    
    @staticmethod
    def wants_continuous(text: str) -> bool:
        low = text.lower()
        return any(t in low for t in _TRIGGERS_CONTINUOUS)
    
    @staticmethod
    def wants_stop(text: str) -> bool:
        low = text.lower()
        return any(t in low for t in _TRIGGERS_STOP)
    
    @staticmethod
    def wants_status(text: str) -> bool:
        low = text.lower()
        return any(t in low for t in _TRIGGERS_STATUS)

    def start_continuous(self) -> AgentResponse:
        """Avvia apprendimento continuo in background."""
        if self._continuous_running:
            return AgentResponse(
                text="Apprendimento continuo già in corso!",
                action="auto_learning_already_running",
                success=True,
                model="qwen+webbridge",
                metadata=self._stats,
            )
        
        self._continuous_running = True
        self._stop_event.clear()
        self._continuous_thread = threading.Thread(target=self._continuous_loop, daemon=True)
        self._continuous_thread.start()
        
        return AgentResponse(
            text=f"🚀 Apprendimento continuo avviato! Ciclo su {len(_TECH_TOPICS)} topic tecnici. "
                 f"Dì 'ferma apprendimento' per interrompere.",
            action="auto_learning_continuous_started",
            success=True,
            model="qwen+webbridge",
            metadata={"topics_count": len(_TECH_TOPICS), "topics_preview": _TECH_TOPICS[:5]},
        )
    
    def stop_continuous(self) -> AgentResponse:
        """Ferma apprendimento continuo."""
        if not self._continuous_running:
            return AgentResponse(
                text="Nessun apprendimento continuo in corso.",
                action="auto_learning_not_running",
                success=True,
                model="qwen+webbridge",
            )
        
        self._stop_event.set()
        self._continuous_running = False
        
        return AgentResponse(
            text=f"⏹️ Apprendimento continuo fermato. "
                 f"Totale neuroni imparati: {self._stats['total_learned']}. "
                 f"Sessioni completate: {self._stats['sessions']}.",
            action="auto_learning_continuous_stopped",
            success=True,
            model="qwen+webbridge",
            metadata=self._stats.copy(),
        )
    
    def get_status(self) -> AgentResponse:
        """Restituisce stato apprendimento."""
        cervello = get_cervello()
        total_neurons = sum(len(lobo.neuroni) for lobo in cervello.lobi.values())
        
        if self._continuous_running:
            text = (
                f"🔄 Apprendimento continuo ATTIVO\n"
                f"• Topic corrente: {self._stats['current_topic']}\n"
                f"• Neuroni imparati questa sessione: {self._stats['total_learned']}\n"
                f"• Sessioni completate: {self._stats['sessions']}\n"
                f"• Errori: {self._stats['errors']}\n"
                f"• Totale cervello: {total_neurons} neuroni\n"
                f"Dì 'ferma apprendimento' per interrompere."
            )
        else:
            text = (
                f"⏸️ Apprendimento continuo INATTIVO\n"
                f"• Ultima sessione: {self._stats['sessions']} cicli\n"
                f"• Ultimi neuroni: {self._stats['total_learned']}\n"
                f"• Totale cervello: {total_neurons} neuroni\n"
                f"Dì 'inizia apprendimento continuo' per avviare."
            )
        
        return AgentResponse(
            text=text,
            action="auto_learning_status",
            success=True,
            model="qwen+webbridge",
            metadata={**self._stats, "total_brain_neurons": total_neurons, "running": self._continuous_running},
        )
    
    def _continuous_loop(self) -> None:
        """Loop infinito di apprendimento."""
        import random
        
        topic_index = 0
        shuffled_topics = _TECH_TOPICS.copy()
        random.shuffle(shuffled_topics)
        
        while not self._stop_event.is_set():
            queued = self._queue.pop()
            topic = queued if queued else shuffled_topics[topic_index % len(shuffled_topics)]
            self._stats["current_topic"] = topic
            
            try:
                # Notifica inizio topic
                self._bus.publish(
                    EventType.CHAT_ASSISTANT_MESSAGE,
                    {"content": f"🔍 Apprendimento: {topic}", "agent": "auto_learning", "status": "learning"},
                )
                
                # Fa una singola sessione di apprendimento
                result = self._learn_topic(topic)
                
                if result.get("success"):
                    self._stats["total_learned"] += result.get("learned_count", 0)
                    self._stats["sessions"] += 1
                else:
                    self._stats["errors"] += 1
                
                # Notifica progresso ogni 5 sessioni
                if self._stats["sessions"] % 5 == 0:
                    self._bus.publish(
                        EventType.CHAT_ASSISTANT_MESSAGE,
                        {
                            "content": f"📚 Progresso: {self._stats['sessions']} topic, {self._stats['total_learned']} neuroni",
                            "agent": "auto_learning", 
                            "status": "progress"
                        },
                    )
                
            except Exception as e:
                self._stats["errors"] += 1
                print(f"[AutoLearning] Errore su {topic}: {e}")
            
            topic_index += 1
            
            # Pausa tra topic (30-60 secondi per non sovraccaricare)
            pause = random.uniform(30, 60)
            if self._stop_event.wait(timeout=pause):
                break
        
        self._continuous_running = False
        self._stats["current_topic"] = ""
        
        # Notifica fine
        self._bus.publish(
            EventType.CHAT_ASSISTANT_MESSAGE,
            {
                "content": f"✅ Apprendimento continuo completato. Totale: {self._stats['total_learned']} neuroni",
                "agent": "auto_learning",
                "status": "completed"
            },
        )
    
    def _learn_topic(self, topic: str) -> Dict[str, Any]:
        """Apprende un singolo topic. Ritorna dict con success e learned_count."""
        try:
            engine = self._pick_qwen()
        except Exception:
            return {"success": False, "error": "qwen unavailable"}
        
        queries = self._make_queries(engine, topic)
        learned_count = 0
        
        for query in queries[:2]:
            if self._stop_event.is_set():
                break
                
            url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            nav = self._bridge.command(
                "navigate",
                {"url": url, "newTab": True, "group_title": "JARVIS Learn"},
                max_chars=600,
            )
            snap = {"ok": False, "text": ""}
            if nav.get("ok"):
                time.sleep(1.5)
                snap = self._bridge.snapshot_text(max_chars=2600)
            if not snap.get("ok") or not snap.get("text"):
                snap = self._fetch_search_text(query, max_chars=2600)
            if not snap.get("ok") or not snap.get("text"):
                continue
            
            facts = self._fallback_facts(topic, query, str(snap["text"]))
            if not facts:
                facts = self._extract_facts(engine, topic, query, str(snap["text"]))
            for fact in facts[:3]:
                if self._save_fact(fact, topic, query):
                    learned_count += 1
            
            # Pausa breve tra query
            if self._stop_event.wait(timeout=5):
                break
        
        return {"success": learned_count > 0, "learned_count": learned_count}

    def run(self, user_input: str) -> AgentResponse:
        start = time.time()
        topic = self._extract_topic(user_input)
        status = self._bridge.status()

        try:
            engine = self._pick_qwen()
        except Exception as e:
            return AgentResponse(
                text=f"Non posso avviare l'apprendimento: nessun modello Qwen locale disponibile ({e}).",
                action="auto_learning_qwen_unavailable",
                success=False,
                latency_ms=int((time.time() - start) * 1000),
                model="qwen+webbridge",
            )

        queries = self._make_queries(engine, topic)
        learned: List[Dict[str, Any]] = []
        errors: List[str] = []

        for query in queries[:2]:
            url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            nav = self._bridge.command(
                "navigate",
                {"url": url, "newTab": True, "group_title": "JARVIS Learn"},
                max_chars=600,
            )
            snap = {"ok": False, "text": ""}
            if nav.get("ok"):
                time.sleep(1.5)
                snap = self._bridge.snapshot_text(max_chars=2600)
            else:
                errors.append(f"navigate:{query}")
            if not snap.get("ok") or not snap.get("text"):
                errors.append(f"snapshot:{query}")
                snap = self._fetch_search_text(query, max_chars=2600)
            if not snap.get("ok") or not snap.get("text"):
                errors.append(f"http_fetch:{query}")
                continue
            facts = self._fallback_facts(topic, query, str(snap["text"]))
            if not facts:
                facts = self._extract_facts(engine, topic, query, str(snap["text"]))
            for fact in facts[:3]:
                saved = self._save_fact(fact, topic, query)
                if saved and not any(item["contenuto"] == saved["contenuto"] for item in learned):
                    learned.append(saved)

        elapsed = int((time.time() - start) * 1000)
        if not learned:
            err = ", ".join(errors[:4]) or "nessun fatto affidabile estratto"
            return AgentResponse(
                text=f"Apprendimento automatico non completato su '{topic}': {err}.",
                action="auto_learning_failed",
                success=False,
                latency_ms=elapsed,
                model=getattr(engine, "default_model", "qwen"),
                metadata={"topic": topic, "queries": queries, "errors": errors},
            )

        by_lobo: Dict[str, int] = {}
        for item in learned:
            by_lobo[item["lobo"]] = by_lobo.get(item["lobo"], 0) + 1
        summary = ", ".join(f"{k}:{v}" for k, v in sorted(by_lobo.items()))
        return AgentResponse(
            text=(
                f"Apprendimento automatico completato con Qwen su '{topic}'. "
                f"Salvati {len(learned)} neuroni nel cervello ({summary})."
            ),
            action="auto_learning_web_qwen",
            success=True,
            latency_ms=elapsed,
            model=getattr(engine, "default_model", "qwen"),
            metadata={
                "topic": topic,
                "queries": queries,
                "learned": learned,
                "errors": errors,
                "webbridge": status,
            },
        )

    def _pick_qwen(self) -> Engine:
        probe = OllamaEngine()
        qwen_models = [m for m in probe.list_models() if "qwen" in m.lower()]
        if qwen_models:
            model = qwen_models[0]
            engine = OllamaEngine(default_model=model, keep_alive="30m")
            self._assert_qwen_ollama_only(engine)
            if engine.is_available():
                return engine
        raise RuntimeError("Ollama non espone modelli qwen")

    def _make_queries(self, engine: Engine, topic: str) -> List[str]:
        self._assert_qwen_ollama_only(engine)
        sys = "Genera 2 query web brevi in italiano. Output JSON: {\"queries\":[...]}"
        user = f"Tema:{truncate_to_budget(topic, 80)}"
        messages = [Message("system", sys), Message("user", user)]
        try:
            resp = engine.chat(messages, temperature=0.2, max_tokens=180)
            get_tracker().record(
                "qwen-auto-learning",
                input_tokens=resp.prompt_tokens or estimate_messages_tokens(messages),
                output_tokens=resp.completion_tokens or estimate_tokens(resp.text),
            )
            data = self._parse_json(resp.text)
            queries = [str(q).strip() for q in data.get("queries", []) if str(q).strip()]
        except Exception:
            queries = []
        if not queries:
            queries = [topic, f"{topic} guida"]
        return [q[:120] for q in queries[:2]]

    def _extract_facts(self, engine: Engine, topic: str, query: str, snapshot: str) -> List[Dict[str, Any]]:
        self._assert_qwen_ollama_only(engine)
        sys = (
            "Estrai solo conoscenza utile e stabile da risultati web. "
            "No pubblicità, no cookie, no frasi vaghe. Output JSON: "
            "{\"facts\":[{\"contenuto\":\"max 180 char\",\"lobo\":\"ippocampo|frontale|temporale|parietale|occipitale|cerebellum\",\"tag\":[\"...\"]}]}"
        )
        user = (
            f"TEMA:{truncate_to_budget(topic, 80)}\n"
            f"QUERY:{truncate_to_budget(query, 60)}\n"
            f"WEB:{truncate_to_budget(snapshot, 650)}"
        )
        messages = [Message("system", sys), Message("user", user)]
        try:
            resp = engine.chat(messages, temperature=0.15, max_tokens=240)
            get_tracker().record(
                "qwen-auto-learning",
                input_tokens=resp.prompt_tokens or estimate_messages_tokens(messages),
                output_tokens=resp.completion_tokens or estimate_tokens(resp.text),
            )
            data = self._parse_json(resp.text)
            facts = data.get("facts", [])
            parsed = [f for f in facts if isinstance(f, dict)]
            return parsed or self._fallback_facts(topic, query, snapshot)
        except Exception:
            return self._fallback_facts(topic, query, snapshot)

    def _fallback_facts(self, topic: str, query: str, snapshot: str) -> List[Dict[str, Any]]:
        seen = set()
        facts: List[Dict[str, Any]] = []
        bad = (
            "duckduckgo",
            "cookie",
            "privacy",
            "javascript",
            "search",
            "settings",
            "advertisement",
            "feedback",
            "images",
            "videos",
            "maps",
        )
        for raw in snapshot.splitlines():
            line = re.sub(r"\s+", " ", raw).strip(" -•\t")
            low = line.lower()
            if len(line) < 45 or len(line) > 220:
                continue
            if any(b in low for b in bad):
                continue
            key = low[:80]
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                {
                    "contenuto": line[:180],
                    "lobo": "ippocampo",
                    "tag": ["web", "fallback", topic[:24], query[:24]],
                }
            )
            if len(facts) >= 2:
                break
        return facts

    def _fetch_search_text(self, query: str, *, max_chars: int) -> Dict[str, Any]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            res = httpx.get(
                url,
                timeout=12.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 JARVISMK2/0.1",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            res.raise_for_status()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        raw = res.text
        raw = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw)
        raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</a>", "\n", raw)
        text = re.sub(r"(?s)<[^>]+>", " ", raw)
        text = unescape(text)
        lines: List[str] = []
        seen = set()
        for line in text.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            low = clean.lower()
            if len(clean) < 35 or len(clean) > 220:
                continue
            if any(b in low for b in ("duckduckgo", "privacy", "cookie", "feedback", "settings")):
                continue
            key = low[:90]
            if key in seen:
                continue
            seen.add(key)
            lines.append(clean)
            if len("\n".join(lines)) >= max_chars:
                break

        return {"ok": bool(lines), "text": "\n".join(lines)[:max_chars]}

    @staticmethod
    def _assert_qwen_ollama_only(engine: Engine) -> None:
        model = str(getattr(engine, "default_model", "") or getattr(engine, "name", "")).lower()
        engine_type = type(engine).__name__.lower()
        if "kimi" in model or "kimi" in engine_type:
            raise RuntimeError("Apprendimento bloccato: Kimi non è permesso")
        if not isinstance(engine, OllamaEngine):
            raise RuntimeError("Apprendimento bloccato: sono permessi solo modelli locali Ollama/Qwen")
        if "qwen" not in model:
            raise RuntimeError(f"Apprendimento bloccato: modello non-Qwen non permesso ({model})")

    def _save_fact(self, fact: Dict[str, Any], topic: str, query: str, source_url: str = "") -> Optional[Dict[str, Any]]:
        contenuto = str(fact.get("contenuto", "")).strip()
        if len(contenuto) < 30:
            return None
        lobo = str(fact.get("lobo", "ippocampo")).strip().lower()
        if lobo not in _VALID_LOBI:
            lobo = "ippocampo"
        tags = [str(t).strip()[:28] for t in fact.get("tag", []) if str(t).strip()]
        tags = list(dict.fromkeys(["auto-web", "qwen", topic[:28], query[:28], *tags]))[:8]
        meta: Dict[str, Any] = {"query": query}
        if source_url:
            meta["source_url"] = source_url
        nid = get_cervello().impara(
            contenuto=contenuto[:260],
            tipo="fatto_web",
            lobo=lobo,
            fonte="apprendimento_automatico_web_qwen",
            tag=tags,
            metadata=meta,
        )
        return {"id": nid, "lobo": lobo, "contenuto": contenuto[:120]}

    def queue_add(self, topic: str) -> None:
        self._queue.add(topic)

    def queue_add_many(self, topics: List[str]) -> None:
        self._queue.add_many(topics)

    def queue_list(self) -> List[Dict[str, Any]]:
        return self._queue.list()

    def queue_remove(self, idx: int) -> bool:
        return self._queue.remove(idx)

    def queue_clear(self) -> None:
        self._queue.clear()

    @staticmethod
    def _extract_topic(text: str) -> str:
        low = text.lower()
        start = -1
        for trigger in _TRIGGERS:
            idx = low.find(trigger)
            if idx != -1:
                start = idx + len(trigger)
                break
        topic = text[start:] if start != -1 else text
        topic = re.sub(r"^\s*(su|riguardo|di|per|circa|:|-)+\s*", "", topic, flags=re.I)
        topic = re.sub(r"\b(su internet|nel web|online|automatico|automaticamente)\b", "", topic, flags=re.I)
        topic = re.sub(r"\s+", " ", topic).strip(" .,:;-")
        return topic[:160] or _DEFAULT_TOPIC

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            raw = match.group(0)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
