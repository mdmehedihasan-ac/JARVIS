# JARVIS MK2

> Personal AI Assistant — fusione delle parti migliori di
> [**OpenJarvis**](https://github.com/open-jarvis/OpenJarvis) (architettura modulare local-first, agents, connettori, canali) e
> [**JARVIS**](https://github.com/mdmehedihasan-ac/JARVIS) (persona italiana, cervello a 6 lobi, voce, swarm multi-agente, auto-apprendimento).

## Filosofia

- **Local-first** — gira con Ollama sul tuo Mac (Apple Silicon ottimizzato). Cloud solo se serve.
- **Personalità italiana** — "Buongiorno, signore." Voce Alice/ElevenLabs, STT Groq Whisper IT.
- **Cervello cognitivo** — 6 lobi con neuroni che si rafforzano (Hebb) e decadono. Visualizzabile come grafo (stile Obsidian).
- **Auto-apprendimento** — pattern, correzioni, skill acquisition, prompt/routing optimization in background.
- **Multi-agente** — orchestrator + swarm CrewAI (Architetto → Sviluppatore → Revisore) con gestione VRAM "staffetta".
- **Canali** — Telegram, web chat, (estendibile a Discord/Slack/Signal/iMessage).
- **Connettori** — Obsidian (con sync automatico nei lobi del cervello), estendibili a Gmail/Notion/etc.

## Architettura

```
JARVISMK2/
├── backend/
│   └── src/jarvismk2/
│       ├── cli.py              # CLI Click (jarvis ask|chat|serve|brain|skill|...)
│       ├── server.py           # FastAPI + WebSocket per il frontend
│       ├── core/               # config, types, registry, eventbus
│       ├── brain/              # cervello a 6 lobi + auto-apprendimento (brain_v2)
│       ├── memory/             # memoria episodica con embeddings semantici
│       ├── engine/             # Ollama, Groq, OpenAI-compat
│       ├── agents/             # orchestrator, swarm CrewAI, ReAct semplice
│       ├── skills/             # sequenze nominate di tool call + match
│       ├── voice/              # ascolto (STT IT) + voce (TTS IT)
│       ├── connectors/         # Obsidian + estensioni future
│       ├── channels/           # Telegram + estensioni future
│       └── computer_use/       # controllo macOS (AppleScript, screenshot)
├── frontend/                   # React 19 + Vite + Tailwind 4 + shadcn/ui
│   └── src/
│       ├── pages/              # Chat, Brain (grafo lobi), Agents, Skills, Settings
│       ├── components/Chat/    # ChatArea, MessageBubble, InputArea, MicButton
│       ├── components/Brain/   # grafo force-directed dei lobi/neuroni
│       └── lib/                # api client + zustand store
├── pyproject.toml              # uv-based
└── .env.example
```

## Installazione

### 1. Backend (Python 3.10+)

```bash
# Installa uv se non ce l'hai
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sincronizza dipendenze (core + voice + swarm + telegram + memory)
uv sync --extra all

# Copia env
cp .env.example .env
# (apri .env e compila ciò che ti serve — è tutto opzionale)
```

### 2. Ollama (modelli locali)

```bash
# Installa Ollama: https://ollama.com
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b   # opzionale, modello "heavy"
ollama serve              # in un terminale dedicato
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev               # http://localhost:5173
```

## Comandi rapidi

```bash
# Chat one-shot
uv run jarvis ask "che ore sono?"

# REPL conversazionale
uv run jarvis chat

# Server completo (REST + WebSocket + frontend dev)
uv run jarvis serve

# Stato del cervello
uv run jarvis brain status

# Sync vault Obsidian → lobi
uv run jarvis brain sync-obsidian

# Lista skill
uv run jarvis skill list

# Esegui swarm su un task
uv run jarvis swarm run "scrivi script Python che..."

# Bot Telegram
uv run jarvis channel telegram start
```

## Crediti

- **OpenJarvis** by [@open-jarvis](https://github.com/open-jarvis) — Apache 2.0
- **JARVIS** by [@mdmehedihasan-ac](https://github.com/mdmehedihasan-ac)

Vedi `STARTUP.md` per la guida operativa completa.
