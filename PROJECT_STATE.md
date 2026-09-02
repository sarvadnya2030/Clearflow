# ClearFlow — Project State & Improvement Roadmap

> Last updated: 2026-04-17

---

## Current State

### What's Built

| Layer | Component | Status | Notes |
|---|---|---|---|
| **API Gateway** | `gateway` :8080 | ✅ Complete | WebFlux, idempotency, rate-limiting, 3-broker fan-out |
| **Fraud Detection** | `fraud-scoring` :8081 | ✅ Complete | LightGBM stub, velocity checks, Redis state |
| **Validation** | `validation-enrichment` :8082 | ✅ Complete | Camel routes, IBAN/BIC/embargo checks |
| **AML Screening** | `aml-compliance` :8083 | ✅ Complete | Fuzzy SDN/PEP, Camunda BPMN, 0.85 threshold |
| **Routing** | `routing-execution` :8084 | ✅ Complete | 12 rails, Chain of Responsibility, saga compensation |
| **Settlement** | `settlement` :8085 | ✅ Complete | Double-entry accounting, LedgerEntry, optimistic locking |
| **Audit** | `audit` :8086 | ✅ Complete | SHA-256 hash chain, Cassandra, immutable trail |
| **MCP AI Gateway** | `mcp-readonly-gateway` :8087 | ✅ Complete | 13 tools, code graph, broker topology, LLM RCA |
| **Config Server** | `config-server` :8888 | ✅ Complete | Spring Cloud Config, per-service YAML |
| **Frontend** | `frontend` :3000 | ✅ Complete | React + Vite, MCP chat, payment search, dashboard |

### Message Broker Topology

| Broker | Role | Topics/Queues |
|---|---|---|
| **Kafka** | Event streaming fan-out | 17 topics incl. DLQs |
| **ActiveMQ Artemis** | Camel orchestration backbone | 11 queues + saga queues |
| **Solace** | Hierarchical pub/sub stub | 1 topic |
| **Resilience4j** | Circuit breakers | 3 (KAFKA, ACTIVEMQ, SOLACE) |

### Knowledge Graph (graphify)
- **1,162 nodes**, **1,471 edges**, **94 communities**
- God nodes: `ElasticsearchLogFetcher` (24 edges), `ClearFlowMcpTools` (20 edges)
- Hyperedges: Cascading Failure Event Types, Three-Broker Messaging Topology, Regulatory Compliance Suite, AML Framework, MCP Tools Ecosystem

### MCP Tools (13 total)
1. `getPaymentTimeline` — ES log timeline reconstruction
2. `classifyRootCause` — ML classifier (FRAUD_BLOCK, AML_HIT, TIMEOUT, etc.)
3. `analyzeSystemicFailure` — cluster-level pattern detection
4. `getRailPerformance` — per-rail throughput/latency metrics
5. `getComplianceSnapshot` — CTR/SAR/OFAC screening metrics
6. `detectAnomalies` — statistical outlier detection
7. `getCircuitBreakerStatus` — Resilience4j state read
8. `getKafkaLag` — consumer group lag
9. `getPaymentSummary` — aggregate payment stats
10. `getCamelRouteHealth` — Camel route uptime/error rates
11. `getFraudPatternAnalysis` — velocity/country risk breakdown
12. `explainIncidentWithCode` — ES + code graph + LLM → Java-class-level RCA
13. `traceBrokerCascade` — cascade failure trace across all 3 brokers

### Compliance Coverage
- ISO 20022 pacs.008 payment format
- FATF Recommendations (40 rules)
- EU AML6D
- OFAC SDN/PEP screening
- Basel III LCR
- CTR / SAR auto-generation
- SHA-256 hash chain audit trail (tamper-evident)

### Test Suite
- **41 tests passing** (as of 2026-03-02)
- `PaymentArchTest` — ArchUnit layer enforcement
- `FraudScoringServiceTest` — ML scoring unit tests
- `FuzzyMatchTest` — SDN/PEP matching accuracy
- `RailSelectionTest` — 12-rail routing logic
- `DoubleEntryAccountingTest` — ledger balance assertions
- `HashChainIntegrityTest` — tamper detection
- `PaymentTimelineReconstructorTest`, `RootCauseAnalysisServiceTest`, `RootCauseClassifierTest`

