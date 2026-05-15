import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import type { BrainStato } from '../../lib/api';

/* ─── layout 3D ───────────────────────────────────────────────────── */
const LOBE_POS: Record<string, [number, number, number]> = {
  frontale:   [ 0.0,  2.0,  1.8],
  temporale:  [ 2.6,  0.0,  0.0],
  parietale:  [-2.6,  0.0,  0.0],
  occipitale: [ 0.0,  0.4, -2.4],
  cerebellum: [ 0.0, -2.5,  0.0],
  ippocampo:  [ 0.0,  0.0,  0.0],
};

interface Props { stato: BrainStato | null }
interface LobeInfo {
  key: string; nome: string; colore: string;
  neuroni: number; carico: number;
  top: Array<{ contenuto: string; forza: number }>;
}

/* ─── neurone singolo ─────────────────────────────────────────────── */
function NeuronDot({ position, color, forza, idx }: {
  position: [number, number, number]; color: string; forza: number; idx: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const baseR = 0.04 + forza * 0.05;

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.elapsedTime;
    const pulse = 1 + Math.sin(t * 2.5 + idx * 1.7) * 0.25;
    ref.current.scale.setScalar(pulse);
  });

  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[baseR, 12, 12]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={2}
        toneMapped={false}
      />
    </mesh>
  );
}

/* ─── lobo ────────────────────────────────────────────────────────── */
function LobeNode({ data }: { data: LobeInfo }) {
  const pos = LOBE_POS[data.key];
  const coreRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);

  const neuronOffsets = useMemo(() => {
    const pts: [number, number, number][] = [];
    const n = Math.min(data.neuroni, 24);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      const y = 1 - (i / Math.max(n - 1, 1)) * 2;
      const rad = Math.sqrt(1 - y * y);
      const th = golden * i;
      const r = 0.55 + (data.top[i]?.forza ?? 0.5) * 0.35;
      pts.push([Math.cos(th) * rad * r, y * r, Math.sin(th) * rad * r]);
    }
    return pts;
  }, [data.neuroni, data.top]);

  const baseSize = 0.7 + Math.min(data.neuroni, 20) * 0.025;

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (coreRef.current) {
      coreRef.current.scale.setScalar(1 + Math.sin(t * 1.5 + pos[0]) * 0.06);
      coreRef.current.rotation.y = t * 0.15;
    }
    if (glowRef.current) {
      glowRef.current.scale.setScalar(1 + Math.sin(t * 0.8) * 0.1);
    }
  });

  return (
    <group position={pos}>
      {/* glow esterno */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[baseSize * 1.3, 24, 24]} />
        <meshBasicMaterial
          color={data.colore}
          transparent
          opacity={0.08 + data.carico * 0.1}
          side={THREE.BackSide}
          depthWrite={false}
        />
      </mesh>

      {/* core */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[baseSize * 0.35, 16, 16]} />
        <meshStandardMaterial
          color={data.colore}
          emissive={data.colore}
          emissiveIntensity={1.2 + data.carico * 0.8}
          transparent
          opacity={0.85}
          toneMapped={false}
        />
      </mesh>

      {/* label HTML overlay */}
      <Html
        position={[0, baseSize * 1.5, 0]}
        center
        distanceFactor={8}
        zIndexRange={[0, 0]}
        style={{ pointerEvents: 'none' }}
      >
        <div className="text-center select-none whitespace-nowrap">
          <div
            className="text-xs font-bold tracking-wider drop-shadow-[0_0_4px_rgba(0,0,0,0.9)]"
            style={{ color: data.colore }}
          >
            {data.nome.toUpperCase()}
          </div>
          <div className="text-[10px] text-white/40 mt-0.5">
            {data.neuroni} neuroni
          </div>
        </div>
      </Html>

      {/* neuroni */}
      {neuronOffsets.map((off, i) => (
        <NeuronDot
          key={i}
          position={off}
          color={data.colore}
          forza={data.top[i]?.forza ?? 0.5}
          idx={i}
        />
      ))}
    </group>
  );
}

