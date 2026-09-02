import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import NavBar from './components/NavBar.jsx';
import PaymentSearch from './components/PaymentSearch.jsx';
import Chat from './components/Chat.jsx';
import PaymentFlowFixed from './components/PaymentFlowFixed.jsx';
import GraphifyViewer from './components/GraphifyViewer.jsx';
import CascadeSimulation from './components/CascadeSimulation.jsx';
import EnhancedDashboard from './components/EnhancedDashboard.jsx';
import LiveLogViewer from './components/LiveLogViewer.jsx';
import {
  fetchOverview, fetchRails, fetchFraudMetrics,
  fetchAlerts, fetchSystemicHealth, fetchServiceHealth,
  cacheRead,
} from './api/clearflow.js';

// Dev token (HS256, expires 2030) — written at module load so all API calls have auth immediately
const DEV_TOKEN = 'eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiZGVtby1vcHMiLCAiaXNzIjogImNsZWFyZmxvdy1kZXYiLCAiaWF0IjogMTc3ODg2MTYxMSwgImV4cCI6IDE4OTM0NTYwMDAsICJzY29wZSI6ICJtY3A6cmVhZCBtY3A6YWRtaW4ifQ._Iz89MiCOyVY9m0MUsuSJhlFqsXY-OYvlV2ML2SFPuQ';
if (!localStorage.getItem('clearflow_token')) {
  localStorage.setItem('clearflow_token', DEV_TOKEN);
}

// ── Colours ──────────────────────────────────────────────────
// Recharts renders to SVG and needs real color strings, not CSS classes --
// these values MUST match app.css's :root custom properties exactly (kept
// as the single source of truth; this is a mirror, not a second palette).
// className use elsewhere in this file always prefers the CSS classes
// (.c-accent, .stat-card.accent-*, etc.) over this object.
const CHART_COLORS = {
  border: '#1e2a3a', surface2: '#1e293b', text: '#f1f5f9', muted: '#94a3b8',
  accent: '#00d4aa', blue: '#3b82f6', purple: '#8b5cf6',
  amber: '#f59e0b', red: '#ef4444', green: '#10b981',
};

const RAIL_COLORS = {
  SEPA_INSTANT: '#00d4aa', SWIFT_GPI: '#3b82f6', FEDWIRE: '#8b5cf6',
  CHIPS: '#f59e0b', FASTER_PAYMENTS: '#06b6d4', CHAPS: '#10b981',
  SEPA_CT: '#6366f1', SWIFT_MT103: '#ec4899', SEPA_CREDIT_TRANSFER: '#00d4aa',
  OTHER: '#64748b',
};
const FRAUD_COLORS = [CHART_COLORS.green, CHART_COLORS.amber, CHART_COLORS.red, '#ff2222'];

const SERVICES = [
  { name: 'Gateway',          port: 8080 },
  { name: 'Fraud Scoring',    port: 8081 },
  { name: 'Validation',       port: 8082 },
  { name: 'AML Compliance',   port: 8083 },
  { name: 'Routing',          port: 8084 },
  { name: 'Settlement',       port: 8085 },
  { name: 'Audit',            port: 8086 },
  { name: 'MCP AI Gateway',   port: 8087 },
];

// ── Helpers ──────────────────────────────────────────────────
function fmt(n) { return n == null ? '—' : Number(n).toLocaleString(); }
function fmtTs(ts) { try { return new Date(ts).toLocaleTimeString(); } catch { return ts; } }

