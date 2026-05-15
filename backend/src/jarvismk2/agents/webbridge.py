from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from jarvismk2.connectors.webbridge import WebBridgeConnector, get_webbridge
from jarvismk2.core.types import AgentResponse
from jarvismk2.engine.base import Message
from jarvismk2.engine.router import get_router
from jarvismk2.engine.token_budget import (
    estimate_messages_tokens,
    estimate_tokens,
    get_budget,
    get_tracker,
    truncate_to_budget,
)

_URL_RE = re.compile(r"\b((?:https?://|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/\S*)?)")
_BARE_DOMAIN_RE = re.compile(r"\b([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)(?:/\S*)?")
_WEB_HINTS = (
    "webbridge",
    "browser",
    "pagina corrente",
    "leggi la pagina",
    "riassumi la pagina",
    "apri pagina",
    "apri sito",
    "vai sul sito",
    "visita sito",
    "url",
    "tab",
    "naviga",
    "navigare",
    "apri http",
    "apri www",
    "clicca",
    "click",
    "compila",
    "scrivi nel campo",
    "leggi questa pagina",
    "leggi la pagina",
    "riassumi la pagina",
    "riassumi tab",
    "riassumi tab attivo",
    "salva pagina",
    "salva come nota",
    "estrai struttura",
    "cosa vedi",
    "cerca su",
    "cerca nel browser",
    "riproduci",
    "play",
    "youtube",
    "spotify",
    "open.spotify",
    "youtu.be",
)
_READ_HINTS = (
    "leggi",
    "riassumi",
    "estrai",
    "analizza",
    "cosa vedi",
    "trova",
    "cerca nella pagina",
)


