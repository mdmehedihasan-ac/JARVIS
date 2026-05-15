import { useEffect, useRef } from 'react';
import type { VoiceMode } from '../hooks/useVoiceEngine';

interface HUDCircleProps {
  size?: number;
  showLabel?: boolean;
  mode?: VoiceMode;
  amplitude?: number;
}

const CYAN = '#00d4ff';
const CYAN_BRIGHT = '#40e8ff';
const CYAN_WHITE = '#b0f0ff';
const ORANGE = '#ff8c42';
const GREEN = '#39ff9e';

// Per-mode speed/brightness multipliers
const MODE_CFG: Record<VoiceMode, { speed: number; alpha: number; color: string }> = {
  idle:      { speed: 0.4,  alpha: 0.45, color: CYAN },
  awake:     { speed: 0.9,  alpha: 0.75, color: CYAN_BRIGHT },
  listening: { speed: 1.2,  alpha: 1.0,  color: GREEN },
  thinking:  { speed: 2.2,  alpha: 1.0,  color: ORANGE },
  speaking:  { speed: 1.5,  alpha: 0.9,  color: CYAN_WHITE },
};

export function HUDCircle({ size = 500, showLabel = true, mode = 'idle', amplitude = 0 }: HUDCircleProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const modeRef = useRef(mode);
  const ampRef = useRef(amplitude);

  // Keep refs current without restarting the animation loop
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { ampRef.current = amplitude; }, [amplitude]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = size;
    const h = size;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);

    const cx = w / 2;
    const cy = h / 2;
    const R = w * 0.44; // max radius
    let t = 0;

    function setGlow(color: string, blur: number) {
      if (!ctx) return;
      ctx.shadowColor = color;
      ctx.shadowBlur = blur;
    }

    function clearGlow() {
      if (!ctx) return;
      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
    }

    function arc(r: number, startAngle: number, endAngle: number, color: string, width: number, glow = 0) {
      if (!ctx) return;
      if (glow > 0) setGlow(color, glow);
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.arc(cx, cy, r, startAngle, endAngle);
      ctx.stroke();
      if (glow > 0) clearGlow();
    }

    function fullRing(r: number, color: string, width: number, glow = 0) {
      arc(r, 0, Math.PI * 2, color, width, glow);
    }

    function segmentedRing(r: number, segments: number, gapRatio: number, color: string, width: number, rotation: number, glow = 0) {
      if (!ctx) return;
      const segAngle = (Math.PI * 2) / segments;
      const drawAngle = segAngle * (1 - gapRatio);
      if (glow > 0) setGlow(color, glow);
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      for (let i = 0; i < segments; i++) {
        const start = rotation + i * segAngle;
        ctx.beginPath();
        ctx.arc(cx, cy, r, start, start + drawAngle);
        ctx.stroke();
      }
      if (glow > 0) clearGlow();
    }

    function dots(r: number, count: number, dotSize: number, color: string, rotation: number, squareStyle = false) {
      if (!ctx) return;
      ctx.fillStyle = color;
      for (let i = 0; i < count; i++) {
        const angle = rotation + (i / count) * Math.PI * 2;
        const x = cx + Math.cos(angle) * r;
        const y = cy + Math.sin(angle) * r;
        if (squareStyle) {
          ctx.fillRect(x - dotSize / 2, y - dotSize / 2, dotSize, dotSize);
        } else {
          ctx.beginPath();
          ctx.arc(x, y, dotSize, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    function ticks(innerR: number, outerR: number, count: number, color: string, width: number, rotation = 0) {
      if (!ctx) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      for (let i = 0; i < count; i++) {
        const angle = rotation + (i / count) * Math.PI * 2;
        const x1 = cx + Math.cos(angle) * innerR;
        const y1 = cy + Math.sin(angle) * innerR;
        const x2 = cx + Math.cos(angle) * outerR;
        const y2 = cy + Math.sin(angle) * outerR;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);

      const cfg = MODE_CFG[modeRef.current];
      const spd = cfg.speed;
      const al = cfg.alpha;
      const mc = cfg.color;
      const amp = ampRef.current;

      t += 0.005 * spd;

      // ── Background radial glow ──
      const bgGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.2);
      bgGlow.addColorStop(0, 'rgba(0, 50, 80, 0.15)');
      bgGlow.addColorStop(0.4, 'rgba(0, 30, 60, 0.08)');
      bgGlow.addColorStop(1, 'transparent');
      ctx.fillStyle = bgGlow;
      ctx.fillRect(0, 0, w, h);

      // ── LAYER 1: Outermost ring ──
      fullRing(R, `rgba(0,212,255,${0.08 * al})`, 1);
      arc(R, t * 0.1, t * 0.1 + Math.PI * 0.8, mc, 3 * al, 15 * al);
      arc(R, t * 0.1 + Math.PI * 1.1, t * 0.1 + Math.PI * 1.7, CYAN, 2 * al, 10 * al);
      dots(R, 40, 2, `rgba(0,212,255,${0.3 * al})`, 0, true);

      // ── LAYER 2: Outer tick ring ──
      const r2 = R * 0.92;
      ticks(r2 - 6, r2, 120, `rgba(0,212,255,${0.2 * al})`, 0.5);
      ticks(r2 - 10, r2, 24, `rgba(0,212,255,${0.5 * al})`, 1.2);
      for (let i = 0; i < 8; i++) {
        const angle = t * 0.15 + (i / 120) * Math.PI * 2;
        const x1 = cx + Math.cos(angle) * (r2 - 10);
        const y1 = cy + Math.sin(angle) * (r2 - 10);
        const x2 = cx + Math.cos(angle) * r2;
        const y2 = cy + Math.sin(angle) * r2;
        setGlow(mc, 8 * al);
        ctx.strokeStyle = mc;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        clearGlow();
      }

      // ── LAYER 3: Segmented ring ──
      const r3 = R * 0.84;
      segmentedRing(r3, 60, 0.35, `rgba(0,212,255,${0.15 * al})`, 2, -t * 0.2);
      dots(r3, 30, 3, `rgba(0,212,255,${0.25 * al})`, t * 0.05, true);
      arc(r3, -t * 0.2, -t * 0.2 + Math.PI * 0.4, mc, 3 * al, 12 * al);
      arc(r3, -t * 0.2 + Math.PI, -t * 0.2 + Math.PI * 1.3, CYAN, 2 * al, 8 * al);

      // ── LAYER 4: Thick ring ──
      const r4 = R * 0.74;
      fullRing(r4, `rgba(0,212,255,${0.12 * al})`, 1.5);
      arc(r4, t * 0.3, t * 0.3 + Math.PI * 1.2, mc, 4 * al, 20 * al);
      arc(r4, t * 0.3 + Math.PI * 1.5, t * 0.3 + Math.PI * 1.9, CYAN, 3 * al, 15 * al);

      // ── LAYER 5: Inner segmented ring ──
      const r5 = R * 0.64;
      segmentedRing(r5, 40, 0.3, `rgba(0,212,255,${0.2 * al})`, 2, t * 0.15);
      dots(r5 + 3, 40, 1.5, `rgba(0,212,255,${0.4 * al})`, t * 0.15);

      // ── LAYER 6: Waveform ring — reattivo al microfono ──
      const r6 = R * 0.55;
      const waveGain = 3 + amp * 18; // idle: 3px, max mic: ~21px
      ctx.strokeStyle = `rgba(0,212,255,${0.25 * al})`;
      ctx.lineWidth = 1 + amp;
      ctx.beginPath();
      for (let i = 0; i <= 360; i++) {
        const angle = (i / 360) * Math.PI * 2;
        const wave = Math.sin(i * 0.15 + t * 3) * waveGain * 0.5
                   + Math.sin(i * 0.08 + t * 2) * waveGain * 0.4;
        const rr = r6 + wave;
        const x = cx + Math.cos(angle) * rr;
        const y = cy + Math.sin(angle) * rr;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();

      // ── LAYER 7: Inner bright ring ──
      const r7 = R * 0.48;
      fullRing(r7, mc, 2 * al, 15 * al);
      fullRing(r7 - 4, `rgba(0,212,255,${0.15 * al})`, 0.5);

      // ── LAYER 8: Inner segmented ring ──
      const r8 = R * 0.40;
      segmentedRing(r8, 24, 0.4, `rgba(0,212,255,${0.3 * al})`, 1.5, -t * 0.25);
      arc(r8, -t * 0.25 + 0.5, -t * 0.25 + 1.2, mc, 2 * al, 10 * al);

      // ── LAYER 9: Inner glow circle ──
      const r9 = R * 0.32;
      fullRing(r9, `rgba(0,212,255,${0.1 * al})`, 1);
      const innerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, r9);
      innerGlow.addColorStop(0, `rgba(0, 80, 120, ${0.12 * al})`);
      innerGlow.addColorStop(0.7, `rgba(0, 50, 80, ${0.06 * al})`);
      innerGlow.addColorStop(1, 'transparent');
      ctx.fillStyle = innerGlow;
      ctx.beginPath();
      ctx.arc(cx, cy, r9, 0, Math.PI * 2);
      ctx.fill();

      // ── LAYER 10: Innermost ring ──
      const r10 = R * 0.25;
      fullRing(r10, mc, 1.5 * al, 12 * al);
      segmentedRing(r10 - 5, 16, 0.5, `rgba(0,212,255,${0.25 * al})`, 1, t * 0.4);

      // ── Center text ──
      if (showLabel) {
        setGlow(mc, 20 * al);
        ctx.fillStyle = mc;
        ctx.font = `bold ${Math.round(R * 0.11)}px "Inter Variable", monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('J.A.R.V.I.S', cx, cy - 2);
        clearGlow();

        const subLabel = modeRef.current === 'idle' ? 'MK2 SYSTEM ONLINE'
          : modeRef.current === 'awake' ? 'IN ASCOLTO...'
          : modeRef.current === 'listening' ? '● PARLAMI PURE'
          : modeRef.current === 'thinking' ? '▶ ELABORO...'
          : '◎ RISPONDO';

        ctx.fillStyle = `rgba(0,212,255,${0.4 * al})`;
        ctx.font = `${Math.round(R * 0.05)}px monospace`;
        ctx.fillText(subLabel, cx, cy + R * 0.08);
      }

      // ── Sweeping scanner line (compatible approach) ──
      const scanAngle = t * 0.8;
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R * 0.74, 0, Math.PI * 2);
      ctx.clip();
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.74);
      grad.addColorStop(0, 'transparent');
      grad.addColorStop(0.92, 'transparent');
      grad.addColorStop(0.96, 'rgba(0,212,255,0.08)');
      grad.addColorStop(1, 'rgba(0,212,255,0.18)');
      ctx.fillStyle = grad;
      ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
      // rotating bright line
      setGlow(CYAN, 12);
      ctx.strokeStyle = 'rgba(0,212,255,0.25)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(scanAngle) * R * 0.74, cy + Math.sin(scanAngle) * R * 0.74);
      ctx.stroke();
      clearGlow();
      ctx.restore();

      // ── Corner accents (decorative lines outside the main circle) ──
      const accentR = R * 1.05;
      for (let q = 0; q < 4; q++) {
        const base = (q / 4) * Math.PI * 2 + Math.PI / 4;
        arc(accentR, base - 0.08, base + 0.08, 'rgba(0,212,255,0.3)', 2, 6);
      }

      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [size, showLabel]); // mode/amplitude handled via refs — no restart needed

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none"
      style={{ display: 'block' }}
    />
  );
}
