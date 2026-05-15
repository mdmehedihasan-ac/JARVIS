import { useEffect, useState } from 'react';
import { api, type BrainStato } from '../lib/api';
import { Brain3DView } from '../components/Brain/Brain3DView';
import { RefreshCw, FolderSync } from 'lucide-react';

export function BrainPage() {
  const [stato, setStato] = useState<BrainStato | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const s = await api.brain.status();
      setStato(s);
    } catch {
      setStato(null);
    } finally {
      setLoading(false);
    }
  }

  async function syncObsidian() {
    setSyncMsg('Sincronizzo...');
    try {
      const r = await api.brain.syncObsidian();
      setSyncMsg(`Sincronizzati ${r.added} neuroni da Obsidian.`);
      refresh();
    } catch (e) {
      setSyncMsg(`Errore: ${String(e)}`);
    }
    setTimeout(() => setSyncMsg(null), 4000);
  }

  useEffect(() => {
    refresh();
    // Auto-refresh every 5s for live 3D updates
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full">
      <header className="border-b border-zinc-800/80 px-6 py-3 flex items-center justify-between bg-zinc-950/80 backdrop-blur">
        <div>
          <h1 className="text-sm font-semibold tracking-tight">Cervello</h1>
          <p className="text-[11px] text-zinc-500">
            {stato
              ? `${stato.totale_neuroni} neuroni · 6 lobi · stato in tempo reale`
              : '—'}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={syncObsidian}
            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-jarvis-violet/15 hover:bg-jarvis-violet/25 text-jarvis-violet border border-jarvis-violet/30 transition"
          >
            <FolderSync className="w-3.5 h-3.5" />
            Sync Obsidian
          </button>
          <button
            onClick={refresh}
            className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100 border border-zinc-800 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Aggiorna
          </button>
        </div>
      </header>

      {syncMsg && (
        <div className="border-b border-zinc-800/80 bg-jarvis-violet/10 px-6 py-2 text-xs text-jarvis-violet">
          {syncMsg}
        </div>
      )}

      <div className="grid grid-cols-[1fr_320px] flex-1 overflow-hidden">
        <div className="overflow-hidden">
          {stato ? (
            <Brain3DView stato={stato} />
          ) : (
            <div className="h-full grid place-items-center text-zinc-500 text-sm">
              {loading ? 'Caricamento cervello 3D...' : 'Backend non raggiungibile.'}
            </div>
          )}
        </div>
        <aside className="overflow-y-auto border-l border-zinc-800/80 p-4 space-y-3">
          {stato &&
            Object.entries(stato.lobi).map(([key, lobo]) => (
              <div
                key={key}
                className="rounded-xl bg-zinc-900/50 border border-zinc-800 p-3"
                style={{ boxShadow: `0 0 0 1px ${lobo.colore}33` }}
              >
                <div className="flex items-center justify-between">
                  <div className="font-medium text-sm" style={{ color: lobo.colore }}>
                    {lobo.nome}
                  </div>
                  <div className="text-[11px] text-zinc-500">
                    {lobo.neuroni} neuroni
                  </div>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">{lobo.funzione}</p>
                <div className="mt-2 h-1 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, lobo.carico * 100)}%`,
                      background: lobo.colore,
                    }}
                  />
                </div>
                {lobo.top.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {lobo.top.map((t, i) => (
                      <li
                        key={i}
                        className="text-[11px] text-zinc-400 truncate"
                        title={t.contenuto}
                      >
                        · {t.contenuto}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
        </aside>
      </div>
    </div>
  );
}
