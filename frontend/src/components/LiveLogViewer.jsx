import React, { useState, useEffect, useRef } from 'react';

// Ensure token is set for ES queries
const DEV_TOKEN = 'eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiZGVtby1vcHMiLCAiaXNzIjogImNsZWFyZmxvdy1kZXYiLCAiaWF0IjogMTc3ODg2MTYxMSwgImV4cCI6IDE4OTM0NTYwMDAsICJzY29wZSI6ICJtY3A6cmVhZCBtY3A6YWRtaW4ifQ._Iz89MiCOyVY9m0MUsuSJhlFqsXY-OYvlV2ML2SFPuQ';
if (!localStorage.getItem('clearflow_token')) {
  localStorage.setItem('clearflow_token', DEV_TOKEN);
}

const C = {
  bg: '#0d1117', surface: '#161b22', border: '#30363d',
  accent: '#58a6ff', success: '#3fb950', danger: '#f85149',
  warn: '#d29922', muted: '#8b949e', text: '#e6edf3', purple: '#a371f7',
};

const SERVICE_COLORS = {
  'gateway': '#58a6ff',
  'fraud-scoring': '#f97316',
  'validation': '#ec4899',
  'aml-compliance': '#f85149',
  'routing': '#8b5cf6',
  'settlement': '#3fb950',
  'audit': '#06b6d4',
  'mcp': '#a371f7',
};

async function fetchLogs(size = 50, filterPaymentId = null) {
  try {
    const query = filterPaymentId
      ? {
          query: {
            bool: {
              should: [
                { term: { 'paymentId.keyword': filterPaymentId } },
                { term: { 'correlationId.keyword': filterPaymentId } },
                { match: { paymentId: filterPaymentId } },
              ],
              minimum_should_match: 1,
            },
          },
        }
      : {
          query: {
            bool: {
              must_not: [
                { match_phrase: { message: 'Seeking to offset' } },
                { match_phrase: { message: 'Error handler threw an exception' } },
                { match_phrase: { message: 'Idempotency skip' } },
                { match_phrase: { message: 'clearflow.mcp.access' } },
                { match_phrase: { message: 'Error reading request, ignored' } },
              ],
            },
          },
        };

    // Use Vite proxy (/es → localhost:9200) — never call ES directly from browser
    const resp = await fetch('/es/clearflow-*/_search?size=' + size, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...query,
        sort: [{ '@timestamp': { order: 'desc' } }],
      }),
    });

    if (!resp.ok) return [];

    const data = await resp.json();
    return data.hits?.hits || [];
  } catch {
    return [];
  }
}

function extractService(log) {
  const source = log._source || {};
  if (source.service) return source.service;
  if (source.logger_name) {
    const match = source.logger_name.match(/com\.clearflow\.(\w+)/);
    if (match) return match[1];
  }
  return 'unknown';
}

