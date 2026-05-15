# JARVIS MK2 — Guida operativa

Fusione di [`open-jarvis/OpenJarvis`](https://github.com/open-jarvis/OpenJarvis) e
[`mdmehedihasan-ac/JARVIS`](https://github.com/mdmehedihasan-ac/JARVIS).

## 1. Prerequisiti

- **macOS** (consigliato: Apple Silicon 16 GB+), Linux o WSL2
- **Python ≥ 3.10** (consigliato 3.11 / 3.12)
- **Node ≥ 20**
- **[Ollama](https://ollama.com)** per i modelli locali (opzionale, ma è la modalità di default)
- (Opzionale) Chiavi API per: Groq (STT), ElevenLabs (TTS), Gemini (embeddings), OpenAI / Anthropic (cloud fallback), Telegram (canale)

## 2. Setup backend

```bash
cd ~/JARVISMK2

# Installa uv se non lo hai
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sincronizza tutte le dipendenze opzionali utili
uv sync --extra all
# o, minimal core: uv sync

# Configura
cp .env.example .env
# Modifica .env: percorso Obsidian, chiavi API, wake words, etc.
```

## 3. Ollama (modelli locali)

```bash
# Installa Ollama da https://ollama.com poi:
ollama pull qwen2.5:7b        # fast
ollama pull qwen2.5:14b       # heavy (per lo swarm)
ollama serve                  # tenere acceso in un terminale dedicato
```

## 4. Setup frontend

```bash
cd ~/JARVISMK2/frontend
npm install
```

## 5. Avvio

### A — Tutto-in-uno (terminali separati)

**Terminal 1 — Backend:**
```bash
cd ~/JARVISMK2
uv run jarvis serve
# → http://127.0.0.1:8765
```

**Terminal 2 — Frontend:**
```bash
cd ~/JARVISMK2/frontend
npm run dev
# → http://localhost:5173
```

Apri il browser su <http://localhost:5173>. Vedrai la chat con la persona italiana, il grafo del cervello, le skill, gli agenti, le impostazioni.

### B — Solo CLI

```bash
uv run jarvis doctor                # diagnosi
uv run jarvis chat                  # REPL conversazionale
uv run jarvis ask "che ore sono?"   # one-shot
uv run jarvis brain status          # stato lobi
uv run jarvis brain sync-obsidian   # importa vault Obsidian nei lobi
uv run jarvis skill list            # skill disponibili
uv run jarvis swarm "scrivi script Python che..."  # CrewAI
uv run jarvis channel telegram      # bot Telegram (richiede token)
uv run jarvis listen                # voce: ascolto + risposta + TTS
```

## 6. Endpoint principali (REST + WS)

| Metodo | Path | Descrizione |
|---|---|---|
| `GET` | `/api/health` | stato + engines disponibili |
| `GET` | `/api/config` | configurazione corrente |
| `POST` | `/api/chat` | one-shot non streaming |
| `WS` | `/ws/chat` | streaming token-by-token |
| `WS` | `/ws/events` | event bus (brain, voice, channels) |
| `GET` | `/api/brain/status` | stato 6 lobi |
| `GET` | `/api/brain/graph` | grafo force-directed |
| `POST` | `/api/brain/sync-obsidian` | reimporta vault |
| `GET` | `/api/episodic/stats` | stats memoria episodica |
| `GET` | `/api/skills` | lista skill |
| `POST` | `/api/skills/{nome}/run` | esegui skill |
| `GET` | `/api/learning/status` | dashboard apprendimento |

## 7. Architettura, in breve

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND  (React 19 + Vite + Tailwind 4)                        │
│  Pagine: Chat · Cervello (grafo) · Skills · Agenti · Settings    │
└────────────────────────────┬─────────────────────────────────────┘
              REST + WebSocket │
┌────────────────────────────▼─────────────────────────────────────┐
│  BACKEND  (FastAPI + Click)                                       │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  ORCHESTRATOR                                              │   │
│  │   1. Skill match  → SkillsManager.esegui()                 │   │
│  │   2. /swarm o intent codice → Swarm CrewAI                 │   │
│  │   3. Default → SimpleAgent (Brain + Episodic context)      │   │
│  └────┬──────────────────┬──────────────────┬─────────────────┘   │
│       │                  │                  │                     │
│  ┌────▼─────┐  ┌─────────▼──────┐  ┌────────▼───────┐            │
│  │ CERVELLO │  │ EPISODIC MEM   │  │ LEARNING (v2)  │            │
│  │ 6 lobi   │  │ JSON-L + embed │  │ pattern, skill │            │
│  │ Hebb     │  │ Gemini opzion. │  │ acquisition,   │            │
│  │ + decay  │  │                │  │ routing weights│            │
│  └──────────┘  └────────────────┘  └────────────────┘            │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐    │
│  │ ENGINES      │  │ VOICE        │  │ CHANNELS            │    │
│  │ Ollama +     │  │ Ascolto (IT) │  │ Telegram            │    │
│  │ Groq/OpenAI  │  │ Voce (Alice/ │  │ (long polling)      │    │
│  │ fallback     │  │  ElevenLabs) │  │                     │    │
│  └──────────────┘  └──────────────┘  └─────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ CONNECTORS:  Obsidian vault → sync nei lobi del cervello │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## 8. Cosa abbiamo preso dai due progetti

**Da OpenJarvis** *(`open-jarvis/OpenJarvis`)*:
- Architettura modulare `agents / skills / connectors / channels / engine`
- CLI Click ricca, FastAPI server, WebSocket
- `Registry`, `EventBus`, telegram channel polished, Obsidian scanner
- Tooling: `uv`, `ruff`, `pyproject.toml` pulito

**Da JARVIS (mdmehedihasan)** *(`mdmehedihasan-ac/JARVIS`)*:
- Persona italiana, voce Alice/ElevenLabs, ascolto Groq Whisper IT
- **Cervello a 6 lobi** con neuroni Hebbiani e grafo force-directed
- **Brain v2**: auto-apprendimento, pattern, skill acquisition, routing weights
- **Memoria episodica** con embeddings Gemini
- **Swarm CrewAI**: Architetto → Sviluppatore → Revisore + staffetta VRAM
- Skill come sequenze nominate di tool call con trigger keywords
- Obsidian → sync diretto nei lobi (clienti, errori_risolti, sessioni)

## 9. Storage

Tutto sotto `~/.jarvismk2/`:

```
~/.jarvismk2/
├── cervello.json             # stato dei 6 lobi
├── learning_state.json       # brain v2 (skill acquisite, pattern, weights)
├── skills.json               # skill custom
└── memory/
    ├── episodes.jsonl        # log episodi append-only
    └── episodes_embeddings.json
```

## 10. Estendere

- **Nuovo canale** → `backend/src/jarvismk2/channels/<nome>.py` (segui `telegram.py`)
- **Nuovo connettore** → `backend/src/jarvismk2/connectors/<nome>.py` (segui `obsidian.py`)
- **Nuovo agente** → `backend/src/jarvismk2/agents/<nome>.py`, registralo in `orchestrator.py`
- **Nuovo engine** → `backend/src/jarvismk2/engine/<nome>.py`, aggiungilo in `router.py`
- **Nuova skill** → API `POST /api/skills` o `~/.jarvismk2/skills.json` direttamente
- **Nuova pagina UI** → `frontend/src/pages/`, aggiungi rotta in `App.tsx` e voce in `Layout.tsx`

## 11. Troubleshooting

- `jarvis doctor` mostra cosa funziona e cosa manca
- Backend non si avvia → controlla `uv run python -c "import jarvismk2"` e `pip` deps
- Frontend bianco → `npm run build` e controlla console del browser
- Ollama irraggiungibile → `curl http://localhost:11434/api/tags`
- WebSocket non si connette → controlla che il backend stia girando e che `JARVIS_PORT` nel `.env` corrisponda al proxy di Vite (default 8765)
- Voce non parla → su macOS, prova `say -v Alice "test"`; se vuoi qualità, configura `ELEVENLABS_API_KEY`

## 12. Crediti

- **OpenJarvis** — Apache 2.0, by [open-jarvis](https://github.com/open-jarvis)
- **JARVIS** — by [mdmehedihasan-ac](https://github.com/mdmehedihasan-ac)
- **MK2 mix** — by [Giacomo Tronconi](https://github.com/giacomotronconi)

Buon lavoro, signore. 🛰️
