/**
 * useWidgetCommands — maps voice/text commands to widget open/close actions.
 * Called by OrbPage after each command is submitted to decide if a widget
 * should be shown instead of (or alongside) the JARVIS response.
 */
import { useCallback, useState } from 'react';

export type WidgetId = 'brain' | 'skills' | 'chat' | 'queue' | null;

const RULES: { patterns: string[]; widget: WidgetId }[] = [
  { patterns: ['cervello', 'neuroni', 'brain', 'lobi', 'memoria neurale', 'knowledge'], widget: 'brain' },
  { patterns: ['skill', 'automaz', 'automazione', 'competenz', 'task'], widget: 'skills' },
  { patterns: ['chat', 'storico', 'cronolog', 'conversaz', 'messagg'], widget: 'chat' },
  { patterns: ['coda', 'queue', 'apprendimento', 'learning', 'impar'], widget: 'queue' },
  { patterns: ['chiudi', 'nascondi', 'chiudere', 'close', 'hide'], widget: null },
];

export function useWidgetCommands() {
  const [activeWidget, setActiveWidget] = useState<WidgetId>(null);

  const resolveCommand = useCallback((text: string): WidgetId | undefined => {
    const lower = text.toLowerCase();

    // Explicit close
    if (RULES.find((r) => r.widget === null)?.patterns.some((p) => lower.includes(p))) {
      setActiveWidget(null);
      return null;
    }

    for (const rule of RULES) {
      if (rule.widget === null) continue;
      if (rule.patterns.some((p) => lower.includes(p))) {
        setActiveWidget(rule.widget);
        return rule.widget;
      }
    }
    return undefined; // no widget match → normal JARVIS response
  }, []);

  const closeWidget = useCallback(() => setActiveWidget(null), []);

  return { activeWidget, resolveCommand, closeWidget };
}
