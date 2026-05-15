import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Bot, Brain, GraduationCap, Workflow } from 'lucide-react';

interface LearningStatus {
  skills_acquired: number;
  patterns_detected: number;
  interactions_logged: boolean;
  routing_weights: Record<string, number>;
  background_running: boolean;
}

export function AgentsPage() {
  const [learning, setLearning] = useState<LearningStatus | null>(null);
  const [episodicStats, setEpisodicStats] = useState<{
    totale_episodi: number;
    con_embedding: number;
    max: number;
  } | null>(null);

  useEffect(() => {
    api.learning.status().then((s) => setLearning(s as unknown as LearningStatus)).catch(() => {});
    api.episodic.stats().then(setEpisodicStats).catch(() => {});
  }, []);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <header className="border-b border-zinc-800/80 px-6 py-3 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
        <h1 className="text-sm font-semibold tracking-tight">Agenti</h1>
        <p className="text-[11px] text-zinc-500">
          Architettura multi-agente · orchestrator + swarm + auto-apprendimento
        </p>
      </header>

      <div className="px-6 py-6 space-y-6 max-w-5xl mx-auto w-full">
        {/* Orchestrator */}
        <AgentCard
          icon={<Bot className="w-5 h-5" />}
          color="#00d4ff"
          name="Orchestrator"
          subtitle="Routing principale"
          desc="Decide tra skill match, swarm multi-agente e chat semplice. Esegue il pre-routing e arricchisce il prompt con cervello + episodi."
        >
          <div className="text-xs text-zinc-500 space-y-1">
            <div>
              <span className="text-zinc-300">Skill match:</span> auto via
              trigger keywords
            </div>
            <div>
              <span className="text-zinc-300">Swarm trigger:</span> "scrivi
              codice", "sviluppa", "/swarm ..."
            </div>
            <div>
              <span className="text-zinc-300">Default:</span> SimpleAgent +
              cervello + episodic memory
            </div>
          </div>
        </AgentCard>

        {/* Swarm */}
        <AgentCard
          icon={<Workflow className="w-5 h-5" />}
          color="#7b2fff"
          name="Swarm (CrewAI)"
          subtitle="Architetto → Sviluppatore → Revisore"
          desc="Pipeline sequenziale di 3 agenti CrewAI con Ollama locale. Staffetta VRAM: qwen2.5:14b heavy (keep_alive=0s) + qwen2.5:7b fast (keep_alive=-1)."
        >
          <ol className="text-xs text-zinc-400 space-y-1 list-decimal pl-4">
            <li>
              <b>Architetto</b> (heavy) — produce piano d'azione strutturato
            </li>
            <li>
              <b>Sviluppatore</b> (fast) — scrive codice production-ready
            </li>
            <li>
              <b>Revisore</b> (heavy) — analizza, corregge, restituisce versione finale
            </li>
          </ol>
        </AgentCard>

        {/* Brain / Cervello */}
        <AgentCard
          icon={<Brain className="w-5 h-5" />}
          color="#ff2d55"
          name="Cervello a 6 Lobi"
          subtitle="Memoria cognitiva + episodi"
          desc="6 lobi (Frontale, Temporale, Parietale, Occipitale, Cervelletto, Ippocampo) con neuroni Hebbiani: rinforzo per uso, decadimento nel tempo, sync da Obsidian."
        >
          <div className="grid grid-cols-2 gap-2 text-xs text-zinc-400">
            <Stat
              label="Episodi salvati"
              value={
                episodicStats ? `${episodicStats.totale_episodi}/${episodicStats.max}` : '—'
              }
            />
            <Stat
              label="Con embedding"
              value={episodicStats ? `${episodicStats.con_embedding}` : '—'}
            />
          </div>
        </AgentCard>

        {/* Learning */}
        <AgentCard
          icon={<GraduationCap className="w-5 h-5" />}
          color="#ffcc00"
          name="Auto-Apprendimento (Brain v2)"
          subtitle="Pattern, correzioni, skill acquisition, routing"
          desc="Loop in background ogni 5 minuti: ricalcola routing weights da model_stats, dedup pattern, esporta knowledge. Osserva ogni interazione per migliorare nel tempo."
        >
          <div className="grid grid-cols-2 gap-2 text-xs text-zinc-400">
            <Stat
              label="Skill acquisite"
              value={learning?.skills_acquired ?? '—'}
            />
            <Stat
              label="Pattern rilevati"
              value={learning?.patterns_detected ?? '—'}
            />
            <Stat
              label="Background loop"
              value={learning?.background_running ? 'attivo' : 'fermo'}
              ok={!!learning?.background_running}
            />
            <Stat
              label="Routing weights"
              value={
                learning?.routing_weights
                  ? Object.keys(learning.routing_weights).length
                  : 0
              }
            />
          </div>
        </AgentCard>
      </div>
    </div>
  );
}

function AgentCard({
  icon,
  color,
  name,
  subtitle,
  desc,
  children,
}: {
  icon: React.ReactNode;
  color: string;
  name: string;
  subtitle: string;
  desc: string;
  children?: React.ReactNode;
}) {
  return (
    <article
      className="rounded-2xl bg-zinc-900/50 border border-zinc-800 p-5"
      style={{ boxShadow: `0 0 0 1px ${color}33` }}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-10 h-10 rounded-xl grid place-items-center ring-1"
          style={{ background: `${color}22`, borderColor: `${color}66`, color }}
        >
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <h2 className="font-semibold tracking-tight" style={{ color }}>
              {name}
            </h2>
            <span className="text-[11px] text-zinc-500">{subtitle}</span>
          </div>
          <p className="mt-1 text-sm text-zinc-400 leading-snug">{desc}</p>
          {children && <div className="mt-3">{children}</div>}
        </div>
      </div>
    </article>
  );
}

function Stat({
  label,
  value,
  ok,
}: {
  label: string;
  value: React.ReactNode;
  ok?: boolean;
}) {
  return (
    <div className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wide">
        {label}
      </div>
      <div className={ok ? 'text-jarvis-green text-sm' : 'text-zinc-200 text-sm'}>
        {value}
      </div>
    </div>
  );
}
