import React from 'react';

const C = {
  bg: '#0d1117', surface: '#161b22', border: '#30363d',
  accent: '#58a6ff', muted: '#8b949e', text: '#e6edf3',
};

function GraphifyViewer() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: 'calc(100vh - 120px)' }}>
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: 0 }}>
            🔗 ClearFlow Codebase Architecture Graph
          </h2>
          <p style={{ fontSize: 12, color: C.muted, margin: '4px 0 0 0' }}>
            Interactive knowledge graph — all 8 microservices, dependencies, and code structure. Click nodes to explore.
          </p>
        </div>
        <a
          href="/graphify-out/graph.html"
          target="_blank"
          rel="noreferrer"
          style={{
            fontSize: 11, color: C.accent, background: C.accent + '18',
            border: `1px solid ${C.accent}44`, borderRadius: 6,
            padding: '5px 12px', textDecoration: 'none', fontWeight: 600,
          }}
        >
          ↗ Open Full Screen
        </a>
      </div>

      <div style={{ flex: 1, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
        <iframe
          title="Graphify — ClearFlow Codebase Graph"
          src="/graphify-out/graph.html"
          style={{ width: '100%', height: '100%', border: 'none' }}
        />
      </div>
    </div>
  );
}

export default GraphifyViewer;
