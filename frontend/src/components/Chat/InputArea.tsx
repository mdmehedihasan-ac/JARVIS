import { useEffect, useRef, useState } from 'react';
import { useApp } from '../../lib/store';
import { api, openChatWs, type WsChatEvent } from '../../lib/api';

const SLASH_CMDS: { cmd: string; desc: string; expand?: string }[] = [
  { cmd: '/swarm', desc: 'Avvia swarm multi-agente' },
  { cmd: '/learn', desc: 'Apprendi da internet', expand: 'avvia apprendimento automatico su ' },
  { cmd: '/queue', desc: 'Aggiungi topic alla coda', expand: 'impara su ' },
  { cmd: '/web', desc: 'Comando browser', expand: 'webbridge ' },
  { cmd: '/skill', desc: 'Crea skill', expand: 'crea skill ' },
  { cmd: '/stop', desc: 'Ferma apprendimento', expand: 'ferma apprendimento' },
  { cmd: '/status', desc: 'Stato apprendimento', expand: 'stato apprendimento' },
  { cmd: '/clear', desc: 'Pulisci chat' },
  { cmd: '/export', desc: 'Esporta conversazione' },
  { cmd: '/new', desc: 'Nuova sessione' },
];

export function InputArea() {
  const [value, setValue] = useState('');
  const [showSlash, setShowSlash] = useState(false);
  const [slashFilter, setSlashFilter] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const streaming = useApp((s) => s.streaming);
  const currentMsgId = useApp((s) => s.currentMsgId);
  const messages = useApp((s) => s.messages);
  const pushMessage = useApp((s) => s.pushMessage);
  const appendStream = useApp((s) => s.appendStream);
  const startStream = useApp((s) => s.startStream);
  const finishStream = useApp((s) => s.finishStream);
  const clearChat = useApp((s) => s.clearChat);
  const newSession = useApp((s) => s.newSession);
  const exportChat = useApp((s) => s.exportChat);

  useEffect(() => {
    function onSuggest(ev: Event) {
      const detail = (ev as CustomEvent<string>).detail;
      if (typeof detail === 'string') send(detail);
    }
    window.addEventListener('jarvis:suggest', onSuggest);
    return () => window.removeEventListener('jarvis:suggest', onSuggest);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        textareaRef.current?.focus();
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'e') {
        e.preventDefault();
        doExport();
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'n') {
        e.preventDefault();
        newSession();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function autosize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

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

  function handleSlashCmd(cmd: string): boolean {
    const entry = SLASH_CMDS.find((c) => c.cmd === cmd);
    if (!entry) return false;
    if (cmd === '/clear') { clearChat(); setValue(''); return true; }
    if (cmd === '/export') { doExport(); setValue(''); return true; }
    if (cmd === '/new') { newSession(); setValue(''); return true; }
    if (entry.expand !== undefined) {
      setValue(entry.expand);
      setShowSlash(false);
      textareaRef.current?.focus();
      return true;
    }
    const prefer = cmd.replace('/', '');
    const msgText = cmd === '/swarm'
      ? (value.replace('/swarm', '').trim() || 'swarm task')
      : value.trim();
    send(msgText, undefined, prefer);
    return true;
  }

  function send(text?: string, _evt?: unknown, prefer?: string) {
    const msg = (text ?? value).trim();
    if (!msg || streaming) return;

    if (msg.startsWith('/')) {
      const parts = msg.split(' ');
      const handled = handleSlashCmd(parts[0]);
      if (handled && !SLASH_CMDS.find((c) => c.cmd === parts[0])?.expand) return;
    }

    const msgId = `msg_${Date.now()}`;
    pushMessage({ role: 'user', content: msg });
    setValue('');
    setShowSlash(false);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    startStream(msgId);
    const ws = openChatWs();
    wsRef.current = ws;
    let accumulated = '';
    let opened = false;
    let settled = false;
    let responseStarted = false;
    const fallbackTimer = window.setTimeout(() => {
      if (!opened && !settled) {
        ws.close();
        void sendRestFallback(msg, prefer);
      }
    }, 2500);
    const responseTimer = window.setTimeout(() => {
      if (opened && !responseStarted && !settled) {
        settled = true;
        ws.close();
        void sendRestFallback(msg, prefer);
      }
    }, 12000);
    ws.onopen = () => {
      opened = true;
      window.clearTimeout(fallbackTimer);
      ws.send(JSON.stringify({
        message: prefer ? msg : msg,
        history: messages.map((m) => ({ role: m.role, content: m.content })),
        prefer,
        speak: false,
      }));
    };
    ws.onmessage = (ev) => {
      try {
        const data: WsChatEvent = JSON.parse(ev.data);
        if (data.type === 'token') {
          responseStarted = true;
          accumulated += data.token;
          appendStream(data.token);
        } else if (data.type === 'done') {
          settled = true;
          window.clearTimeout(responseTimer);
          finishStream(data.text || accumulated);
          ws.close();
        } else if (data.type === 'error') {
          settled = true;
          window.clearTimeout(responseTimer);
          appendStream(`\n\n[ERR] ${data.error}`);
          finishStream();
          ws.close();
        }
      } catch { /* ignore */ }
    };
    ws.onerror = () => {
      if (!settled) {
        settled = true;
        window.clearTimeout(fallbackTimer);
        window.clearTimeout(responseTimer);
        void sendRestFallback(msg, prefer);
      }
    };
    ws.onclose = () => {
      wsRef.current = null;
      window.clearTimeout(fallbackTimer);
      window.clearTimeout(responseTimer);
    };
  }

  async function sendRestFallback(msg: string, prefer?: string) {
    try {
      const resp = await api.chat(msg, messages.map((m) => ({ role: m.role, content: m.content })), prefer, false);
      finishStream(resp.text);
    } catch {
      appendStream('\n\n[ERR] CONNESSIONE BACKEND FALLITA');
      finishStream();
    }
  }

  async function stop() {
    if (currentMsgId) {
      try { await api.cancel(currentMsgId); } catch { /* ignore */ }
    }
    wsRef.current?.close();
    finishStream();
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Escape') { setShowSlash(false); return; }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (showSlash) {
        const filtered = SLASH_CMDS.filter((c) => c.cmd.startsWith(slashFilter));
        if (filtered.length > 0) { handleSlashCmd(filtered[0].cmd); return; }
      }
      send();
    }
  }

  function onChangeValue(v: string) {
    setValue(v);
    autosize();
    if (v.startsWith('/') && !v.includes(' ')) {
      setSlashFilter(v);
      setShowSlash(true);
    } else {
      setShowSlash(false);
    }
  }

  const filteredCmds = SLASH_CMDS.filter((c) => c.cmd.startsWith(slashFilter));

  return (
    <div className="shrink-0 pb-2">
      <div className="max-w-2xl mx-auto px-4 relative">
        {showSlash && filteredCmds.length > 0 && (
          <div className="absolute bottom-full mb-1 left-4 right-4 bg-[#001a2a]/95 border border-[#00d4ff]/20 backdrop-blur-sm z-50">
            {filteredCmds.map((c) => (
              <button
                key={c.cmd}
                onClick={() => handleSlashCmd(c.cmd)}
                className="w-full text-left px-3 py-1.5 hover:bg-[#00d4ff]/10 flex gap-3 items-center"
              >
                <span className="text-[11px] font-mono text-[#00d4ff]">{c.cmd}</span>
                <span className="text-[10px] font-mono text-[#00d4ff]/40">{c.desc}</span>
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 hud-input px-3 py-2 bg-[#001a2a]/45 backdrop-blur-sm">
          <textarea
            ref={textareaRef}
            value={value}
            placeholder={streaming ? 'JARVIS PROCESSING...' : 'ENTER COMMAND · / FOR SHORTCUTS'}
            disabled={streaming}
            onChange={(e) => onChangeValue(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            className="flex-1 bg-transparent resize-none outline-none text-[12px] text-[#00d4ff]/80 placeholder:text-[#00d4ff]/20 disabled:opacity-40 font-mono"
          />
          <button
            onClick={() => (streaming ? void stop() : send())}
            disabled={!streaming && !value.trim()}
            className="px-3 py-1.5 text-[9px] font-mono tracking-wider border border-[#00d4ff]/30 text-[#00d4ff] hover:bg-[#00d4ff]/10 transition disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {streaming ? 'ABORT' : 'TRANSMIT'}
          </button>
        </div>
        <p className="mt-1 text-[8px] font-mono text-[#00d4ff]/20 text-center tracking-wider">
          ENTER · SHIFT+ENTER NEW LINE · / COMANDI · ⌘K FOCUS · ⌘⇧E EXPORT · ⌘⇧N NUOVA SESSIONE
        </p>
      </div>
    </div>
  );
}
