"""Swarm — CrewAI multi-agent pipeline (Architect → Developer → Reviewer).

Adapted from ``jarvis_swarm.py`` in mdmehedihasan-ac/JARVIS.  We keep the
VRAM-staffetta trick (``keep_alive=-1`` for fast model, ``keep_alive=0s`` for
heavy) so Apple Silicon 16GB stays happy.

CrewAI / LangChain are optional deps — :class:`Swarm` raises a clear
``RuntimeError`` if they aren't installed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from jarvismk2.core.config import get_config

logger = logging.getLogger(__name__)


class Swarm:
    """Three-agent CrewAI pipeline against local Ollama models."""

    def __init__(self, fast_model: Optional[str] = None, heavy_model: Optional[str] = None) -> None:
        cfg = get_config()
        self.fast_model = fast_model or cfg.ollama.model_fast
        self.heavy_model = heavy_model or cfg.ollama.model_heavy
        self.ollama_host = cfg.ollama.host
        self._crew = None  # lazy

    # ── lazy CrewAI import + setup ────────────────────────────────────
    def _build(self) -> Any:
        if self._crew is not None:
            return self._crew

        try:
            from crewai import Agent, Crew, Process, Task  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "CrewAI not installed. Run `uv sync --extra swarm`."
            ) from e
        try:
            from langchain_ollama import ChatOllama  # type: ignore
        except ImportError:
            try:
                from langchain_community.chat_models import ChatOllama  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "langchain-ollama (or langchain-community) not installed. "
                    "Run `uv sync --extra swarm`."
                ) from e

        # CrewAI hits OpenAI by default — make sure the proxy points to Ollama
        os.environ.setdefault("OPENAI_API_KEY", "sk-fake-local-only")

        cfg = get_config()
        llm_fast = ChatOllama(
            model=self.fast_model,
            base_url=self.ollama_host,
            keep_alive=cfg.ollama.keep_alive_fast,
        )
        llm_heavy = ChatOllama(
            model=self.heavy_model,
            base_url=self.ollama_host,
            keep_alive=cfg.ollama.keep_alive_heavy,
            temperature=0.1,
        )

        architetto = Agent(
            role="Software Architect",
            goal=(
                "Analizzare i requisiti dell'utente e produrre un piano d'azione "
                "dettagliato, con struttura logica, dipendenze, flusso dati, "
                "casi d'uso critici. NON scrivere codice finale."
            ),
            backstory=(
                "Architetto software con 20 anni di esperienza. "
                "Sistemi enterprise robusti e scalabili. "
                "Diagrammi dei componenti, librerie, struttura directory, "
                "task atomici per gli sviluppatori."
            ),
            llm=llm_heavy,
            verbose=False,
            allow_delegation=False,
        )
        sviluppatore = Agent(
            role="Senior Python Developer",
            goal=(
                "Prendere il piano d'azione dell'architetto e trasformarlo "
                "in codice Python production-ready, pulito, completo."
            ),
            backstory=(
                "Senior developer. Codice production-ready: type hints, "
                "docstring minimali, gestione errori robusta, no globali."
            ),
            llm=llm_fast,
            verbose=False,
            allow_delegation=False,
        )
        revisore = Agent(
            role="QA & Security Reviewer",
            goal=(
                "Analizzare il codice prodotto e trovare bug, vulnerabilità, "
                "violazioni di best practice. Restituire la versione finale corretta."
            ),
            backstory=(
                "Revisore severo. Cerca SQL injection, race condition, "
                "hardcoded secrets, mancanza di error handling, query N+1."
            ),
            llm=llm_heavy,
            verbose=False,
            allow_delegation=False,
        )

        self._architetto = architetto
        self._sviluppatore = sviluppatore
        self._revisore = revisore
        self._task_cls = Task
        self._crew_cls = Crew
        self._process = Process

        return True

    # ── run ───────────────────────────────────────────────────────────
    def run(self, task_description: str) -> str:
        self._build()
        Task = self._task_cls
        Crew = self._crew_cls
        Process = self._process

        task_arch = Task(
            description=(
                f"{task_description}\n\n"
                "FASE ARCHITETTO: produci un piano d'azione dettagliato.\n"
                "Output: lista file, librerie con versioni, schema DB (se serve), "
                "flusso dati, task atomici per lo sviluppatore."
            ),
            expected_output=(
                "Piano d'azione in italiano, strutturato, pronto per essere "
                "implementato da un senior developer."
            ),
            agent=self._architetto,
        )
        task_dev = Task(
            description=(
                "FASE SVILUPPATORE: scrivi codice Python completo seguendo il piano.\n"
                "Regole: type hints, gestione errori specifica, no f-string in SQL, "
                "credenziali da .env, requirements inline. "
                "Separa i file con marker ###FILE: nome.py."
            ),
            expected_output=(
                "Codice Python completo, production-ready, di tutti i file, "
                "separati da marker ###FILE."
            ),
            agent=self._sviluppatore,
            context=[task_arch],
        )
        task_qa = Task(
            description=(
                "FASE REVISORE: analizza il codice, correggi tutti i problemi. "
                "Verifica: secret hardcoded, query parametrizzate, gestione errori, "
                "context manager su DB, DRY, naming, test minimi. "
                "Restituisci il codice INTEGRALE corretto."
            ),
            expected_output=(
                "Codice Python finale, validato, di TUTTI i file, "
                "pronto per la produzione."
            ),
            agent=self._revisore,
            context=[task_dev],
        )

        crew = Crew(
            agents=[self._architetto, self._sviluppatore, self._revisore],
            tasks=[task_arch, task_dev, task_qa],
            process=Process.sequential,
            verbose=False,
        )
        result = crew.kickoff()
        # CrewAI 0.55+ returns a `CrewOutput`; older versions return str
        if hasattr(result, "raw"):
            return str(result.raw)
        return str(result)
