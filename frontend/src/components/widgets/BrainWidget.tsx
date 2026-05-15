import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api, type BrainStato } from '../../lib/api';

export function BrainWidget({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<BrainStato | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);

  useEffect(() => {
    api.brain.status().then(setData).catch(() => {});
  }, []);

  function search(q: string) {
    if (!q.trim()) { setResults([]); return; }
    api.brain.search(q, 6).then(setResults).catch(() => {});
  }

  return (
    <div className="widget-panel">
      <WidgetHeader title="NEURAL BRAIN" onClose={onClose} />

      {data && (
        <div className="mb-3">
          <div className="flex justify-between items-center mb-2">
            <span className="font-mono text-[9px] text-[#4eeeff]/50 tracking-widest">TOTAL NEURONS</span>
            <span className="font-mono text-[18px] text-[#4eeeff] hud-text-glow">{data.totale_neuroni}</span>
          </div>
          <div className="grid grid-cols-2 gap-1">
            {Object.entries(data.lobi).map(([id, lobo]) => (
              <div key={id} className="flex items-center justify-between px-2 py-1 border border-[#4eeeff]/10 bg-[#001a2a]/30">
                <span className="font-mono text-[8px] text-[#4eeeff]/60 truncate">{lobo.nome.toUpperCase()}</span>
                <span className="font-mono text-[9px] text-[#9df6ff]">{lobo.neuroni}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && search(query)}
          placeholder="CERCA NEURONI..."
          className="flex-1 bg-[#001a2a]/60 border border-[#4eeeff]/20 px-2 py-1 font-mono text-[10px] text-[#4eeeff] placeholder:text-[#4eeeff]/25 outline-none"
        />
        <button onClick={() => search(query)} className="px-2 py-1 border border-[#4eeeff]/30 font-mono text-[9px] text-[#4eeeff] hover:bg-[#4eeeff]/10">
          GO
        </button>
      </div>

      {results.length > 0 && (
        <div className="space-y-1 max-h-36 overflow-y-auto">
          {results.map((r, i) => (
            <div key={i} className="px-2 py-1 border border-[#4eeeff]/10 bg-[#001a2a]/20">
              <div className="font-mono text-[8px] text-[#4eeeff]/40">{r.lobo?.toUpperCase()} · {(r.forza ?? 0).toFixed(2)}</div>
              <div className="font-mono text-[9px] text-[#9df6ff] line-clamp-2">{r.contenuto}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WidgetHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <span className="font-mono text-[10px] tracking-[0.3em] text-[#4eeeff]/70">{title}</span>
      <button onClick={onClose} className="text-[#4eeeff]/40 hover:text-[#4eeeff]">
        <X size={13} />
      </button>
    </div>
  );
}
