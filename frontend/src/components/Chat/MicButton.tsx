import { useRef, useState } from 'react';
import { Mic, MicOff } from 'lucide-react';
import { cn } from '../../lib/utils';

interface Props {
  onTranscript: (text: string) => void;
  lang?: string;
}

// Uses the Web Speech API (no extra deps).  Falls back gracefully if
// the browser doesn't support it (Firefox without flags, etc.).
export function MicButton({ onTranscript, lang = 'it-IT' }: Props) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  function toggle() {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    // Browser detection (Chrome/Edge/Safari)
    const SR =
      (window as any).webkitSpeechRecognition ||
      (window as any).SpeechRecognition;
    if (!SR) {
      alert(
        'Speech recognition non supportato in questo browser. Usa Chrome/Edge/Safari.',
      );
      return;
    }
    const rec = new SR();
    rec.lang = lang;
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e: any) => {
      const text = e.results[0][0].transcript as string;
      onTranscript(text);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.start();
    recognitionRef.current = rec;
    setListening(true);
  }

  return (
    <button
      onClick={toggle}
      title={listening ? 'Stop dettatura' : 'Detta col microfono (IT)'}
      className={cn(
        'w-9 h-9 grid place-items-center rounded-xl ring-1 transition',
        listening
          ? 'bg-jarvis-rose/20 ring-jarvis-rose/40 text-jarvis-rose'
          : 'bg-zinc-800/60 ring-zinc-700 text-zinc-400 hover:text-zinc-200',
      )}
    >
      {listening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
    </button>
  );
}
