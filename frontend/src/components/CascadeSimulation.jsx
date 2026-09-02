import React, { useState, useRef, useEffect } from 'react';

// Ensure token is set
const DEV_TOKEN = 'eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiZGVtby1vcHMiLCAiaXNzIjogImNsZWFyZmxvdy1kZXYiLCAiaWF0IjogMTc3ODg2MTYxMSwgImV4cCI6IDE4OTM0NTYwMDAsICJzY29wZSI6ICJtY3A6cmVhZCBtY3A6YWRtaW4ifQ._Iz89MiCOyVY9m0MUsuSJhlFqsXY-OYvlV2ML2SFPuQ';
if (!localStorage.getItem('clearflow_token')) {
  localStorage.setItem('clearflow_token', DEV_TOKEN);
}

const C = {
  bg: '#0d1117', surface: '#161b22', border: '#30363d',
  accent: '#58a6ff', success: '#3fb950', danger: '#f85149',
  warn: '#d29922', muted: '#8b949e', text: '#e6edf3', purple: '#a371f7',
};

const SERVICES = [
  { id: 'aml-compliance',   name: 'AML Compliance',   port: 8083, critical: true },
  { id: 'routing-execution', name: 'Routing',         port: 8084, critical: true },
  { id: 'settlement',        name: 'Settlement',      port: 8085, critical: true },
  { id: 'validation-enrichment', name: 'Validation',  port: 8082, critical: false },
];

const PARTIES = [
  { name: 'Alpine Logistics GmbH',  iban: 'DE89370400440532013000',     bic: 'DEUTDEDBXXX', country: 'DE' },
  { name: 'Euro Trade SARL',        iban: 'FR7630006000011234567890189', bic: 'BNPAFRPPXXX', country: 'FR' },
  { name: 'HSBC Holdings PLC',      iban: 'GB29NWBK60161331926819',     bic: 'HBUKGB4BXXX', country: 'GB' },
  { name: 'UBS AG Zurich',          iban: 'CH5604835012345678009',       bic: 'UBSWCHZHXXX', country: 'CH' },
  { name: 'ING Bank NV',            iban: 'NL91ABNA0417164300',         bic: 'INGBNL2AXXX', country: 'NL' },
  { name: 'Banco Santander SA',     iban: 'ES9121000418450200051332',   bic: 'BSCHESMM',    country: 'ES' },
  { name: 'UniCredit SpA',          iban: 'IT60X0542811101000000123456', bic: 'UNCRITMM',    country: 'IT' },
  { name: 'Raiffeisen Bank Intl',   iban: 'AT611904300234573201',       bic: 'RZOOAT2L',    country: 'AT' },
];

const CHANNELS = ['SEPA', 'SWIFT_GPI', 'FASTER_PAYMENTS', 'FEDWIRE'];

function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

function buildPayload() {
  const debtorIdx = Math.floor(Math.random() * PARTIES.length);
  let creditorIdx = Math.floor(Math.random() * PARTIES.length);
  while (creditorIdx === debtorIdx) creditorIdx = Math.floor(Math.random() * PARTIES.length);
  const d = PARTIES[debtorIdx], c = PARTIES[creditorIdx];
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  return {
    instructionId: uuid(),
    endToEndId: `E2E-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${Math.floor(Math.random()*90000+10000)}`,
    uetr: uuid(),
    debtor:   { name: d.name, iban: d.iban, bic: d.bic, address: `${d.country} HQ`,     country: d.country },
    creditor: { name: c.name, iban: c.iban, bic: c.bic, address: `${c.country} Branch`, country: c.country },
    amount:   parseFloat((Math.random() * 249900 + 100).toFixed(2)),
    currency: ['EUR','USD','GBP','CHF'][Math.floor(Math.random()*4)],
    valueDate: tomorrow.toISOString().split('T')[0],
    purpose: 'SUPP',
    remittanceInfo: `Invoice INV-${Math.floor(Math.random()*90000+10000)}`,
    channel: CHANNELS[Math.floor(Math.random() * CHANNELS.length)],
  };
}

async function toggleService(serviceId, action) {
  try {
    const resp = await fetch(`/mcp/admin/service/${serviceId}/${action}`, { method: 'POST' });
    return resp.ok;
  } catch {
    return false;
  }
}

