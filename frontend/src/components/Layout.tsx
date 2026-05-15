import { useEffect, useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useApp } from '../lib/store';
import { api, openEventsWs } from '../lib/api';
import { HUDCircle } from './HUDCircle';
import { HUDClock, HUDPanel, MiniBarChart, MiniLineGraph, MiniWaveform } from './HUDWidgets';

const NAV = [
  { to: '/chat', label: 'COMMS' },
  { to: '/brain', label: 'NEURAL' },
  { to: '/skills', label: 'SKILLS' },
  { to: '/agents', label: 'AGENTS' },
  { to: '/settings', label: 'SYSTEM' },
];

export function Layout() {
  const health = useApp((s) => s.health);
  const online = !!health?.ok;
  const location = useLocation();
  const [learningStatus, setLearningStatus] = useState('IDLE');
  const [neuronCount, setNeuronCount] = useState<number | null>(null);
  const [queueSize, setQueueSize] = useState<number>(0);
  const isChat = location.pathname === '/' || location.pathname.startsWith('/chat');

  useEffect(() => {
    const ws = openEventsWs();
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        const payload = data.payload ?? data.data;
        if (data.type === 'chat_assistant_message' || data.type === 'CHAT_ASSISTANT_MESSAGE') {
          if (payload?.agent === 'auto_learning' || payload?.agent === 'auto_learning_continuous') {
            setLearningStatus(payload.status === 'completed' ? 'IDLE' : 'ACTIVE');
          }
        }
        if (data.type === 'brain_neuron_learned' || data.type === 'BRAIN_NEURON_LEARNED') {
          setNeuronCount((n) => (n !== null ? n + 1 : null));
        }
      } catch {
        // ignore
      }
    };
    ws.onerror = () => {};
    return () => ws.close();
  }, []);

  useEffect(() => {
    function poll() {
      api.brain.status()
        .then((s) => setNeuronCount(s.totale_neuroni))
        .catch(() => {});
      api.learning.queue.list()
        .then((q) => setQueueSize(q.length))
        .catch(() => {});
      api.learning.continuous.status()
        .then((s) => setLearningStatus(s.running ? 'ACTIVE' : 'IDLE'))
        .catch(() => {});
    }
    poll();
    const id = window.setInterval(poll, 15_000);
    return () => clearInterval(id);
  }, []);

  const activeEngines = health?.engines
    ? Object.entries(health.engines).filter(([, ok]) => ok).map(([name]) => name)
    : [];

  return (
    <div className="h-dvh w-dvw overflow-hidden relative text-[#4eeeff] hud-scanlines jarvis-hud-bg">
      <div className="absolute inset-0 jarvis-grid opacity-70" />
      <div className="absolute inset-0 jarvis-vignette" />

      <header className="absolute top-0 left-0 right-0 h-12 z-50 px-5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="font-mono text-[11px] tracking-[0.35em] text-[#9df6ff] hud-text-glow uppercase">
            JARVIS OS
          </div>
          <div className="w-56 h-px bg-gradient-to-r from-[#4eeeff]/70 via-[#4eeeff]/20 to-transparent" />
          <div className="font-mono text-[9px] tracking-[0.25em] text-[#4eeeff]/45">
            STARK INDUSTRIES INTERFACE // MK2
          </div>
        </div>
        <div className="flex items-center gap-5 font-mono text-[9px] tracking-[0.18em]">
          <StatusBadge ok={online} label="CORE" />
          <StatusBadge ok={!!health?.engines?.['ollama-fast']} label="OLLAMA" />
          <StatusBadge ok={!!health?.webbridge?.ok} label="WEB" />
          <StatusBadge ok={learningStatus === 'ACTIVE'} label={`LEARN ${learningStatus}`} />
          {neuronCount !== null && (
            <span className="text-[#4eeeff]/50 font-mono text-[8px] tracking-widest">
              {neuronCount} <span className="opacity-60">NEURONS</span>
            </span>
          )}
          {queueSize > 0 && (
            <span className="text-[#ffcc00]/70 font-mono text-[8px] tracking-widest">
              {queueSize} <span className="opacity-60">QUEUE</span>
            </span>
          )}
        </div>
      </header>

      <nav className="absolute top-14 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2">
        {NAV.map(({ to, label }) => {
          const isActive = location.pathname === to || location.pathname.startsWith(`${to}/`);
          return (
            <NavLink
              key={to}
              to={to}
              className={`px-4 py-1.5 border font-mono text-[9px] tracking-[0.22em] transition-all ${
                isActive
                  ? 'border-[#4eeeff]/70 bg-[#4eeeff]/10 text-[#d8fbff] hud-text-glow'
                  : 'border-[#4eeeff]/15 bg-[#001a2a]/25 text-[#4eeeff]/45 hover:border-[#4eeeff]/45 hover:text-[#9df6ff]'
              }`}
            >
              {label}
            </NavLink>
          );
        })}
      </nav>

      <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
        <div className="relative scale-[0.72] md:scale-[0.82] xl:scale-100">
          <div className="absolute inset-0 rounded-full blur-3xl bg-[#00d4ff]/10 scale-90" />
          <HUDCircle size={620} showLabel />
          {!isChat && (
            <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 font-mono text-[18px] tracking-[0.22em] text-[#4eeeff]/55 hud-text-glow">
              STARK INDUSTRIES
            </div>
          )}
        </div>
      </div>

      <section className="absolute left-4 top-16 w-[250px] z-30 space-y-3">
        <HUDPanel title="SYSTEM AUDIO">
          <MiniWaveform width={218} height={54} />
          <MetricGrid rows={[
            ['FREQ', '48.2KHZ'],
            ['GAIN', '0.82'],
            ['NOISE', 'LOW'],
          ]} />
        </HUDPanel>
        <HUDPanel title="CORE PROCESSING">
          <MiniLineGraph width={218} height={58} />
          <MetricGrid rows={[
            ['CPU', online ? '42%' : 'N/A'],
            ['MEM', '66%'],
            ['I/O', 'ACTIVE'],
          ]} />
        </HUDPanel>
        <HUDPanel title="NETWORK TRAFFIC UP">
          <MiniBarChart width={218} height={52} bars={28} />
        </HUDPanel>
        <HUDPanel title="ENGINE MATRIX">
          <div className="space-y-1">
            {activeEngines.slice(0, 6).map((name) => (
              <div key={name} className="flex items-center justify-between font-mono text-[9px]">
                <span className="text-[#4eeeff]/45">{name.toUpperCase()}</span>
                <span className="text-[#8dffef] hud-text-glow-green">ONLINE</span>
              </div>
            ))}
            {activeEngines.length === 0 && (
              <div className="font-mono text-[9px] text-[#ff5d7d]/70">NO ACTIVE ENGINE</div>
            )}
          </div>
        </HUDPanel>
      </section>

      <section className="absolute right-4 top-16 w-[265px] z-30 space-y-3">
        <HUDPanel title="JARVIS OS">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] text-[#4eeeff]/45">VER {health?.version ?? '2.0'}</div>
              <div className="font-mono text-[10px] text-[#4eeeff]/45">
                USER {health?.persona?.user_name?.toUpperCase() ?? 'SIGNORE'}
              </div>
            </div>
            <HUDClock />
          </div>
        </HUDPanel>
        <HUDPanel title="ENVIRONMENT">
          <div className="flex items-start gap-4">
            <div className="font-mono text-[38px] leading-none text-[#d8fbff] hud-text-glow">30°C</div>
            <div className="font-mono text-[9px] leading-relaxed text-[#4eeeff]/45">
              FAIR<br />
              HUMIDITY 45%<br />
              PRESSURE 1012MB<br />
              WIND 6KM/H
            </div>
          </div>
        </HUDPanel>
        <HUDPanel title="MODULE STATUS">
          <ModuleRow label="BACKEND" ok={online} />
          <ModuleRow label="WEBBRIDGE" ok={!!health?.webbridge?.ok} />
          <ModuleRow label="BRAIN" ok={online} />
          <ModuleRow label="SKILLS" ok={online} />
          <ModuleRow label="SWARM" ok={online} />
          <ModuleRow label="AUTO LEARNING" ok={learningStatus === 'ACTIVE'} />
        </HUDPanel>
        <HUDPanel title="DATABASE / OBSIDIAN">
          <MiniLineGraph width={232} height={54} />
          <div className="mt-1 font-mono text-[9px] text-[#4eeeff]/40">
            VAULT SYNC CHANNEL READY
          </div>
        </HUDPanel>
      </section>

      {!isChat && (
        <>
          <section className="absolute left-[285px] bottom-10 w-[220px] z-20 hidden xl:block">
            <HUDPanel title="NEURAL CACHE">
              <MiniBarChart width={190} height={46} bars={22} />
              <MetricGrid rows={[
                ['LOBI', '6'],
                ['MEMORY', 'EPISODIC'],
                ['SYNC', 'OBSIDIAN'],
              ]} />
            </HUDPanel>
          </section>

          <section className="absolute right-[285px] bottom-10 w-[220px] z-20 hidden xl:block">
            <HUDPanel title="SIGNAL MONITOR">
              <MiniWaveform width={190} height={46} />
              <MetricGrid rows={[
                ['PING', '12MS'],
                ['STREAM', 'WS'],
                ['TOKEN', 'LIVE'],
              ]} />
            </HUDPanel>
          </section>
        </>
      )}

      <main className="absolute inset-x-[200px] md:inset-x-[285px] top-24 bottom-5 z-40 pointer-events-auto">
        <Outlet />
      </main>
    </div>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="hud-status-dot"
        style={{ color: ok ? '#8dffef' : '#ff5d7d', background: ok ? '#8dffef' : '#ff5d7d' }}
      />
      <span className={ok ? 'text-[#8dffef]/80' : 'text-[#ff5d7d]/70'}>{label}</span>
    </div>
  );
}

function ModuleRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between font-mono text-[9px] py-0.5">
      <span className={ok ? 'text-[#4eeeff]/55' : 'text-[#4eeeff]/20'}>{label}</span>
      <span className={ok ? 'text-[#8dffef] hud-text-glow-green' : 'text-[#ff5d7d]/70'}>
        {ok ? 'ONLINE' : 'OFFLINE'}
      </span>
    </div>
  );
}

function MetricGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="mt-2 grid grid-cols-3 gap-1">
      {rows.map(([label, value]) => (
        <div key={label} className="border border-[#4eeeff]/10 px-1.5 py-1" style={{ background: 'rgba(78,238,255,0.03)' }}>
          <div className="font-mono text-[7px] tracking-[0.15em] text-[#4eeeff]/30">{label}</div>
          <div className="font-mono text-[9px] text-[#d8fbff]/70">{value}</div>
        </div>
      ))}
    </div>
  );
}
