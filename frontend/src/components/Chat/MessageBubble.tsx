import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Sparkles } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { ReactNode } from 'react';

interface Props {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  footer?: ReactNode;
}

export function MessageBubble({ role, content, footer }: Props) {
  const isUser = role === 'user';
  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      <div
        className={cn(
          'w-8 h-8 rounded-lg grid place-items-center shrink-0 ring-1',
          isUser
            ? 'bg-zinc-800 ring-zinc-700 text-zinc-300'
            : 'bg-jarvis-cyan/15 ring-jarvis-cyan/30 text-jarvis-cyan',
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
      </div>
      <div
        className={cn(
          'rounded-2xl px-4 py-3 max-w-[78%] text-sm prose-jarvis',
          isUser
            ? 'bg-zinc-800/80 text-zinc-100'
            : 'bg-zinc-900/60 ring-1 ring-zinc-800 text-zinc-100',
        )}
      >
        {content && (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        )}
        {footer}
      </div>
    </div>
  );
}
