/**
 * useVoiceEngine — always-on voice for JARVIS ORB
 *
 * States:
 *   idle      → continuous STT, local wake-word check only, zero API calls
 *   awake     → 30s window, full command recognition
 *   listening → STT active inside awake window
 *   thinking  → waiting for backend response
 *   speaking  → TTS playing response
 *
 * Optimisation:
 *   - STT never fully stopped (avoids ~500ms mic-open latency)
 *   - Backend called ONLY after wake word + command
 *   - Whisper used if /api/stt/available returns true, else Web Speech
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, openChatWs, openEventsWs, type ChatMessage, type WsChatEvent } from '../lib/api';

export type VoiceMode = 'idle' | 'awake' | 'listening' | 'thinking' | 'speaking';

const WAKE_WORDS = ['jarvis', 'j.a.r.v.i.s', 'ehi jarvis', 'hey jarvis', 'ok jarvis'];
const ACTIVE_WINDOW_MS = 30_000;
const LANG = 'it-IT';

interface SendOptions {
  speak: boolean;
  prefer?: string;
}

interface VoiceEngineState {
  mode: VoiceMode;
  transcript: string;       // current partial transcript
  lastCommand: string;      // last command sent
  lastResponse: string;     // last assistant response
  amplitude: number;        // 0-1 mic level for ORB animation
  whisperAvailable: boolean;
}

interface VoiceEngineActions {
  sendText: (text: string) => void;
  toggleMute: () => void;
  muted: boolean;
  forceAwake: () => void;
}

export function useVoiceEngine(): VoiceEngineState & VoiceEngineActions {
  const [mode, setMode] = useState<VoiceMode>('idle');
  const [transcript, setTranscript] = useState('');
  const [lastCommand, setLastCommand] = useState('');
  const [lastResponse, setLastResponse] = useState('');
  const [lastSpokenText, setLastSpokenText] = useState('');
  const [amplitude, setAmplitude] = useState(0);
  const [muted, setMuted] = useState(false);
  const [whisperAvailable, setWhisperAvailable] = useState(false);

  const recognitionRef = useRef<any>(null);
  const sleepTimerRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const ampFrameRef = useRef<number>(0);
  const modeRef = useRef<VoiceMode>('idle');
  const mutedRef = useRef(false);
  const historyRef = useRef<ChatMessage[]>([]);
  const lastMsgIdRef = useRef<string>('');

  // Keep ref in sync so closures always read current mode
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { mutedRef.current = muted; }, [muted]);

  // Check Whisper availability on mount
  useEffect(() => {
    api.health().then((h) => {
      // whisper flagged via health or dedicated endpoint
      const w = !!(h as any).whisper;
      setWhisperAvailable(w);
    }).catch(() => {});
  }, []);

  // ── Amplitude analyser ──────────────────────────────────────────
  const startAmplitude = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;

      const buf = new Uint8Array(analyser.frequencyBinCount);
      function tick() {
        analyser.getByteFrequencyData(buf);
        const avg = buf.reduce((a, b) => a + b, 0) / buf.length;
        setAmplitude(avg / 128);
        ampFrameRef.current = requestAnimationFrame(tick);
      }
      tick();
    } catch {
      // mic permission denied — amplitude stays 0
    }
  }, []);

  const stopAmplitude = useCallback(() => {
    cancelAnimationFrame(ampFrameRef.current);
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    analyserRef.current = null;
    setAmplitude(0);
  }, []);

  // ── Sleep timer ─────────────────────────────────────────────────
  const resetSleepTimer = useCallback(() => {
    window.clearTimeout(sleepTimerRef.current);
    sleepTimerRef.current = window.setTimeout(() => {
      setMode('idle');
      setTranscript('');
    }, ACTIVE_WINDOW_MS);
  }, []);

  // ── Send to backend ─────────────────────────────────────────────
  const sendToBackend = useCallback((text: string, options: SendOptions) => {
    if (!text.trim()) return;

    // Interrupt previous request: close old WS, call backend cancel, flush TTS
    const prevWs = wsRef.current;
    if (prevWs) {
      prevWs.onmessage = null;
      prevWs.onerror = null;
      prevWs.onclose = null;
      prevWs.close();
      wsRef.current = null;
    }
    const prevMsgId = lastMsgIdRef.current;
    if (prevMsgId) {
      api.cancel(prevMsgId).catch(() => {});
    }

    const msgId = crypto.randomUUID();
    lastMsgIdRef.current = msgId;

    setTranscript('');
    setLastCommand(text);
    setMode('thinking');

    const ws = openChatWs();
    wsRef.current = ws;
    let accumulated = '';
    let settled = false;
    const shouldSpeak = options.speak;
    const prefer = options.prefer;

    ws.onopen = () => {
      ws.send(JSON.stringify({
        message: text,
        history: historyRef.current.slice(-10),
        speak: shouldSpeak,
        prefer,
        msg_id: msgId,
        cancel_previous: !!prevMsgId,
        previous_msg_id: prevMsgId,
      }));
    };

    ws.onmessage = (ev) => {
      try {
        const data: WsChatEvent = JSON.parse(ev.data);
        if (data.type === 'token') {
          accumulated += data.token;
        } else if (data.type === 'done' || data.type === 'error') {
          if (!settled) {
            settled = true;
            const reply = data.type === 'done' ? (data.text || accumulated) : '⚠ Errore risposta';
            historyRef.current = [
              ...historyRef.current.slice(-19),
              { role: 'user' as const, content: text },
              { role: 'assistant' as const, content: reply },
            ];
            setLastResponse(reply);
            if (shouldSpeak) {
              // mode switches to speaking via backend voice.tts_speaking event
              // keep thinking until TTS actually starts to avoid flicker
              setLastSpokenText(reply);
            } else {
              setMode('awake');
              resetSleepTimer();
            }
            ws.close();
          }
        }
      } catch { /* ignore */ }
    };

    ws.onerror = () => {
      if (!settled) {
        settled = true;
        api.chat(text, historyRef.current.slice(-10), prefer, shouldSpeak)
          .then((r) => {
            setLastResponse(r.text);
            if (shouldSpeak) {
              setMode('speaking');
            } else {
              setMode('awake');
              resetSleepTimer();
            }
          })
          .catch(() => {
            setMode('awake');
            resetSleepTimer();
          });
      }
    };
  }, [resetSleepTimer]);

  // ── Web Speech Recognition ───────────────────────────────────────
  const startRecognition = useCallback(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SR) return;

    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
    }

    const rec = new SR();
    rec.lang = LANG;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    recognitionRef.current = rec;

    rec.onresult = (e: any) => {
      if (mutedRef.current) return;
      let interim = '';
      let final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript.toLowerCase().trim();
        if (e.results[i].isFinal) final += t + ' ';
        else interim += t;
      }

      const current = (final || interim).trim();
      if (!current) return;

      const currentMode = modeRef.current;

      if (currentMode === 'idle') {
        // Only check for wake word — no API calls
        const hasWake = WAKE_WORDS.some((w) => current.includes(w));
        if (hasWake) {
          setMode('awake');
          setTranscript('');
          resetSleepTimer();
        }
        return;
      }

      // Active window
      if (currentMode === 'awake' || currentMode === 'listening') {
        setMode('listening');
        setTranscript(current);
        resetSleepTimer();

        if (final.trim()) {
          // Remove wake word prefix if present
          let cmd = final.trim();
          WAKE_WORDS.forEach((w) => {
            cmd = cmd.replace(new RegExp(`^${w}[,\\s]*`, 'i'), '').trim();
          });
          if (cmd.length > 1) {
            sendToBackend(cmd, { speak: true, prefer: 'kimi' });
          }
        }
      }
    };

    rec.onend = () => {
      // Auto-restart to keep continuous
      if (!mutedRef.current) {
        try { rec.start(); } catch { /* ignore */ }
      }
    };

    rec.onerror = (e: any) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      // restart on error
      setTimeout(() => {
        if (!mutedRef.current && recognitionRef.current === rec) {
          try { rec.start(); } catch { /* ignore */ }
        }
      }, 500);
    };

    try { rec.start(); } catch { /* ignore */ }
  }, [sendToBackend, resetSleepTimer]);

  useEffect(() => {
    const ws = openEventsWs();
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type !== 'voice.tts_speaking') return;
        const payload = data.payload ?? {};
        if (payload.state === 'start') {
          if (typeof payload.text === 'string' && payload.text) {
            setLastResponse(payload.text);
          }
          setMode('speaking');
        }
        if (payload.state === 'end') {
          setMode('awake');
          resetSleepTimer();
        }
      } catch {
        // ignore
      }
    };
    ws.onerror = () => {};
    return () => ws.close();
  }, [resetSleepTimer]);

  // ── Init on mount ────────────────────────────────────────────────
  useEffect(() => {
    if (!muted) {
      startRecognition();
      startAmplitude();
    }
    return () => {
      recognitionRef.current?.stop();
      stopAmplitude();
      window.clearTimeout(sleepTimerRef.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Public API ───────────────────────────────────────────────────
  const sendText = useCallback((text: string) => {
    if (!text.trim()) return;
    setMode('awake');
    sendToBackend(text, { speak: false, prefer: undefined });
  }, [sendToBackend]);

  const toggleMute = useCallback(() => {
    setMuted((m) => {
      const next = !m;
      mutedRef.current = next;
      if (next) {
        recognitionRef.current?.stop();
        stopAmplitude();
      } else {
        startRecognition();
        startAmplitude();
      }
      return next;
    });
  }, [startRecognition, stopAmplitude, startAmplitude]);

  const forceAwake = useCallback(() => {
    setMode('awake');
    resetSleepTimer();
  }, [resetSleepTimer]);

  return {
    mode, transcript, lastCommand, lastResponse,
    amplitude, whisperAvailable,
    sendText, toggleMute, muted, forceAwake,
  };
}
