# ClearFlow — Architecture & File Structure

> ISO 20022 Payment Orchestration Platform
> Java 21 · Spring Boot 3.3.2 · Maven multi-module · 41 tests passing

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture Diagram](#system-architecture-diagram)
3. [Payment Lifecycle](#payment-lifecycle)
4. [Module Reference](#module-reference)
5. [File Structure](#file-structure)
6. [Messaging Topology](#messaging-topology)
7. [Data Stores](#data-stores)
8. [Payment Rail Routing](#payment-rail-routing)
9. [AML & Fraud](#aml--fraud)
10. [MCP Gateway & AI Layer](#mcp-gateway--ai-layer)
11. [Frontend](#frontend)
12. [Infrastructure](#infrastructure)
13. [Test Suite](#test-suite)

---

## Overview

ClearFlow is a production-grade ISO 20022 payment orchestration hub. A single `pacs.008` credit transfer request enters via the REST gateway and flows through a chain of microservices — validation, fraud scoring, AML compliance, rail routing, settlement, and audit — using three messaging brokers (Kafka, ActiveMQ Artemis, Solace) as the backbone.

Key design goals:
- **Event-driven**: every pipeline stage communicates via durable messages, not synchronous HTTP
- **Multi-broker**: Kafka for event streaming + status tracking, ActiveMQ for guaranteed delivery, Solace for topic-based fan-out
- **Immutable audit**: SHA-256 hash chain in Cassandra — every state transition is hash-linked
- **Live status tracking**: gateway listens to all 9 Kafka lifecycle topics and writes current status to Redis — `GET /api/v1/payments/{id}/status` always reflects real pipeline state
- **AI-queryable**: MCP read-only gateway exposes the platform to LLM-powered tooling via Ollama / OpenRouter

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                │
│   React Frontend :3000          External API Consumers (JWT)        │
└────────────────┬───────────────────────────┬────────────────────────┘
                 │ HTTP                       │ HTTP
                 ▼                            ▼
┌────────────────────────┐      ┌─────────────────────────────────┐
│   GATEWAY  :8080        │      │    MCP READONLY GW  :8087       │
│  POST /api/v1/payments  │      │  GET  /mcp/payments/{id}/*      │
│  GET  /{id}/status      │◄────►│  POST /mcp/chat                 │
│  JWT auth (Keycloak)    │      │  Ollama qwen3.5:0.8b            │
│  Rate limiting (Redis)  │      │  → fallback: OpenRouter         │
│  Idempotency (Redis)    │      └─────────────────────────────────┘
└────────┬───────────────┘
         │  Publishes PaymentInitiatedEvent
         ├─► Kafka   (clearflow.payment.initiated)
         ├─► ActiveMQ (CLEARFLOW.PAYMENT.INITIATED)
         └─► Solace  (clearflow/payments/initiated/{CCY}/{COUNTRY})
                 │
                 ▼
┌─────────────────────────────┐
│   VALIDATION-ENRICHMENT     │  :8082  Apache Camel
│   IBAN / BIC validation     │
│   Embargo country pre-check │
│   Currency validation       │
│   → VALIDATED / REJECTED    │
└────────┬────────────────────┘
         │
         ├──────────────────────────────────┐
         ▼                                  ▼
┌───────────────────────┐     ┌─────────────────────────────┐
│  FRAUD SCORING :8081  │     │  AML COMPLIANCE  :8083      │
│  LightGBM stub        │     │  FuzzyScreeningEngine       │
│  Heuristic rules      │     │  Soundex phonetic match     │
│  Velocity checks      │     │  SDN list  150 entries      │
│  Country risk matrix  │     │  PEP list   50 entries      │
│  → FRAUD_EVALUATED    │     │  FATF grey-list EDD flag    │
│  → PAYMENT_BLOCKED    │     │  → AML_SANCTIONS_CLEAR/HIT  │
└───────────────────────┘     └─────────────┬───────────────┘
                                             │
                                             ▼
                              ┌──────────────────────────────┐
                              │  ROUTING EXECUTION  :8084    │
                              │  12 rail rules (priority)    │
                              │  Liquidity reservation       │
                              │  Saga compensation route     │
                              │  → PAYMENT_ROUTED / FAILED   │
                              └──────────────┬───────────────┘
                                             │
                                             ▼
                              ┌──────────────────────────────┐
                              │  SETTLEMENT  :8085           │
                              │  Double-entry ledger         │
                              │  Cassandra + ClickHouse      │
                              │  → PAYMENT_SETTLED           │
                              └──────────────┬───────────────┘
                                             │
         ┌───────────────────────────────────┘
         │  All 9 Kafka lifecycle topics
         ▼
┌────────────────────────┐     ┌─────────────────────────────┐
│  AUDIT  :8086          │     │  GATEWAY status tracker     │
│  SHA-256 hash chain    │     │  PaymentStatusKafkaConsumer │
│  Cassandra persistence │     │  → Redis payment:status:{id}│
│  GET /api/v1/audit/{id}│     │     TTL 2h                  │
└────────────────────────┘     └─────────────────────────────┘
```

---

## Payment Lifecycle

```
Client  POST /api/v1/payments
  │
  ├─ Idempotency check (Redis SHA-256 sig)    → 409 CONFLICT if seen before
  ├─ Rate limit check (Redis token bucket)    → 429 TOO_MANY_REQUESTS
  ├─ Build PaymentInitiatedEvent
  ├─ Publish → Kafka + ActiveMQ + Solace
  ├─ Seed status: INITIATED in Redis
  └─ Return 202 ACCEPTED { paymentId, links.status }

  status: INITIATED
       ↓ (ActiveMQ)
ValidationEnrichment
  ├─ IBAN format, BIC format, embargo countries, currency
  ├─ VALIDATED → ActiveMQ + Kafka       status: VALIDATED
  └─ REJECTED  → ActiveMQ + Kafka       status: REJECTED

  status: VALIDATED
       ↓ (Kafka + ActiveMQ — parallel)
FraudScoring                          AMLCompliance
  ├─ Feature engineering                ├─ Fuzzy SDN match (Jaro-Winkler ≥ 0.85)
  ├─ LightGBM score 0–100              ├─ Soundex phonetic variants
  ├─ Heuristic additive rules           ├─ 150 SDN entries, 50 PEP entries
  ├─ Velocity window (Redis)            ├─ FATF grey-list EDD
  ├─ Country risk matrix                ├─ AML_SANCTIONS_CLEAR → Kafka  status: AML_SCREENED
  ├─ FRAUD_EVALUATED → Kafka            └─ AML_SANCTIONS_HIT  → Kafka  status: BLOCKED
  └─ PAYMENT_BLOCKED → Kafka  status: BLOCKED

  status: AML_SCREENED
       ↓ (ActiveMQ)
RoutingExecution
  ├─ 12 priority-ordered rail rules → first match wins
  ├─ Liquidity reservation check
  ├─ PAYMENT_ROUTED → ActiveMQ + Kafka  status: ROUTED
  └─ PAYMENT_FAILED → Kafka             status: FAILED

  status: ROUTED
       ↓ (ActiveMQ)
Settlement
  ├─ Double-entry ledger (DEBIT nostro / CREDIT beneficiary)
  ├─ Write SettlementRecord → Cassandra
  ├─ Write analytics row   → ClickHouse
  └─ PAYMENT_SETTLED → ActiveMQ + Kafka  status: SETTLED

All events → Audit (SHA-256 hash chain, Cassandra)
```

---

## Module Reference

| Module | Port | Role |
|---|---|---|
| `common` | — | Shared domain events, Kafka topics, MQ queues, Solace topics, resilience config, security utilities |
| `config-server` | 8888 | Spring Cloud Config Server — serves per-service YAML from classpath |
| `gateway` | 8080 | ISO 20022 ingestion, JWT auth, idempotency, rate limiting, live status tracking |
| `fraud-scoring` | 8081 | Risk scoring: LightGBM stub + heuristics + velocity + country risk matrix |
| `validation-enrichment` | 8082 | IBAN/BIC validation, embargo pre-check, currency check, enrichment |
| `aml-compliance` | 8083 | SDN/PEP fuzzy screening, Soundex, FATF grey-list, Oracle persistence |
| `routing-execution` | 8084 | Rail selection engine (12 rules), liquidity reservation, saga compensation |
| `settlement` | 8085 | Double-entry ledger, Cassandra settlement records, ClickHouse analytics |
| `audit` | 8086 | SHA-256 hash chain over all lifecycle events, Cassandra persistence |
| `mcp-readonly-gateway` | 8087 | AI read-only interface: LLM chat (Ollama/OpenRouter), payment tools, access log |

---

## File Structure

```
clearflow/
├── pom.xml                                   # Parent POM — Java 21, Spring Boot 3.3.2
├── Jenkinsfile
├── sonar-project.properties
│
├── common/
│   └── src/main/java/com/clearflow/common/
│       ├── domain/
│       │   ├── PaymentInitiatedEvent.java    # Core event record flowing through entire pipeline
│       │   ├── EnrichedPaymentEvent.java
│       │   └── FraudEvaluatedEvent.java
│       ├── messaging/
│       │   ├── KafkaTopics.java              # All Kafka topic name constants
│       │   ├── MQQueues.java                 # All ActiveMQ queue name constants
│       │   └── SolaceTopics.java             # Solace topic prefix
│       ├── exception/
│       │   ├── PaymentException.java
│       │   ├── DuplicatePaymentException.java
│       │   └── ProblemDetailBuilder.java
│       ├── resilience/CircuitBreakerNames.java
│       ├── observability/MetricsConstants.java
│       └── security/
│           ├── MaskedIbanSerializer.java     # Masks IBANs in logs/events
│           └── CorrelationIdFilter.java
│
├── config-server/
│   └── src/main/resources/
│       ├── application.yml
│       └── config/                           # Per-service config files
│           ├── application.yml               # Shared defaults
│           ├── gateway.yml
│           ├── fraud-scoring.yml
│           ├── validation-enrichment.yml
│           ├── aml-compliance.yml
│           ├── routing-execution.yml
│           ├── settlement.yml
│           ├── audit.yml
│           └── mcp-readonly-gateway.yml
│
├── gateway/
│   └── src/main/java/com/clearflow/gateway/
│       ├── GatewayApplication.java
│       ├── controller/
│       │   └── PaymentController.java        # POST /api/v1/payments
│       │                                     # GET  /api/v1/payments/{id}/status
│       ├── domain/
│       │   ├── PaymentStatus.java            # ACCEPTED | INITIATED | VALIDATED |
│       │   │                                 # AML_SCREENED | ROUTED | LIQUIDITY_RESERVED |
│       │   │                                 # SETTLED | REJECTED | BLOCKED | FAILED | DUPLICATE
│       │   ├── PaymentStatusResponse.java    # Record: paymentId, status, stage, message, updatedAt
│       │   │                                 # + 4-arg compat constructor (stage defaults "gateway")
│       │   ├── PaymentRequest.java
│       │   ├── PaymentResponse.java
│       │   ├── PaymentChannel.java
│       │   ├── Iban.java / IbanValidator.java
│       │   └── IdempotencyResult.java
│       ├── config/
│       │   ├── SecurityConfig.java           # JWT resource server (Keycloak)
│       │   ├── RedisConfig.java              # ReactiveRedisTemplate<String,String> bean
│       │   └── GatewayKafkaConsumerConfig.java  # Non-transactional consumer factory
│       │                                        # group-id: gateway-status-tracker
│       ├── messaging/
│       │   ├── KafkaEventPublisher.java      # Transactional producer → payment.initiated
│       │   ├── ActiveMQPublisher.java
│       │   └── SolacePublisher.java
│       ├── service/
│       │   ├── IdempotencyService.java       # SHA-256 sig → Redis, returns cached response
│       │   └── RateLimitingFilter.java       # Token bucket per clientId
│       ├── status/
│       │   ├── PaymentStatusService.java     # updateStatus() / getStatus()
│       │   │                                 # Redis key: payment:status:{id}, TTL 2h
│       │   └── PaymentStatusKafkaConsumer.java  # 9 @KafkaListeners, one per lifecycle topic
│       │                                        # → calls statusService.updateStatus().subscribe()
│       ├── exception/GlobalExceptionHandler.java
│       └── demo/
│           └── DemoDataLoader.java           # 100 scenarios on startup (clearflow.demo.enabled=true)
│               ├── Group A (30) — Routine retail/corporate
│               │   A01–A08: SEPA_INSTANT  (€500–€22K, 8 SEPA corridors)
│               │   A09–A14: FASTER_PAYMENTS (£850–£280K, 6 domestic GBP)
│               │   A15–A22: FEDACH ($12.5K–$980K, 8 domestic USD)
│               │   A23–A30: SEPA_CT (€100K–€420K, 8 large corporates)
│               ├── Group B (15) — High-value treasury
│               │   B01–B03: CHAPS  (£2M / £5.5M / £12M)
│               │   B04–B06: CHIPS  ($10M / $25M / $50M)
│               │   B07–B09: FEDWIRE non-CHIPS ($1.5M / $5M / $15M)
│               │   B10–B12: SEPA_CT large (€1M / €2.5M / €5M)
│               │   B13–B15: SWIFT_GPI ($800K US→CH, $2M US→SG, €3.5M DE→HK)
│               ├── Group C (15) — Cross-border correspondent
│               │   AU→US, CA→GB, HK→DE, JP→FR, ZA→NL, AE→GB, BR→US
│               ├── Group D (15) — Fraud/suspicious
│               │   Velocity breach, high-risk DE/US/FR→RU, off-hours 03:00 UTC,
│               │   OFAC embargoed (IR/KP/CU), structuring just below €10K
│               ├── Group E (10) — AML/compliance edge cases
│               │   Structuring completion, PEP-linked accounts, FATF grey-list,
│               │   SDN phonetic hit attempts, round-trip legs 1+2
│               └── Group F (15) — Operational edge cases
│                   Round-trip leg 3, duplicate instructionId, embargoed debtor (CU/SY),
│                   liquidity exceeded, FX conversion, BACS→CHAPS routing precedence
│
├── fraud-scoring/
│   └── src/main/java/com/clearflow/fraud/
│       ├── messaging/FraudKafkaConsumer.java     # Consumes clearflow.payment.validated
│       ├── service/
│       │   ├── FraudScoringService.java          # Orchestrates scoring pipeline
│       │   ├── FeatureEngineeringService.java    # Builds feature vector
│       │   ├── LightGBMStubClient.java           # Deterministic model stub (0–100)
│       │   ├── HeuristicScoringService.java      # Additive rule-based overlay
│       │   ├── VelocityCheckService.java         # Redis sliding window per IBAN
│       │   └── CountryRiskMatrix.java            # Per-country base risk (RU=9, IR=10…)
│       ├── domain/FraudRequest.java / FraudResponse.java / RiskBand.java
│       ├── controller/FraudScoringController.java
│       └── config/FraudKafkaConfig.java
│
├── validation-enrichment/
│   └── src/main/java/com/clearflow/validation/
│       ├── camel/ValidationEnrichmentCamelRoute.java  # Main Camel pipeline
│       ├── processor/
│       │   ├── BICValidationProcessor.java
│       │   ├── CurrencyValidationProcessor.java
│       │   └── EmbargoPreCheckProcessor.java          # Blocks CU/IR/KP/SY/BY/MM/SD
│       ├── domain/PaymentEnrichment.java / ValidationRecord.java
│       └── config/EmbargoDataLoader.java
│
├── aml-compliance/
│   ├── src/main/java/com/clearflow/compliance/
│   │   ├── camel/AMLCamelRoute.java               # PAYMENT_VALIDATED → screened/hit
│   │   ├── processor/AMLScreeningProcessor.java
│   │   ├── service/
│   │   │   ├── FuzzyScreeningEngine.java           # Jaro-Winkler + Soundex + alias expansion
│   │   │   └── SDNLoader.java                      # Loads CSVs at startup
│   │   ├── domain/SDNEntry.java / ScreeningRecord.java / ScreeningResult.java
│   │   └── repository/ScreeningRecordRepository.java
│   └── src/main/resources/data/
│       ├── sdn_sample.csv   (150 entries, 1 header row = 151 lines)
│       │   UIDs 1001–1025  Terrorist orgs (Al-Qaeda, HAMAS, ISIS, Hezbollah, LeT…)
│       │   UIDs 1026–1055  Iranian entities (Bank Melli, NIOC, IRGC, Mahan Air…)
│       │   UIDs 1056–1080  Russian/Belarus (VTB, Gazprombank, Wagner, Sberbank…)
│       │   UIDs 1081–1095  DPRK (Lazarus Group, RGB, Korea Kwangson…)
│       │   UIDs 1096–1115  Narcotics traffickers (Sinaloa, CJNG, MS-13…)
│       │   UIDs 1116–1150  Fuzzy test variants (LAZURUS GROUP, MULLER HANS…)
│       └── pep_sample.csv   (50 entries, 1 header row = 51 lines)
│           UIDs 2001–2010  Heads of State   (RU/CN/NG/VE/IR/KP/BY/ZW/SD/MM)
│           UIDs 2011–2020  Finance Ministers
│           UIDs 2021–2030  Central Bank Governors
│           UIDs 2031–2037  Defence Ministers / Security Chiefs
│           UIDs 2038–2042  Parliament Speakers
│           UIDs 2043–2050  Regional Governors (incl. DE/FR/IT low-risk test entries)
│
├── routing-execution/
│   └── src/main/java/com/clearflow/routing/
│       ├── camel/
│       │   ├── RoutingCamelRoute.java              # AML_CLEAR → routed/failed
│       │   └── SagaCompensationRoute.java          # Handles PAYMENT_SETTLEMENT_FAILED
│       ├── service/
│       │   ├── RailSelectionEngine.java            # Sorts by priority, first match wins
│       │   ├── LiquidityReservationService.java
│       │   ├── PaymentRailRule.java                # Interface: matches() + select() + priority()
│       │   ├── InsufficientLiquidityException.java
│       │   └── rules/RailRules.java                # 12 @Bean rules — see Rail Routing table
│       ├── domain/PaymentRail.java / RoutingContext.java
│       └── processor/RailSelectionProcessor.java / LiquidityReservationProcessor.java
│
├── settlement/
│   └── src/main/java/com/clearflow/settlement/
│       ├── camel/SettlementCamelRoute.java
│       ├── service/SettlementService.java          # DEBIT nostro / CREDIT beneficiary
│       ├── domain/LedgerEntry.java / EntryType.java / SettlementRecord.java
│       ├── repository/LedgerRepository.java (Cassandra) / SettlementRepository.java (Cassandra)
│       ├── processor/SettlementProcessor.java
│       └── controller/SettlementController.java
│
├── audit/
│   └── src/main/java/com/clearflow/audit/
│       ├── messaging/AuditEventConsumer.java       # Listens to all 9 lifecycle Kafka topics
│       ├── service/HashChainService.java           # SHA-256(prevHash + paymentId + event + ts)
│       ├── domain/AuditRecord.java / AuditRecordKey.java / ChainVerificationResult.java
│       ├── repository/AuditRepository.java         # Cassandra
│       └── controller/AuditController.java         # GET /api/v1/audit/{paymentId}
│
├── mcp-readonly-gateway/
│   └── src/main/java/com/clearflow/mcp/
│       ├── McpReadonlyGatewayApplication.java
│       ├── config/MCPSecurityConfig.java            # permit-all (no Keycloak needed locally)
│       ├── controller/
│       │   ├── MCPController.java                  # All /mcp/** endpoints
│       │   └── ChatRequest.java
│       ├── llm/
│       │   ├── LLMClient.java                      # Interface: chat() + providerName()
│       │   ├── LLMMessage.java                     # Record: role, content
│       │   ├── LLMConfig.java                      # Bean factory: ollama|openrouter|fallback
│       │   ├── OllamaLLMClient.java                # POST /api/chat (stream:false)
│       │   ├── OpenRouterLLMClient.java             # POST /chat/completions (OpenAI-compat)
│       │   └── FallbackLLMClient.java              # Tries Ollama → falls back to OpenRouter
│       ├── service/
│       │   ├── McpRateLimiter.java                 # In-memory per-subject rate limit
│       │   └── AccessLogService.java               # Publishes to clearflow.mcp.access.log
│       └── tool/
│           ├── MCPTool.java                        # Interface: name() + execute(Map)
│           ├── PaymentTimelineTool.java
│           ├── FraudScoreTool.java
│           ├── ComplianceTool.java
│           └── MetricsTool.java
│
├── frontend/                                        # React 18 + Vite + Recharts
│   ├── package.json
│   ├── vite.config.js                              # /mcp proxy → localhost:8087
│   └── src/
│       ├── App.jsx                                 # Hash-based router: dashboard|search|chat
│       ├── api/mcpApi.js                           # fetch wrapper for all /mcp/* calls
│       └── components/
│           ├── NavBar.jsx
│           ├── Dashboard.jsx                       # Stat cards, bar charts, service health
│           ├── PaymentSearch.jsx                   # Payment ID → timeline+risk+compliance
│           └── Chat.jsx                            # LLM chat with payment context + chips
│
├── infrastructure/
│   ├── docker-compose.yml                          # Full stack (see Infrastructure section)
│   ├── helm/clearflow/                             # Kubernetes Helm chart
│   └── prometheus/prometheus.yml / alerts.yml
│
└── synthetic-load-generator/                        # Load testing tooling
```

---

## Messaging Topology

### Kafka Topics

| Topic | Producer | Consumer(s) |
|---|---|---|
| `clearflow.payment.initiated` | Gateway | Fraud Scoring, Audit, Gateway status tracker |
| `clearflow.payment.validated` | Validation | AML Compliance, Audit, Gateway status tracker |
| `clearflow.payment.rejected` | Validation | Audit, Gateway status tracker |
| `clearflow.fraud.evaluated` | Fraud Scoring | Audit |
| `clearflow.payment.blocked` | Fraud Scoring | Audit, Gateway status tracker |
| `clearflow.aml.sanctions.clear` | AML Compliance | Routing, Audit, Gateway status tracker |
| `clearflow.aml.sanctions.hit` | AML Compliance | Audit, Gateway status tracker |
| `clearflow.payment.routed` | Routing | Settlement, Audit, Gateway status tracker |
| `clearflow.payment.failed` | Routing | Audit, Gateway status tracker |
| `clearflow.payment.settled` | Settlement | Audit, Gateway status tracker |
| `clearflow.analytics.settlement` | Settlement | ClickHouse |
| `clearflow.mcp.access.log` | MCP Gateway | Audit/analytics |
| `clearflow.payment.dlq` | Various | Ops |

### ActiveMQ Queues

```
CLEARFLOW.PAYMENT.INITIATED
  → CLEARFLOW.PAYMENT.VALIDATED
    → CLEARFLOW.PAYMENT.ROUTED
      → CLEARFLOW.PAYMENT.SETTLED
```

### Solace Topics

Fan-out: `clearflow/payments/initiated/{CURRENCY}/{DEBTOR_COUNTRY}`
Enables currency/corridor-specific subscribers without re-routing.

---

## Data Stores

| Store | Used By | Purpose |
|---|---|---|
| **Redis** | Gateway | Idempotency cache, rate-limit token bucket, payment status (`payment:status:{id}` TTL 2h) |
| **Oracle XE** | Validation, AML, Routing | Validation records, screening records, routing decisions |
| **MongoDB** | Validation, Gateway | Payment enrichment documents |
| **Cassandra** | Settlement, Audit | Settlement records, immutable SHA-256 hash-chain audit log |
| **ClickHouse** | Settlement | Analytics — rail distribution, settlement latency histograms |
| **CockroachDB** | (reserved) | Future distributed ledger |

---

## Payment Rail Routing

Rules in `RailRules.java` evaluated by priority — **first match wins**.

| Priority | Rail | Condition |
|---|---|---|
| 0 | `INTERNAL` | Same first-4-char BIC prefix on both sides |
| 1 | `SEPA_INSTANT` | EUR, both SEPA countries, amount < €100K |
| 2 | `SEPA_CREDIT_TRANSFER` | EUR, both SEPA countries, any amount |
| 3 | `FASTER_PAYMENTS` | GBP, GB→GB, ≤ £1M |
| 4 | `CHAPS` | GBP, > £1M **or** channel=CHAPS (this overrides BACS at p11) |
| 5 | `CHIPS` | USD, US→US, ≥ $1M, debtor/creditor BIC in CHIPS member set |
| 6 | `FEDWIRE` | USD, US→US, ≥ $1M (non-CHIPS fallback) |
| 7 | `FEDACH` | USD, US→US, any amount (domestic sub-$1M) |
| 8 | `SWIFT_GPI` | Cross-border, ≥ $50K |
| 10 | `TARGET2` | EUR, SEPA debtor, ≥ €1M |
| 11 | `BACS` | GBP, GB→GB, > £1M (lower priority than CHAPS — demonstrates precedence) |
| MAX | `SWIFT_MT103` | Any cross-border (catch-all) |

**CHIPS member BIC prefixes**: CHAS, CITI, BOFA, WFBI, BNYC, MLCO, DEUT, HSBC, BARW, DBNY, SOCG, BNPA

---

## AML & Fraud

### Fraud Scoring Pipeline

```
PaymentInitiatedEvent
  → FeatureEngineeringService     amount, currency, country, time-of-day, velocity window
  → LightGBMStubClient            deterministic score 0–100 keyed on payment attributes
  → HeuristicScoringService       additive rules: +20 embargoed country, +15 off-hours, etc.
  → VelocityCheckService          Redis sliding window — same IBAN, 10-min window
  → CountryRiskMatrix             per-country base risk: IR=10, KP=10, RU=9, NG=7 …
  → RiskBand: LOW (0–30) | MEDIUM (30–60) | HIGH (60–80) | CRITICAL (80–100)
```

### AML Screening

- **Fuzzy name match**: Jaro-Winkler similarity ≥ 0.85 on name tokens
- **Soundex phonetic**: catches `LAZURUS GROUP` → `LAZARUS GROUP`
- **Alias expansion**: parses `AKA:` fields in SDN CSV into additional match candidates
- **PEP screening**: exact + fuzzy match on 50 synthetic PEP entries
- **FATF grey-list**: country codes → Enhanced Due Diligence flag on payment

---

## MCP Gateway & AI Layer

### LLM Configuration

```yaml
# mcp-readonly-gateway/src/main/resources/application.yml
clearflow.llm:
  provider: fallback                  # ollama | openrouter | fallback
  ollama:
    base-url: http://localhost:11434
    model: qwen3.5:0.8b               # fast local model
  openrouter:
    api-key: ${OPENROUTER_API_KEY:}
    model: meta-llama/llama-3.1-8b-instruct:free
```

`FallbackLLMClient`: tries Ollama first; if Ollama returns an error string or throws, automatically retries with OpenRouter.

### MCP Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/mcp/payments/{id}/timeline` | Full event timeline for a payment |
| GET | `/mcp/payments/{id}/risk` | Fraud score + risk band |
| GET | `/mcp/payments/{id}/compliance` | AML screening result |
| GET | `/mcp/metrics/rails` | Rail distribution (24h) |
| GET | `/mcp/metrics/fraud` | Fraud histogram (24h) |
| POST | `/mcp/chat` | LLM chat `{ question, paymentId?, history[] }` |

### Chat Flow

```
POST /mcp/chat { question, paymentId?, history[] }
  ├─ Rate limit check (per-subject in-memory)
  ├─ If paymentId → run PaymentTimelineTool + FraudScoreTool + ComplianceTool
  │   → append results as system context
  ├─ Build message list: [system + context, ...history, user question]
  ├─ LLMClient.chat(messages)
  │   └─ FallbackLLMClient: Ollama → OpenRouter
  └─ Return { answer: "...", provider: "ollama/qwen3.5:0.8b (fallback: openrouter)" }
```

---

## Frontend

React 18 SPA, Vite dev server on `:3000`. All API calls proxy to `:8087/mcp`.

| Page | Hash route | What it shows |
|---|---|---|
| Dashboard | `#dashboard` | 6 stat cards · Rail distribution bar chart · Fraud score distribution · 8-service health grid |
| Payment Search | `#search` | Payment ID input → parallel fetch timeline + risk + compliance → rendered as JSON cards |
| AI Chat | `#chat` | LLM chat interface · Optional payment ID context · 4 suggested prompts · typing indicator · provider label |

**Auth**: token stored in `localStorage` as `clearflow_token`, sent as `Authorization: Bearer …`. MCP gateway runs permit-all locally (no Keycloak required).

**Start frontend**:
```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## Infrastructure

### Docker Compose — full service inventory

| Service | Image | Port(s) | Network |
|---|---|---|---|
| `activemq-artemis` | apache/activemq-artemis:2.31.2 | 61616, 8161 | internal |
| `solace` | solace/solace-pubsub-standard:10.8 | 55555, 8088 | internal |
| `zookeeper` | confluentinc/cp-zookeeper:7.5.3 | 2181 | internal |
| `kafka` | confluentinc/cp-kafka:7.5.3 | 9092 | internal |
| `oracle` | gvenzl/oracle-xe:21-slim | 1521 | internal |
| `cassandra` | cassandra:4.1.3 | 9042 | internal |
| `mongodb` | mongo:7.0.4 | 27017 | internal |
| `redis` | redis:7.2.3-alpine | 6379 | internal |
| `clickhouse` | clickhouse-server:23.11 | 8123, 9000 | internal + observability |
| `cockroachdb` | cockroachdb/cockroach:v23.2.0 | 26257 | internal |
| `camunda/zeebe` | camunda/zeebe:8.3.4 | 26500 | internal |
| `vault` | hashicorp/vault:1.15.4 | 8200 | internal |
| `elasticsearch` | elasticsearch:8.11.3 | 9200 | both |
| `kibana` | kibana:8.11.3 | 5601 | observability |
| `logstash` | logstash:8.11.3 | 5044 | both |
| `jaeger` | jaegertracing/all-in-one:1.52.0 | 16686 | observability |
| `prometheus` | prom/prometheus:v2.48.1 | 9090 | observability |
| `grafana` | grafana/grafana:10.2.3 | 3000 | observability |
| `sonarqube` | sonarqube:10.3.0-community | 9000 | both |

### Quick start

```bash
# 1. Start infrastructure
docker compose -f infrastructure/docker-compose.yml up -d

# 2. Build all modules
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/admin-/.maven/maven-3.9.12/bin/mvn package -q --no-transfer-progress

# 3. Run MCP gateway standalone (Ollama must be running)
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/admin-/.maven/maven-3.9.12/bin/mvn -pl mcp-readonly-gateway spring-boot:run \
  --no-transfer-progress

# 4. Start frontend
cd frontend && npm install && npm run dev
# → http://localhost:3000

# 5. Run all tests
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/admin-/.maven/maven-3.9.12/bin/mvn test --no-transfer-progress
```

---

## Test Suite

**41 tests, all passing.**

| Module | Test Class | Tests | What is tested |
|---|---|---|---|
| `gateway` | `PaymentControllerTest` | 2 | Rate limit decision record, DUPLICATE status preservation |
| `gateway` | `PaymentArchTest` | 6 | ArchUnit: controllers in `..controller..`, no KafkaTemplate in `..service..`, domain is Spring-free, no `@Repository`, messaging doesn't depend on service layer |
| `fraud-scoring` | `FraudScoringServiceTest` | 7 | LightGBM scores, heuristic additive rules, velocity window, country risk, CRITICAL/HIGH/LOW/MEDIUM bands |
| `aml-compliance` | `FuzzyMatchTest` | 7 | Exact SDN match, Jaro-Winkler fuzzy, Soundex phonetic variants, alias expansion, clean-pass scenarios |
| `routing-execution` | `RailSelectionTest` | 12 | All 12 rail rules, priority ordering, BACS→CHAPS precedence, CHIPS vs FEDWIRE selection |
| `settlement` | `DoubleEntryAccountingTest` | 3 | Balanced double-entry, imbalance exception, multi-currency |
| `audit` | `HashChainIntegrityTest` | 4 | Chain integrity, tamper detection, sequence ordering, genesis block |
