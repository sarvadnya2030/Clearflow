/**
 * ClearFlow live API client.
 * All paths are relative so the Vite proxy handles CORS in dev:
 *   /mcp  → http://localhost:8087
 *   /api  → http://localhost:8080
 *   /es   → http://localhost:9200
 */
import axios from 'axios';

const mcp = axios.create({ baseURL: '/mcp', timeout: 180000 }); // 180s for NVIDIA reasoning
const api = axios.create({ baseURL: '/api/v1', timeout: 5000 });
const es  = axios.create({ baseURL: '/es',  timeout: 5000 });

// Inject JWT on every MCP request
mcp.interceptors.request.use((config) => {
  const token = localStorage.getItem('clearflow_token');
  if (token && token !== '__dev__') {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

/** Safely unwrap an axios call. Returns null on any error. */
async function safe(promise) {
  try {
    const res = await promise;
    return res.data ?? null;
  } catch {
    return null;
  }
}

// ── localStorage cache ─────────────────────────────────────
const CACHE_PREFIX = 'cf_cache_';

function cacheWrite(key, data) {
  try {
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ data, ts: Date.now() }));
  } catch { /* storage full — ignore */ }
}

export function cacheRead(key) {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    return raw ? JSON.parse(raw) : null; // { data, ts }
  } catch {
    return null;
  }
}

/** Fetch with automatic cache write. Returns { data, fromCache: false } on live hit,
 *  { data, fromCache: true, ts } when falling back to localStorage. */
async function fetchCached(key, promise) {
  const live = await safe(promise);
  if (live !== null) {
    cacheWrite(key, live);
    return { data: live, fromCache: false };
  }
  const cached = cacheRead(key);
  if (cached) return { data: cached.data, fromCache: true, ts: cached.ts };
  return { data: null, fromCache: false };
}

// ── MCP metrics ────────────────────────────────────────────

export async function fetchOverview() {
  return fetchCached('overview', mcp.get('/metrics/overview'));
}

export async function fetchRails() {
  return fetchCached('rails', mcp.get('/metrics/rails'));
}

export async function fetchFraudMetrics() {
  return fetchCached('fraud', mcp.get('/metrics/fraud'));
}

export async function fetchAlerts(windowMinutes = 30) {
  return fetchCached('alerts', mcp.get('/alerts/active', { params: { windowMinutes } }));
}

export async function fetchSystemicHealth(windowMinutes = 15) {
  return fetchCached('systemic', mcp.get('/diagnostics/systemic', { params: { windowMinutes } }));
}

/** GET /mcp/payments/{id}/timeline */
export async function fetchPaymentTimeline(paymentId) {
  if (!paymentId) return null;
  return safe(mcp.get(`/payments/${encodeURIComponent(paymentId)}/timeline`));
}

/** GET /mcp/forecast/settlement?horizonHours=24 */
export async function fetchSettlementForecast(horizonHours = 24) {
  return safe(mcp.get('/forecast/settlement', { params: { horizonHours } }));
}

/** GET /mcp/anomalies/uetr?windowMinutes=60 */
export async function fetchUetrAnomalies(windowMinutes = 60) {
  return safe(mcp.get('/anomalies/uetr', { params: { windowMinutes } }));
}

// ── Payment data ────────────────────────────────────────────

/**
 * Direct ES query for recent payments.
 * Falls back to the gateway search endpoint if ES is unreachable.
 */
export async function fetchRecentPayments(n = 20) {
  const esResult = await safe(
    es.post('/clearflow-payments/_search', {
      size: n,
      sort: [{ '@timestamp': { order: 'desc' } }],
      query: { match_all: {} },
    })
  );
  if (esResult?.hits?.hits) {
    return esResult.hits.hits.map((h) => h._source);
  }
  // Fallback: gateway REST endpoint
  return safe(api.get('/payments', { params: { size: n, sort: 'createdAt,desc' } }));
}

// ── Service health ──────────────────────────────────────────

const SERVICES = [
  { name: 'Gateway',          port: 8080 },
  { name: 'Fraud Scoring',    port: 8081 },
  { name: 'Validation',       port: 8082 },
  { name: 'AML Compliance',   port: 8083 },
  { name: 'Routing',          port: 8084 },
  { name: 'Settlement',       port: 8085 },
  { name: 'Audit',            port: 8086 },
  { name: 'MCP Gateway',      port: 8087 },
];

/**
 * Probe all services via the MCP aggregated health endpoint.
 * Avoids per-service Vite proxy issues with large chunked actuator responses.
 */
export async function fetchServiceHealth() {
  const live = await safe(mcp.get('/diagnostics/health-summary'));
  if (live) {
    cacheWrite('services', live);
    return { data: live, fromCache: false };
  }
  const cached = cacheRead('services');
  if (cached) return { data: cached.data, fromCache: true, ts: cached.ts };
  return { data: {}, fromCache: false };
}

/** GET /mcp/payments/{id}/explain → full LLM root cause analysis */
export async function fetchExplain(paymentId) {
  if (!paymentId) return null;
  return safe(mcp.get(`/payments/${encodeURIComponent(paymentId)}/explain`));
}

/** POST /mcp/chat → NVIDIA Nemotron answer */
export async function fetchChat({ question, paymentId, history }) {
  return safe(mcp.post('/chat', { question, paymentId, history }));
}

/** GET /mcp/payments/{id}/timeline */
export async function fetchTimeline(paymentId) {
  if (!paymentId) return null;
  return safe(mcp.get(`/payments/${encodeURIComponent(paymentId)}/timeline`));
}