/* ─── connessioni curve tra lobi ──────────────────────────────────── */
function Connections({ lobes }: { lobes: LobeInfo[] }) {
  const lines = useMemo(() => {
    const result: THREE.Line[] = [];
    for (let i = 0; i < lobes.length; i++) {
      for (let j = i + 1; j < lobes.length; j++) {
        const from = new THREE.Vector3(...LOBE_POS[lobes[i].key]);
        const to = new THREE.Vector3(...LOBE_POS[lobes[j].key]);
        const mid = from.clone().lerp(to, 0.5);
        mid.y += 0.4;
        const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
        const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(24));
        const mat = new THREE.LineBasicMaterial({
          color: lobes[i].colore,
          transparent: true,
          opacity: 0.15,
          depthWrite: false,
        });
        result.push(new THREE.Line(geo, mat));
      }
    }
    return result;
  }, [lobes]);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    lines.forEach((ln, i) => {
      (ln.material as THREE.LineBasicMaterial).opacity =
        0.08 + Math.sin(t * 0.6 + i * 0.5) * 0.05;
    });
  });

  return (
    <group>
      {lines.map((ln, i) => <primitive key={i} object={ln} />)}
    </group>
  );
}

/* ─── particelle che viaggiano lungo le connessioni ───────────────── */
function EnergyDots({ lobes }: { lobes: LobeInfo[] }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);

  const routes = useMemo(() => {
    const r: Array<{ from: THREE.Vector3; to: THREE.Vector3; speed: number; off: number; col: string }> = [];
    if (lobes.length < 2) return r;
    for (let i = 0; i < 18; i++) {
      const a = lobes[i % lobes.length];
      const b = lobes[(i + 1 + Math.floor(i / 3)) % lobes.length];
      if (a.key === b.key) continue;
      r.push({
        from: new THREE.Vector3(...LOBE_POS[a.key]),
        to: new THREE.Vector3(...LOBE_POS[b.key]),
        speed: 0.25 + (i % 5) * 0.08,
        off: (i * 0.37) % 1,
        col: a.colore,
      });
    }
    return r;
  }, [lobes]);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    routes.forEach((rt, i) => {
      const m = refs.current[i];
      if (!m) return;
      const prog = ((t * rt.speed + rt.off) % 1 + 1) % 1;
      m.position.lerpVectors(rt.from, rt.to, prog);
      m.position.y += Math.sin(prog * Math.PI) * 0.5;
      const s = 0.025 + Math.sin(prog * Math.PI) * 0.025;
      m.scale.setScalar(s);
      const mat = m.material as THREE.MeshBasicMaterial;
      mat.opacity = Math.sin(prog * Math.PI) * 0.95;
    });
  });

  return (
    <group>
      {routes.map((rt, i) => (
        <mesh
          key={i}
          ref={(el) => { refs.current[i] = el; }}
        >
          <sphereGeometry args={[1, 8, 8]} />
          <meshBasicMaterial
            color={rt.col}
            transparent
            opacity={0}
            toneMapped={false}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  );
}

/* ─── sfondo stelle ───────────────────────────────────────────────── */
function Stars() {
  const ref = useRef<THREE.Points>(null);
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const n = 800;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 18 + Math.random() * 22;
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      pos[i * 3]     = r * Math.sin(ph) * Math.cos(th);
      pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
      pos[i * 3 + 2] = r * Math.cos(ph);
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);

  useFrame(({ clock }) => {
    if (ref.current) ref.current.rotation.y = clock.elapsedTime * 0.012;
  });

  return (
    <points ref={ref} geometry={geo}>
      <pointsMaterial color="#7788aa" size={0.05} transparent opacity={0.5} sizeAttenuation />
    </points>
  );
}

/* ─── scena ───────────────────────────────────────────────────────── */
function Scene({ stato }: { stato: BrainStato | null }) {
  const lobes: LobeInfo[] = useMemo(() => {
    if (!stato) return [];
    return Object.entries(stato.lobi).map(([key, l]) => ({
      key, nome: l.nome, colore: l.colore, neuroni: l.neuroni,
      carico: l.carico, top: l.top,
    }));
  }, [stato]);

  return (
    <>
      <ambientLight intensity={0.3} />
      <pointLight position={[6, 6, 6]} intensity={1} color="#ffffff" />
      <pointLight position={[-5, -3, -4]} intensity={0.4} color="#7b2fff" />
      <pointLight position={[0, -5, 3]} intensity={0.3} color="#00d4ff" />

      <Stars />

      {lobes.map(l => <LobeNode key={l.key} data={l} />)}
      {lobes.length > 1 && <Connections lobes={lobes} />}
      {lobes.length > 1 && <EnergyDots lobes={lobes} />}

      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        autoRotate
        autoRotateSpeed={0.4}
        minDistance={3}
        maxDistance={20}
        dampingFactor={0.06}
        enableDamping
      />
    </>
  );
}

/* ─── export ──────────────────────────────────────────────────────── */
export function Brain3DView({ stato }: Props) {
  const [wsOk, setWsOk] = useState(false);

  useEffect(() => {
    const url = `ws://${window.location.hostname}:8765/ws/events`;
    let ws: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    function connect() {
      try {
        ws = new WebSocket(url);
        ws.onopen = () => setWsOk(true);
        ws.onclose = () => { setWsOk(false); retry = setTimeout(connect, 3000); };
        ws.onerror = () => ws?.close();
      } catch { /* ignore */ }
    }
    connect();
    return () => { clearTimeout(retry); ws?.close(); };
  }, []);

  const totalN = stato?.totale_neuroni ?? 0;

  return (
    <div className="relative w-full h-full" style={{ background: '#050a14' }}>
      <Canvas
        camera={{ position: [0, 2, 8], fov: 45 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true }}
        style={{ background: '#050a14' }}
        onCreated={({ gl }) => {
          gl.setClearColor(new THREE.Color('#050a14'), 1);
        }}
      >
        <Scene stato={stato} />
      </Canvas>

      <div className="absolute top-4 left-4 pointer-events-none select-none">
        <div className="bg-black/60 backdrop-blur border border-white/10 rounded-2xl px-5 py-3">
          <div className="text-[10px] text-white/40 uppercase tracking-[0.15em]">Neural Network</div>
          <div className="text-2xl font-light text-white tabular-nums mt-0.5">{totalN}</div>
          <div className="text-[10px] text-white/30">neuroni · 6 lobi</div>
        </div>
      </div>

      <div className="absolute top-4 right-4 pointer-events-none select-none">
        <div className="bg-black/60 backdrop-blur border border-white/10 rounded-xl px-3 py-1.5 flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${wsOk ? 'bg-emerald-400 shadow-[0_0_6px_#34d399]' : 'bg-zinc-600'}`} />
          <span className="text-[10px] text-white/40">{wsOk ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </div>

      <div className="absolute bottom-4 right-4 pointer-events-none select-none">
        <div className="bg-black/40 border border-white/5 rounded-lg px-3 py-1.5 text-[9px] text-white/20">
          scroll zoom · drag orbita · destro pan
        </div>
      </div>

      {totalN === 0 && (
        <div className="absolute inset-0 grid place-items-center pointer-events-none">
          <div className="bg-black/80 border border-white/10 rounded-2xl px-10 py-8 text-center backdrop-blur">
            <div className="w-10 h-10 mx-auto mb-3 rounded-full border border-cyan-500/30 grid place-items-center">
              <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
            </div>
            <div className="text-sm font-medium text-white/80">Cervello inizializzato</div>
            <p className="text-[11px] text-white/30 mt-2 max-w-[220px]">
              Conversa con JARVIS per far crescere la rete neurale in 3D.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
