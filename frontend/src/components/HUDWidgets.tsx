import { useEffect, useRef } from 'react';

/* ── Mini waveform / audio visualizer ──────────────────────────────── */
export function MiniWaveform({ width = 160, height = 40 }: { width?: number; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);
    let t = 0;

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      t += 0.04;
      ctx.strokeStyle = 'rgba(0,212,255,0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x < width; x++) {
        const y = height / 2 + Math.sin(x * 0.08 + t) * 8 + Math.sin(x * 0.15 + t * 1.3) * 4 + Math.sin(x * 0.03 + t * 0.7) * 6;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Second wave
      ctx.strokeStyle = 'rgba(0,212,255,0.2)';
      ctx.beginPath();
      for (let x = 0; x < width; x++) {
        const y = height / 2 + Math.sin(x * 0.06 + t * 0.8 + 1) * 10 + Math.cos(x * 0.12 + t * 1.1) * 3;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      animRef.current = requestAnimationFrame(draw);
    }
    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [width, height]);

  return <canvas ref={canvasRef} className="pointer-events-none" />;
}

/* ── Mini bar chart ────────────────────────────────────────────────── */
export function MiniBarChart({ width = 120, height = 35, bars = 16 }: { width?: number; height?: number; bars?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);
    let t = 0;
    const barW = (width - bars * 2) / bars;

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      t += 0.02;
      for (let i = 0; i < bars; i++) {
        const h = (Math.sin(i * 0.5 + t) * 0.5 + 0.5) * height * 0.8 + height * 0.1;
        const x = i * (barW + 2);
        const alpha = 0.3 + (h / height) * 0.5;
        ctx.fillStyle = `rgba(0,212,255,${alpha})`;
        ctx.fillRect(x, height - h, barW, h);
      }
      animRef.current = requestAnimationFrame(draw);
    }
    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [width, height, bars]);

  return <canvas ref={canvasRef} className="pointer-events-none" />;
}

/* ── Mini line graph ───────────────────────────────────────────────── */
export function MiniLineGraph({ width = 140, height = 40 }: { width?: number; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);
    let t = 0;

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);
      t += 0.03;
      // Grid
      ctx.strokeStyle = 'rgba(0,212,255,0.06)';
      ctx.lineWidth = 0.5;
      for (let y = 0; y < height; y += 8) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
      }
      // Line
      ctx.strokeStyle = 'rgba(0,212,255,0.6)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x < width; x++) {
        const y = height * 0.5 + Math.sin(x * 0.05 + t) * height * 0.25 + Math.sin(x * 0.12 + t * 2) * height * 0.1;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      // Fill under
      ctx.lineTo(width, height);
      ctx.lineTo(0, height);
      ctx.closePath();
      ctx.fillStyle = 'rgba(0,212,255,0.04)';
      ctx.fill();
      animRef.current = requestAnimationFrame(draw);
    }
    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [width, height]);

  return <canvas ref={canvasRef} className="pointer-events-none" />;
}

/* ── HUD Panel wrapper ─────────────────────────────────────────────── */
export function HUDPanel({
  title,
  children,
  className = '',
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`hud-panel hud-corner rounded-sm ${className}`}>
      {title && (
        <div className="px-2 py-1 border-b border-[#00d4ff]/10">
          <span className="text-[8px] font-mono tracking-[0.2em] text-[#00d4ff]/30 uppercase">{title}</span>
        </div>
      )}
      <div className="p-2">{children}</div>
    </div>
  );
}

/* ── Clock display ─────────────────────────────────────────────────── */
export function HUDClock() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const w = 100, h = 30;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      const now = new Date();
      const time = now.toLocaleTimeString('it-IT', { hour12: false });
      ctx.fillStyle = '#00d4ff';
      ctx.shadowColor = '#00d4ff';
      ctx.shadowBlur = 10;
      ctx.font = 'bold 16px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(time, w / 2, h / 2);
      ctx.shadowBlur = 0;
      animRef.current = requestAnimationFrame(draw);
    }
    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  return <canvas ref={canvasRef} className="pointer-events-none" />;
}
