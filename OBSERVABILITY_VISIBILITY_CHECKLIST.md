# ClearFlow Observability — Visibility Checklist for Demos

**Purpose**: Ensure ALL observability tools are visible and working during demos. Reviewers should see the complete story: payments flowing + all dashboards showing data in real-time.

---

## Pre-Demo Checklist (Before Opening Dashboards)

### 1. **Services Running** ✅
```bash
for p in 8080 8081 8082 8083 8084 8085 8086 8087; do
  echo -n "Port :$p — "
  curl -s localhost:$p/actuator/health | jq -r .status || echo "DOWN"
done
```
Expected: All 8 services show `UP`

### 2. **Infrastructure Running** ✅
```bash
cd infrastructure && docker compose ps | grep -E "Up|Exited"
```
Expected: 
- ✅ kafka: Up
- ✅ zookeeper: Up
- ✅ elasticsearch: Up
- ✅ kibana: Up
- ✅ prometheus: Up
- ✅ grafana: Up
- ✅ jaeger: Up
- ✅ activemq-artemis: Up
- ✅ redis: Up
- ✅ mongodb: Up
- ✅ cassandra: Up

### 3. **Elasticsearch Indices Exist** ✅
```bash
curl -s http://localhost:9200/_cat/indices?v | grep clearflow
```
Expected: At least one index starting with `clearflow-`

### 4. **Prometheus Targets Healthy** ✅
- Go to: http://localhost:9090/targets
- Look for: Status = `UP` for all services
- Expected: 8+ targets (gateway, fraud-scoring, etc.)

### 5. **Grafana Dashboards Loaded** ✅
- Go to: http://localhost:3001
- Home → Dashboards
- Expected: At least 5 ClearFlow dashboards visible

---

## Dashboard URLs (Open in Tabs)

**Copy-paste these URLs into browser tabs BEFORE sending payments:**

```
Tab 1: Grafana (Payment Metrics)
http://localhost:3001/d/clearflow-main/clearflow-payment-operations

Tab 2: Kibana (Logs)
http://localhost:5601/app/discover#/

Tab 3: Jaeger (Traces)
http://localhost:16686/search?service=gateway

Tab 4: Prometheus (Raw Metrics)
http://localhost:9090/graph

Tab 5: ActiveMQ (Queue Monitor)
http://localhost:8161

Bonus: ElasticSearch (API)
http://localhost:9200/_plugin/kibana
```

---

## Demo Narrative — "Show All Systems Alive"

### **Phase 1: Show Dashboards Ready** (2 min)

"Before we send any payments, notice what we have running:

**[Point to each tab]**

1. **Grafana** — Business metrics. See the payment funnel chart? It's empty now.
2. **Kibana** — Log search. Any payment traces will appear here grouped by `correlationId`.
3. **Jaeger** — Distributed tracing. Shows which service is slow.
4. **Prometheus** — Raw metrics scraped from all 8 services.
5. **ActiveMQ Console** — Message queue depths. Shows broker health.

All five systems are watching the payment pipeline. Now let's send payments and watch them all light up."

### **Phase 2: Send Payments** (2 min)

```bash
python3 live_payment_sender.py
```

### **Phase 3: Watch in Real-Time** (5 min)

**[As payments arrive, point out each system]**

**Grafana:**
- Watch the **acceptance rate** bar grow (should reach ~95%)
- Watch the **payment funnel**: 100 → fraud → validation → AML → routing → settlement
- Watch **per-rail breakdown** (SEPA, SWIFT, CHIPS, etc.)
- Watch **latency histogram** fill in

**Kibana:**
- Logs appear in real-time
- Each payment shows as 7 entries (one per service)
- Sort by `timestamp` — see the progression through stages
- Filter by `service: fraud-scoring` — see only fraud evaluation logs

**Jaeger:**
- Trace count increases
- Click a trace → see 7 spans (gateway → fraud → validation → AML → routing → settlement → audit)
- Span duration shows where time is spent (usually AML)

**Prometheus:**
- Query: `rate(clearflow_payment_accepted_total[1m])`
- Watch the graph climb as payments complete
- Query: `histogram_quantile(0.99, clearflow_payment_latency_ms)`
- Watch p99 latency (should be < 500ms)

**ActiveMQ Console:**
- Queue `clearflow.payment.initiated` shows volume
- Queue `clearflow.payments.dlq` should stay at 0 (no failures)
- After test completes, all queues drain to empty

---

## Data Visibility Verification Matrix

During the demo, verify these points are visible:

