import React from 'react';

const LINKS = [
  { id: 'dashboard', label: '📊 Dashboard (Legacy)' },
  { id: 'realtime',  label: '📈 Real-Time Dashboard' },
  { id: 'logs',      label: '📝 Live Logs' },
  { id: 'flow',      label: '🚀 Live Payments + Root Cause' },
  { id: 'cascade',   label: '🔴 Cascade Simulation' },
  { id: 'graphify',  label: '🔗 Graphify' },
  { id: 'search',    label: '🤖 AI Root Cause' },
  { id: 'chat',      label: '💬 AI Chat' },
];

export default function NavBar({ page, navigate, services = [] }) {
  const downCount   = services.filter(s => s.status !== 'UP').length;
  const allUnknown  = services.every(s => s.status === 'UNKNOWN');
  const allUp       = downCount === 0 && !allUnknown;
  const dotClass    = allUnknown ? 'unknown' : allUp ? 'up' : 'down';
  const statusLabel = allUnknown ? 'Checking…' : allUp ? 'All systems operational' : `${downCount} service${downCount > 1 ? 's' : ''} down`;

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="brand-icon">⚡</span>
        <span className="brand-name">ClearFlow</span>
        <span className="brand-sub">ISO 20022 · NVIDIA Nemotron</span>
      </div>
      <div className="navbar-links">
        {LINKS.map(l => (
          <button key={l.id} className={`nav-link ${page === l.id ? 'active' : ''}`} onClick={() => navigate(l.id)}>
            {l.label}
          </button>
        ))}
      </div>
      <div className="status-indicator">
        <span className={`status-dot ${dotClass}`} style={{ width: 7, height: 7 }} />
        {statusLabel}
      </div>
    </nav>
  );
}
