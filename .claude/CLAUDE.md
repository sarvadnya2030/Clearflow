# Real-Time Payment Cascade Intelligence — Project-Specific Instructions

## Standing Rule: Verify Every Built Component Actually Returns Real Data

Before trusting or evaluating any new evidence source, endpoint, or
pipeline stage (code graph, broker topology, blast radius, RAG context,
any API) — manually inspect its actual output, not just whether the
caller returns HTTP 200 without error. A component can run clean,
return a plausible-looking response, and still be silently empty or
wrong (confirmed 2026-09-01: `CodeGraphService.getCodeContext` returned
"(no code context found)" for every real service call all session,
because of a `deriveModule()` path-parsing bug — every LLM prompt this
project built believed it had real code-graph access and did not, and
every downstream eval number computed from it was invalid until this
was caught by direct inspection, not by an error).

**Practice**: after building or changing anything that feeds evidence
into a decision (a ranking, an LLM prompt, a score) — call it directly,
print/log the raw output, and read it. If it's empty, wrong, or
nonsensical, fix or discard it before trusting anything built on top of
it. Do not assume correctness from "it compiled" or "the endpoint
responded." This is a standing practice for this project, not a one-off
fix — apply it to every new evidence source going forward.

## Startup Checklist (Required Before Any Work)

**CRITICAL: Always run this first:**

```bash
cd /home/admin-/Desktop/EDI6/clearflow
bash start_live_traffic.sh
```

Expected output:
```
  ✓ gateway (:8080)
  ✓ fraud-scoring (:8081)
  ✓ validation-enrichment (:8082)
  ✓ aml-compliance (:8083)
  ✓ routing-execution (:8084)
  ✓ settlement (:8085)
  ✓ audit (:8086)
  ✓ mcp-readonly-gateway (:8087)
```

If any service shows ✗, check `/home/admin-/Desktop/EDI6/clearflow/dev-logs/{service}.log`

**Typical startup issues:**
1. **Kafka topics missing** → Script creates them, but if failures occur: `cd infrastructure && docker compose exec -T kafka kafka-topics --list | grep clearflow`
2. **ActiveMQ blocked** → Already fixed (pool=200), check `gateway/src/main/resources/application-dev.yml`
3. **Port conflicts** → Kill old processes: `pkill -f "\.jar"`

---

## Common Commands

```bash
# View service status
for p in 8080 8081 8082 8083 8084 8085 8086 8087; do
  curl -s localhost:$p/actuator/health | jq .status
done

# Tail a service log
tail -f dev-logs/gateway.log
tail -f dev-logs/fraud-scoring.log

# Run load test
python3 batch_100k.py

# Stop all services
bash stop_live_traffic.sh
```

---

## Architecture Context

- **8 microservices** on ports 8080–8087, all Spring Boot 3.3.2 with Java 21
- **Message brokers**: Kafka (events) + ActiveMQ Artemis (JMS coordination)
- **Databases**: H2 (dev), MongoDB, Cassandra, Redis, Elasticsearch
- **Pipeline**: 7-stage payment processing (fraud → validation → AML → routing → settlement → audit)
- **Memory**: Each service runs with `-Xmx2048m -Xms1024m -XX:+UseG1GC`

---

## Known Issues & Fixes (Already Applied)

| Issue | Fix | File |
|-------|-----|------|
| 100K test cascading failure (0.2% accept) | ✓ Increased ActiveMQ pool (50→200), circuit breaker tuning (50%→80%) | `gateway/src/main/resources/application-dev.yml` |
| Gateway heap OOM | ✓ Doubled heap (1GB→2GB), G1GC + 200ms pause target | start_live_traffic.sh |
| Kafka topics missing | ✓ Script auto-creates 9 topics on startup | start_live_traffic.sh |
| Services failing health checks | ✓ Wait for topics to initialize, increased timeouts | start_live_traffic.sh |

---

## Test Workflow

After services are UP:

```bash
# 1. Quick smoke test (15 payments, all stages)
python3 live_payment_sender.py

# Expected: Sent=15, Accepted=15 (HTTP 202), Rejected=0

# 2. Heavy load test (100K payments in 200 batches)
python3 batch_100k.py

# Expected (validated 2026-04-29):
#   accept=95% (5K AML correctly rejected), p99=206ms, p95=154ms, errors=0%
#   Full pipeline funnel: 95K/95K fraud→validated→AML→routed→settled, 0 routing failures
# Old result (before fixes): 0.2% acceptance rate with cascading failure
```

---

## Project State (as of 2026-04-29)

**Phase Status:**
- ✅ Phase 1 — Enterprise DevOps (COMPLETE)
- ✅ Phase 2 — Performance & Reliability (COMPLETE)
- ✅ Phase 3 Partial — ELK + MCP + correlationId trace (COMPLETE as of 2026-04-29)
  - ELK pipeline operational (9 ES indices, grok extraction, KAFKA_INPUT tag fix)
  - MCP endpoints working: /timeline, /risk, /compliance, /metrics/rails, /metrics/overview
  - correlationId propagated via MDC through all 6 Kafka consumer stages
  - 100K batch test: all SLA gates pass, 0 routing failures, 95K/95K full pipeline
  - TODO: Vault secrets injection, mTLS service mesh, API rate limiting by tier
  
- 📋 Phase 4 — AI/ML Enhancement (FUTURE)
  - Real LightGBM model, UETR anomaly detection, settlement forecasting

**Known fixes (2026-04-29):**
| Fix | File |
|-----|------|
| correlationId MDC in all 6 @KafkaListener handlers | Fraud/Validation/AML/Routing/Settlement/AuditEventConsumer.java |
| MAX_IN_FLIGHT 1→5 on all producers | *KafkaConfig.java (6 files) |
| Kafka topics 3→9 partitions | start_live_traffic.sh |
| Nostro accounts 10M→500B | routing-execution/src/main/resources/data.sql |
| Pessimistic locking (SELECT FOR UPDATE) | LiquidityReservationService.java |
| LiquidityReleaseConsumer post-settlement | routing-execution/src/main/java/.../LiquidityReleaseConsumer.java |
| ES queries .keyword suffix removed | ElasticsearchLogFetcher.java |

**Current Score**: 8.6/10 (target after Phase 3: 9.5/10)

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `QUICK_START.md` | Quick reference for service startup |
| `PROJECT_STATE.md` | Full roadmap, gap analysis, test coverage |
| `TEST_RESULTS_100K_FAILURE.md` | Root cause analysis of prior 0.2% acceptance failure |
| `dev-logs/*.log` | Service logs (not tracked in git) |
| `start_live_traffic.sh` | Startup orchestration (builds, starts, health checks) |
| `batch_100k.py` | 100K payment load test |

---

## Remember

- Services write logs to `/home/admin-/Desktop/EDI6/clearflow/dev-logs/` (not git-tracked)
- All 8 services must be ✅ UP before running tests
- Kafka topics auto-created by script, but failures are usually topic/pool exhaustion
- If startup fails, check logs: most common is "topic not found" → Kafka delay or port in use
