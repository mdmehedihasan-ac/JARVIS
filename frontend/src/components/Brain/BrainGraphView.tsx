import { useEffect, useMemo, useRef, useState } from 'react';
import type { BrainGraph, BrainEdge, BrainNode } from '../../lib/api';

interface Props {
  graph: BrainGraph;
}

// Tiny force-directed layout (no deps). Good enough for ≤ 200 nodes.
// We run a fixed number of iterations on mount/graph-change, then render
// the result on an SVG with pan + zoom.

interface Sim {
  x: number;
  y: number;
  vx: number;
  vy: number;
  node: BrainNode;
}

const ITERATIONS = 220;
const W = 1200;
const H = 800;

function buildSim(graph: BrainGraph): { nodes: Sim[]; edges: BrainEdge[] } {
  const cx = W / 2;
  const cy = H / 2;
  const lobi = graph.nodes.filter((n) => n.type === 'lobo');
  const angleStep = (Math.PI * 2) / Math.max(lobi.length, 1);
  const lobeAnchor: Record<string, { x: number; y: number }> = {};
  lobi.forEach((l, i) => {
    const r = 230;
    lobeAnchor[l.id] = {
      x: cx + r * Math.cos(i * angleStep - Math.PI / 2),
      y: cy + r * Math.sin(i * angleStep - Math.PI / 2),
    };
  });

  const sim: Sim[] = graph.nodes.map((n) => {
    if (n.type === 'lobo') {
      const a = lobeAnchor[n.id];
      return { x: a.x, y: a.y, vx: 0, vy: 0, node: n };
    }
    const anchor = lobeAnchor[`lobo:${n.lobo}`] ?? { x: cx, y: cy };
    return {
      x: anchor.x + (Math.random() - 0.5) * 120,
      y: anchor.y + (Math.random() - 0.5) * 120,
      vx: 0,
      vy: 0,
      node: n,
    };
  });

  const byId: Record<string, Sim> = {};
  sim.forEach((s) => (byId[s.node.id] = s));

  const repulsion = 1800;
  const linkStrength = 0.02;
  const damping = 0.82;

  for (let it = 0; it < ITERATIONS; it++) {
    // repulsion (O(n^2) — fine for our scale)
    for (let i = 0; i < sim.length; i++) {
      for (let j = i + 1; j < sim.length; j++) {
        const a = sim[i];
        const b = sim[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) {
          d2 = 1;
          dx = Math.random();
          dy = Math.random();
        }
        const f = repulsion / d2;
        const fx = (dx / Math.sqrt(d2)) * f;
        const fy = (dy / Math.sqrt(d2)) * f;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }
    // attraction along edges
    for (const e of graph.edges) {
      const a = byId[e.source];
      const b = byId[e.target];
      if (!a || !b) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const ideal = e.type === 'membership' ? 90 : 180;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const diff = dist - ideal;
      const f = diff * linkStrength;
      const fx = (dx / dist) * f;
      const fy = (dy / dist) * f;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
    // lobi pinned (gentle pull to anchor)
    for (const s of sim) {
      if (s.node.type === 'lobo') {
        const a = lobeAnchor[s.node.id];
        s.vx += (a.x - s.x) * 0.05;
        s.vy += (a.y - s.y) * 0.05;
      }
    }
    // integrate
    for (const s of sim) {
      s.vx *= damping;
      s.vy *= damping;
      s.x += s.vx * 0.5;
      s.y += s.vy * 0.5;
    }
  }

  return { nodes: sim, edges: graph.edges };
}

export function BrainGraphView({ graph }: Props) {
  const layout = useMemo(() => buildSim(graph), [graph]);
  const [hovered, setHovered] = useState<BrainNode | null>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const draggingRef = useRef<{ x: number; y: number } | null>(null);

  const nodesById = useMemo(() => {
    const m: Record<string, Sim> = {};
    layout.nodes.forEach((n) => (m[n.node.id] = n));
    return m;
  }, [layout]);

  function onWheel(e: React.WheelEvent<SVGSVGElement>) {
    e.preventDefault();
    const next = Math.max(0.3, Math.min(2.5, scale * (e.deltaY > 0 ? 0.92 : 1.08)));
    setScale(next);
  }

  function onMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    draggingRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  }

  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!draggingRef.current) return;
    setPan({
      x: e.clientX - draggingRef.current.x,
      y: e.clientY - draggingRef.current.y,
    });
  }

  function onMouseUp() {
    draggingRef.current = null;
  }

  return (
    <div className="relative w-full h-full bg-[radial-gradient(ellipse_at_center,#0a1320_0%,#070b11_70%)]">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-full cursor-grab active:cursor-grabbing"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${scale})`}>
          {/* edges */}
          {layout.edges.map((e, i) => {
            const a = nodesById[e.source];
            const b = nodesById[e.target];
            if (!a || !b) return null;
            const isSyn = e.type === 'synapse';
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={isSyn ? '#ffffff22' : a.node.color || '#ffffff15'}
                strokeWidth={isSyn ? 1 : 1.4}
                strokeDasharray={isSyn ? '4 3' : undefined}
                opacity={isSyn ? 0.6 : 0.5}
              />
            );
          })}
          {/* nodes */}
          {layout.nodes.map((s) => {
            const n = s.node;
            const isLobo = n.type === 'lobo';
            return (
              <g
                key={n.id}
                transform={`translate(${s.x}, ${s.y})`}
                onMouseEnter={() => setHovered(n)}
                onMouseLeave={() => setHovered((h) => (h === n ? null : h))}
                style={{ cursor: 'pointer' }}
              >
                {isLobo && (
                  <circle
                    r={n.size + 6}
                    fill={`${n.color}22`}
                    stroke="none"
                    style={{ pointerEvents: 'none' }}
                  />
                )}
                <circle
                  r={n.size}
                  fill={isLobo ? `${n.color}55` : `${n.color}88`}
                  stroke={n.color}
                  strokeWidth={isLobo ? 2.5 : 1}
                  style={{
                    filter: isLobo
                      ? `drop-shadow(0 0 18px ${n.color}cc)`
                      : `drop-shadow(0 0 6px ${n.color}aa)`,
                  }}
                />
                {isLobo && (
                  <text
                    y={-n.size - 8}
                    textAnchor="middle"
                    fontSize={12}
                    fontWeight={600}
                    fill={n.color}
                    style={{ pointerEvents: 'none' }}
                  >
                    {n.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {layout.nodes.length > 0 &&
        layout.nodes.filter((s) => s.node.type === 'neurone').length === 0 && (
          <div className="absolute inset-0 grid place-items-center pointer-events-none">
            <div className="rounded-2xl bg-zinc-900/90 border border-zinc-800 px-6 py-5 text-center max-w-sm backdrop-blur shadow-2xl">
              <div className="text-jarvis-cyan text-2xl font-bold mb-1">6</div>
              <div className="text-sm font-semibold text-zinc-200">
                Lobi attivi · 0 neuroni
              </div>
              <p className="text-xs text-zinc-500 mt-2">
                Il cervello è inizializzato ma ancora vuoto. Inizia a conversare
                con JARVIS per creare la tua rete neurale personale.
              </p>
            </div>
          </div>
        )}

      {hovered && (
        <div className="absolute bottom-4 left-4 max-w-md rounded-xl bg-zinc-900/95 border border-zinc-800 px-4 py-3 backdrop-blur shadow-xl">
          <div
            className="text-xs font-semibold"
            style={{ color: hovered.color }}
          >
            {hovered.type === 'lobo' ? hovered.label : 'NEURONE'}
          </div>
          <div className="text-sm mt-0.5 text-zinc-100">
            {hovered.type === 'lobo'
              ? hovered.funzione
              : hovered.contenuto || hovered.label}
          </div>
          {hovered.type === 'neurone' && (
            <div className="mt-1 text-[11px] text-zinc-500 flex gap-3">
              <span>forza: {(hovered.forza ?? 0).toFixed(2)}</span>
              <span>lobo: {hovered.lobo}</span>
              {hovered.tags && hovered.tags.length > 0 && (
                <span>· tag: {hovered.tags.slice(0, 3).join(', ')}</span>
              )}
            </div>
          )}
        </div>
      )}
      <div className="absolute top-4 right-4 text-[11px] text-zinc-500 bg-zinc-900/80 border border-zinc-800 rounded-lg px-2 py-1 backdrop-blur">
        scroll zoom · drag pan
      </div>
    </div>
  );
}
