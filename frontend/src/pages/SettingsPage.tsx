import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface ConfigView {
  persona: { name: string; user_name: string; lang: string };
  ollama: { host: string; model_fast: string; model_heavy: string };
  voice: { wake_words: string[]; elevenlabs_voice_id: string };
  obsidian: { vault_path: string; configured: boolean };
  telegram: { configured: boolean };
}

export function SettingsPage() {
  const [cfg, setCfg] = useState<ConfigView | null>(null);

  useEffect(() => {
    api.config().then((c) => setCfg(c as unknown as ConfigView)).catch(() => setCfg(null));
  }, []);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <header className="border-b border-zinc-800/80 px-6 py-3 bg-zinc-950/80 backdrop-blur sticky top-0 z-10">
        <h1 className="text-sm font-semibold tracking-tight">Impostazioni</h1>
        <p className="text-[11px] text-zinc-500">
          Configurazione corrente (sola lettura, modificabile via <code>.env</code>)
        </p>
      </header>

      <div className="px-6 py-6 space-y-6 max-w-3xl mx-auto w-full">
        {!cfg ? (
          <div className="text-zinc-500 text-sm">Caricamento configurazione…</div>
        ) : (
          <>
            <Section title="Persona">
              <Row k="Nome" v={cfg.persona.name} />
              <Row k="Utente" v={cfg.persona.user_name} />
              <Row k="Lingua" v={cfg.persona.lang} />
            </Section>

            <Section title="Ollama (LLM locale)">
              <Row k="Host" v={cfg.ollama.host} />
              <Row k="Modello fast" v={cfg.ollama.model_fast} />
              <Row k="Modello heavy" v={cfg.ollama.model_heavy} />
            </Section>

            <Section title="Voce">
              <Row k="Wake words" v={cfg.voice.wake_words.join(', ')} />
              <Row k="ElevenLabs voice id" v={cfg.voice.elevenlabs_voice_id} />
            </Section>

            <Section title="Obsidian">
              <Row k="Vault path" v={cfg.obsidian.vault_path || '— non configurato —'} />
              <Row k="Configurato" v={cfg.obsidian.configured ? '✓' : '✗'} />
            </Section>

            <Section title="Telegram">
              <Row k="Bot token" v={cfg.telegram.configured ? '✓ configurato' : '— non configurato —'} />
            </Section>

            <div className="text-xs text-zinc-500 pt-2 border-t border-zinc-800">
              Per modificare qualsiasi parametro, edita <code>~/JARVISMK2/.env</code> e
              riavvia il backend con <code>uv run jarvis serve</code>.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-zinc-900/50 border border-zinc-800 overflow-hidden">
      <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-950/70">
        <h2 className="text-xs uppercase tracking-wide text-zinc-400">{title}</h2>
      </div>
      <dl className="divide-y divide-zinc-800">{children}</dl>
    </section>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-4 px-4 py-2.5 text-sm">
      <dt className="text-zinc-500">{k}</dt>
      <dd className="text-zinc-100 break-all">{v}</dd>
    </div>
  );
}