// ── Components ───────────────────────────────────────────────
// accent props below reference the .stat-card.accent-* / .c-* utility
// classes in app.css -- keeps every colored element on the same shared
// palette instead of a one-off hex value per call site.
function KPI({ label, value, sub, accent = 'accent' }) {
  return (
    <div className={`stat-card${accent !== 'accent' ? ` accent-${accent}` : ''}`}>
      <div className={`stat-value c-${accent}`}>{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function Card({ title, badge, children }) {
  return (
    <div className="chart-card">
      {(title || badge) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          {title && <div className="chart-title" style={{ marginBottom: 0 }}>{title}</div>}
          {badge && (
            <span
              className="badge"
              style={{
                marginLeft: 'auto', letterSpacing: 1,
                color: `var(--${badge.accent})`, background: `var(--${badge.accent})22`,
                border: `1px solid var(--${badge.accent})44`,
              }}
            >
              {badge.label}
            </span>
          )}
        </div>
      )}
      {children}
    </div>
  );
}

function ServiceBadge({ svc }) {
  const statusClass = svc.status === 'UP' ? 'up' : svc.status === 'UNKNOWN' ? 'unknown' : 'down';
  const badgeClass = svc.status === 'UP' ? 'badge-green' : svc.status === 'UNKNOWN' ? 'badge' : 'badge-red';
  return (
    <div className="service-card">
      <div className={`status-dot ${statusClass}`} />
      <div style={{ flex: 1 }}>
        <div className="service-name">{svc.name}</div>
        <div className="service-port">:{svc.port}</div>
      </div>
      <span className={badgeClass}>{svc.status}</span>
    </div>
  );
}

function AlertRow({ service, count }) {
  const severity = count >= 50 ? 'CRITICAL' : count >= 10 ? 'HIGH' : 'MEDIUM';
  const accent = severity === 'CRITICAL' ? 'red' : severity === 'HIGH' ? 'amber' : 'accent';
  return (
    <div className="alert-row">
      <div className="alert-dot" style={{ background: `var(--${accent})` }} />
      <span className="alert-service">{service}</span>
      <span className="alert-count">{fmt(count)} alerts</span>
      <span className={`alert-severity c-${accent}`} style={{ background: `var(--${accent})22` }}>{severity}</span>
    </div>
  );
}

// ── Pull stored cache for instant paint ─────────────────────
function seedFromCache() {
  const ov  = cacheRead('overview')?.data ?? null;
  const rl  = cacheRead('rails')?.data;
  const fr  = cacheRead('fraud')?.data;
  const sh  = cacheRead('services')?.data ?? {};
  const ts  = [cacheRead('overview'), cacheRead('rails'), cacheRead('fraud')]
    .filter(Boolean).reduce((min, r) => Math.min(min, r.ts), Infinity);
  return {
    overview: ov,
    rails: rl && typeof rl === 'object'
      ? Object.entries(rl).map(([rail, count]) => ({ rail, count: Number(count || 0) })).sort((a, b) => b.count - a.count)
      : [],
    fraud: fr && typeof fr === 'object'
      ? Object.entries(fr).map(([band, count]) => ({ band, count: Number(count || 0) }))
      : [],
    services: SERVICES.map(s => ({ ...s, status: sh[s.name] ?? 'UNKNOWN' })),
    staleTs: isFinite(ts) ? ts : null,
  };
}

// ── Main Dashboard ───────────────────────────────────────────
function Dashboard({ onServicesChange }) {
  const seed = seedFromCache();
  const [overview,   setOverview]   = useState(seed.overview);
  const [rails,      setRails]      = useState(seed.rails);
  const [fraud,      setFraud]      = useState(seed.fraud);
  const [alerts,     setAlerts]     = useState(null);
  const [systemic,   setSystemic]   = useState(null);
  const [services,   setServices]   = useState(seed.services);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [loading,    setLoading]    = useState(seed.staleTs === null); // skip spinner if we have cache
  const [staleTs,    setStaleTs]    = useState(seed.staleTs);

  const refresh = useCallback(async () => {
    const [ov, rl, fr, al, sy, sh] = await Promise.all([
      fetchOverview(), fetchRails(), fetchFraudMetrics(),
      fetchAlerts(60), fetchSystemicHealth(15), fetchServiceHealth(),
    ]);

    // Track whether ANY response came from cache
    const anyFromCache = [ov, rl, fr, al, sy, sh].some(r => r?.fromCache);
    const oldestCacheTs = [ov, rl, fr, al, sy, sh]
      .filter(r => r?.fromCache && r?.ts)
      .reduce((min, r) => Math.min(min, r.ts), Infinity);

    if (ov?.data)   setOverview(ov.data);
    if (rl?.data && typeof rl.data === 'object') {
      setRails(Object.entries(rl.data).map(([rail, count]) => ({ rail, count: Number(count || 0) })).sort((a, b) => b.count - a.count));
    }
    if (fr?.data && typeof fr.data === 'object') {
      setFraud(Object.entries(fr.data).map(([band, count]) => ({ band, count: Number(count || 0) })));
    }
    if (al?.data) setAlerts(al.data);
    if (sy?.data) setSystemic(sy.data);

    const shData = sh?.data ?? {};
    const updated = SERVICES.map(s => ({ ...s, status: shData[s.name] ?? 'UNKNOWN' }));
    setServices(updated);
    onServicesChange?.(updated);

    setStaleTs(anyFromCache && isFinite(oldestCacheTs) ? oldestCacheTs : null);
    setLastUpdate(new Date());
    setLoading(false);
  }, []);

  // Propagate seeded services to NavBar immediately on mount
  useEffect(() => { onServicesChange?.(seed.services); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(); const id = setInterval(refresh, 20000); return () => clearInterval(id); }, [refresh]);

  const submitted = overview?.paymentsSubmitted ?? 0;
  const settled   = overview?.settled ?? 0;
  const settlePct = submitted > 0 ? ((settled / submitted) * 100).toFixed(1) : '0';

  const alertsByService = alerts?.alertsByService || {};
  const alertEntries    = Object.entries(alertsByService).filter(([, c]) => c > 0).sort(([, a], [, b]) => b - a);

  const funnel = [
    { stage: 'Submitted',  count: submitted },
    { stage: 'AML OK',     count: submitted - (overview?.amlBlocked ?? 0) },
    { stage: 'Routed',     count: overview?.routed ?? settled },
    { stage: 'Settled',    count: settled },
  ].filter(s => s.count > 0);

  const staleAgeMin = staleTs ? Math.round((Date.now() - staleTs) / 60000) : 0;

  return (
    <div className="page">

      {/* ── Stale data banner ── */}
      {staleTs && (
        <div className="stale-banner">
          <span className="stale-icon">⚠</span>
          <span className="stale-text">
            Backend offline — showing cached data from {staleAgeMin < 1 ? 'just now' : `${staleAgeMin} min ago`}
          </span>
          <span className="stale-hint">
            Charts and KPIs reflect last successful poll. Start services to go live.
          </span>
        </div>
      )}

      {/* ── Header ── */}
      <div className="page-header">
        <h1>Operations Dashboard</h1>
        <span className={`status-pill ${staleTs ? 'cached' : 'live'}`}>{staleTs ? '● CACHED' : '● LIVE'}</span>
        <span className="header-timestamp">{lastUpdate ? `Updated ${fmtTs(lastUpdate)}` : 'Loading…'}</span>
        <button className="btn-ghost" onClick={refresh}>Refresh</button>
      </div>

      {/* ── KPI row ── */}
      <div className="stat-grid">
        <KPI label="Payments (24h)"  value={loading ? '…' : fmt(submitted)}    sub="submitted to pipeline"            accent="accent" />
        <KPI label="Settlement Rate" value={loading ? '…' : `${settlePct}%`}    sub={`${fmt(settled)} settled`}        accent="green"  />
        <KPI label="Fraud Flagged"   value={loading ? '…' : fmt(overview?.fraudFlagged ?? 0)}  sub="high-risk payments"  accent="amber"  />
        <KPI label="AML Blocked"     value={loading ? '…' : fmt(overview?.amlBlocked ?? 0)}    sub="sanctions & embargo" accent="red"    />
        <KPI label="Avg Latency"     value={loading ? '…' : `${overview?.avgLatencyMs ?? 0}ms`} sub="pipeline end-to-end" accent="purple" />
        <KPI label="Active Rails"    value={loading ? '…' : fmt(rails.length || overview?.activeRails)} sub="payment rails"  accent="accent" />
      </div>

      {/* ── Service Health ── */}
      <Card title="Service Health" badge={{ label: '8 MICROSERVICES', accent: 'green' }}>
        <div className="service-grid">
          {services.map(s => <ServiceBadge key={s.port} svc={s} />)}
        </div>
      </Card>

      {/* ── Charts row ── */}
      <div className="chart-grid cols-3">

        {/* Pipeline funnel */}
        <Card title="Pipeline Funnel (24h)">
          {funnel.length === 0
            ? <div className="empty-state" style={{ padding: 32 }}>{loading ? 'Loading…' : 'No data yet — run a payment batch'}</div>
            : <ResponsiveContainer width="100%" height={220}>
                <BarChart data={funnel} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <XAxis dataKey="stage" tick={{ fill: CHART_COLORS.muted, fontSize: 10 }} />
                  <YAxis tick={{ fill: CHART_COLORS.muted, fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: CHART_COLORS.surface2, border: `1px solid ${CHART_COLORS.border}`, color: CHART_COLORS.text }} />
                  <Bar dataKey="count" fill={CHART_COLORS.accent} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
          }
        </Card>

        {/* Rail distribution */}
        <Card title="Rail Distribution (24h)">
          {rails.length === 0
            ? <div className="empty-state" style={{ padding: 32 }}>{loading ? 'Loading…' : 'No data'}</div>
            : <ResponsiveContainer width="100%" height={220}>
                <BarChart data={rails} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <XAxis dataKey="rail" tick={{ fill: CHART_COLORS.muted, fontSize: 9 }} />
                  <YAxis tick={{ fill: CHART_COLORS.muted, fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: CHART_COLORS.surface2, border: `1px solid ${CHART_COLORS.border}`, color: CHART_COLORS.text }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {rails.map(e => <Cell key={e.rail} fill={RAIL_COLORS[e.rail] || RAIL_COLORS.OTHER} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
          }
        </Card>

        {/* Fraud risk bands */}
        <Card title="Fraud Risk Bands (24h)">
          {fraud.length === 0
            ? <div className="empty-state" style={{ padding: 32 }}>{loading ? 'Loading…' : 'No data'}</div>
            : <ResponsiveContainer width="100%" height={220}>
                <BarChart data={fraud} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <XAxis dataKey="band" tick={{ fill: CHART_COLORS.muted, fontSize: 9 }} />
                  <YAxis tick={{ fill: CHART_COLORS.muted, fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: CHART_COLORS.surface2, border: `1px solid ${CHART_COLORS.border}`, color: CHART_COLORS.text }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {fraud.map((e, i) => <Cell key={e.band} fill={FRAUD_COLORS[i] || CHART_COLORS.muted} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
          }
        </Card>
      </div>

      {/* ── Alerts + Systemic row ── */}
      <div className="chart-grid">

        {/* Active alerts */}
        <Card title="Active Alerts (last 60 min)">
          {alertEntries.length === 0
            ? <div className="empty-state" style={{ padding: 24 }}>{loading ? 'Loading…' : 'No active alerts'}</div>
            : alertEntries.map(([svc, count]) => <AlertRow key={svc} service={svc} count={count} />)
          }
        </Card>

        {/* Systemic diagnostics */}
        <Card
          title="Systemic Diagnostics — AI Analysis"
          badge={systemic ? { label: systemic.severity || 'NORMAL', accent: systemic.isSystemic ? 'red' : 'green' } : undefined}
        >
          {!systemic
            ? <div className="empty-state" style={{ padding: 24 }}>{loading ? 'Loading…' : 'No data'}</div>
            : <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div className="diag-field">
                  <span className="diag-label">STATUS: </span>
                  <span className={systemic.isSystemic ? 'c-red' : 'c-green'} style={{ fontWeight: 700 }}>
                    {systemic.isSystemic ? 'SYSTEMIC ISSUE DETECTED' : 'NORMAL'}
                  </span>
                </div>
                {systemic.affectedServices?.length > 0 && (
                  <div className="diag-field"><span className="diag-label">AFFECTED: </span>{systemic.affectedServices.join(', ')}</div>
                )}
                {systemic.pattern && (
                  <div className="diag-field"><span className="diag-label">PATTERN: </span>{systemic.pattern}</div>
                )}
                {systemic.llmNarrative && (
                  <div className="diag-narrative">
                    <div className="diag-narrative-title">🤖 NVIDIA NEMOTRON ANALYSIS</div>
                    <div style={{ lineHeight: 1.5 }}>{systemic.llmNarrative}</div>
                  </div>
                )}
                {systemic.suggestedAction && (
                  <div className="diag-action">
                    <div className="diag-action-title">ACTION</div>
                    <div style={{ fontSize: 12 }}>{systemic.suggestedAction}</div>
                  </div>
                )}
              </div>
          }
        </Card>
      </div>

      {/* ── Quick links ── */}
      <Card title="Quick Links">
        <div className="quick-links">
          {[
            { label: '📊 Kibana', url: 'http://localhost:5601', accent: 'amber' },
            { label: '📈 Grafana', url: 'http://localhost:3000', accent: 'accent' },
            { label: '🔍 Jaeger Traces', url: 'http://localhost:16686', accent: 'purple' },
            { label: '🛡 Prometheus', url: 'http://localhost:9090', accent: 'red' },
            { label: '🗄 Swagger UI', url: 'http://localhost:8087/swagger-ui.html', accent: 'green' },
          ].map(({ label, url, accent }) => (
            <a
              key={url} href={url} target="_blank" rel="noreferrer"
              className={`quick-link-chip c-${accent}`}
              style={{ background: `var(--${accent})15`, borderColor: `var(--${accent})44` }}
            >
              {label}
            </a>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── Root app ─────────────────────────────────────────────────
export default function App() {
  const [page,     setPage]     = useState(window.location.hash.replace('#', '') || 'dashboard');
  const [services, setServices] = useState(SERVICES.map(s => ({ ...s, status: 'UNKNOWN' })));

  useEffect(() => {
    const onHash = () => setPage(window.location.hash.replace('#', '') || 'dashboard');
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Poll service health globally so NavBar always reflects real status
  useEffect(() => {
    async function pollHealth() {
      try {
        const sh = await fetchServiceHealth();
        const shData = sh?.data ?? {};
        setServices(SERVICES.map(s => ({ ...s, status: shData[s.name] ?? 'UNKNOWN' })));
      } catch { /* silent — keep current status */ }
    }
    pollHealth();
    const id = setInterval(pollHealth, 15000);
    return () => clearInterval(id);
  }, []);

  function navigate(p) { window.location.hash = p; setPage(p); }

  return (
    <div className="app">
      <NavBar page={page} navigate={navigate} services={services} />
      <main className="main-content">
        {page === 'dashboard' && <Dashboard onServicesChange={setServices} />}
        {page === 'realtime'  && <EnhancedDashboard />}
        {page === 'logs'      && <LiveLogViewer />}
        {page === 'flow'      && <PaymentFlowFixed />}
        {page === 'cascade'   && <CascadeSimulation />}
        {page === 'graphify'  && <GraphifyViewer />}
        {page === 'search'    && <PaymentSearch />}
        {page === 'chat'      && <Chat />}
      </main>
    </div>
  );
}
