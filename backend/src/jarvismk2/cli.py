"""Click-based CLI: ``jarvis ask | chat | serve | brain | skill | swarm | channel | doctor``."""

from __future__ import annotations

import json
import logging
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jarvismk2 import __version__

console = Console()


# ── lazy imports (so `jarvis --help` is fast) ─────────────────────────────
def _orchestrator():
    from jarvismk2.agents.orchestrator import get_orchestrator

    return get_orchestrator()


def _cervello():
    from jarvismk2.brain.cervello import get_cervello

    return get_cervello()


def _episodic():
    from jarvismk2.brain.episodic import get_episodic

    return get_episodic()


def _skills():
    from jarvismk2.skills.manager import get_skills_manager

    return get_skills_manager()


def _router():
    from jarvismk2.engine.router import get_router

    return get_router()


def _cfg():
    from jarvismk2.core.config import get_config

    return get_config()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── root ─────────────────────────────────────────────────────────────────
@click.group(invoke_without_command=True)
@click.option("--log-level", default=None, help="DEBUG | INFO | WARNING | ERROR")
@click.version_option(__version__, prog_name="jarvis")
@click.pass_context
def main(ctx: click.Context, log_level: Optional[str]) -> None:
    """JARVIS MK2 — Personal AI Assistant."""
    _setup_logging(log_level or _cfg().log_level)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── ask ──────────────────────────────────────────────────────────────────
@main.command()
@click.argument("question", nargs=-1, required=True)
@click.option("--prefer", default=None, help="Force a routing path: simple | swarm")
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
def ask(question: tuple[str, ...], prefer: Optional[str], no_stream: bool) -> None:
    """Single-shot question."""
    text = " ".join(question)
    orch = _orchestrator()

    if no_stream:
        resp = orch.run(text, prefer=prefer)
        console.print(resp.text)
        console.print(
            f"[dim](engine: {resp.metadata.get('engine', resp.model)} | "
            f"latency: {resp.latency_ms} ms)[/dim]"
        )
        return

    try:
        for chunk in orch.stream(text):
            sys.stdout.write(chunk)
            sys.stdout.flush()
        sys.stdout.write("\n")
    except RuntimeError as e:
        console.print(f"[red]Errore:[/red] {e}")
        sys.exit(1)


# ── chat (REPL) ──────────────────────────────────────────────────────────
@main.command()
def chat() -> None:
    """Interactive REPL."""
    cfg = _cfg()
    orch = _orchestrator()
    console.print(
        Panel.fit(
            f"[bold cyan]{cfg.persona.name}[/bold cyan] — al suo servizio, {cfg.persona.user_name}.\n"
            "[dim]/quit per uscire, /swarm <task> per usare il team multi-agente[/dim]",
            border_style="cyan",
        )
    )
    history = []
    while True:
        try:
            user = console.input("[bold green]>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Buona giornata, signore.[/dim]")
            break
        if not user:
            continue
        if user in {"/quit", "/exit", "/bye"}:
            console.print("[dim]Buona giornata, signore.[/dim]")
            break

        from jarvismk2.core.types import ChatMessage

        history.append(ChatMessage(role="user", content=user))
        accumulated = ""
        try:
            for chunk in orch.stream(user, history=history[:-1]):
                accumulated += chunk
                sys.stdout.write(chunk)
                sys.stdout.flush()
            sys.stdout.write("\n")
        except RuntimeError as e:
            console.print(f"[red]Errore:[/red] {e}")
            continue
        history.append(ChatMessage(role="assistant", content=accumulated))


# ── serve ────────────────────────────────────────────────────────────────
@main.command()
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
@click.option("--reload", is_flag=True, help="Auto-reload on file changes (dev)")
def serve(host: Optional[str], port: Optional[int], reload: bool) -> None:
    """Run the FastAPI server (REST + WebSocket)."""
    import uvicorn

    cfg = _cfg()
    h = host or cfg.server.host
    p = port or cfg.server.port
    console.print(
        Panel.fit(
            f"[bold cyan]JARVIS MK2[/bold cyan] in ascolto su [bold]http://{h}:{p}[/bold]\n"
            f"Frontend atteso su [bold]{cfg.server.frontend_origin}[/bold]\n"
            "[dim]Endpoint principali: /api/health, /api/chat, /ws/chat, /ws/events[/dim]",
            border_style="cyan",
        )
    )
    uvicorn.run(
        "jarvismk2.server:app",
        host=h,
        port=p,
        reload=reload,
        log_level=cfg.log_level.lower(),
    )