### Infrastructure Stack
```
Kafka + ZooKeeper    — event streaming
ActiveMQ Artemis     — JMS orchestration
Solace               — hierarchical pub/sub
Redis                — idempotency + rate limiting + cache
Oracle XE            — JPA persistence (prod)
H2                   — JPA persistence (dev profile)
Cassandra            — audit hash chain
MongoDB              — enrichment document store
ClickHouse           — OLAP analytics (declared, pending wire-up)
CockroachDB          — distributed SQL (declared, pending wire-up)
Elasticsearch 8      — structured log storage (634k+ events ingested)
Kibana               — log visualization
Prometheus           — metrics scraping
Grafana              — dashboards (infra running, dashboards TBD)
Jaeger               — distributed tracing
Vault                — secrets management
Keycloak             — OAuth2/JWT (dev profile bypasses)
SonarQube            — static analysis
```

### Dev Profile (added 2026-04-17)
All 8 services now start with `SPRING_PROFILES_ACTIVE=dev`:
- Oracle → H2 in-memory (create-drop)
- Cassandra → excluded in settlement; `clearflow_dev` keyspace in audit
- JWT → DevSecurityConfig permits all (no Keycloak needed)
- Brokers → localhost instead of Docker hostnames
- Start: `bash start_live_traffic.sh` → `python3 live_payment_sender.py`

---

## Current Score: 8.6 / 10

### Gaps vs Enterprise Standard

| Gap | Impact | Effort |
|---|---|---|
| No GitHub Actions CI/CD | Critical — enterprise hiring bar | Low |
| No Kubernetes/Helm charts | Critical — every bank runs k8s | Medium |
| No Grafana dashboard definitions | High — "show me observability" question | Low |
| No load test results | High — "what TPS can it handle?" | Low |
| No Prometheus alerting rules | High — SLA/SLO definition | Low |
| ClickHouse analytics not wired | Medium — settlement reporting incomplete | Medium |
| No SWIFT GPI UETR tracking API | Medium — SWIFT interoperability proof | Medium |
| No API contract (OpenAPI export) | Medium — integration partner story | Low |
| No mTLS between services | Medium — zero-trust networking | Medium |
| Frontend not wired to live data | Medium — demo impact | Medium |

---

## Improvement Roadmap

### Phase 1 — Enterprise DevOps (✅ COMPLETE — 2026-04-17)
- [x] Dev profiles for all 8 services (`application-dev.yml`)
- [x] Live traffic startup script (`start_live_traffic.sh`)
- [x] Live payment sender (`live_payment_sender.py` — ISO 20022 pacs.008)
- [x] **GitHub Actions CI** — `.github/workflows/ci.yml` (test → sonar → OWASP → Docker matrix)
- [x] **GitHub Actions CD** — `.github/workflows/cd.yml` (Helm staging + canary prod)
- [x] **Kubernetes Helm charts** — `k8s/helm/clearflow/` (all 8 services, HPA, Ingress, Secrets)
- [x] **Prometheus alerting rules** — `infrastructure/prometheus/alerts/clearflow-alerts.yml` (18 rules)
- [x] **Grafana dashboard JSON** — `infrastructure/grafana/provisioning/` (payment pipeline board)
- [x] **k6 load test** — `load-tests/k6/payment_load_test.js` (ramp → 200 VUs, SLA assertions)
- [x] **README overhaul** — badge wall, architecture diagram, full tech stack, enterprise-ready

### Phase 2 — Performance & Reliability (✅ COMPLETE — 2026-04-17)
- [x] **k6 load test suite** — `load-tests/k6/payment_load_test.js` (ramp 0→200 VUs, SLA assertions)
- [x] **ClickHouse analytics wire-up** — `ClickHouseAnalyticsService` (async write, `@ConditionalOnProperty`)
- [x] **SWIFT GPI UETR tracking** — `UETRTrackerController` `/api/v1/payments/track/{uetr}` (6-agent chain)
- [x] **Avro schema contracts** — `common/src/main/avro/*.avsc` (PaymentInitiated, FraudEvaluated, Enriched)
- [x] **demo.sh rewrite** — 8-act interactive demo showing all features end-to-end
- [x] **deploy.sh** — single-command Docker deployment (`bash deploy.sh`)

### Phase 3 — Security Hardening
- [ ] **Vault secrets injection** — replace env var credentials with Vault dynamic secrets
- [ ] **mTLS service mesh** — Istio sidecar injection between services
- [ ] **API rate limit by client tier** — Gold/Silver/Bronze SLA tiers in gateway

### Phase 4 — AI/ML Enhancement
- [ ] **Real LightGBM model** — replace stub with actual trained fraud model
- [ ] **UETR anomaly detection** — unsupervised clustering on payment patterns
- [ ] **MCP Tool 14: forecastSettlement** — LLM-powered settlement prediction

---

## Target Score After Phase 1+2: 9.5 / 10

The additions below turn this from an impressive demo into an **enterprise-deployable platform**
that mirrors what Goldman Sachs, JPMorgan, Barclays, and Deutsche Bank run in production.
