import { useEffect, useState } from 'react';
import { api, type Skill } from '../lib/api';
import { Play, Trash2, RefreshCw, Zap } from 'lucide-react';

export function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<{ nome: string; data: Record<string, unknown> } | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setSkills(await api.skills.list());
    } catch {
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }

  async function run(nome: string) {
    setRunning(nome);
    try {
      const data = await api.skills.run(nome);
      setResult({ nome, data });
    } catch (e) {
      setResult({ nome, data: { error: String(e) } });
    } finally {
      setRunning(null);
    }
  }

  async function remove(nome: string) {
    if (!confirm(`Eliminare la skill '${nome}'?`)) return;
    await api.skills.delete(nome);
    refresh();
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="flex flex-col h-full">
      <header className="border-b border-zinc-800/80 px-6 py-3 flex items-center justify-between bg-zinc-950/80 backdrop-blur">
        <div>
          <h1 className="text-sm font-semibold tracking-tight">Skills</h1>
          <p className="text-[11px] text-zinc-500">
            {skills.length} skill · sequenze di tool call con auto-match
          </p>
        </div>
        <button
          onClick={refresh}
          className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 border border-zinc-800 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Aggiorna
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-5xl mx-auto">
          {skills.map((s) => (
            <article
              key={s.nome}
              className="rounded-2xl bg-zinc-900/50 border border-zinc-800 p-4 hover:border-zinc-700 transition"
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5 text-jarvis-gold" />
                    <h2 className="font-semibold text-sm truncate">{s.nome}</h2>
                    {s.auto && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide bg-jarvis-cyan/15 text-jarvis-cyan">
                        default
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-zinc-400">{s.descrizione}</p>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => run(s.nome)}
                    disabled={running === s.nome}
                    className="w-8 h-8 grid place-items-center rounded-lg bg-jarvis-green/15 hover:bg-jarvis-green/25 text-jarvis-green border border-jarvis-green/30 transition disabled:opacity-50"
                    title="Esegui"
                  >
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => remove(s.nome)}
                    className="w-8 h-8 grid place-items-center rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-500 hover:text-jarvis-rose border border-zinc-800 transition"
                    title="Elimina"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {s.trigger_keywords?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {s.trigger_keywords.map((k) => (
                    <span
                      key={k}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400"
                    >
                      {k}
                    </span>
                  ))}
                </div>
              )}

              <ol className="mt-3 space-y-1">
                {s.azioni.map((a, i) => (
                  <li key={i} className="text-[11px] text-zinc-500 truncate">
                    {i + 1}. <code className="text-zinc-300">{a.tool}</code>
                    {a.args && Object.keys(a.args).length > 0 && (
                      <span className="text-zinc-600">
                        ({Object.entries(a.args).map(([k, v]) => `${k}=${String(v)}`).join(', ')})
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </article>
          ))}
          {skills.length === 0 && !loading && (
            <p className="text-zinc-500 text-sm col-span-full text-center py-10">
              Nessuna skill. Crea la prima via API o CLI{' '}
              <code>jarvis skill</code>.
            </p>
          )}
        </div>

        {result && (
          <div className="max-w-5xl mx-auto mt-6 rounded-2xl bg-zinc-900/50 border border-zinc-800 p-4">
            <div className="text-xs text-zinc-500">
              Risultato di <code className="text-zinc-300">{result.nome}</code>
            </div>
            <pre className="mt-2 text-[11px] text-zinc-300 whitespace-pre-wrap overflow-x-auto">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
