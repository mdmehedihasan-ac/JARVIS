import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { useApp } from '../../lib/store';

export function ChatWidget({ onClose }: { onClose: () => void }) {
  const messages = useApp((s) => s.messages);
  const exportChat = useApp((s) => s.exportChat);
  const clearChat = useApp((s) => s.clearChat);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function doExport() {
    const txt = exportChat();
    if (!txt) return;
    const blob = new Blob([txt], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `jarvis_chat_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="widget-panel">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[10px] tracking-[0.3em] text-[#4eeeff]/70">CHAT HISTORY</span>
        <div className="flex gap-2 items-center">
          <button onClick={doExport} className="font-mono text-[8px] text-[#4eeeff]/40 hover:text-[#4eeeff] tracking-widest">EXPORT</button>
          <button onClick={clearChat} className="font-mono text-[8px] text-[#ff5d7d]/40 hover:text-[#ff5d7d] tracking-widest">CLEAR</button>
          <button onClick={onClose} className="text-[#4eeeff]/40 hover:text-[#4eeeff]"><X size={13} /></button>
        </div>
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <div className="font-mono text-[9px] text-[#4eeeff]/25 text-center py-4">NO MESSAGES</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`px-2 py-1.5 border ${m.role === 'user' ? 'border-[#4eeeff]/20 bg-[#001a2a]/40' : 'border-[#9df6ff]/10 bg-[#001a3a]/30'}`}>
            <div className={`font-mono text-[8px] mb-0.5 ${m.role === 'user' ? 'text-[#4eeeff]/50' : 'text-[#9df6ff]/50'}`}>
              {m.role.toUpperCase()}
            </div>
            <div className="font-mono text-[9px] text-[#d8fbff]/70 whitespace-pre-wrap break-words">
              {m.content.slice(0, 400)}{m.content.length > 400 ? '…' : ''}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