# ── doctor ───────────────────────────────────────────────────────────────
@main.command()
def doctor() -> None:
    """Health check: env + engines + data dir."""
    cfg = _cfg()
    r = _router()
    available = r.available()
    table = Table(title="JARVIS MK2 — Doctor", show_lines=True)
    table.add_column("Componente", style="cyan")
    table.add_column("Stato")
    table.add_column("Dettagli", style="dim")

    table.add_row("Versione", "ok", __version__)
    table.add_row("Persona", "ok", f"{cfg.persona.name} / lang={cfg.persona.lang}")
    table.add_row("Data dir", "ok", str(cfg.data_dir))

    for name, ok in available.items():
        table.add_row(
            f"Engine: {name}",
            "[green]ready[/green]" if ok else "[yellow]non disponibile[/yellow]",
            cfg.ollama.host if name.startswith("ollama") else "",
        )

    table.add_row(
        "Groq STT",
        "[green]ready[/green]" if cfg.cloud.groq else "[yellow]GROQ_API_KEY mancante[/yellow]",
        "",
    )
    table.add_row(
        "ElevenLabs TTS",
        "[green]ready[/green]" if cfg.cloud.elevenlabs else "[yellow]fallback macOS say[/yellow]",
        "",
    )
    table.add_row(
        "Obsidian",
        "[green]ready[/green]" if cfg.obsidian.is_configured else "[yellow]non configurato[/yellow]",
        cfg.obsidian.vault_path or "—",
    )
    table.add_row(
        "Telegram",
        "[green]ready[/green]" if cfg.telegram.bot_token else "[yellow]non configurato[/yellow]",
        "",
    )

    console.print(table)


# ── brain group ──────────────────────────────────────────────────────────
@main.group()
def brain() -> None:
    """Cervello a 6 lobi + memoria episodica."""


@brain.command("status")
def brain_status() -> None:
    stato = _cervello().stato()
    table = Table(title="Cervello — stato lobi", show_lines=True)
    table.add_column("Lobo", style="cyan")
    table.add_column("Funzione", style="dim")
    table.add_column("Neuroni", justify="right")
    table.add_column("Carico", justify="right")
    for nome, lobo in stato["lobi"].items():
        table.add_row(
            nome.upper(),
            lobo["funzione"][:50],
            str(lobo["neuroni"]),
            f"{lobo['carico']:.2f}",
        )
    console.print(table)
    console.print(f"[dim]Totale neuroni: {stato['totale_neuroni']}[/dim]")


@brain.command("graph")
@click.option("--out", default=None, help="Save JSON to this file")
def brain_graph_cmd(out: Optional[str]) -> None:
    g = _cervello().grafo()
    if out:
        from pathlib import Path

        Path(out).write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]Grafo salvato in {out}[/green]")
    else:
        console.print_json(json.dumps(g))


@brain.command("learn")
@click.argument("contenuto")
@click.option("--tipo", default="fatto", show_default=True)
@click.option(
    "--lobo",
    type=click.Choice(["frontale", "temporale", "parietale", "occipitale", "cerebellum", "ippocampo"]),
    default="temporale",
    show_default=True,
)
@click.option("--tag", multiple=True)
def brain_learn_cmd(contenuto: str, tipo: str, lobo: str, tag: tuple[str, ...]) -> None:
    nid = _cervello().impara(contenuto=contenuto, tipo=tipo, lobo=lobo, tag=list(tag))
    console.print(f"[green]Neurone creato:[/green] {nid}")


@brain.command("sync-obsidian")
def brain_sync_obsidian() -> None:
    from jarvismk2.connectors.obsidian import ObsidianConnector

    conn = ObsidianConnector()
    if not conn.is_configured():
        console.print("[yellow]OBSIDIAN_VAULT_PATH non configurato in .env[/yellow]")
        return
    added = conn.sync_to_brain()
    console.print(f"[green]Sincronizzati {added} neuroni dal vault Obsidian[/green]")