function LogEntry({ log, onClickId }) {
  const source = log._source || {};
  const service = extractService(log);
  const color = SERVICE_COLORS[service] || C.muted;
  const timestamp = source['@timestamp'] ? new Date(source['@timestamp']).toLocaleTimeString() : '—';
  const level = source.level || 'INFO';
  const message = source.message || JSON.stringify(source).slice(0, 100);
  const correlationId = source.correlationId;
  const paymentId = source.paymentId || source.instructionId;

  const levelColor = level === 'ERROR' ? C.danger : level === 'WARN' ? C.warn : level === 'DEBUG' ? C.muted : C.success;

  return (
    <div style={{
      display: 'flex',
      gap: 10,
      padding: '8px 12px',
      background: log._index % 2 ? '#21262d' : '#161b22',
      borderBottom: `1px solid ${C.border}33`,
      fontSize: 11,
      fontFamily: 'monospace',
      borderLeft: `3px solid ${color}`,
    }}>
      <span style={{ color: C.muted, minWidth: 75 }}>{timestamp}</span>
      <span style={{ color, fontWeight: 700, minWidth: 100 }}>{service.toUpperCase()}</span>
      <span style={{ color: levelColor, minWidth: 50, fontWeight: 600 }}>{level}</span>
      <span style={{ flex: 1, color: C.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {message}
      </span>
      {paymentId && (
        <button
          onClick={() => onClickId(paymentId)}
          style={{
            background: 'transparent',
            border: 'none',
            color: C.accent,
            cursor: 'pointer',
            textDecoration: 'underline',
            minWidth: 100,
            textAlign: 'right',
            padding: 0,
            fontFamily: 'monospace',
            fontSize: 10,
          }}
        >
          {paymentId.slice(0, 8)}
        </button>
      )}
    </div>
  );
}

export default function LiveLogViewer() {
  const [logs, setLogs] = useState([]);
  const [autoscroll, setAutoscroll] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [traceLog, setTraceLog] = useState([]);
  const scrollRef = useRef(null);
  const logListRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoscroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoscroll]);

  // Poll logs every 2 seconds
  useEffect(() => {
    const pollLogs = async () => {
      const newLogs = await fetchLogs(50);
      setLogs(newLogs);
    };

    pollLogs();
    const interval = setInterval(pollLogs, 2000);
    return () => clearInterval(interval);
  }, []);

  // Load trace for selected ID
  useEffect(() => {
    const loadTrace = async () => {
      if (!selectedId) {
        setTraceLog([]);
        return;
      }
      const traceLogs = await fetchLogs(100, selectedId);
      setTraceLog(traceLogs);
    };

    loadTrace();
  }, [selectedId]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: 'calc(100vh - 200px)' }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, marginBottom: 4 }}>Live Log Viewer</h1>
        <p style={{ fontSize: 12, color: C.muted }}>Real-time Elasticsearch log tail with service filtering and payment tracing</p>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: C.text }}>
          <input
            type="checkbox"
            checked={autoscroll}
            onChange={(e) => setAutoscroll(e.target.checked)}
            style={{ cursor: 'pointer' }}
          />
          Autoscroll
        </label>
        {selectedId && (
          <>
            <span style={{ fontSize: 12, color: C.muted }}>
              Tracing: <span style={{ color: C.accent, fontFamily: 'monospace' }}>{selectedId.slice(0, 12)}...</span>
            </span>
            <button
              onClick={() => setSelectedId(null)}
              style={{
                background: 'transparent',
                border: `1px solid ${C.border}`,
                color: C.muted,
                padding: '4px 10px',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 11,
              }}
            >
              Clear Trace
            </button>
          </>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: C.muted }}>
          {selectedId ? `${traceLog.length} trace entries` : `${logs.length} recent logs`}
        </span>
      </div>

      {/* Main log display */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          background: C.bg,
          border: `1px solid ${C.border}`,
          borderRadius: 6,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div style={{ flex: 1 }}>
          {(selectedId ? traceLog : logs).length === 0 ? (
            <div style={{ padding: 20, color: C.muted, textAlign: 'center' }}>
              {selectedId ? 'No trace entries found' : 'Waiting for logs...'}
            </div>
          ) : (
            (selectedId ? traceLog : logs).map((log, i) => (
              <LogEntry key={i} log={log} onClickId={setSelectedId} />
            ))
          )}
        </div>
      </div>

      {/* Service Legend */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, padding: 12 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
          Service Colors
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
          {Object.entries(SERVICE_COLORS).map(([service, color]) => (
            <div key={service} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
              <span style={{ color: C.text, textTransform: 'capitalize' }}>{service.replace('-', ' ')}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Info */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}55`, borderRadius: 6, padding: 12, fontSize: 11, color: C.muted }}>
        <strong style={{ color: C.text }}>💡 How to use:</strong> Logs auto-refresh every 2 seconds. Click a payment ID in the right column to see the full payment trace across all services. Use the Clear Trace button to return to live view.
      </div>
    </div>
  );
}
