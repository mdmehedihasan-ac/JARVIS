import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Mic, MicOff, Brain, Zap, MessageSquare, BookOpen, Settings } from 'lucide-react';
import { HUDCircle } from '../components/HUDCircle';
import { BrainWidget } from '../components/widgets/BrainWidget';
import { SkillsWidget } from '../components/widgets/SkillsWidget';
import { ChatWidget } from '../components/widgets/ChatWidget';
import { QueueWidget } from '../components/widgets/QueueWidget';
import { useVoiceEngine } from '../hooks/useVoiceEngine';
import { useWidgetCommands, type WidgetId } from '../hooks/useWidgetCommands';

const MODE_COLORS: Record<string, string> = {
  idle:      'text-[#4eeeff]/40',
  awake:     'text-[#40e8ff]',
  listening: 'text-[#39ff9e]',
  thinking:  'text-[#ff8c42]',
  speaking:  'text-[#b0f0ff]',
};

const MODE_LABELS: Record<string, string> = {
  idle:      'STANDBY — DI\' "JARVIS" PER SVEGLIARMI',
  awake:     'IN ASCOLTO · 30s',
  listening: '● REC — PARLA PURE',
  thinking:  '▶ ELABORO...',
  speaking:  '◎ RISPONDO',
};

export function OrbPage() {
  const voice = useVoiceEngine();
  const { activeWidget, resolveCommand, closeWidget } = useWidgetCommands();
  const [textInput, setTextInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  function handleTextSend() {
    const t = textInput.trim();
    if (!t) return;
    setTextInput('');
    resolveCommand(t);
    voice.sendText(t);
  }

  function handleWidgetButton(id: WidgetId) {
    if (activeWidget === id) {
      closeWidget();
    } else {
      // open directly without sending to backend
      resolveCommand(id ?? '');
    }
  }

  const orbSize = Math.min(window.innerWidth, window.innerHeight) * 0.72;
  const clampedSize = Math.max(320, Math.min(orbSize, 620));

  return (
    <div className="relative h-dvh w-dvw overflow-hidden bg-[#000d18] text-[#4eeeff] hud-scanlines">
      {/* Grid + vignette */}
      <div className="absolute inset-0 jarvis-grid opacity-40 pointer-events-none" />
      <div className="absolute inset-0 jarvis-vignette pointer-events-none" />

      {/* ── Top status bar ── */}
      <header className="absolute top-0 inset-x-0 h-10 z-50 flex items-center justify-between px-5">
        <div className="font-mono text-[9px] tracking-[0.3em] text-[#4eeeff]/30">JARVIS OS · MK2</div>
        <span className={`font-mono text-[9px] tracking-[0.22em] transition-colors ${MODE_COLORS[voice.mode]}`}>
          {MODE_LABELS[voice.mode]}
        </span>
        <Link to="/chat" className="font-mono text-[8px] tracking-widest text-[#4eeeff]/30 hover:text-[#4eeeff]/60 transition">
          HUD →
        </Link>
      </header>

      {/* ── Central ORB ── */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
        <div className="relative">
          {/* Outer glow */}
          <div
            className="absolute inset-0 rounded-full blur-3xl transition-opacity duration-700"
            style={{
              background: voice.mode === 'listening' ? 'rgba(57,255,158,0.06)'
                : voice.mode === 'thinking' ? 'rgba(255,140,66,0.06)'
                : 'rgba(0,212,255,0.05)',
            }}
          />
          <HUDCircle
            size={clampedSize}
            showLabel
            mode={voice.mode}
            amplitude={voice.amplitude}
          />
        </div>
      </div>

      {/* ── Transcript band ── */}
      <div className="absolute bottom-36 inset-x-0 flex flex-col items-center gap-1 z-30 pointer-events-none px-8">
        {voice.transcript && (
          <div className="font-mono text-[11px] text-[#39ff9e]/80 tracking-wide bg-[#001a2a]/60 px-4 py-1 max-w-xl text-center">
            ▶ {voice.transcript}
          </div>
        )}
        {voice.lastResponse && (
          <div className="font-mono text-[10px] text-[#b0f0ff]/60 tracking-wide bg-[#001a2a]/40 px-4 py-1 max-w-2xl text-center line-clamp-3">
            {voice.lastResponse}
          </div>
        )}
      </div>

      {/* ── Text input bar ── */}
      <div className="absolute bottom-16 inset-x-0 flex justify-center z-40 px-4">
        <div className="flex gap-2 w-full max-w-lg items-center bg-[#001a2a]/60 border border-[#4eeeff]/15 px-3 py-2 backdrop-blur-sm">
          <input
            ref={inputRef}
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTextSend()}
            placeholder={voice.mode === 'idle' ? 'SCRIVI O DI\' "JARVIS"...' : 'COMANDO TESTO...'}
            className="flex-1 bg-transparent outline-none font-mono text-[11px] text-[#4eeeff]/80 placeholder:text-[#4eeeff]/20"
          />
          <button
            onClick={voice.toggleMute}
            className={`p-1.5 border transition ${voice.muted ? 'border-[#ff5d7d]/40 text-[#ff5d7d]/70' : 'border-[#4eeeff]/20 text-[#4eeeff]/50 hover:text-[#4eeeff]'}`}
            title={voice.muted ? 'Riattiva microfono' : 'Silenzia microfono'}
          >
            {voice.muted ? <MicOff size={13} /> : <Mic size={13} />}
          </button>
          <button
            onClick={handleTextSend}
            disabled={!textInput.trim()}
            className="px-3 py-1 border border-[#4eeeff]/20 font-mono text-[9px] text-[#4eeeff]/60 hover:bg-[#4eeeff]/10 disabled:opacity-20 tracking-widest transition"
          >
            SEND
          </button>
        </div>
      </div>

      {/* ── Widget toggle buttons ── */}
      <div className="absolute bottom-4 inset-x-0 flex justify-center gap-3 z-40">
        {([
          { id: 'brain' as WidgetId, icon: Brain, label: 'BRAIN' },
          { id: 'skills' as WidgetId, icon: Zap, label: 'SKILLS' },
          { id: 'chat' as WidgetId, icon: MessageSquare, label: 'CHAT' },
          { id: 'queue' as WidgetId, icon: BookOpen, label: 'QUEUE' },
        ] as const).map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            onClick={() => handleWidgetButton(id)}
            className={`flex items-center gap-1.5 px-3 py-1 border font-mono text-[8px] tracking-widest transition ${
              activeWidget === id
                ? 'border-[#4eeeff]/60 bg-[#4eeeff]/15 text-[#4eeeff]'
                : 'border-[#4eeeff]/15 text-[#4eeeff]/35 hover:border-[#4eeeff]/40 hover:text-[#4eeeff]/70'
            }`}
          >
            <Icon size={10} />
            {label}
          </button>
        ))}
        <Link
          to="/settings"
          className="flex items-center gap-1.5 px-3 py-1 border border-[#4eeeff]/15 font-mono text-[8px] tracking-widest text-[#4eeeff]/35 hover:border-[#4eeeff]/40 hover:text-[#4eeeff]/70 transition"
        >
          <Settings size={10} />
          SYS
        </Link>
      </div>

      {/* ── Widget overlay ── */}
      {activeWidget && (
        <div className="absolute bottom-20 right-5 z-50 w-72 animate-slide-up">
          {activeWidget === 'brain' && <BrainWidget onClose={closeWidget} />}
          {activeWidget === 'skills' && <SkillsWidget onClose={closeWidget} />}
          {activeWidget === 'chat' && <ChatWidget onClose={closeWidget} />}
          {activeWidget === 'queue' && <QueueWidget onClose={closeWidget} />}
        </div>
      )}
    </div>
  );
}
