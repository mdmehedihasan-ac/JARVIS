import { useEffect, useRef } from 'react';
import { useApp } from '../../lib/store';
import { StreamingDots } from './StreamingDots';

export function ChatArea() {
  const messages = useApp((s) => s.messages);
  const streaming = useApp((s) => s.streaming);
  const buffer = useApp((s) => s.streamingBuffer);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages.length, buffer]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto hud-scroll">
      <div className="max-w-2xl mx-auto px-4 py-4 space-y-3">
        {messages.length === 0 && !streaming && <EmptyState />}

        {messages.map((m, i) => (
          <HUDMessageBubble key={i} role={m.role} content={m.content} />
        ))}

        {streaming && (
          <HUDMessageBubble
            role="assistant"
            content={buffer}
            footer={!buffer ? <StreamingDots /> : null}
          />
        )}
      </div>
    </div>
  );
}

function HUDMessageBubble({
  role,
  content,
  footer,
}: {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  footer?: React.ReactNode;
}) {
  const isUser = role === 'user';
  return (
    <div className={`hud-fade-in ${isUser ? 'flex justify-end' : 'flex justify-start'}`}>
      <div className={`max-w-[82%] ${isUser ? 'hud-msg-user' : 'hud-msg-assistant'} p-2.5 rounded-sm`}>
        <div className="flex items-center gap-2 mb-1.5">
          <span className={`text-[9px] font-mono tracking-[0.15em] ${isUser ? 'text-[#00d4ff]/60' : 'text-[#00ff88]/60'}`}>
            {isUser ? 'USER' : 'JARVIS'}
          </span>
          <div className="h-px flex-1 bg-gradient-to-r from-[#00d4ff]/10 to-transparent" />
          <span className="text-[9px] font-mono text-[#00d4ff]/30">
            {new Date().toLocaleTimeString('it-IT', { hour12: false })}
          </span>
        </div>
        <div className="text-[12px] leading-relaxed text-[#00d4ff]/80 whitespace-pre-wrap font-mono">
          {content || (footer ? footer : '')}
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center pt-2 space-y-2 hud-fade-in">
      <div>
        <h2 className="text-sm font-mono tracking-[0.14em] text-[#00d4ff]/70">
          BUONGIORNO, SIGNORE.
        </h2>
        <p className="text-[8px] font-mono text-[#00d4ff]/25 mt-1 max-w-md mx-auto">
          JARVIS MK2 ONLINE · MULTI-AGENT · AWAITING COMMAND
        </p>
      </div>
    </div>
  );
}
