import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { OrbPage } from './pages/OrbPage';
import { ChatPage } from './pages/ChatPage';
import { BrainPage } from './pages/BrainPage';
import { SkillsPage } from './pages/SkillsPage';
import { AgentsPage } from './pages/AgentsPage';
import { SettingsPage } from './pages/SettingsPage';
import { api } from './lib/api';
import { useApp } from './lib/store';

export default function App() {
  const setHealth = useApp((s) => s.setHealth);

  useEffect(() => {
    let alive = true;
    const refresh = () => {
      api
        .health()
        .then((h) => {
          if (alive) setHealth(h);
        })
        .catch(() => alive && setHealth(null));
    };
    refresh();
    const t = setInterval(refresh, 10_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [setHealth]);

  return (
    <Routes>
      {/* ── Standalone fullscreen ORB (no Layout navbar) ── */}
      <Route index element={<OrbPage />} />
      <Route path="orb" element={<OrbPage />} />

      {/* ── HUD Layout with nav ── */}
      <Route element={<Layout />}>
        <Route path="chat" element={<ChatPage />} />
        <Route path="brain" element={<BrainPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
