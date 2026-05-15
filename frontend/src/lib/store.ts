import { create } from 'zustand';
import type { ChatMessage, HealthInfo } from './api';

const STORAGE_KEY = 'jarvis_chat_history';
const MAX_STORED = 120;

function loadHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return (JSON.parse(raw) as ChatMessage[]).slice(-MAX_STORED);
  } catch {
    return [];
  }
}

function saveHistory(msgs: ChatMessage[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs.slice(-MAX_STORED)));
  } catch {
    // quota exceeded — ignore
  }
}

interface AppState {
  health: HealthInfo | null;
  setHealth: (h: HealthInfo | null) => void;

  // chat
  messages: ChatMessage[];
  streaming: boolean;
  streamingBuffer: string;
  currentMsgId: string;
  setMessages: (m: ChatMessage[]) => void;
  pushMessage: (m: ChatMessage) => void;
  appendStream: (token: string) => void;
  startStream: (msgId?: string) => void;
  finishStream: (text?: string) => void;
  clearChat: () => void;
  newSession: () => void;
  exportChat: () => string;
}

export const useApp = create<AppState>((set, get) => ({
  health: null,
  setHealth: (h) => set({ health: h }),

  messages: loadHistory(),
  streaming: false,
  streamingBuffer: '',
  currentMsgId: '',
  setMessages: (m) => { saveHistory(m); set({ messages: m }); },
  pushMessage: (m) =>
    set((s) => {
      const next = [...s.messages, m];
      saveHistory(next);
      return { messages: next };
    }),
  appendStream: (token) => set((s) => ({ streamingBuffer: s.streamingBuffer + token })),
  startStream: (msgId) => set({ streaming: true, streamingBuffer: '', currentMsgId: msgId ?? '' }),
  finishStream: (text) =>
    set((s) => {
      const content = text ?? s.streamingBuffer;
      if (!content) return { streaming: false };
      const next = [...s.messages, { role: 'assistant' as const, content }];
      saveHistory(next);
      return { streaming: false, messages: next, streamingBuffer: '', currentMsgId: '' };
    }),
  clearChat: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ messages: [], streaming: false, streamingBuffer: '', currentMsgId: '' });
  },
  newSession: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ messages: [], streaming: false, streamingBuffer: '', currentMsgId: '' });
  },
  exportChat: () => {
    const { messages } = get();
    return messages
      .map((m) => `[${m.role.toUpperCase()}]\n${m.content}`)
      .join('\n\n---\n\n');
  },
}));
