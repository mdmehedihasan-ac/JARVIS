import { useEffect, useState } from 'react';
import { X, Play, Clock } from 'lucide-react';
import { api, type Skill } from '../../lib/api';

export function SkillsWidget({ onClose }: { onClose: () => void }) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<string>('');

  useEffect(() => {
    api.skills.list().then(setSkills).catch(() => {});
  }, []);

  async function run(nome: string) {
    setRunning(nome);
    setResult('');
    try {
      const r = await api.skills.run(nome);
      setResult(JSON.stringify(r, null, 2));
    } catch (e: any) {
      setResult(`ERR: ${e.message}`);
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="widget-panel">
      <WidgetHeader title="SKILLS" onClose={onClose} />

      {skills.length === 0 && (
        <div className="font-mono text-[9px] text-[#4eeeff]/30 text-center py-4">NO SKILLS REGISTERED</div>
      )}

      <div className="space-y-1 max-h-56 overflow-y-auto">
        {skills.map((s) => (
          <div key={s.nome} className="flex items-center justify-between px-2 py-1.5 border border-[#4eeeff]/10 bg-[#001a2a]/20 gap-2">
            <div className="flex-1 min-w-0">
              <div className="font-mono text-[9px] text-[#9df6ff] truncate">{s.nome.toUpperCase()}</div>
              <div className="font-mono text-[8px] text-[#4eeeff]/35 truncate">{s.descrizione}</div>
            </div>
            <div className="flex gap-1 shrink-0">
              {s.schedule_every_seconds && (
                <Clock size={10} className="text-[#ffcc00]/60 mt-0.5" />
              )}
              <button
                onClick={() => run(s.nome)}
                disabled={running === s.nome}
                className="p-1 border border-[#4eeeff]/25 text-[#4eeeff] hover:bg-[#4eeeff]/10 disabled:opacity-40"
              >
                <Play size={9} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {result && (
        <pre className="mt-2 p-2 bg-[#001a2a]/60 border border-[#4eeeff]/10 font-mono text-[8px] text-[#9df6ff]/60 max-h-24 overflow-auto whitespace-pre-wrap">
          {result}
        </pre>
      )}
    </div>
  );
}

function WidgetHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <span className="font-mono text-[10px] tracking-[0.3em] text-[#4eeeff]/70">{title}</span>
      <button onClick={onClose} className="text-[#4eeeff]/40 hover:text-[#4eeeff]"><X size={13} /></button>
    </div>
  );
}
