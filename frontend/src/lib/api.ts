// Tiny REST + WebSocket client for the JARVIS MK2 backend.

export type ChatRole = 'system' | 'user' | 'assistant' | 'tool';

export interface ChatMessage {
  role: ChatRole;
  content: string;
  ts?: number;
}

export interface ChatResponse {
  text: string;
  action: string;
  success: boolean;
  latency_ms: number;
  model: string;
  metadata: Record<string, unknown>;
}

export interface HealthInfo {
  ok: boolean;
  version: string;
  engines: Record<string, boolean>;
  persona: { name: string; user_name: string; lang: string };
  webbridge?: { ok: boolean; running?: boolean; extension_connected?: boolean };
}

export interface BrainStato {
  lobi: Record<
    string,
    {
      nome: string;
      funzione: string;
      colore: string;
      neuroni: number;
      carico: number;
      attivo: boolean;
      top: Array<{ contenuto: string; forza: number }>;
    }
  >;
  totale_neuroni: number;
  ultimo_aggiornamento: string;
}

export interface BrainNode {
  id: string;
  label: string;
  type: 'lobo' | 'neurone';
  color: string;
  size: number;
  lobo: string;
  forza?: number;
  carico?: number;
  contenuto?: string;
  funzione?: string;
  tags?: string[];
}

export interface BrainEdge {
  source: string;
  target: string;
  type: 'membership' | 'synapse';
  weight: number;
  shared_tags?: string[];
}

export interface BrainGraph {
  nodes: BrainNode[];
  edges: BrainEdge[];
  stats: {
    totale_nodi: number;
    totale_archi: number;
    totale_lobi: number;
    totale_neuroni: number;
  };
}

export interface Skill {
  nome: string;
  descrizione: string;
  azioni: Array<{ tool: string; args: Record<string, unknown> }>;
  tag: string[];
  trigger_keywords: string[];
  auto?: boolean;
  created_ts?: number;
  schedule_every_seconds?: number | null;
}

export interface LearningQueueItem {
  topic: string;
  ts: number;
}

export interface BrainSearchResult {
  id: string;
  contenuto: string;
  lobo: string;
  forza: number;
  fonte: string;
  tag: string[];
}

export interface SchedulerJob {
  name: string;
  every_seconds: number | null;
  next_run: number;
  last_run: number;
  runs: number;
  enabled: boolean;
}

const API = ''; // proxied by vite dev server

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json();
}

async function jpost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json();
}

async function jdelete<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json();
}

// ── REST ────────────────────────────────────────────────────────────
export const api = {
  health: () => jget<HealthInfo>('/api/health'),
  config: () => jget<Record<string, unknown>>('/api/config'),

  chat: (message: string, history: ChatMessage[], prefer?: string, speak = false) =>
    jpost<ChatResponse>('/api/chat', { message, history, prefer, speak }),
  cancel: (msgId: string) => jpost<{ ok: boolean }>('/api/cancel', { msg_id: msgId }),

  brain: {
    status: () => jget<BrainStato>('/api/brain/status'),
    graph: (maxPerLobo = 25) =>
      jget<BrainGraph>(`/api/brain/graph?max_per_lobo=${maxPerLobo}`),
    learn: (contenuto: string, tipo: string, lobo: string, tag: string[] = []) =>
      jpost<{ id: string; ok: boolean }>(
        `/api/brain/learn?contenuto=${encodeURIComponent(contenuto)}&tipo=${encodeURIComponent(tipo)}&lobo=${encodeURIComponent(lobo)}`,
        tag,
      ),
    syncObsidian: () => jpost<{ added: number }>('/api/brain/sync-obsidian', {}),
    search: (q: string, top = 8) =>
      jget<BrainSearchResult[]>(`/api/brain/search?q=${encodeURIComponent(q)}&top=${top}`),
  },

  episodic: {
    stats: () => jget<{ totale_episodi: number; con_embedding: number; max: number }>('/api/episodic/stats'),
    recent: (n = 20) => jget<Array<Record<string, unknown>>>(`/api/episodic/recent?n=${n}`),
    search: (q: string, topK = 5) =>
      jget<Array<Record<string, unknown>>>(
        `/api/episodic/search?q=${encodeURIComponent(q)}&top_k=${topK}`,
      ),
  },

  skills: {
    list: () => jget<Skill[]>('/api/skills'),
    create: (body: Omit<Skill, 'auto' | 'created_ts'>) =>
      jpost<{ ok: boolean }>('/api/skills', body),
    delete: (nome: string) => jdelete<{ ok: boolean }>(`/api/skills/${encodeURIComponent(nome)}`),
    run: (nome: string) =>
      jpost<Record<string, unknown>>(`/api/skills/${encodeURIComponent(nome)}/run`, {}),
    schedule: (nome: string, every_seconds: number) =>
      jpost<{ ok: boolean }>(`/api/skills/${encodeURIComponent(nome)}/schedule`, { every_seconds }),
    unschedule: (nome: string) =>
      jdelete<{ ok: boolean }>(`/api/skills/${encodeURIComponent(nome)}/schedule`),
  },

  learning: {
    status: () => jget<Record<string, unknown>>('/api/learning/status'),
    export: () => jget<Record<string, unknown>>('/api/learning/export'),
    continuous: {
      status: () => jget<{ running: boolean; stats: Record<string, unknown> }>('/api/learning/continuous'),
      start: () => jpost<{ ok: boolean; text: string }>('/api/learning/continuous/start', {}),
      stop: () => jpost<{ ok: boolean; text: string }>('/api/learning/continuous/stop', {}),
    },
    queue: {
      list: () => jget<LearningQueueItem[]>('/api/learning/queue'),
      add: (topic: string) => jpost<{ ok: boolean; queue_size: number }>('/api/learning/queue', { topic }),
      remove: (idx: number) => jdelete<{ ok: boolean }>(`/api/learning/queue/${idx}`),
      clear: () => jdelete<{ ok: boolean }>('/api/learning/queue'),
    },
  },

  scheduler: {
    jobs: () => jget<SchedulerJob[]>('/api/scheduler/jobs'),
  },

  cancel: (msgId: string) =>
    jpost<{ ok: boolean; cancelled?: string; error?: string }>(
      `/api/cancel?msg_id=${encodeURIComponent(msgId)}`, {}
    ),

  obsidian: {
    search: (q: string, topK = 10) =>
      jget<Array<Record<string, unknown>>>(`/api/obsidian/search?q=${encodeURIComponent(q)}&top_k=${topK}`),
    write: (title: string, content: string, subdir = 'web', source_url = '') =>
      jpost<{ ok: boolean; path?: string; title?: string; error?: string }>(
        `/api/obsidian/write?title=${encodeURIComponent(title)}&content=${encodeURIComponent(content)}&subdir=${encodeURIComponent(subdir)}&source_url=${encodeURIComponent(source_url)}`,
        {}
      ),
  },
};

// ── WebSocket streaming chat ────────────────────────────────────────
export type WsChatEvent =
  | { type: 'token'; token: string }
  | { type: 'done'; text: string }
  | { type: 'error'; error: string };

export function openChatWs(): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}/ws/chat`;
  return new WebSocket(url);
}

export function openEventsWs(): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}/ws/events`;
  return new WebSocket(url);
}