| Observable | Where | What to Look For |
|-----------|-------|-----------------|
| **Payment arrival** | Grafana | Funnel left bar increases |
| **Fraud evaluation** | Kibana + Grafana | Fraud scores appear in logs, fraud rate panel updates |
| **Validation stage** | Kibana | `event: validation.complete` entries appear |
| **AML hit** | Kibana + Grafana | Some payments show `aml.sanctions.hit`, rejection rate increases |
| **Routing** | Kibana | `event: payment.routed`, `rail: SEPA_INSTANT` etc. visible |
| **Settlement** | Kibana + Prometheus | `event: payment.settled`, settlement metric increments |
| **Audit** | Kibana | `event: audit.recorded` with `hash: SHA-256-...` |
| **Latency** | Jaeger + Prometheus | Trace duration matches metric, p99 < 500ms |
| **Error handling** | ActiveMQ console | DLQ depth stays 0 |
| **Complete journey** | Kibana search | Filter by one `correlationId` → see exactly 7 events in order |

---

## Advanced Demo Move: Trace One Payment

**After sending payments, show the complete journey of a single payment:**

1. **Copy a paymentId from the output** (e.g., `3edbeb7f-ed6d-490d-ab8d-966254e8e5dc`)

2. **In Kibana**, search:
   ```
   correlationId: 3edbeb7f-ed6d-490d-ab8d-966254e8e5dc
   ```

3. **See exactly 7 log entries in order:**
   ```
   00:05:12.001 — gateway      | payment.initiated
   00:05:12.004 — fraud        | fraud.evaluated (PASS)
   00:05:12.006 — validation   | validation.complete
   00:05:12.009 — aml          | aml.sanctions.clear
   00:05:12.011 — routing      | payment.routed (SEPA_INSTANT)
   00:05:12.014 — settlement   | payment.settled
   00:05:12.015 — audit        | audit.recorded (SHA-256)
   ```

4. **In Jaeger**, select `gateway` service → find a trace with that `traceId` → click to expand → see 7 spans matching the log timeline

5. **Explain:**
   "This payment took 14 milliseconds from API to settlement. Every service logged it, every service traced it, and we can see the exact progression. That's production-grade observability."

---

## For Evaluators: Verification Checklist

Use this to validate observability is working:

- [ ] Grafana loads without errors
- [ ] At least 5 dashboards visible (clearflow-*)
- [ ] Kibana shows >= 100 clearflow-* logs after test
- [ ] Can search by `correlationId` and get exactly 7 results
- [ ] Jaeger shows >= 5 traces with `service: gateway`
- [ ] Prometheus has >= 50 metrics labeled `clearflow_*`
- [ ] ActiveMQ console shows queue names and depths
- [ ] Elasticsearch indices are queryable
- [ ] All timestamps are ISO 8601 UTC
- [ ] Payment acceptance rate visible in Grafana >= 90%
- [ ] p99 latency visible in Prometheus < 500ms
- [ ] DLQ depth in ActiveMQ = 0 (no silent drops)
- [ ] All 7 services appear in Kibana logs (gateway, fraud, validation, aml, routing, settlement, audit)

---

## Troubleshooting — Why Dashboards Show No Data

| Problem | Cause | Fix |
|---------|-------|-----|
| Grafana shows "No Data" | Services just started, no metrics yet | Wait 30s, then refresh |
| Kibana shows "No results" | No payments sent yet | Run `python3 live_payment_sender.py` |
| Jaeger shows "No traces" | Traces sampled at 10% | Send 100+ payments to guarantee a trace |
| Prometheus targets RED | Service health check endpoint not ready | Wait 15s, refresh http://localhost:9090/targets |
| ActiveMQ console won't load | Artemis takes time to boot | Wait 20s after docker compose up |
| Elasticsearch index empty | Logstash processing delay | Wait 5s after first log line, then refresh |

---

## Post-Demo: Capture Artifacts for Paper

**While dashboards are still live (data fresh), capture:**

1. **Grafana screenshot**: Dashboard → Export → PNG (payment funnel visible)
2. **Kibana screenshot**: Payment timeline (correlationId search with 7 events)
3. **Jaeger screenshot**: Trace waterfall (7 spans, end-to-end latency)
4. **Prometheus screenshot**: Query result (p99 latency histogram)
5. **ActiveMQ screenshot**: Queue depths after test

Save these as:
```
evaluation-artifacts/screenshots/
  ├── grafana-payment-funnel.png
  ├── kibana-payment-timeline.png
  ├── jaeger-trace-waterfall.png
  ├── prometheus-p99-latency.png
  └── activemq-queue-depths.png
```

These become **Figures 2-3** in your paper.

---

## Summary: Observability Visibility in ClearFlow

**What makes this demo powerful:**

- ✅ **Not simulated**: Real payments flowing through real services
- ✅ **Not just code**: 5 independent observability systems all showing the same story
- ✅ **Not just metrics**: Logs, traces, and dashboards together prove causality
- ✅ **Not just frontend**: All data is queryable (Kibana full-text search, Prometheus PromQL)
- ✅ **Production-grade**: This is what you'd build at a real bank

Reviewers see: **Payment → Fraud → Validation → AML → Routing → Settlement → Audit**, all visible simultaneously across 5 dashboards. No claims, no synthesized data — just what the system is actually doing, right now.