@brain.command("episodic")
@click.argument("query", nargs=-1, required=False)
@click.option("--top-k", default=5, show_default=True)
def brain_episodic(query: tuple[str, ...], top_k: int) -> None:
    mem = _episodic()
    if not query:
        console.print_json(json.dumps(mem.stats()))
        return
    q = " ".join(query)
    block = mem.render_prompt_block(q, top_k=top_k)
    console.print(block or "[dim]Nessun episodio rilevante[/dim]")


# ── skill group ──────────────────────────────────────────────────────────
@main.group()
def skill() -> None:
    """Skill — sequenze nominate di tool call."""


@skill.command("list")
def skill_list() -> None:
    table = Table(title="Skills disponibili", show_lines=True)
    table.add_column("Nome", style="cyan")
    table.add_column("Descrizione", style="dim")
    table.add_column("Trigger", style="green")
    table.add_column("Step", justify="right")
    for s in _skills().list():
        table.add_row(
            s["nome"],
            (s.get("descrizione") or "")[:60],
            ", ".join(s.get("trigger_keywords", []) or [])[:60],
            str(len(s.get("azioni", []))),
        )
    console.print(table)


@skill.command("run")
@click.argument("nome")
def skill_run(nome: str) -> None:
    res = _skills().esegui(nome)
    console.print_json(json.dumps(res, ensure_ascii=False))


@skill.command("delete")
@click.argument("nome")
def skill_delete(nome: str) -> None:
    ok = _skills().delete(nome)
    console.print(f"[{'green' if ok else 'red'}]ok={ok}[/]")


# ── swarm ────────────────────────────────────────────────────────────────
@main.command()
@click.argument("task", nargs=-1, required=True)
def swarm(task: tuple[str, ...]) -> None:
    """Esegue il team CrewAI (Architetto → Sviluppatore → Revisore)."""
    from jarvismk2.agents.swarm import Swarm

    desc = " ".join(task)
    try:
        out = Swarm().run(desc)
    except RuntimeError as e:
        console.print(f"[red]Swarm non disponibile:[/red] {e}")
        sys.exit(1)
    console.print(Panel(out, title="Risultato Swarm", border_style="cyan"))


# ── channel group ────────────────────────────────────────────────────────
@main.group()
def channel() -> None:
    """Canali di I/O (Telegram, …)."""


@channel.command("telegram")
@click.option("--once", is_flag=True, help="Blocca finché non interrotto (Ctrl+C)")
def channel_telegram(once: bool) -> None:
    """Avvia il bot Telegram con orchestrator."""
    from jarvismk2.channels.telegram import make_telegram_bot_orchestrator_glue

    chan = make_telegram_bot_orchestrator_glue()
    if not chan:
        console.print("[yellow]TELEGRAM_BOT_TOKEN non configurato[/yellow]")
        sys.exit(1)
    chan.start()
    console.print("[green]Bot Telegram avviato.[/green]")
    if once:
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            chan.stop()
            console.print("[dim]Telegram channel fermato.[/dim]")


# ── voice ────────────────────────────────────────────────────────────────
@main.command()
@click.option("--wake", multiple=True, help="Override wake words")
def listen(wake: tuple[str, ...]) -> None:
    """Avvia ascolto continuo: wake word + STT IT + orchestrator + TTS."""
    from jarvismk2.voice.ascolto import Ascolto
    from jarvismk2.voice.voce import Voce

    voce = Voce()
    orch = _orchestrator()

    def _on_cmd(text: str) -> None:
        console.print(f"[cyan]Comando:[/cyan] {text}")
        try:
            resp = orch.run(text)
        except RuntimeError as e:
            console.print(f"[red]Errore engine:[/red] {e}")
            return
        console.print(f"[green]{resp.text}[/green]")
        voce.parla(resp.text)

    a = Ascolto(on_command=_on_cmd, wake_words=list(wake) or None)
    a.start()
    voce.parla("Sistemi online. Pronto, signore.")
    console.print(
        "[cyan]Ascolto attivo.[/cyan] Wake words: "
        + ", ".join(a._wake_words)  # pyright: ignore[reportPrivateUsage]
        + "  (Ctrl+C per fermare)"
    )
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        a.stop()
        voce.stop()
        console.print("[dim]Ascolto terminato.[/dim]")
