import React, { useState } from 'react';
import { fetchExplain } from '../api/clearflow.js';

const C = {
  bg:      '#0d1117',
  surface: '#161b22',
  border:  '#30363d',
  accent:  '#58a6ff',
  success: '#3fb950',
  danger:  '#f85149',
  warn:    '#d29922',
  muted:   '#8b949e',
  text:    '#e6edf3',
  purple:  '#a371f7',
};

const STATUS_COLOR = {
  SETTLED:     C.success,
  BLOCKED:     C.danger,
  FAILED:      C.warn,
  IN_PROGRESS: C.accent,
  NOT_FOUND:   C.muted,
  UNKNOWN:     C.muted,
};

const CATEGORY_COLOR = {
  AML_SANCTIONS:      C.danger,
  FRAUD_CRITICAL:     '#f97316',
  FRAUD_VELOCITY:     '#fb923c',
  EMBARGO_BLOCKED:    '#dc2626',
  DUPLICATE_PAYMENT:  C.purple,
  VALIDATION_FAILURE: '#6366f1',
  ROUTING_FAILURE:    C.accent,
  SETTLEMENT_FAILURE: '#ec4899',
  SYSTEM_ERROR:       C.muted,
  UNKNOWN:            C.muted,
  NO_DATA:            C.muted,
};

const CONFIDENCE_COLOR = { HIGH: C.success, MEDIUM: C.warn, LOW: C.muted };

const STAGE_ICON = { COMPLETED: '✅', FAILED: '❌', SKIPPED: '⏭', PENDING: '⏳' };

function Badge({ label, color }) {
  return (
    <span style={{
      background: (color || C.muted) + '22',
      color: color || C.muted,
      border: `1px solid ${color || C.muted}55`,
      borderRadius: 6, padding: '2px 10px',
      fontWeight: 700, fontSize: 12, letterSpacing: 0.5,
    }}>
      {label}
    </span>
  );
}