async function pollStatus(paymentId) {
  const token = localStorage.getItem('clearflow_token') || 'dev';
  try {
    const resp = await fetch(`/mcp/payments/${paymentId}/explain`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    return data?.overallStatus || 'UNKNOWN';
  } catch {
    return null;
  }
}

export default function CascadeSimulation() {
  const [stoppedService, setStoppedService] = useState(null);
  const [running, setRunning] = useState(false);
  const [payments, setPayments] = useState([]);
  const [cascadeDetected, setCascadeDetected] = useState(false);
  const [timeline, setTimeline] = useState([]);
  const pollingRef = useRef(null);

  const startCascade = async () => {
    if (!stoppedService) {
      alert('Select a service to stop first');
      return;
    }
    setRunning(true);
    setPayments([]);
    setCascadeDetected(false);
    setTimeline([{
      ts: new Date(),
      event: `Stopping ${stoppedService.name}...`,
    }]);

    const ok = await toggleService(stoppedService.id, 'stop');
    if (!ok) {
      setTimeline(prev => [...prev, {
        ts: new Date(),
        event: '⚠️ Failed to stop service',
      }]);
    } else {
      setTimeline(prev => [...prev, {
        ts: new Date(),
        event: `✓ ${stoppedService.name} stopped`,
      }]);
    }

    await new Promise(r => setTimeout(r, 1000));
    setTimeline(prev => [...prev, {
      ts: new Date(),
      event: 'Sending 50 payments...',
    }]);

    const batchPayments = [];
    for (let i = 0; i < 50; i++) {
      const payload = buildPayload();
      try {
        const resp = await fetch('/api/v1/payments', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const body = await resp.json().catch(() => ({}));
        const pid = body.paymentId || payload.instructionId;
        batchPayments.push({
          id: pid,
          status: resp.status === 202 ? 'ACCEPTED' : 'REJECTED',
          amount: payload.amount,
          currency: payload.currency,
          submittedAt: new Date(),
        });
        setPayments(prev => [...prev, batchPayments[batchPayments.length - 1]]);
      } catch {
        batchPayments.push({
          id: payload.instructionId,
          status: 'ERROR',
          amount: payload.amount,
          currency: payload.currency,
          submittedAt: new Date(),
        });
        setPayments(prev => [...prev, batchPayments[batchPayments.length - 1]]);
      }
    }

    setTimeline(prev => [...prev, {
      ts: new Date(),
      event: `✓ Submitted 50 payments (${batchPayments.filter(p => p.status === 'ACCEPTED').length} accepted)`,
    }]);

    let cascaded = false;
    let failureCount = 0;
    let pollCount = 0;

    pollingRef.current = setInterval(async () => {
      pollCount++;
      let failed = 0;
      for (const p of batchPayments) {
        const s = await pollStatus(p.id);
        if (s && (s.includes('FAILED') || s.includes('REJECTED'))) failed++;
      }
      failureCount = failed;

      if (failed > batchPayments.length * 0.5 && !cascaded) {
        cascaded = true;
        setCascadeDetected(true);
        setTimeline(prev => [...prev, {
          ts: new Date(),
          event: `🔴 CASCADING FAILURE DETECTED: ${failed}/${batchPayments.length} payments failed (${stoppedService.name} unavailable)`,
        }]);
      }

      if (pollCount > 8) {
        clearInterval(pollingRef.current);
        setRunning(false);
      }
    }, 2000);
  };

  const recover = async () => {
    if (!stoppedService) return;
    setTimeline(prev => [...prev, {
      ts: new Date(),
      event: `Restarting ${stoppedService.name}...`,
    }]);

    const ok = await toggleService(stoppedService.id, 'start');
    if (ok) {
      setTimeline(prev => [...prev, {
        ts: new Date(),
        event: `✓ ${stoppedService.name} recovered`,
      }]);
    } else {
      setTimeline(prev => [...prev, {
        ts: new Date(),
        event: '⚠️ Recovery failed',
      }]);
    }

    setCascadeDetected(false);
    clearInterval(pollingRef.current);
  };

  const failedCount = payments.filter(p => p.status === 'REJECTED').length;
  const acceptedCount = payments.filter(p => p.status === 'ACCEPTED').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: C.text, marginBottom: 4 }}>Cascade Failure Simulation</h1>
        <p style={{ fontSize: 12, color: C.muted }}>Stop a critical service mid-batch and watch MCP detect the cascade in real-time.</p>
      </div>

      {/* Service Selector */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: C.muted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
          Select Service to Stop
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
          {SERVICES.map(svc => (
            <button
              key={svc.id}
              onClick={() => !running && setStoppedService(svc)}
              disabled={running}
              style={{
                background: stoppedService?.id === svc.id ? C.accent : C.bg,
                border: `1px solid ${stoppedService?.id === svc.id ? C.accent : C.border}`,
                color: stoppedService?.id === svc.id ? C.bg : C.text,
                padding: '10px 14px',
                borderRadius: 6,
                cursor: running ? 'not-allowed' : 'pointer',
                fontWeight: 600,
                fontSize: 12,
                transition: 'all 0.2s',
                opacity: running ? 0.5 : 1,
              }}
            >
              {svc.name}
              {svc.critical && ' ⚠️'}
            </button>
          ))}
        </div>
      </div>

      {/* Control Buttons */}
      <div style={{ display: 'flex', gap: 10 }}>
        <button
          onClick={startCascade}
          disabled={running || !stoppedService}
          style={{
            background: C.danger,
            color: C.text,
            border: 'none',
            padding: '10px 20px',
            borderRadius: 6,
            cursor: running || !stoppedService ? 'not-allowed' : 'pointer',
            fontWeight: 700,
            fontSize: 13,
            opacity: running || !stoppedService ? 0.5 : 1,
          }}
        >
          {running ? '⏳ Running...' : '▶️ Start Cascade Test'}
        </button>
        {cascadeDetected && (
          <button
            onClick={recover}
            style={{
              background: C.success,
              color: C.bg,
              border: 'none',
              padding: '10px 20px',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            🔄 Recover Service
          </button>
        )}
      </div>

      {/* Cascade Detection Alert */}
      {cascadeDetected && (
        <div style={{
          background: 'rgba(248,81,73,0.10)',
          border: `1px solid ${C.danger}55`,
          borderLeft: `3px solid ${C.danger}`,
          borderRadius: 8,
          padding: '14px 16px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.danger }}>🔴 CASCADE DETECTED</div>
          <div style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>
            {stoppedService.name} is down. Downstream services are failing to process payments.
            Accepted: <strong style={{ color: C.success }}>{acceptedCount}</strong> | Failed: <strong style={{ color: C.danger }}>{failedCount}</strong>
          </div>
        </div>
      )}

      {/* Timeline */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: C.muted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
          Event Timeline
        </div>
        <div style={{ maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {timeline.length === 0 ? (
            <div style={{ color: C.muted, fontSize: 12 }}>No events yet</div>
          ) : (
            timeline.map((e, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, fontSize: 12 }}>
                <span style={{ color: C.muted, minWidth: 60, fontFamily: 'monospace' }}>
                  {e.ts.toLocaleTimeString()}
                </span>
                <span style={{ color: C.text }}>{e.event}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Payments Table */}
      {payments.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: C.muted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
            Payment Status ({payments.length} submitted)
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                  <th style={{ textAlign: 'left', padding: '8px 0', color: C.muted, fontWeight: 600 }}>ID (first 8)</th>
                  <th style={{ textAlign: 'left', padding: '8px 0', color: C.muted, fontWeight: 600 }}>Status</th>
                  <th style={{ textAlign: 'right', padding: '8px 0', color: C.muted, fontWeight: 600 }}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {payments.slice(0, 15).map((p, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${C.border}33` }}>
                    <td style={{ padding: '6px 0', color: C.text, fontFamily: 'monospace', fontSize: 11 }}>
                      {p.id.slice(0, 8)}
                    </td>
                    <td style={{ padding: '6px 0' }}>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: 3,
                        fontSize: 10,
                        fontWeight: 700,
                        background: p.status === 'ACCEPTED' ? C.success + '22' : p.status === 'REJECTED' ? C.danger + '22' : C.warn + '22',
                        color: p.status === 'ACCEPTED' ? C.success : p.status === 'REJECTED' ? C.danger : C.warn,
                      }}>
                        {p.status}
                      </span>
                    </td>
                    <td style={{ padding: '6px 0', textAlign: 'right', color: C.text }}>
                      {p.amount.toFixed(2)} {p.currency}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {payments.length > 15 && (
              <div style={{ color: C.muted, fontSize: 11, marginTop: 8 }}>
                ... and {payments.length - 15} more
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
