import React, { useState } from 'react';

const C = {
  bg: '#0d1117', surface: '#161b22', border: '#30363d',
  accent: '#58a6ff', success: '#3fb950', muted: '#8b949e', text: '#e6edf3',
};

function DashboardTabs() {
  const [activeTab, setActiveTab] = useState('kibana');

  const tabs = [
    {
      id: 'kibana',
      label: '📊 Kibana - Logs',
      url: 'http://localhost:5601/app/discover',
      description: 'Search and analyze all payment logs with full correlationId tracing',
    },
    {
      id: 'grafana',
      label: '📈 Grafana - Metrics',
      url: 'http://localhost:3000/d/clearflow-payments',
      description: 'Real-time metrics: throughput, latency, success rate',
    },
    {
      id: 'prometheus',
      label: '⚙️ Prometheus - Raw Data',
      url: 'http://localhost:9090/graph',
      description: 'Raw Prometheus metrics explorer',
    },
    {
      id: 'jaeger',
      label: '🔍 Jaeger - Traces',
      url: 'http://localhost:16686/search',
      description: 'Distributed tracing: see each payment flowing through 7 services',
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: 'calc(100vh - 200px)' }}>
      {/* Tab Navigation */}
      <div style={{
        display: 'flex',
        gap: 8,
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderBottom: `2px solid ${C.border}`,
        padding: 12,
        borderRadius: '8px 8px 0 0',
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: activeTab === tab.id ? C.accent : 'transparent',
              color: activeTab === tab.id ? C.bg : C.muted,
              border: 'none',
              padding: '8px 16px',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 12,
              transition: 'all 0.2s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Description */}
      <div style={{
        background: C.bg,
        padding: '12px 16px',
        fontSize: 12,
        color: C.muted,
        borderBottom: `1px solid ${C.border}`,
      }}>
        {tabs.find(t => t.id === activeTab)?.description}
      </div>

      {/* Tab Content */}
      <div style={{
        flex: 1,
        background: C.bg,
        borderRadius: '0 0 8px 8px',
        overflow: 'hidden',
      }}>
        {tabs.map(tab => (
          activeTab === tab.id && (
            <div key={tab.id} style={{ width: '100%', height: '100%' }}>
              <iframe
                title={tab.label}
                src={tab.url}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                }}
              />
            </div>
          )
        ))}
      </div>

      {/* Info Box */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '0 0 8px 8px',
        padding: 12,
        fontSize: 11,
        color: C.muted,
        marginTop: 8,
      }}>
        <strong style={{ color: C.text }}>💡 Tip:</strong> All dashboards are pre-configured. No manual setup needed.
        Just browse the analytics.
      </div>
    </div>
  );
}

export default DashboardTabs;