function StageRow({ stage, isLast }) {
  const [open, setOpen] = useState(stage.status === 'FAILED');
  const failed = stage.status === 'FAILED';
  const color = failed ? C.danger : stage.status === 'COMPLETED' ? C.success : C.muted;

  return (
    <div style={{ display: 'flex', gap: 0 }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 32, flexShrink: 0 }}>
        <div style={{
          width: 12, height: 12, borderRadius: '50%', background: color,
          boxShadow: `0 0 6px ${color}`, flexShrink: 0, marginTop: 14,
        }} />
        {!isLast && <div style={{ width: 2, flex: 1, background: C.border, marginTop: 2 }} />}
      </div>

      <div style={{
        flex: 1, marginBottom: isLast ? 0 : 8,
        background: failed ? '#f8514908' : '#ffffff04',
        border: `1px solid ${failed ? C.danger + '44' : C.border}`,
        borderRadius: 8, overflow: 'hidden',
      }}>
        <button
          onClick={() => setOpen((o) => !o)}
          style={{
            width: '100%', background: 'none', border: 'none', cursor: 'pointer',
            padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10,
          }}
        >
          <span style={{ fontSize: 15 }}>{STAGE_ICON[stage.status] || '○'}</span>
          <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: C.text, textAlign: 'left' }}>
            {stage.displayName}
          </span>
          {stage.durationMs != null && (
            <span style={{ fontSize: 11, color: C.muted }}>{stage.durationMs}ms</span>
          )}
          {stage.timestamp && (
            <span style={{ fontSize: 11, color: C.muted, marginLeft: 8 }}>
              {new Date(stage.timestamp).toLocaleTimeString()}
            </span>
          )}
          <span style={{ fontSize: 10, color: C.muted }}>{open ? '▲' : '▼'}</span>
        </button>

        {open && (
          <div style={{ padding: '0 14px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {stage.keyEvent && (
              <div style={{ fontSize: 12, color: C.muted }}>
                <strong style={{ color: C.text }}>Event: </strong>{stage.keyEvent}
              </div>
            )}
            {stage.keyDetail && (
              <div style={{
                fontSize: 11, fontFamily: 'monospace', background: '#21262d',
                borderRadius: 4, padding: '6px 10px', color: failed ? C.danger : C.accent,
                wordBreak: 'break-all',
              }}>
                {stage.keyDetail}
              </div>
            )}
            {stage.logs?.slice(0, 4).map((log, i) => (
              <div key={i} style={{
                fontSize: 11, fontFamily: 'monospace', color: C.muted,
                background: '#0d1117', borderRadius: 4, padding: '4px 8px', wordBreak: 'break-all',
              }}>
                <span style={{ color: log.level === 'ERROR' ? C.danger : log.level === 'WARN' ? C.warn : '#3fb95066' }}>
                  [{log.level}]
                </span>
                {' '}{log.message}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RcaCard({ data }) {
  const statusColor = STATUS_COLOR[data.overallStatus] || C.muted;
  const catColor    = CATEGORY_COLOR[data.causeCategory] || C.muted;
  const confColor   = CONFIDENCE_COLOR[data.classifierConfidence] || C.muted;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`,
        borderTop: `3px solid ${statusColor}`, borderRadius: 8, padding: 20,
        display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start',
      }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 11, color: C.muted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Payment ID</div>
          <div style={{ fontSize: 13, fontFamily: 'monospace', color: C.accent, wordBreak: 'break-all' }}>{data.paymentId}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge label={data.overallStatus} color={statusColor} />
          {data.causeCategory && <Badge label={data.causeCategory.replace(/_/g, ' ')} color={catColor} />}
          {data.classifierConfidence && <Badge label={`${data.classifierConfidence} confidence`} color={confColor} />}
          {data.failedAtService && <Badge label={`⚡ ${data.failedAtService}`} color={C.warn} />}
        </div>
        <div style={{ fontSize: 11, color: C.muted, textAlign: 'right', minWidth: 80 }}>{data.analysisMs}ms</div>
      </div>

      {/* Rule-based result */}
      {data.primaryCause && data.causeCategory !== 'NO_DATA' && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16 }}>
          <div style={{ fontSize: 11, color: C.muted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Rule-based Classifier</div>
          <div style={{ fontSize: 13, color: C.text }}>{data.primaryCause}</div>
          {data.primaryEvidence && (
            <div style={{
              fontSize: 11, fontFamily: 'monospace', color: C.muted, marginTop: 8,
              background: '#21262d', borderRadius: 4, padding: '6px 10px', wordBreak: 'break-all',
            }}>
              {data.primaryEvidence}
            </div>
          )}
        </div>
      )}

      {/* NVIDIA Nemotron narrative */}
      {data.narrativeSummary && (
        <div style={{
          background: 'linear-gradient(135deg, #0d1117 0%, #161b22 100%)',
          border: `1px solid ${C.purple}44`,
          borderLeft: `3px solid ${C.purple}`,
          borderRadius: 8, padding: 20,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{ fontSize: 16 }}>🤖</span>
            <div style={{ fontSize: 11, color: C.purple, textTransform: 'uppercase', letterSpacing: 1, fontWeight: 700 }}>
              AI Root Cause — NVIDIA Nemotron 30B
            </div>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: C.muted, background: '#21262d', padding: '2px 8px', borderRadius: 10 }}>
              {data.llmProvider}
            </span>
          </div>
          <p style={{ fontSize: 14, color: C.text, lineHeight: 1.6, margin: 0 }}>{data.narrativeSummary}</p>
          {data.immediateAction && (
            <div style={{
              marginTop: 12, background: 'rgba(88,166,255,0.08)',
              borderLeft: `2px solid ${C.accent}`, borderRadius: 4, padding: '10px 14px',
            }}>
              <div style={{ fontSize: 11, color: C.accent, fontWeight: 700, marginBottom: 4 }}>IMMEDIATE ACTION</div>
              <div style={{ fontSize: 13, color: C.text }}>{data.immediateAction}</div>
            </div>
          )}
          {data.regulatoryNote && (
            <div style={{
              marginTop: 8, background: 'rgba(210,153,34,0.08)',
              borderLeft: `2px solid ${C.warn}`, borderRadius: 4, padding: '10px 14px',
            }}>
              <div style={{ fontSize: 11, color: C.warn, fontWeight: 700, marginBottom: 4 }}>REGULATORY NOTE</div>
              <div style={{ fontSize: 13, color: C.text }}>{data.regulatoryNote}</div>
            </div>
          )}
        </div>
      )}

      {/* 7-stage pipeline trace */}
      {data.timeline?.stages?.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 20 }}>
          <div style={{ fontSize: 11, color: C.muted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16 }}>
            7-Stage Pipeline Trace · {data.timeline.totalLogEvents} log events indexed
          </div>
          {data.timeline.stages.map((s, i) => (
            <StageRow key={s.order} stage={s} isLast={i === data.timeline.stages.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PaymentSearch() {
  const [input, setInput]     = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState(null);
  const [error, setError]     = useState(null);

  async function search(id) {
    const paymentId = (id || input).trim();
    if (!paymentId) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await fetchExplain(paymentId);
      if (!data) throw new Error('No response — is the MCP gateway up?');
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text }}>AI Root Cause Analysis</h1>
        <p style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>
          Enter any payment ID → get the full 7-stage pipeline trace + NVIDIA Nemotron 30B root cause explanation.
        </p>
      </div>

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="e.g. c9d677c9-8931-431c-9792-4d30fea42956"
            style={{
              flex: 1, background: '#21262d', border: `1px solid ${C.border}`,
              color: C.accent, padding: '10px 14px', borderRadius: 6,
              fontSize: 13, fontFamily: 'monospace', outline: 'none',
            }}
          />
          <button
            onClick={() => search()}
            disabled={loading || !input.trim()}
            style={{
              background: loading ? '#21262d' : C.accent,
              color: loading ? C.muted : '#0d1117',
              border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
              padding: '10px 24px', borderRadius: 6, fontWeight: 700, fontSize: 13, minWidth: 110,
            }}
          >
            {loading ? '⏳ Thinking…' : '🔍 Analyse'}
          </button>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: C.muted }}>Quick examples:</span>
          {[
            { label: '⚡ JPY Liquidity Failure', id: 'c9d677c9-8931-431c-9792-4d30fea42956' },
            { label: '✅ SEPA Settled',          id: 'de68fbb9-f021-4613-913a-ab5ba5e0d4c2' },
          ].map(({ label, id }) => (
            <button key={id} onClick={() => { setInput(id); search(id); }} style={{
              background: '#21262d', border: `1px solid ${C.border}`, color: C.muted,
              padding: '3px 12px', borderRadius: 12, fontSize: 11, cursor: 'pointer',
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div style={{
          background: C.surface, border: `1px solid ${C.purple}44`,
          borderRadius: 8, padding: 40, textAlign: 'center',
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🧠</div>
          <div style={{ fontSize: 15, color: C.purple, fontWeight: 600 }}>NVIDIA Nemotron is reasoning…</div>
          <div style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>
            Fetching ELK logs → reconstructing 7-stage timeline → generating root cause narrative
          </div>
        </div>
      )}

      {error && !loading && (
        <div style={{
          background: 'rgba(248,81,73,0.08)', border: '1px solid rgba(248,81,73,0.3)',
          borderRadius: 8, padding: 16, color: C.danger, fontSize: 13,
        }}>
          ⚠️ {error}
        </div>
      )}

      {result && !loading && <RcaCard data={result} />}
    </div>
  );
}
