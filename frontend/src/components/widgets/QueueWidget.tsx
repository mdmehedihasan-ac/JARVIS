import { useEffect, useState } from 'react';
import { X, Trash2, Plus } from 'lucide-react';
import { api, type LearningQueueItem } from '../../lib/api';

export function QueueWidget({ onClose }: { onClose: () => void }) {
  const [queue, setQueue] = useState<LearningQueueItem[]>([]);
  const [newTopic, setNewTopic] = useState('');
  const [continuous, setContinuous] = useState(false);

  function refresh() {
    api.learning.queue.list().then(setQueue).catch(() => {});
    api.learning.continuous.status().then((s) => setContinuous(s.running)).catch(() => {});
  }

  useEffect(() => { refresh(); }, []);

  async function add() {
    if (!newTopic.trim()) return;
    await api.learning.queue.add(newTopic.trim()).catch(() => {});
    setNewTopic('');
    refresh();
  }

  async function remove(idx: number) {
    await api.learning.queue.remove(idx).catch(() => {});
    refresh();
  }

  async function toggleContinuous() {
    if (continuous) {
      await api.learning.continuous.stop().catch(() => {});
    } else {
      await api.learning.continuous.start().catch(() => {});
    }
    setTimeout(refresh, 400);
  }

  return (
    <div className="widget-panel">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-[10px] tracking-[0.3em] text-[#4eeeff]/70">LEARNING QUEUE</span>
        <button onClick={onClose} className="text-[#4eeeff]/40 hover:text-[#4eeeff]"><X size={13} /></button>
      </div>

      <div className="flex items-center justify-between mb-2 px-2 py-1 border border-[#4eeeff]/10">
        <span className="font-mono text-[9px] text-[#4eeeff]/50">CONTINUOUS LEARNING</span>
        <button
          onClick={toggleContinuous}
          className={`font-mono text-[8px] px-2 py-0.5 border tracking-widest transition ${continuous ? 'border-[#ff5d7d]/50 text-[#ff5d7d]' : 'border-[#9df6ff]/30 text-[#9df6ff]/60 hover:text-[#9df6ff]'}`}
        >
          {continuous ? 'STOP' : 'START'}
        </button>
      </div>

      <div className="flex gap-2 mb-2">
        <input
          value={newTopic}
          onChange={(e) => setNewTopic(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="AGGIUNGI TOPIC..."
          className="flex-1 bg-[#001a2a]/60 border border-[#4eeeff]/20 px-2 py-1 font-mono text-[10px] text-[#4eeeff] placeholder:text-[#4eeeff]/25 outline-none"
        />
        <button onClick={add} className="px-2 py-1 border border-[#4eeeff]/30 text-[#4eeeff] hover:bg-[#4eeeff]/10">
          <Plus size={11} />
        </button>
      </div>

      <div className="space-y-1 max-h-44 overflow-y-auto">
        {queue.length === 0 && (
          <div className="font-mono text-[9px] text-[#4eeeff]/25 text-center py-3">QUEUE EMPTY</div>
        )}
        {queue.map((item, i) => (
          <div key={i} className="flex items-center justify-between px-2 py-1 border border-[#4eeeff]/10 bg-[#001a2a]/20 gap-2">
            <span className="font-mono text-[9px] text-[#9df6ff] flex-1 truncate">{item.topic}</span>
            <button onClick={() => remove(i)} className="text-[#ff5d7d]/40 hover:text-[#ff5d7d]">
              <Trash2 size={9} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
