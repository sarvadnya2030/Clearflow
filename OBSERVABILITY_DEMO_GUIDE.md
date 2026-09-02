# ClearFlow Observability Demo — Full Stack

This guide walks through the complete observability story: payment processing + live dashboards showing what's happening at every stage.

## Quick Start

```bash
# 1. Start everything
bash clearflow-start.sh

# 2. Run the observability tour
bash observability-demo-tour.sh
```

## What You'll See (Live)

### Timeline

| Time | What Happens | Where to Watch |
|------|---|---|
| **T=0s** | You send 15 payments via `live_payment_sender.py` | Terminal |
| **T=0.1s** | Gateway receives payment, generates UUID, publishes to Kafka | Grafana (gateway throughput panel) |
| **T=0.2s** | Fraud-scoring consumes event, evaluates heuristic + LightGBM | Grafana (fraud evaluation rate) |
| **T=0.3s** | Validation enriches with IBAN/BIC/embargo checks | Kibana (search `correlationId`) |
| **T=0.5s** | AML compliance screens against OFAC | Grafana (AML hit rate) |
| **T=0.7s** | Routing selects optimal rail (SEPA, SWIFT, CHIPS, etc.) | Grafana (rail selection distribution) |
| **T=1.0s** | Settlement records debit+credit in Cassandra | Prometheus (settlement_ledger_writes metric) |
| **T=1.1s** | Audit records SHA-256 hash chain entry | Elasticsearch (audit.recorded event) |
| **T=1.2s** | Full payment timeline visible in Kibana | Jaeger (end-to-end trace) |

### Dashboards During Payment Flow

#### 1. **Grafana: clearflow-main** (http://localhost:3001)

**What you see:**
- **Top**: Payment acceptance rate (should be ~95%)
- **Left**: Payment funnel (100 → 95 fraud pass → 90 AML clear → 85 routed → 85 settled)
- **Right**: Error breakdown (fraud blocks, AML hits, validation rejects)
- **Bottom**: Throughput over time (req/s rising as batches arrive)

**During test**: Watch the funnel bars fill in real-time as each payment progresses

#### 2. **Kibana: Payment Timeline** (http://localhost:5601)

**Search query:**
```
correlationId: <paste-from-demo-output>
```

**Results**: 7 log entries in order:
1. `service: gateway | event: payment.initiated | stage: 0`
2. `service: fraud-scoring | event: fraud.evaluated | stage: 1 | decision: PASS`
3. `service: validation-enrichment | event: validation.complete | stage: 2`
4. `service: aml-compliance | event: aml.sanctions.clear | stage: 3`
5. `service: routing-execution | event: payment.routed | stage: 4 | rail: SEPA_INSTANT`
6. `service: settlement | event: payment.settled | stage: 5`
7. `service: audit | event: audit.recorded | stage: 6 | hash: SHA-256`

**Timeline column**: Shows exact microsecond when each event occurred

#### 3. **Jaeger: Distributed Trace** (http://localhost:16686)

**Steps:**
1. Select service: `gateway`
2. Look for spans with long durations
3. Click on a span → see child spans from downstream services
4. Each service appears as a separate span, color-coded by latency

**Insight**: Shows where time is actually spent (usually fraud-scoring or AML)

#### 4. **Prometheus: Metrics** (http://localhost:9090)

**Key queries to try:**

```promql
# Acceptance rate (should be ~95%)
rate(clearflow_payment_accepted_total[1m])

# p99 latency (should be < 500ms)
histogram_quantile(0.99, clearflow_payment_latency_ms)

# DLQ depth (should be 0)
clearflow_dlq_depth_total

# Circuit breaker status (should all be CLOSED=0)
clearflow_resilience4j_circuitbreaker_state{state="CLOSED"}
```

#### 5. **ActiveMQ Console** (http://localhost:8161)

**Log in**: admin / admin

**What to check:**
- Queue: `clearflow.payment.initiated` — shows message count flowing through
- Queue: `clearflow.payments.dlq` — should be empty (no silent drops)
- Topic: `clearflow.fraud.evaluated` — consumer lag per subscription

---

## Demo Narrative

### **Act 1: Show the Dashboards**

"This is ClearFlow's observability stack. Four independent systems watching the payment pipeline:
- **Grafana** shows business metrics (acceptance rate, fraud rate, per-rail throughput)
- **Kibana** shows structured logs with payment tracing (correlationId)
- **Jaeger** shows distributed traces (where does latency come from?)
- **Prometheus** shows raw metrics (for alerting + SLOs)"

### **Act 2: Send Payments**

