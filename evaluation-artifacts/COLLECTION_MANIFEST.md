# ClearFlow Evaluation Artifacts Collection

**Collection Date**: 2026-05-21  
**Evaluation Type**: Tiers 1-4 (Full evaluation for academic paper)

## Contents

### Tier 1 — Essential Artifacts (Real Data)

- **dev-logs/** — Raw JSON logs from 100K payment soak test
  - Gateway logs: payment ingestion, idempotency checks, rate limiting
  - Fraud-scoring logs: heuristic + LightGBM scores
  - Audit logs: SHA-256 hash chain integrity records
  - All logs include `correlationId` for payment tracing
  - Total events: ~91,146 (from prior run; current run TBD)
  
- **batch_100k_eval_run.log** — Console output from 100K test
  - Per-batch acceptance rates
  - Latency percentiles (p50, p95, p99)
  - Error breakdown
  - Final SLA assessment

- **generate_summary_*.csv** — Per-batch statistics
  - Timestamp, batch #, accepted count, error count, latency min/max/avg

### Tier 2 — Ablation Study Data (Optional)

Pre-configured test scenarios:
```
C1: pool=50,   θ=50%   (original failure config)
C2: pool=100,  θ=50%   (partial fix)
C3: pool=100,  θ=75%, wait=60s  (tuned)
C4: pool=200,  θ=75%, partitions=12 (final fix)
```

Status: Not yet collected (requires ~4 hours for all runs)

### Tier 3 — Observability Artifacts

- **grafana/** — Grafana dashboard definitions (7 dashboards)
  - clearflow-main.json — payment pipeline overview
  - clearflow-payments.json — per-rail throughput
  - clearflow-fraud.json — fraud rates and patterns
  - clearflow-infrastructure.json — JVM, Kafka, Redis metrics
  - clearflow-slo.json — SLA/SLO burn rate
  - clearflow-command-center.json — ops command center
  - clearflow-fraud-intelligence.json — fraud pattern analysis

- **graphify-out/** — Knowledge graph (1,162 nodes, 1,471 edges)
  - graph.json — JSON-LD knowledge graph
  - graph.html — Interactive visualization
  - GRAPH_REPORT.md — Community detection report

- **Screenshots/** (To be added)
  - Grafana dashboard during 100K run
  - Kibana log search by correlationId
  - Cascade failure timeline

### Tier 4 — AI/LLM Evaluation

MCP tool responses on real payments:

- **mcp-outputs/getPaymentTimeline** — Full timeline for sample payments
  - Events per payment: initiated → fraud → validated → AML → routed → settled → audited
  - Correlations between service logs
  
- **mcp-outputs/classifyRootCause** — Root cause classification
  - FRAUD_BLOCK, AML_HIT, TIMEOUT, BROKER_FAILURE, etc.
  - Classifier metrics: Cohen's κ, F₁ score (TBD)

- **mcp-outputs/explainIncidentWithCode** — LLM-powered RCA
  - ES logs + code graph context + LLM response
  - Java class names, method names cited
  - Hallucination check: comparing LLM claims to actual codebase (TBD)

## Usage for Paper

| Section | Uses | Status |
|---------|------|--------|
| Table III (Payment Throughput) | batch_100k_eval_run.log | ✓ Real data |
| Table IV (Latency Distribution) | batch_100k_eval_run.log | ✓ Real data |
| Table V (Cascade Failure) | dev-logs + graphify-out | ✓ Real data |
| Table VI (MCP Classifier Metrics) | mcp-outputs | ⏳ In progress |
| Fig. 2 (Cascade Timeline) | Kibana screenshot | ⏳ To capture |
| Fig. 3 (Pipeline Recovery) | Grafana screenshot | ⏳ To capture |
| Algorithm 1 (Root Cause Analysis) | code graph + LLM outputs | ⏳ To generate |

## File Sizes (Estimated)

```
dev-logs/              ~200-500 MB (depends on compression)
graphify-out/          ~50 MB
grafana/               ~2 MB
mcp-outputs/           ~10 MB
batch_100k_eval_run.log ~5 MB
TOTAL                  ~260-560 MB
```

## Next Steps

1. ✅ Run 100K test to completion (in progress)
2. ⏳ Collect dev-logs/
3. ⏳ Take Grafana/Kibana screenshots
4. ⏳ Query MCP tools for real failed payments
5. ⏳ Zip and package for paper
