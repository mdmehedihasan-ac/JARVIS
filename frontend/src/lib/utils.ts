import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}