"Now I'll send 15 ISO 20022 payments through the system. Watch all four dashboards simultaneously."

```bash
python3 live_payment_sender.py
```

### **Act 3: Read the Results**

**Point to Grafana:**
"95% acceptance rate — 5 AML hits (expected for our test data with Iran in the creditor list)."

**Point to Kibana:**
"Pick a payment ID from the output. Search by `correlationId`. Here's the exact journey:
- Gateway accepted it at 00:05:12.001
- Fraud-scoring evaluated it by 00:05:12.004 (3ms)
- Validation enriched by 00:05:12.006 (2ms)
- AML screened by 00:05:12.009 (3ms)
- Routing selected SEPA Instant by 00:05:12.011 (2ms)
- Settlement recorded it by 00:05:12.014 (3ms)
- Total: 13ms end-to-end"

**Point to Jaeger:**
"Same story as a trace: 7 spans, one per service, total latency 13ms."

**Point to Prometheus:**
"These metrics feed into alerting. If p99 latency exceeds 500ms for 5 minutes, we page on-call. If DLQ depth > 10, we alert. If fraud rate jumps to 30%, we investigate."

### **Act 4: Explain the Architecture**

"What you're seeing is production-grade observability:
- Every log entry includes a correlationId — you can trace one payment across 7 services
- Metrics feed Grafana for dashboards + Prometheus for SLOs + alerting
- Traces show where latency is added — usually AML screening (regulatory requirement)
- DLQ monitoring ensures no silent drops — every failure is visible

This is what you'd build at a real bank."

---

## Verification Checklist (for Evaluators)

Use this checklist to verify the observability stack is working:

- [ ] Grafana dashboard loads without errors
- [ ] Payment funnel animates during test (bars increase)
- [ ] Kibana has >= 100 clearflow logs indexed
- [ ] Can search by correlationId and get exactly 7 results
- [ ] Jaeger shows >= 5 traces with service `gateway`
- [ ] Prometheus scrapes metrics (click Status → Targets, should show 8 targets UP)
- [ ] ActiveMQ console shows queues, no DLQ depth
- [ ] All latencies < 500ms p99
- [ ] Acceptance rate >= 90%

---

## Architecture: Observability Data Flow

```
Payment enters gateway (:8080)
     │
     ├─► Logstash (TCP :5044, JSON decoder)
     │     │
     │     └─► Elasticsearch :9200 (index: clearflow-YYYY.MM.DD)
     │           │
     │           ├─► Kibana :5601 (search UI)
     │           └─► MCP gateway (query API)
     │
     ├─► Spring Cloud Sleuth (distributed trace)
     │     │
     │     └─► Jaeger :16686 (trace visualization)
     │
     └─► Micrometer (metrics collection)
           │
           └─► Prometheus :9090 (time-series DB)
                 │
                 └─► Grafana :3001 (dashboard UI)
```

---

## Using Observability for the Paper

| Table | Dashboard | How to Capture |
|---|---|---|
| Table III (Latency) | Prometheus query: `histogram_quantile(0.99, ...)` | Screenshot the query result |
| Table IV (Fraud Rate) | Grafana fraud-intelligence dashboard | Screenshot during 100K run |
| Table V (Cascade) | Kibana timeline during failure | Screenshot log sequence |
| Fig. 2 (Timeline) | Kibana logs sorted by timestamp | Screenshot the table |
| Fig. 3 (Recovery) | Grafana acceptance rate graph | Screenshot the line chart |

---

## Troubleshooting

**Grafana shows no data:**
- Services might still be starting. Wait 30s after `clearflow-start.sh` completes
- Check Prometheus targets: http://localhost:9090/targets (all should be GREEN)

**Kibana has no logs:**
- Elasticsearch indices might not be created yet. Send a payment first via `live_payment_sender.py`
- Check: `curl http://localhost:9200/_cat/indices?v | grep clearflow`

**Jaeger shows no traces:**
- Traces are sampled at 10%. Send 100+ payments to guarantee a trace appears
- Check service dropdown is set to `gateway` or `mcp-readonly-gateway`

**ActiveMQ console won't load:**
- Wait 20s after docker compose up — Artemis takes time to boot
- Check: `curl http://localhost:8161` (should return HTML)

---

## Next Steps

1. **Run observability demo**: `bash observability-demo-tour.sh`
2. **Capture screenshots**: Use screenshots for paper figures
3. **Export dashboards**: Grafana → Export → Save as JSON for reproducibility
4. **Verify metrics**: Run `batch_100k.py` and check all SLAs

