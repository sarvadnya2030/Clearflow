# ClearFlow — System Architecture

> ISO 20022 Payment Orchestration Platform
> Mirrors the internal payment infrastructure at JPMorgan Chase, Barclays, Citi, and Mastercard.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Payment Lifecycle — End to End](#3-payment-lifecycle--end-to-end)
4. [Service Deep Dives](#4-service-deep-dives)
   - 4.1 Gateway
   - 4.2 Fraud Scoring
   - 4.3 Validation & Enrichment
   - 4.4 AML Compliance
   - 4.5 Routing & Execution
   - 4.6 Settlement
   - 4.7 Audit
   - 4.8 Config Server
   - 4.9 MCP Read-only Gateway
5. [Rail Selection Logic](#5-rail-selection-logic)
6. [Data Stores](#6-data-stores)
7. [Messaging Topology](#7-messaging-topology)
8. [Security Model](#8-security-model)
9. [Observability Stack](#9-observability-stack)
10. [Resilience Patterns](#10-resilience-patterns)
11. [Frontend Dashboard](#11-frontend-dashboard)
12. [AI / MCP Layer](#12-ai--mcp-layer)
13. [Infrastructure & Deployment](#13-infrastructure--deployment)
14. [Configuration Management](#14-configuration-management)
15. [Test Coverage](#15-test-coverage)
16. [Design Rationale](#16-design-rationale)

---

## 1. Executive Summary

ClearFlow is a **production-grade, event-driven payment orchestration platform** built on the ISO 20022 messaging standard. It processes payments from submission to final settlement and audit, applying real-time fraud scoring, AML/sanctions screening, intelligent rail selection, double-entry bookkeeping, and an immutable hash-chained audit log — all observable through a React dashboard and queryable by LLMs via an MCP gateway.

The technology stack was verified against 2024–2025 job postings from JPMorgan Chase, Barclays, Citi, and Mastercard, making the architecture directly representative of what those institutions run in production.

**Key numbers:**
- **10 microservices** across a Maven multi-module monorepo
- **12 payment rails** (SEPA Instant, SEPA CT, Faster Payments, CHAPS, CHIPS, FEDWIRE, FEDACH, SWIFT GPI, SWIFT MT103, TARGET2, BACS, INTERNAL)
- **3 messaging systems** in parallel: ActiveMQ Artemis (IBM MQ-compatible), Solace, Kafka
- **7 data stores**: Oracle XE, CockroachDB, Cassandra, MongoDB, Redis, ClickHouse, Elasticsearch
- **41 tests** across 7 test classes, all passing

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Client (JWT + OAuth2)                                              │
│  POST /api/v1/payments  ──────────────────────────────────►         │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
             ┌────────────────▼────────────────┐
             │         GATEWAY  :8080          │
             │  - Rate limiting (Bucket4j)     │
             │  - Idempotency (Redis SHA-256)  │
             │  - JWT validation               │
             │  - Publishes to 3 brokers       │
             └───┬────────────┬────────────────┘
                 │            │
         ActiveMQ AMQ     Kafka
         (IBM MQ API)   (events)
                 │            │
    ┌────────────▼──┐   ┌─────▼────────────┐
    │  VALIDATION   │   │  FRAUD SCORING   │
    │  :8082        │   │  :8081           │
    │  Apache Camel │   │  LightGBM+       │
    │  IBAN/BIC/    │   │  Heuristics      │
    │  Embargo/FX   │   └──────────────────┘
    └──────┬────────┘
           │
    ┌──────▼────────┐
    │  AML COMP.    │
    │  :8083        │
    │  Fuzzy SDN/   │
    │  PEP + Camunda│
    └──────┬────────┘
           │
    ┌──────▼────────┐
    │  ROUTING EXEC │
    │  :8084        │
    │  Chain of     │
    │  Responsibility│
    │  + Liquidity  │
    └──────┬────────┘
           │
    ┌──────▼────────┐
    │  SETTLEMENT   │
    │  :8085        │
    │  Double-entry │
    │  Bookkeeping  │
    └──────┬────────┘
           │
    ┌──────▼────────┐
    │  AUDIT        │
    │  :8086        │
    │  SHA-256      │
    │  Hash Chain   │
    └───────────────┘

    ┌──────────────────────────────┐
    │  MCP GATEWAY  :8087          │
    │  Read-only AI/LLM endpoints  │
    │  + Ollama / OpenRouter chat  │
    └──────────────────────────────┘

    ┌──────────────────────────────┐
    │  FRONTEND  :3000             │
    │  React + Vite dashboard      │
    └──────────────────────────────┘

    ┌──────────────────────────────┐
    │  CONFIG SERVER  :8888        │
    │  Spring Cloud Config         │
    └──────────────────────────────┘
```

---

## 3. Payment Lifecycle — End to End

A payment travels through 7 services in sequence. Here is every step:

### Step 1 — Client Submission (Gateway :8080)

The client sends a `POST /api/v1/payments` with an ISO 20022-flavored JSON body (`pacs.008` inspired):

```json
{
  "instructionId": "8b1f8f5f-...",
  "endToEndId": "E2E-0001",
  "uetr": "f3d3b8ee-...",
  "debtor":   { "name": "ALPINE LOGISTICS GMBH", "iban": "DE89...", "bic": "DEUTDEDBXXX", "country": "DE" },
  "creditor": { "name": "EURO TRADE SARL",        "iban": "FR14...", "bic": "BNPAFRPP",    "country": "FR" },
  "amount": 1250.55,
  "currency": "EUR",
  "channel": "SEPA"
}
```

**Gateway applies three gates before accepting:**

| Gate | Mechanism | Store |
|------|-----------|-------|
| Authentication | JWT RS256 validated against Keycloak issuer | Keycloak |
| Rate limiting | Token bucket (20 req/min per subject) via Bucket4j | In-memory |
| Idempotency | SHA-256 of `instructionId + amount + debtorIban`, 24h TTL | Redis |

If the idempotency key already exists, the gateway returns the cached response immediately — no downstream processing.

On acceptance, the gateway:
1. Assigns a `paymentId` (UUID)
2. Publishes the event to **ActiveMQ Artemis** (`PAYMENT.INITIATED` queue) — consumed by validation
3. Publishes the event to **Solace** (`clearflow/payments/initiated` topic)
4. Publishes the event to **Kafka** (`payment.initiated` topic) — consumed by fraud scoring
5. Caches the payment response in Redis for idempotency replay

### Step 2 — Fraud Scoring (fraud-scoring :8081)

Fraud scoring runs **in parallel** with validation (both consume from Kafka/AMQ simultaneously).

The fraud pipeline is:

```
FraudKafkaConsumer
  → FeatureEngineeringService  (extracts 15+ numeric features)
  → LightGBMStubClient         (reactive WebClient to model server, circuit-breaker protected)
  → if circuit open → HeuristicScoringService (fallback)
  → CountryRiskMatrix          (FATF black/grey list lookup)
  → publishes FraudEvaluatedEvent to Kafka
```

**Features extracted include:**
- Amount (raw, log-scaled, z-score)
- Cross-border flag
- Country risk score (both debtor and creditor)
- Velocity metrics (transaction count in 1h/24h windows)
- Channel type encoding

**Country Risk Matrix:**
- Risk 10: Iran, North Korea, Syria, Cuba (FATF black list / sanctions)
- Risk 9: Russia, Belarus, Sudan, Myanmar
- Risk 6: FATF grey list (Algeria, Bolivia, Haiti, Lebanon, etc.)
- Risk 1: US, UK, DE, FR, SG, JP, AU (low-risk jurisdictions)

**Risk Bands:**
- `LOW` (0–30): Auto-proceed
- `MEDIUM` (30–60): Proceed with monitoring
- `HIGH` (60–80): Enhanced Due Diligence flag
- `CRITICAL` (80+): Block and alert

### Step 3 — Validation & Enrichment (validation-enrichment :8082)

Consumes from `PAYMENT.INITIATED` AMQ queue. Implemented as an **Apache Camel route** with 5 sequential processors and a dead-letter channel:

```
from("jms:queue:PAYMENT.INITIATED")
  → IBANValidationProcessor      (mod-97 check, country code validation)
  → BICValidationProcessor       (ISO 9362 format, 8/11 char)
  → CurrencyValidationProcessor  (ISO 4217 currency code)
  → EmbargoPreCheckProcessor     (country against embargo list)
  → EnrichmentProcessor          (adds ECB FX rate, BIC metadata, value date)
  → choice:
      VALID  → PAYMENT.VALIDATED + kafka:payment.validated
      INVALID → PAYMENT.REJECTED + kafka:payment.rejected
```

**Error handling:** 3 retries with exponential backoff (1s base), then dead-letter to `PAYMENT.DLQ`.

**Enrichment adds:**
- ECB FX rate (fetched via `java.net.http.HttpClient` from ECB XML feed)
- Normalized BIC metadata
- Payment value date

### Step 4 — AML Compliance (aml-compliance :8083)

Consumes enriched events via Apache Camel, then:

```
AMLCamelRoute
  → AMLScreeningProcessor
      → FuzzyScreeningEngine.screenPayment(debtorName, creditorName, sdnList)
      → PEPLoader (Politically Exposed Persons list)
      → SDNLoader (OFAC SDN list — 50 sample entries)
      → Camunda Zeebe BPMN workflow (AMLScreeningProcess.bpmn)
```

**FuzzyScreeningEngine — 3-stage name matching:**

1. **Exact match** — Unicode-normalised (NFD + diacritic strip), uppercased, token-sorted comparison
2. **Fuzzy match** — Jaro-Winkler similarity score ≥ configurable threshold (default 0.85)
3. **Soundex match** — Phonetic encoding of the first token; catches spelling variants like "KHALID" vs "KHALED"

The `canonicalize()` function sorts name tokens alphabetically before comparison, so "AL-RASHID KHALID" and "KHALID AL-RASHID" both normalise to the same canonical form.

**Output:**
- `NONE` → proceeds to routing
- `FUZZY` or `SOUNDEX` → EDD (Enhanced Due Diligence) flag set, Camunda review process started
- `EXACT` → payment blocked, Kafka alert published

### Step 5 — Routing & Execution (routing-execution :8084)

Implements the **Chain of Responsibility** pattern. All `PaymentRailRule` beans are sorted by priority and tested in order — the first matching rule wins.

```
RailSelectionEngine
  → sorted list of PaymentRailRule beans
  → first rule where matches(ctx) == true → select(ctx)
  → LiquidityReservationService (checks + reserves nostro balance)
  → publishes routed event downstream
```

If settlement fails, `SagaCompensationRoute` (Apache Camel) listens on `PAYMENT.SETTLEMENT.FAILED` and publishes a `PAYMENT.COMPENSATED` event to reverse the liquidity reservation.

See [Section 5](#5-rail-selection-logic) for the full rail decision matrix.

### Step 6 — Settlement (settlement :8085)

Implements **double-entry bookkeeping** with `SERIALIZABLE` transaction isolation:

```
SettlementCamelRoute
  → SettlementService.settlePayment()
      → create LedgerEntry DEBIT  (debtor account)
      → create LedgerEntry CREDIT (creditor account)
      → verify: SUM(DEBIT) == SUM(CREDIT) for this paymentId
          if imbalance → throw AccountingImbalanceException → saga compensation
      → create SettlementRecord (status=SETTLED)
      → mask IBANs (first 4 + last 4 visible, e.g. DE89 **** **** 3000)
```

Uses Oracle XE for ledger entries (ACID guarantees, SERIALIZABLE isolation) and CockroachDB for SettlementRecords (geo-distributed, survivable).

### Step 7 — Audit (audit :8086)

Every payment event (initiated → validated → fraud-scored → AML → routed → settled) is recorded in an **immutable SHA-256 hash chain** stored in Cassandra:

```
HashChainService.createRecord(paymentId, eventType, eventData)
  → load previous records for paymentId (ordered by eventTime ASC)
  → previousHash = last record's currentHash (or GENESIS_HASH if first)
  → currentHash  = SHA-256(eventData + previousHash + timestamp + paymentId)
  → blockHeight  = records.size() + 1
  → save AuditRecord to Cassandra
```

**Chain verification** (`GET /api/v1/audit/{paymentId}/verify`):
- Recomputes every hash in the chain
- Verifies each record's `previousHash` matches the preceding record's `currentHash`
- Returns `{ valid: true/false, blockCount, brokenAtBlock }`

This provides **cryptographic tamper evidence** — any modification to a historical record invalidates every subsequent hash. The 7-year retention policy satisfies PCI-DSS and regulatory requirements.

---

## 4. Service Deep Dives

### 4.1 Gateway (:8080)

**Technology:** Spring Boot 3.3.2 + Spring WebFlux (reactive)
**Key classes:**

| Class | Responsibility |
|-------|---------------|
| `PaymentController` | REST endpoint, orchestrates gates, dispatches to brokers |
| `IdempotencyService` | Redis-backed dedup, SHA-256 key, 24h TTL |
| `RateLimitingFilter` | Bucket4j token bucket, 20 req/min per JWT subject |
| `SecurityConfig` | OAuth2 resource server, JWT validation (Keycloak RS256) |
| `ActiveMQPublisher` | JMS publish to PAYMENT.INITIATED queue |
| `SolacePublisher` | Solace topic publish |
| `KafkaEventPublisher` | Kafka publish (payment.initiated) |
| `DemoDataLoader` | 20 realistic ISO 20022 scenarios on startup (opt-in) |

**IBAN handling:** All IBANs are masked in logs and API responses using `MaskedIbanSerializer` — only first 4 and last 4 characters are visible.

---

### 4.2 Fraud Scoring (:8081)

**Technology:** Spring Boot + Kafka Consumer + Resilience4j
**Key classes:**

| Class | Responsibility |
|-------|---------------|
| `FraudScoringService` | Orchestrates feature extraction → model → fallback |
| `FeatureEngineeringService` | Extracts 15+ numeric features from payment event |
| `LightGBMStubClient` | Reactive WebClient to LightGBM model server, circuit-breaker |
| `HeuristicScoringService` | Rule-based fallback when model is unavailable |
| `VelocityCheckService` | Sliding window velocity counters (1h/24h) in Redis |
| `CountryRiskMatrix` | FATF black/grey list scoring, 1–10 risk scale |

**Circuit breaker:** Resilience4j wraps the LightGBM HTTP call. When open (>50% failures), `HeuristicScoringService` takes over, ensuring zero downtime for fraud assessment.

---

### 4.3 Validation & Enrichment (:8082)

**Technology:** Spring Boot + Apache Camel 4.6 + JMS
**Camel route:** `payment-validation-enrichment`

Each processor is a Spring `@Component` injected into the Camel route:

| Processor | What it checks |
|-----------|---------------|
| `IBANValidationProcessor` | MOD-97 checksum, length per country, structure |
| `BICValidationProcessor` | ISO 9362 format, 8 or 11 characters |
| `CurrencyValidationProcessor` | ISO 4217 currency code whitelist |
| `EmbargoPreCheckProcessor` | Debtor/creditor country against embargo list |
| `EnrichmentProcessor` | Adds ECB FX rate, BIC details, value date |

Rejected payments go to `PAYMENT.DLQ` after 3 retry attempts (exponential backoff).

---

### 4.4 AML Compliance (:8083)

**Technology:** Spring Boot + Apache Camel + Camunda Zeebe 8 + Commons Text

The service screens both debtor and creditor names against:
- **SDN list** (OFAC Specially Designated Nationals) — 50 sample entries in `sdn_sample.csv`
- **PEP list** (Politically Exposed Persons) — 20 entries in `pep_sample.csv`

**Screening algorithm (FuzzyScreeningEngine):**
```
normalize()     → NFD Unicode, strip diacritics, uppercase, collapse whitespace
canonicalize()  → sort tokens alphabetically (handles "First Last" vs "Last First")
screenName()    → 1. exact string compare
                  2. Jaro-Winkler similarity ≥ threshold
                  3. Soundex phonetic compare on first token
```

Jaro-Winkler is chosen over Levenshtein because it gives higher scores to strings that share a common prefix — important for names where the first few characters are typically the most discriminating.

The Camunda BPMN process (`AMLScreeningProcess.bpmn`) models the manual review workflow for EDD cases, with human task assignment and escalation timers.

---

### 4.5 Routing & Execution (:8084)

**Technology:** Spring Boot + Apache Camel + Chain of Responsibility

**LiquidityReservationService** checks available nostro balance before committing to a rail. If insufficient, throws `InsufficientLiquidityException` and the saga compensation flow is triggered.

**Saga Compensation (SagaCompensationRoute):**
```
from("kafka:PAYMENT_SETTLEMENT_FAILED")
  → release liquidity reservation
  → publish PAYMENT_COMPENSATED to Kafka + AMQ
  → log compensation audit event
```

---

### 4.6 Settlement (:8085)

**Technology:** Spring Boot + Apache Camel + Oracle XE + CockroachDB

**Double-entry invariant:** For every settled payment, `SUM(DEBIT entries) == SUM(CREDIT entries)`. This is enforced in a `SERIALIZABLE` transaction — if violated, an `AccountingImbalanceException` is thrown and the saga compensation flow activates.

**Data split:**
- **Oracle XE** — `LedgerEntry` (individual debit/credit lines, ACID critical)
- **CockroachDB** — `SettlementRecord` (summary record, geo-distributed for high availability)

---

### 4.7 Audit (:8086)

**Technology:** Spring Boot + Cassandra (multi-node)

**Hash chain properties:**
- `GENESIS_HASH = SHA-256("CLEARFLOW-GENESIS-BLOCK-2024-CLEARFLOW")`
- Each block: `currentHash = SHA-256(eventData + previousHash + timestampMs + paymentId)`
- `blockHeight` increments monotonically per paymentId
- 7-year retention (`retentionYears = 7`) per PCI-DSS requirement

Cassandra is chosen for the audit store because its append-only, wide-column model suits the time-series nature of audit events, and its distributed replication provides durability guarantees.

---

### 4.8 Config Server (:8888)

**Technology:** Spring Cloud Config Server

Serves configuration for all 9 other services from `src/main/resources/config/`. Each service bootstraps with `spring.config.import=configserver:http://config-server:8888`.

Per-service config files: `gateway.yml`, `fraud-scoring.yml`, `validation-enrichment.yml`, `aml-compliance.yml`, `routing-execution.yml`, `settlement.yml`, `audit.yml`, `mcp-readonly-gateway.yml`.

---

### 4.9 MCP Read-only Gateway (:8087)

**Technology:** Spring Boot + java.net.http.HttpClient

Provides read-only endpoints for AI/LLM consumption and operator tooling. All endpoints require JWT authentication. Rate limited to 20 requests/minute per subject.

**Read endpoints:**

| Endpoint | Returns |
|----------|---------|
| `GET /mcp/payments/{id}/timeline` | Chronological audit events from Cassandra |
| `GET /mcp/payments/{id}/risk` | Fraud score + explainability from Redis/MongoDB |
| `GET /mcp/payments/{id}/compliance` | AML screening result from Oracle |
| `GET /mcp/metrics/rails` | 24h rail distribution from ClickHouse |
| `GET /mcp/metrics/fraud` | 24h fraud score histogram from ClickHouse |

**AI Chat endpoint:**

`POST /mcp/chat` accepts `{ question, paymentId?, history[] }`:
1. If `paymentId` is provided, all 5 MCPTool implementations gather context
2. A system prompt with ClearFlow domain knowledge is constructed
3. Conversation history is prepended
4. The configured LLM (Ollama or OpenRouter) is called
5. Returns `{ answer, provider }`

---

## 5. Rail Selection Logic

The `RailSelectionEngine` sorts all `PaymentRailRule` beans by priority (lowest = highest precedence) and returns the first match.

| Priority | Rail | Trigger Condition |
|----------|------|------------------|
| 0 | **INTERNAL** | Debtor BIC prefix == Creditor BIC prefix (same institution) |
| 1 | **SEPA_INSTANT** | EUR, both parties in SEPA zone, amount < €100,000 |
| 2 | **SEPA_CT** | EUR, both in SEPA zone (fallback for amounts ≥ €100k) |
| 3 | **FASTER_PAYMENTS** | GBP, both UK, amount ≤ £1,000,000 |
| 4 | **CHAPS** | GBP, amount > £1M OR channel="CHAPS" explicitly requested |
| 5 | **CHIPS** | USD, both US, amount ≥ $1M, one party is a CHIPS member BIC (JPMorgan, Citi, BofA, etc.) |
| 6 | **FEDWIRE** | USD, both US, amount ≥ $1M (non-CHIPS fallback) |
| 7 | **FEDACH** | USD, both US, sub-$1M domestic |
| 8 | **SWIFT_GPI** | Cross-border, amount ≥ $50,000 |
| 10 | **TARGET2** | EUR, debtor in SEPA zone, amount ≥ €1,000,000 |
| 11 | **BACS** | GBP, both UK, amount > £1M (bulk/batch fallback) |
| MAX | **SWIFT_MT103** | Any cross-border payment (catch-all) |

**CHIPS member BIC prefixes recognized:** CHAS (JPMorgan), CITI, BOFA (BofA), WFBI (Wells Fargo), BNYC (BNY Mellon), MLCO (Merrill), DEUT (Deutsche), HSBC, BARW (Barclays), DBNY (Deutsche NY), SOCG (Société Générale), BNPA (BNP Paribas).

---

## 6. Data Stores

| Store | Service(s) | What it holds | Why |
|-------|-----------|---------------|-----|
| **Redis** | Gateway, Fraud | Idempotency keys, payment response cache, fraud score cache, velocity counters | Sub-millisecond reads; TTL-based expiry |
| **Oracle XE** | Settlement, AML | `LedgerEntry` (double-entry lines), AML screening records | ACID + SERIALIZABLE isolation for financial integrity |
| **CockroachDB** | Settlement | `SettlementRecord` summaries | Geo-distributed, Postgres-compatible, survives node failure |
| **Cassandra** | Audit, Settlement | `AuditRecord` hash chain, settlement analytics | Append-only wide column; time-series queries; 7-year retention |
| **MongoDB** | Fraud, Routing | `FraudEvaluatedEvent`, routing decisions | Flexible schema for explainability JSON blobs |
| **ClickHouse** | Settlement, MCP | Aggregated metrics (rail distribution, fraud histograms) | Columnar OLAP — fast aggregation over millions of rows |
| **Elasticsearch** | All (via Logstash) | Structured logs (PCI-DSS masked) | Full-text search, Kibana visualisation |

---

## 7. Messaging Topology

ClearFlow uses **three messaging systems in parallel**, reflecting the mixed broker environments found in large banks:

```
ActiveMQ Artemis (IBM MQ-compatible JMS)
  ├── PAYMENT.INITIATED       → validation-enrichment
  ├── PAYMENT.VALIDATED       → aml-compliance
  ├── PAYMENT.REJECTED        → dead-letter processing
  ├── PAYMENT.DLQ             → dead-letter queue (3 retries + backoff)
  └── PAYMENT.SETTLEMENT.FAILED → saga compensation

Kafka (event streaming)
  ├── payment.initiated       → fraud-scoring (parallel with validation)
  ├── payment.validated       → downstream consumers
  ├── payment.rejected        → alert consumers
  ├── payment.fraud.evaluated → audit, routing
  └── PAYMENT_COMPENSATED     → audit, monitoring

Solace (topic-based publish/subscribe)
  └── clearflow/payments/initiated → external subscribers, real-time dashboards
```

**Why three brokers?**
- **ActiveMQ Artemis** maps directly to IBM MQ JMS APIs — the dominant MQ in UK/EU bank estates (Barclays, HSBC). The Artemis broker implements the same JMS interface, so code is portable.
- **Solace** aligns with Barclays' stated Solace messaging requirement; also used by Deutsche Bank and others for event mesh architectures.
- **Kafka** is the industry standard for high-throughput event streaming and is present in JPMC, Citi, and Mastercard stacks.

---

## 8. Security Model

### Authentication & Authorisation

All services are OAuth2 resource servers. Clients obtain a JWT from Keycloak (realm: `clearflow`), which is validated via RS256 public key at each service boundary.

```
Client → Keycloak (http://localhost:8090/realms/clearflow)
       → JWT (RS256)
       → Service validates issuer + signature + expiry
```

### Transport Security

- All inter-service communication over TLS in production
- Vault (HashiCorp) manages secrets: DB credentials, Kafka SSL keystores, API keys
- Vault dev token: `clearflow-dev-token` (dev mode only — never in production)

### Data Protection

| Field | Protection |
|-------|-----------|
| IBAN | Masked in all logs and API responses (`MaskedIbanSerializer`): shows first 4 + last 4 chars |
| PCI fields | Logstash pipeline strips `pan`, `cvv`, `card_number` before Elasticsearch indexing |
| Audit data | Cassandra encryption at rest (production config) |

### MCP Gateway Access

The MCP Read-only Gateway is strictly read-only (no writes). Security config explicitly denies all methods except `GET /mcp/**` and `POST /mcp/chat`. This ensures LLMs can query data but cannot initiate payments or modify state.

---

## 9. Observability Stack

### Metrics — Prometheus + Grafana

Every service exposes `/actuator/prometheus`. Prometheus scrapes all services. The Grafana dashboard (`infrastructure/grafana-dashboards/payment-dashboard.json`) provides 9 panels:

1. Payment throughput (req/s)
2. Payment status breakdown (pie)
3. Fraud score distribution (histogram)
4. Rail selection distribution (bar)
5. End-to-end latency (p50/p95/p99)
6. AML screening results
7. Settlement success rate
8. Service health status
9. JVM memory + GC metrics

### Tracing — Jaeger + OpenTelemetry

OpenTelemetry Java agent is attached to every service. `X-Correlation-Id` header is propagated through the entire payment pipeline via `CorrelationIdFilter`. Traces are exported to Jaeger (`:16686`) for end-to-end distributed tracing.

### Logging — ELK Stack

Logstash receives JSON logs from all services, applies:
- PCI-DSS field masking (strips `pan`, `cvv`, etc.)
- Per-service index routing (`clearflow-gateway-*`, `clearflow-fraud-*`, etc.)
- Structured field extraction (paymentId, correlationId, rail, fraudScore)

Logs are searchable in Kibana (`:5601`).

### Alerting

10 production-grade Prometheus alert rules in `infrastructure/prometheus/alerts.yml`:

| Alert | Trigger |
|-------|---------|
| `HighFraudRate` | >5% CRITICAL fraud rate in 5 min |
| `AMLBlockSpike` | >10 AML blocks in 5 min |
| `SettlementFailureRate` | >1% settlement failures |
| `PaymentLatencyHigh` | p99 >3s |
| `DLQMessageAccumulation` | DLQ depth >100 |
| `ServiceDown` | Any service health check fails |
| `LiquidityLow` | Nostro balance <10% threshold |
| `AuditChainBreach` | Hash chain verification failure |
| `KafkaConsumerLag` | Consumer lag >10,000 |
| `RedisMemoryPressure` | Redis >80% memory |

### Code Quality — SonarQube

`sonar-project.properties` configured for multi-module analysis (`:9000`). Covers all 10 modules with module-specific source paths.

---

## 10. Resilience Patterns

| Pattern | Implementation | Applied To |
|---------|---------------|-----------|
| Circuit Breaker | Resilience4j | LightGBM model calls in fraud-scoring |
| Dead Letter Queue | ActiveMQ Artemis DLQ | All Camel routes (3 retries + exponential backoff) |
| Idempotency | Redis SHA-256 key | Gateway — prevents duplicate payments |
| Saga / Compensation | Apache Camel route | Settlement failure → liquidity reversal |
| Rate Limiting | Bucket4j (gateway), custom token bucket (MCP) | All external-facing endpoints |
| Config Externalisation | Spring Cloud Config Server | All 9 services |
| Health Checks | Spring Actuator `/health` | All services; probed by Kubernetes liveness/readiness |

---

## 11. Frontend Dashboard

**Location:** `frontend/`
**Stack:** React 18 + Vite 5 + Recharts
**Port:** 3000

```
npm install && npm run dev
```

The Vite dev server proxies `/mcp → :8087` and `/api → :8080`, eliminating CORS issues in development.

### Views

**Dashboard** (`/` `#dashboard`)
- 6 stat cards: payments/24h, settled, fraud flagged, AML blocked, avg latency, active rails
- Rail distribution bar chart (colour-coded by rail type)
- Fraud score histogram (4 bands)
- Service health grid (all 8 services with status indicators)

**Payment Search** (`#search`)
- Enter any payment ID
- Fetches timeline, risk, and compliance in parallel from MCP gateway
- Displays JSON responses in colour-coded code cards

**AI Chat** (`#chat`)
- Suggested questions covering fraud, rails, AML, and saga flows
- Optional payment ID context — attaches tool data to the LLM system prompt
- Shows which LLM provider answered (e.g. `ollama/llama3.2`)
- Typing indicator during LLM inference

**Auth:** JWT token stored in `localStorage`. Prompted on first load via modal. All API calls include `Authorization: Bearer <token>`.

---

## 12. AI / MCP Layer

### Architecture

```
Frontend Chat
    │
    ▼
POST /mcp/chat  (MCPController)
    │
    ├── gather context from MCPTool beans (if paymentId provided)
    │     ├── PaymentTimelineTool
    │     ├── FraudScoreTool
    │     ├── ComplianceTool
    │     └── MetricsTool
    │
    ├── build messages list:
    │     [system: ClearFlow domain prompt + payment context]
    │     [history: prior conversation turns]
    │     [user: current question]
    │
    └── LLMClient.chat(messages)
          ├── OllamaLLMClient    → POST http://localhost:11434/api/chat
          └── OpenRouterLLMClient → POST https://openrouter.ai/api/v1/chat/completions
```

### LLM Provider Configuration

Set in `mcp-readonly-gateway/src/main/resources/application.yml`:

```yaml
clearflow:
  llm:
    provider: ollama          # switch to: openrouter
    ollama:
      base-url: http://localhost:11434
      model: llama3.2
    openrouter:
      base-url: https://openrouter.ai/api/v1
      api-key: ${OPENROUTER_API_KEY:}
      model: meta-llama/llama-3.2-3b-instruct:free
```

Or via environment:
```bash
CLEARFLOW_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
```

**Ollama** (local) is the default — zero cost, works offline, models run on local GPU/CPU.
**OpenRouter** (cloud) provides access to 100+ models (GPT-4, Claude, Llama, Mistral, etc.) via a single API key.

### MCP Design Principles

- **Read-only:** MCP tools only read data, never write. Enforced at security layer.
- **Rate-limited:** 20 requests/minute per authenticated subject.
- **Audited:** Every MCP call is logged via `AccessLogService`.
- **Contextual:** Tools provide real payment context to the LLM, not hallucinated data.

---

## 13. Infrastructure & Deployment

### Docker Compose (Local)

`infrastructure/docker-compose.yml` starts the full stack:

```bash
cd infrastructure
docker compose up -d
```

Services started: Oracle XE, CockroachDB, Cassandra, MongoDB, Redis, Kafka + Zookeeper, ActiveMQ Artemis, Solace, Keycloak, Vault, Elasticsearch, Logstash, Kibana, Jaeger, Prometheus, Grafana, SonarQube.

### Kubernetes / Helm

`infrastructure/helm/clearflow/` contains the Helm chart:

```bash
helm install clearflow ./infrastructure/helm/clearflow \
  --set gateway.image.tag=1.0.0 \
  --set global.environment=production
```

Templates include: `deployment.yaml`, `service.yaml`, `configmap.yaml`, `secret.yaml`, `hpa.yaml` (HorizontalPodAutoscaler), `servicemonitor.yaml` (Prometheus Operator), `serviceaccount.yaml`.

### CI/CD

**GitHub Actions** (`.github/workflows/ci.yml`): build → test → SonarQube → Docker build
**Jenkins** (`Jenkinsfile`): parallel stage pipeline for enterprise CI environments

### Synthetic Load Generator

```bash
cd synthetic-load-generator
pip install -r requirements.txt
python generate_payments.py --count 10000 --concurrency 50
```

Generates realistic ISO 20022 payment payloads across all 20 demo scenarios.

### Demo Data

Set `clearflow.demo.enabled=true` (or `CLEARFLOW_DEMO_ENABLED=true`) to load 20 realistic scenarios on gateway startup:

| Scenario | Description |
|----------|-------------|
| SEPA_INSTANT | EUR domestic, €500 |
| SEPA_CT | EUR cross-SEPA, €250k |
| FASTER_PAYMENTS | GBP domestic, £850 |
| CHAPS | GBP high-value, £2.5M |
| CHIPS | USD $5M between CHIPS member banks |
| FEDWIRE | USD $3M high-value |
| FEDACH | USD domestic ACH |
| SWIFT_GPI | Cross-border, $120k |
| SWIFT_MT103 | International wire |
| INTERNAL | Same institution transfer |
| FRAUD_CRITICAL | US→Iran (FATF black list, score 95+) |
| VELOCITY_BREACH | 3× GBP payments in 60s (velocity rule) |
| FATF_GREY_EDD | Bolivia sender (FATF grey list, EDD triggered) |
| HIGH_RISK | Russia-sourced payment |
| DUPLICATE | Same instructionId as a prior payment (idempotency test) |
| + 5 more | SEPA_LARGE, SWIFT_GPI_LARGE, LEGIT_SMALL, velocity test variants |

---

## 14. Configuration Management

Spring Cloud Config Server centralises all configuration. Each service's `application.yml` contains only local defaults and the config server URL:

```yaml
spring:
  config:
    import: configserver:http://config-server:8888
```

The config server serves per-service YAML files from its classpath. In production, these would be stored in a Git repository (Spring Cloud Config Git backend) for full audit trail of configuration changes.

**Secret management:** Vault (HashiCorp) is integrated for runtime secrets:
- Database passwords
- Kafka SSL keystores and truststores
- OAuth2 client secrets
- API keys (OpenRouter, Solace)

---

## 15. Test Coverage

| Module | Test Class | Tests | What it covers |
|--------|-----------|-------|---------------|
| gateway | `PaymentArchTest` | 6 | ArchUnit rules: no circular deps, layer isolation |
| gateway | `PaymentControllerTest` | 2 | REST endpoint, idempotency response |
| fraud-scoring | `FraudScoringServiceTest` | 7 | Low/medium/high/critical bands, FATF countries, velocity |
| aml-compliance | `FuzzyMatchTest` | 7 | Exact match, Jaro-Winkler fuzzy, Soundex phonetic, no-match |
| routing-execution | `RailSelectionTest` | 12 | All 12 rails selected under correct conditions |
| settlement | `DoubleEntryAccountingTest` | 3 | Balanced entries, imbalance exception, idempotent re-settle |
| audit | `HashChainIntegrityTest` | 4 | Chain creation, verification, tamper detection, genesis block |

Run all 41 tests:
```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/admin-/.maven/maven-3.9.12/bin/mvn test --no-transfer-progress
```

---

## 16. Design Rationale

### Why event-driven?

Bank payment systems process millions of payments per day across services that may have different SLAs and failure modes. Synchronous chaining (REST calls) would mean one slow service blocks the entire pipeline. An event-driven architecture decouples services — each processes at its own pace, retries independently, and failures are isolated.

### Why three messaging brokers?

Each broker serves a different integration pattern present in real bank estates:
- **ActiveMQ Artemis** (IBM MQ API) — the dominant enterprise MQ in UK/EU banks. Banks have 20+ years of IBM MQ integration; Artemis is a drop-in replacement.
- **Solace** — high-throughput pub/sub used for real-time feeds and event mesh architectures.
- **Kafka** — the standard for fraud analytics and ML feature pipelines that need replay and long retention.

### Why double-entry bookkeeping?

Single-entry accounting is susceptible to bugs that create money or lose money silently. Double-entry enforces that every payment creates exactly one DEBIT and one CREDIT of equal amount. The `SERIALIZABLE` isolation level prevents concurrent settlements from breaking this invariant.

### Why SHA-256 hash chains for audit?

A traditional database audit table can be modified by a DBA. A hash chain makes tampering detectable: modifying any historical record changes its hash, which breaks the chain for every subsequent record. This is the same principle used in blockchain and is a requirement in PCI-DSS and FCA/PRA audit frameworks.

### Why fuzzy name matching for AML?

Sanctions lists contain transliterated names from Arabic, Persian, Russian, and other scripts. The same person may appear as "Mohammed", "Muhammad", "Mohamed", or "Muhammed". Exact string matching would miss all variants. Jaro-Winkler + Soundex provides a practical balance between recall (catching real matches) and precision (avoiding too many false positives that would halt legitimate payments).

### Why Apache Camel?

Camel provides a declarative, testable integration DSL. The validation and AML pipeline steps are individual `@Component` processors that can be unit-tested in isolation. The route definition reads like a specification. Barclays' engineering specifications explicitly list Apache Camel as their integration framework of choice.
