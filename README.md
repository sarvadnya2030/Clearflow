# ClearFlow

**Suggested GitHub Repository Name:** `research-drive-clearflow`

**ISO 20022 Payment Orchestration Platform**

> Enterprise-grade payment infrastructure modelled on the technology stacks at JPMorgan Chase, Barclays, Goldman Sachs, and Deutsche Bank — built with Java 21, Spring Boot 3.3, Kafka, Apache Camel, and a Spring AI MCP observability layer.

![Java 21](https://img.shields.io/badge/Java-21-007396?logo=openjdk)
![Spring Boot](https://img.shields.io/badge/Spring_Boot-3.3.2-6DB33F?logo=springboot)
![Kafka](https://img.shields.io/badge/Apache_Kafka-3.6-231F20?logo=apachekafka)
![Camel](https://img.shields.io/badge/Apache_Camel-4.6-E34234)
![Tests](https://img.shields.io/badge/Tests-41_passing-brightgreen)
![ISO 20022](https://img.shields.io/badge/ISO_20022-pacs.008-blue)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What it does

A payment enters at the **Gateway**, fanned out simultaneously to Kafka + ActiveMQ + Solace. It flows through **Fraud Scoring** (LightGBM velocity checks), **Validation** (IBAN/BIC/embargo via Apache Camel), **AML Screening** (OFAC/SDN fuzzy match + Camunda BPMN), **Rail Selection** (12 rails, Chain of Responsibility), **Double-Entry Settlement** (debit/credit ledger with optimistic locking), and finally an **immutable Cassandra audit trail** (SHA-256 hash chain). An AI/MCP gateway answers natural-language ops queries against the live pipeline.

```
POST /api/v1/payments (ISO 20022 pacs.008)
        │
        ▼
  ┌─────────────┐   idempotency (Redis)   rate-limit (Redis)
  │  Gateway    │──► Kafka  ──────────────────────────────┐
  │  :8080      │──► ActiveMQ (Camel backbone)            │
  └─────────────┘──► Solace (hierarchical stub)           │
                                                          │
  ┌───────────────────────────────────────────────────────▼──┐
  │  fraud-scoring :8081   → aml-compliance :8083            │
  │  validation    :8082   → routing-execution :8084         │
  │                          settlement :8085                │
  │                          audit :8086 (hash chain)        │
  └──────────────────────────────────────────────────────────┘
                                                          │
  ┌───────────────────────────────────────────────────────▼──┐
  │  mcp-readonly-gateway :8087                              │
  │  13 AI tools · code graph 1162 nodes · LLM RCA          │
  └──────────────────────────────────────────────────────────┘
```

**10 microservices · 12 payment rails · 3 message brokers · 7 data stores · 41 tests**

---

## Key Engineering Highlights

| Area | Detail |
|---|---|
| **Message Brokers** | Kafka (fan-out, 17 topics) + ActiveMQ Artemis/Camel (orchestration, 11 queues) + Solace (hierarchical pub/sub) |
| **Resilience** | Resilience4j circuit breakers per broker, Saga choreography compensation route, 3-retry DLQ with exponential backoff |
| **Compliance** | FATF, EU AML6D, OFAC SDN/PEP screening (0.85 fuzzy threshold), Basel III LCR, CTR/SAR auto-generation |
| **Settlement** | Double-entry accounting (Debit = Credit assertion), `@Version` optimistic locking, imbalance exception circuit |
| **Audit** | SHA-256 hash chain — each record includes previous record's hash; tamper-evident, court-admissible trail |
| **AI Layer** | Spring AI MCP server with 13 tools: timeline reconstruction, LLM-powered root cause analysis, broker cascade tracing, code graph (1,162 nodes) |
| **Observability** | Prometheus + Grafana dashboards + Jaeger distributed tracing + ELK structured logs (634k+ events) + 18 Prometheus alerting rules |
| **DevOps** | GitHub Actions CI (test → build → SonarQube → Docker) + CD (Helm deploy to staging/prod) + Kubernetes Helm charts with HPA |
| **Performance** | k6 load test: ramp to 200 VUs, SLA: p99 < 500ms, error rate < 1%, accept rate > 95% |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     ClearFlow Architecture                      │
├─────────────────┬──────────────────┬───────────────────────────┤
│  INGESTION      │  PROCESSING      │  PERSISTENCE              │
│                 │                  │                           │
│  Gateway        │  fraud-scoring   │  Oracle XE (JPA)          │
│  ├ WebFlux      │  ├ LightGBM stub │  H2 (dev profile)         │
│  ├ Idempotency  │  ├ Velocity      │  Cassandra (audit chain)  │
│  ├ Rate limit   │  └ Redis state   │  MongoDB (enrichment)     │
│  └ 3-broker     │                  │  Redis (cache/rate limit) │
│    fan-out      │  validation      │  ClickHouse (analytics)   │
│                 │  ├ IBAN/BIC      │  CockroachDB (settlement) │
│                 │  ├ Embargo       │                           │
│                 │  └ Camel routes  ├───────────────────────────┤
│                 │                  │  MESSAGING                │
│                 │  aml-compliance  │                           │
│                 │  ├ SDN/PEP fuzzy │  Kafka :9092              │
│                 │  ├ Camunda BPMN  │  ActiveMQ :61616          │
│                 │  └ CSV watchlist │  Solace :55555            │
│                 │                  │                           │
│                 │  routing         ├───────────────────────────┤
│                 │  ├ 12 rails      │  OBSERVABILITY            │
│                 │  ├ CoR pattern   │                           │
│                 │  └ Saga comp.    │  Prometheus :9090         │
│                 │                  │  Grafana :3001            │
│                 │  settlement      │  Elasticsearch :9200      │
│                 │  ├ Double-entry  │  Kibana :5601             │
│                 │  └ @Version lock │  Jaeger :16686            │
│                 │                  │  SonarQube :9001          │
│                 │  audit           │                           │
│                 │  └ SHA-256 chain ├───────────────────────────┤
│                 │                  │  AI / MCP                 │
│                 │  mcp-gateway     │                           │
│                 │  ├ 13 tools      │  Ollama (local LLM)       │
│                 │  ├ Code graph    │  OpenRouter API           │
│                 │  └ LLM RCA       │  React Dashboard :3000    │
└─────────────────┴──────────────────┴───────────────────────────┘
```

---

## Quick Start (Dev Mode — no Oracle/Keycloak required)

```bash
# 1. Start minimal infrastructure (Kafka, ActiveMQ, Redis, MongoDB, Cassandra, ES)
bash start_live_traffic.sh

# 2. Send live ISO 20022 payments through all 7 services
python3 live_payment_sender.py

# 3. Batch load test
python3 live_payment_sender.py --batch 100
```

Services start with `SPRING_PROFILES_ACTIVE=dev`:
- Oracle → H2 in-memory (schema auto-created)
- JWT → `DevSecurityConfig` permits all (no Keycloak)
- Brokers → localhost

---

## Full Stack Start (Production-like)

```bash
cd infrastructure
docker compose up -d
```

Then build and start all services:

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  mvn clean package -DskipTests --no-transfer-progress
```

---

## Submit a Payment

```bash
curl -X POST http://localhost:8080/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-Correlation-Id: $(uuidgen)" \
  -d '{
    "instructionId": "8b1f8f5f-3139-4cd7-abcb-a179f8f5f97a",
    "endToEndId":    "E2E-20260417-00001",
    "uetr":          "f3d3b8ee-3daf-4c44-8a62-2dbece2ba67c",
    "debtor":   { "name": "Alpine Logistics GmbH", "iban": "DE89370400440532013000",       "bic": "DEUTDEDBXXX", "country": "DE" },
    "creditor": { "name": "Euro Trade SARL",        "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR" },
    "amount": 125000.00,
    "currency": "EUR",
    "channel": "SEPA",
    "remittanceInfo": "Invoice INV-98765"
  }'
# → HTTP 202 Accepted  {"paymentId": "...", "status": "PROCESSING"}
```

---

## MCP AI Tools (13 Tools)

Ask the AI gateway directly or connect Claude Code via SSE:

```bash
# Natural language query
curl -X POST http://localhost:8087/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Why did payment PAY-123 fail? Show me the root cause."}'

# MCP SSE endpoint for Claude Code
# Add to claude_desktop_config.json:
# "clearflow": { "url": "http://localhost:8087/mcp/sse" }
```

| Tool | Description |
|---|---|
| `getPaymentTimeline` | Full ES log timeline for a payment ID |
| `classifyRootCause` | ML-powered failure classification |
| `explainIncidentWithCode` | ES logs + code graph + LLM → Java-class-level RCA |
| `traceBrokerCascade` | Cascade failure trace across Kafka/ActiveMQ/Solace |
| `analyzeSystemicFailure` | Cluster-level pattern detection |
| `getCircuitBreakerStatus` | Resilience4j state per broker |
| `getKafkaLag` | Consumer group lag per topic |
| `getComplianceSnapshot` | CTR/SAR/OFAC hit-rate metrics |
| `getRailPerformance` | Per-rail throughput and latency |
| `detectAnomalies` | Statistical outlier detection on payment streams |
| `getFraudPatternAnalysis` | Velocity and country risk breakdown |
| `getCamelRouteHealth` | Apache Camel route uptime and error rates |
| `getPaymentSummary` | Aggregate payment statistics |

---

## Load Testing

```bash
# Install k6: https://k6.io/docs/get-started/installation/
k6 run load-tests/k6/payment_load_test.js

# With InfluxDB output for Grafana
k6 run --out influxdb=http://localhost:8086/clearflow \
  load-tests/k6/payment_load_test.js
```

**SLA Thresholds:**
- P99 latency < 500ms
- P95 latency < 200ms
- Error rate < 1%
- Accept rate > 95%

---

## Kubernetes Deployment

```bash
# Lint
helm lint k8s/helm/clearflow

# Deploy to staging
helm upgrade --install clearflow k8s/helm/clearflow \
  --namespace clearflow-staging --create-namespace \
  --values k8s/helm/clearflow/values-staging.yaml \
  --set global.image.tag=<git-sha>

# Deploy to production (with HPA: 2–10 replicas per service)
helm upgrade --install clearflow k8s/helm/clearflow \
  --namespace clearflow-prod --create-namespace \
  --values k8s/helm/clearflow/values.yaml
```

---

## CI/CD Pipeline

| Stage | Trigger | Action |
|---|---|---|
| Test | Every PR/push | Unit tests + ArchUnit + JUnit report |
| Quality Gate | Push to main | SonarQube analysis (`quality gate wait=true`) |
| Security Scan | Push to main | OWASP Dependency-Check (fail on CVSS ≥ 9) |
| Docker Build | Push to main | Build + push all 9 images to GHCR (matrix strategy) |
| CD Staging | Push to main | Helm deploy + smoke test |
| CD Production | Manual trigger | Canary 20% rollout + Slack notification |

---

## Observability

| Tool | URL | Purpose |
|---|---|---|
| React Dashboard | http://localhost:3000 | Payment ops UI, MCP chat |
| Grafana | http://localhost:3001 | Payment pipeline dashboard, JVM metrics |
| Kibana | http://localhost:5601 | Structured log search |
| Jaeger | http://localhost:16686 | Distributed trace explorer |
| Prometheus | http://localhost:9090 | Metrics + 18 alerting rules |
| SonarQube | http://localhost:9001 | Code quality gate |
| ActiveMQ Console | http://localhost:8161 | Queue depths, DLQ monitor |

---

## Port Reference

| Service | Port |
|---|---|
| Frontend Dashboard | 3000 |
| Gateway | 8080 |
| Fraud Scoring | 8081 |
| Validation & Enrichment | 8082 |
| AML Compliance | 8083 |
| Routing & Execution | 8084 |
| Settlement | 8085 |
| Audit | 8086 |
| MCP AI Gateway | 8087 |
| Config Server | 8888 |

---

## Tech Stack

| Category | Technologies |
|---|---|
| **Runtime** | Java 21, Spring Boot 3.3.2, Spring WebFlux (reactive gateway) |
| **Messaging** | Apache Kafka 3.6, ActiveMQ Artemis 2.31, Solace PubSub+ 10.8, Apache Camel 4.6 |
| **Persistence** | Oracle XE 21 (JPA), H2 (dev), Cassandra 4.1, MongoDB 7, Redis 7.2, ClickHouse 23.11 |
| **Resilience** | Resilience4j (circuit breaker, retry, rate limiter), Saga choreography |
| **Security** | Spring Security OAuth2 / JWT, Keycloak 22, HashiCorp Vault 1.5 |
| **AI/ML** | Spring AI MCP, Ollama, OpenRouter, LightGBM stub, code knowledge graph |
| **Observability** | Prometheus, Grafana, ELK Stack 8.11, Jaeger 1.52, Micrometer |
| **DevOps** | GitHub Actions CI/CD, Helm 3.14, Kubernetes (HPA), Docker Compose, SonarQube |
| **Testing** | JUnit 5, ArchUnit, Mockito, k6 load tests |
| **Standards** | ISO 20022 pacs.008, FATF, OFAC, EU AML6D, Basel III LCR |

---

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full architecture, payment lifecycle, rail selection, resilience patterns |
| [PROJECT_STATE.md](PROJECT_STATE.md) | Current state, improvement roadmap, target score |
| [RUN-TEST-GUIDE.md](RUN-TEST-GUIDE.md) | Step-by-step test execution guide |
| [load-tests/k6/](load-tests/k6/) | k6 load test scripts |
| [k8s/helm/clearflow/](k8s/helm/clearflow/) | Kubernetes Helm chart |
| [infrastructure/prometheus/alerts/](infrastructure/prometheus/alerts/) | Prometheus alerting rules |
| [infrastructure/grafana/](infrastructure/grafana/) | Grafana dashboard provisioning |