class KimiWebBridgeAgent:
    name = "kimi_webbridge"

    def __init__(self, bridge: Optional[WebBridgeConnector] = None, max_steps: int = 3) -> None:
        self._bridge = bridge or get_webbridge()
        self._max_steps = max_steps

    @staticmethod
    def wants_webbridge(text: str) -> bool:
        low = text.lower()
        if bool(_URL_RE.search(text)):
            return True
        browser_intent = any(h in low for h in _WEB_HINTS)
        if browser_intent:
            return True
        bare_domain_intent = any(w in low for w in ("apri", "open", "vai", "naviga", "visita"))
        return bare_domain_intent and bool(_BARE_DOMAIN_RE.search(text))

    def run(self, user_input: str) -> AgentResponse:
        start = time.time()
        status = self._bridge.status()
        if not status.get("ok"):
            return AgentResponse(
                text="WebBridge non disponibile: avvia Kimi WebBridge e verifica che l'estensione browser sia connessa.",
                action="webbridge_unavailable",
                success=False,
                latency_ms=int((time.time() - start) * 1000),
                model="kimi+webbridge",
                metadata={"webbridge": status},
            )

        direct = self._try_direct(user_input)
        if direct is not None:
            direct.latency_ms = int((time.time() - start) * 1000)
            return direct

        try:
            engine = get_router().get("kimi")
            if not engine.is_available():
                raise RuntimeError("kimi non disponibile")
        except Exception as e:
            return AgentResponse(
                text=f"Kimi non disponibile per usare WebBridge: {e}",
                action="kimi_webbridge_unavailable",
                success=False,
                latency_ms=int((time.time() - start) * 1000),
                model="kimi+webbridge",
            )

        observations: List[str] = ["webbridge:ok"]
        if self._should_snapshot_first(user_input):
            snap = self._bridge.snapshot_text(max_chars=1800)
            observations.append("snapshot:" + str(snap.get("text") or snap.get("error", "")))

        last_result: Dict[str, Any] = {}
        for _ in range(self._max_steps):
            plan = self._plan(engine, user_input, observations)
            action = str(plan.get("action", "answer")).strip().lower()
            if action in {"answer", "stop"}:
                text = str(plan.get("text") or plan.get("answer") or "Fatto.").strip()
                return self._response(text, True, start, observations, last_result)
            result = self._execute(action, plan.get("args") or {})
            last_result = result
            observations.append(f"{action}:{self._obs_text(result)}")
            if action in {"navigate", "find_tab", "click", "fill"} and self._should_snapshot_after(user_input):
                snap = self._bridge.snapshot_text(max_chars=1800)
                observations.append("snapshot:" + str(snap.get("text") or snap.get("error", "")))

        text = self._final_answer(engine, user_input, observations)
        return self._response(text, True, start, observations, last_result)

    def _try_direct(self, text: str) -> Optional[AgentResponse]:
        low = text.lower()
        if "status" in low and "webbridge" in low:
            return AgentResponse(
                text=json.dumps(self._bridge.status(force=True), ensure_ascii=False),
                action="webbridge_status",
                success=True,
                model="webbridge",
            )
        if "lista" in low and "tab" in low:
            res = self._bridge.command("list_tabs", max_chars=1600)
            return AgentResponse(
                text=self._obs_text(res),
                action="webbridge_list_tabs",
                success=bool(res.get("ok")),
                model="webbridge",
                metadata={"result": res},
            )

        # ── riassumi tab attivo ───────────────────────────────────────
        if any(p in low for p in ("riassumi tab attivo", "riassumi tab", "riassumi la pagina", "riassumi pagina")):
            return self._summarize_active_tab(text)

        # ── salva pagina come nota Obsidian ───────────────────────────
        if any(p in low for p in ("salva pagina", "salva come nota", "salva in obsidian")):
            return self._save_page_as_note()

        # ── estrai struttura ──────────────────────────────────────────
        if "estrai struttura" in low:
            return self._extract_structure()

        media = self._try_media_direct(text)
        if media is not None:
            return media
        url = self._extract_url(text)
        simple_open = any(w in low for w in ("apri", "open", "vai", "naviga"))
        needs_read = any(w in low for w in _READ_HINTS)
        if url and simple_open and not needs_read and "clic" not in low and "compila" not in low:
            res = self._bridge.command(
                "navigate",
                {"url": url, "newTab": True, "group_title": "JARVIS"},
                max_chars=700,
            )
            ok = bool(res.get("ok"))
            return AgentResponse(
                text=f"Pagina aperta: {url}" if ok else f"Non riesco ad aprire {url}: {res.get('error') or res.get('data')}",
                action="webbridge_navigate",
                success=ok,
                model="webbridge",
                metadata={"result": res},
            )
        return None

    def _summarize_active_tab(self, user_input: str) -> AgentResponse:
        snap = self._bridge.command("find_tab", {"active": True}, max_chars=400)
        page_url = ""
        if snap.get("ok"):
            page_url = str((snap.get("data") or {}).get("url", ""))
        text_snap = self._bridge.snapshot_text(max_chars=2800)
        text = str(text_snap.get("text", ""))
        if not text:
            return AgentResponse(
                text="Nessun testo leggibile nella tab attiva.",
                action="webbridge_summarize_tab",
                success=False,
                model="webbridge",
            )
        try:
            from jarvismk2.engine.router import get_router
            engine = get_router().get("kimi")
            if not engine.is_available():
                raise RuntimeError("kimi non disponibile")
            from jarvismk2.engine.base import Message as Msg
            from jarvismk2.engine.token_budget import truncate_to_budget as _trunc
            msgs = [
                Msg("system", "Sei JARVIS. Riassumi in italiano la pagina web in 3-5 punti chiave, concisi."),
                Msg("user", f"URL:{page_url}\n\n{_trunc(text, 1800)}"),
            ]
            resp = engine.chat(msgs, temperature=0.2, max_tokens=400)
            return AgentResponse(
                text=resp.text.strip(),
                action="webbridge_summarize_tab",
                success=True,
                model="kimi+webbridge",
                metadata={"url": page_url},
            )
        except Exception as e:
            short = text[:800].strip()
            return AgentResponse(
                text=f"[Riepilogo locale]\n{short}\n\n(Kimi non disponibile: {e})",
                action="webbridge_summarize_tab",
                success=True,
                model="webbridge",
                metadata={"url": page_url},
            )

    def _save_page_as_note(self) -> AgentResponse:
        snap = self._bridge.snapshot_text(max_chars=6000)
        text = str(snap.get("text", ""))
        tab_info = self._bridge.command("find_tab", {"active": True}, max_chars=400)
        page_url = str((tab_info.get("data") or {}).get("url", ""))
        page_title = str((tab_info.get("data") or {}).get("title", "pagina_web"))[:80]
        if not text:
            return AgentResponse(
                text="Nessun contenuto nella pagina da salvare.",
                action="webbridge_save_note",
                success=False,
                model="webbridge",
            )
        try:
            from jarvismk2.connectors.obsidian import ObsidianConnector
            conn = ObsidianConnector()
            result = conn.write_note(
                title=page_title,
                content=text,
                subdir="web",
                tags=["web", "auto"],
                source_url=page_url,
            )
            if result.get("ok"):
                return AgentResponse(
                    text=f"Pagina salvata in Obsidian: {result['title']} ({result['path']})",
                    action="webbridge_save_note",
                    success=True,
                    model="webbridge",
                    metadata=result,
                )
            return AgentResponse(
                text=f"Salvataggio fallito: {result.get('error', 'vault non configurato')}",
                action="webbridge_save_note",
                success=False,
                model="webbridge",
            )
        except Exception as e:
            return AgentResponse(
                text=f"Errore nel salvataggio: {e}",
                action="webbridge_save_note",
                success=False,
                model="webbridge",
            )

    def _extract_structure(self) -> AgentResponse:
        snap = self._bridge.snapshot_text(max_chars=4000)
        text = str(snap.get("text", ""))
        if not text:
            return AgentResponse(
                text="Nessun contenuto disponibile.",
                action="webbridge_extract_structure",
                success=False,
                model="webbridge",
            )
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        headings = [l for l in lines if l.startswith(("#", "##", "###")) or (len(l) < 80 and l.isupper())]
        result = "\n".join(headings[:40]) if headings else "\n".join(lines[:30])
        return AgentResponse(
            text=f"Struttura della pagina:\n{result}",
            action="webbridge_extract_structure",
            success=True,
            model="webbridge",
        )

    def _try_media_direct(self, text: str) -> Optional[AgentResponse]:
        low = text.lower()
        if "youtube" in low or "youtu.be" in low:
            query = self._extract_search_query(text, "youtube")
            url = "https://www.youtube.com"
            if query:
                url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            res = self._bridge.command(
                "navigate",
                {"url": url, "newTab": True, "group_title": "JARVIS"},
                max_chars=700,
            )
            ok = bool(res.get("ok"))
            played = None
            if ok and any(w in low for w in ("riproduci", "play", "avvia")):
                time.sleep(2.0)
                played = self._bridge.command(
                    "evaluate",
                    {"code": "(()=>{const a=[...document.querySelectorAll('a#video-title,a[href^=\"/watch\"]')].find(x=>x.href&&x.href.includes('/watch'));if(a){a.click();return {clicked:true,href:a.href,text:(a.textContent||'').trim().slice(0,120)}}return {clicked:false}})()"},
                    max_chars=700,
                )
            action = "webbridge_youtube_play" if played else "webbridge_youtube"
            msg = "YouTube aperto"
            if query:
                msg += f" con ricerca: {query}"
            if played:
                msg += ". Ho provato ad avviare il primo risultato."
            return AgentResponse(
                text=msg if ok else f"Non riesco ad aprire YouTube: {res.get('error') or res.get('data')}",
                action=action,
                success=ok,
                model="webbridge",
                metadata={"navigate": res, "play": played},
            )

        if "spotify" in low or "open.spotify" in low:
            query = self._extract_search_query(text, "spotify")
            url = "https://open.spotify.com"
            if query:
                url = f"https://open.spotify.com/search/{quote_plus(query)}"
            res = self._bridge.command(
                "navigate",
                {"url": url, "newTab": True, "group_title": "JARVIS"},
                max_chars=700,
            )
            ok = bool(res.get("ok"))
            msg = "Spotify aperto"
            if query:
                msg += f" con ricerca: {query}"
            return AgentResponse(
                text=msg if ok else f"Non riesco ad aprire Spotify: {res.get('error') or res.get('data')}",
                action="webbridge_spotify",
                success=ok,
                model="webbridge",
                metadata={"navigate": res},
            )
        return None

    def _plan(self, engine: Any, user_input: str, observations: List[str]) -> Dict[str, Any]:
        budget = get_budget("kimi")
        obs = truncate_to_budget("\n".join(observations[-4:]), 450)
        sys = (
            "Sei Kimi con WebBridge. Output SOLO JSON. "
            "Azioni: navigate,args{url,newTab}; find_tab,args{url,active}; snapshot,args{}; "
            "click,args{selector}; fill,args{selector,value}; list_tabs,args{}; answer,args{text}. "
            "Usa @e dal snapshot. Max 1 azione. Niente screenshot/base64."
        )
        user = f"REQ:{truncate_to_budget(user_input, 160)}\nOBS:{obs}"
        messages = [Message("system", sys), Message("user", user)]
        resp = engine.chat(messages, temperature=0.1, max_tokens=min(220, budget.max_output))
        get_tracker().record(
            "kimi-webbridge",
            input_tokens=resp.prompt_tokens or estimate_messages_tokens(messages),
            output_tokens=resp.completion_tokens or estimate_tokens(resp.text),
        )
        return self._parse_plan(resp.text)

    def _final_answer(self, engine: Any, user_input: str, observations: List[str]) -> str:
        obs = truncate_to_budget("\n".join(observations[-5:]), 650)
        messages = [
            Message("system", "Rispondi in italiano, breve. Usa solo OBS. Se manca info, dillo."),
            Message("user", f"REQ:{truncate_to_budget(user_input, 180)}\nOBS:{obs}"),
        ]
        resp = engine.chat(messages, temperature=0.2, max_tokens=360)
        get_tracker().record(
            "kimi-webbridge",
            input_tokens=resp.prompt_tokens or estimate_messages_tokens(messages),
            output_tokens=resp.completion_tokens or estimate_tokens(resp.text),
        )
        return resp.text.strip() or "Fatto."

    def _execute(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if action == "snapshot":
            return self._bridge.snapshot_text(max_chars=1800)
        return self._bridge.command(action, args, max_chars=1400)

    def _response(
        self,
        text: str,
        ok: bool,
        start: float,
        observations: List[str],
        last_result: Dict[str, Any],
    ) -> AgentResponse:
        return AgentResponse(
            text=text,
            action="kimi_webbridge",
            success=ok,
            latency_ms=int((time.time() - start) * 1000),
            model="kimi+webbridge",
            metadata={
                "steps": len(observations),
                "last_result": last_result,
                "tokens_optimized": True,
            },
        )

    @staticmethod
    def _parse_plan(text: str) -> Dict[str, Any]:
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            raw = match.group(0)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"action": "answer", "text": text.strip()[:800]}

    @staticmethod
    def _extract_url(text: str) -> str:
        m = _URL_RE.search(text)
        if not m:
            low = text.lower()
            if not any(w in low for w in ("apri", "open", "vai", "naviga", "visita")):
                return ""
            m = _BARE_DOMAIN_RE.search(text)
        if not m:
            return ""
        url = m.group(1).rstrip(".,;)")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    @staticmethod
    def _extract_search_query(text: str, service: str) -> str:
        low = text.lower()
        q = ""
        if "cerca" in low:
            q = text[low.index("cerca") + len("cerca"):]
        elif "search" in low:
            q = text[low.index("search") + len("search"):]
        if not q:
            return ""
        q = re.split(r"\be\s+(?:riproduci|play|avvia|apri)\b", q, maxsplit=1, flags=re.I)[0]
        q = re.sub(rf"\b(?:su|in|nel|nella)?\s*{re.escape(service)}\b.*$", "", q, flags=re.I)
        q = re.sub(r"\b(?:il|la|lo|un|una|uno)\s+(?:primo|prima)\b", "", q, flags=re.I)
        q = re.sub(r"^\s*(?:un|una|uno|il|la|lo)\s+", "", q, flags=re.I)
        q = re.sub(r"^\s*(?:video|canzone|brano|musica)\s+(?:di\s+)?", "", q, flags=re.I)
        q = re.sub(r"\s+", " ", q).strip(" .,:;")
        return q[:120]

    @staticmethod
    def _should_snapshot_first(text: str) -> bool:
        low = text.lower()
        return any(w in low for w in _READ_HINTS) or "clic" in low or "compila" in low

    @staticmethod
    def _should_snapshot_after(text: str) -> bool:
        low = text.lower()
        return any(w in low for w in _READ_HINTS) or "clic" in low or "compila" in low

    @staticmethod
    def _obs_text(result: Dict[str, Any]) -> str:
        if "text" in result:
            return str(result["text"])
        if "error" in result:
            return str(result["error"])
        return json.dumps(result.get("data", result), ensure_ascii=False)[:1600]
