# Real-Time Payment Cascade Intelligence — Production-Grade Improvement Roadmap

> Authored: 2026-04-26 · Model: Claude Opus · Target: banks, card networks, core-banking vendors, fintech buyers
> Current rating: 7.4 / 10 → Target after all phases: 9.5 / 10

This roadmap takes Real-Time Payment Cascade Intelligence from demo-grade to bank-grade in five sequenced phases.
Phase 1 stops the bleeding; phases 2–4 build operational/regulatory credibility; phase 5 is the
differentiation layer that closes enterprise deals.

---

## Summary Table

| Phase | Theme | Goal | Effort | Unblocks |
|---|---|---|---|---|
| **1** | Stop-the-bleeding | Eliminate silent data loss, log-disk outage, settlement starvation | M | All other phases |
| **2** | Resilience & Data Integrity | DLQs, idempotency, back-pressure, chaos tests | L | DORA-style operational resilience claims |
| **3** | Security & Zero-Trust | Vault, mTLS, MCP authn/authz, GDPR masking, SIEM | L | PCI-DSS / ISO 27001; bank security review |
| **4** | Observability & SLO Governance | OTel traces, RED/USE dashboards, runbooks, burn alerts | M | Day-2 ops story; on-call runbooks |
| **5** | Enterprise Differentiation | OpenAPI 3.1, contract tests, real LightGBM, k6 SLA suite, lineage UI | XL | RFP-winning demo to Stripe/Visa/SWIFT |

---

## Quick Wins (< 30 min each — do today, in parallel with Phase 1)

| # | Change | File(s) | Why |
|---|---|---|---|
| QW-1 | Add `RollingFileAppender` (100 MB cap, 14-day retention) | All 7 `src/main/resources/logback-spring.xml` | Stops 8 GB audit.log disk-fill outage |
| QW-2 | Ensure `application-dev.yml` profile never activates by default | All 7 `src/main/resources/application.yml` | Prevents shipping cleartext creds |
| QW-3 | Add `management.endpoint.health.probes.enabled=true` + readiness group | All 7 `application.yml` | k8s readiness/liveness split |
| QW-4 | Fix silent `UNKNOWN` paymentId in audit consumer (Jackson JsonPath vs regex) | `audit/.../messaging/AuditEventConsumer.java` | Fixes poisoned hash-chain rows |
| QW-5 | Add `acks=all`, `enable.idempotence=true` to gateway Kafka producer | `gateway/src/main/resources/application.yml` | Pre-req for Phase 1 outbox safety |
| QW-6 | Set `ack-mode=MANUAL_IMMEDIATE` in audit + settlement consumers | Both `application.yml` | Pre-req for DLQ handling in Phase 2 |
| QW-7 | Add Maven `build-info` plugin | Root `pom.xml` | Git SHA + timestamp on every `/actuator/info` |
| QW-8 | Add `owasp:dependency-check-maven` plugin | Root `pom.xml` | One-shot CVE scan, feeds Phase 3 |

---

## Phase 1 — Stop-the-Bleeding

**Goal**: Eliminate the 5 known production-killers so the platform survives a 100K-payment soak test without data loss or disk crash.

**Business value**: A bank will not start a procurement conversation until the platform survives a soak test. Silent data loss and disk-fill outages are immediate disqualifiers in any RFP.

**Effort**: M (3–5 engineer-days)

**Success criteria**:
- 100K soak: `accepted == settled + explicitly_rejected_with_reason` (zero missing)
- Audit log volume < 50 MB/day (down from 8.1 GB)
- Settlement throughput ≥ 95% of accepted (up from 0.5%)
- Grafana panel `clearflow_dlq_depth` shows 0 in steady state

### Task 1.1 — Kafka outbox + DLQ (replace silent fallback)

**Files**:
- `gateway/src/main/java/com/clearflow/gateway/messaging/KafkaEventPublisher.java`
- New: `gateway/src/main/java/com/clearflow/gateway/messaging/PaymentOutboxEntry.java`
- New: `gateway/src/main/java/com/clearflow/gateway/messaging/OutboxRelayScheduler.java`
- `gateway/src/main/resources/application.yml`

**What to do**:
1. Delete `publishFallback` (the silent-drop method). Replace with a Redis-backed outbox:
   - On publish attempt, `LPUSH outbox:pending <JSON>` inside the same logical unit as the idempotency key `SETNX`.
   - A `@Scheduled(fixedDelay=200)` relay drains the list: `RPOPLPUSH outbox:pending outbox:inflight`, attempts Kafka send with `acks=all` + idempotent producer.
   - On success: `LREM outbox:inflight 1 <entry>`.
   - On failure after 5 retries: move entry to Kafka topic `clearflow.payments.dlq`; emit `clearflow_outbox_dlq_total` Micrometer counter.
2. Remove `@CircuitBreaker` from `publish()` — relay handles retries.
3. Create topic `clearflow.payments.dlq` in `start_live_traffic.sh`.

**Verify**: Stop Kafka mid-test → restart → all payments drain to `payment.initiated`. `clearflow.payments.dlq` stays empty.

**Haiku prompt**:
> Read these files first in order: `gateway/src/main/java/com/clearflow/gateway/messaging/KafkaEventPublisher.java`, `service/IdempotencyService.java`, `gateway/src/main/resources/application.yml`. Implement the Redis-LIST outbox pattern exactly as described in task 1.1 of IMPROVEMENT_ROADMAP.md. Output diffs for KafkaEventPublisher, the two new classes, and application.yml only. Do not modify any other service or file.

---

### Task 1.2 — Fix audit Kafka error-loop

**Files**:
- `audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java`
- New: `audit/src/main/java/com/clearflow/audit/config/AuditKafkaErrorHandler.java`
- `audit/src/main/resources/application.yml`

**What to do**:
1. In `AuditEventConsumer`, wrap `auditRepository.save(...)` in try/catch. On exception:
   - Do NOT rethrow.
   - Log at WARN with a rate-limiter (one log per 60 s per error type).
   - Emit `clearflow_audit_save_failures_total` counter.
   - Forward raw Kafka `ConsumerRecord` to topic `clearflow.audit.dlq`.
2. Register a `DefaultErrorHandler` `@Bean` with `ExponentialBackOff(initialInterval=1000, maxInterval=30000, multiplier=2.0, maxAttempts=3)`.
3. Set `spring.kafka.listener.ack-mode=MANUAL_IMMEDIATE` and `enable-auto-commit=false`.

**Verify**: Kill Cassandra → audit.log grows < 1 MB/min. Restart Cassandra → lag drains.

**Haiku prompt**:
> Read `audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java` and `audit/src/main/resources/application.yml`. Implement task 1.2 from IMPROVEMENT_ROADMAP.md: new `AuditKafkaErrorHandler.java` bean with ExponentialBackOff, wrap the save call, forward to DLQ topic. Output the diff. Do not change HashChainService.

---

### Task 1.3 — Logback rolling file appender (all services)

**Files**:
- New: `common/src/main/resources/logback-rolling-include.xml`
- All 7 `src/main/resources/logback-spring.xml`

**What to do**:
1. Create shared include file `logback-rolling-include.xml` with a `RollingFileAppender`:
   - Policy: `SizeAndTimeBasedRollingPolicy`, max 100 MB per file, 14 days history, 5 GB total cap, `cleanHistoryOnStart=true`.
   - File path: `${LOG_PATH:-dev-logs}/${SERVICE_NAME}.log`.
   - Include in `<root>` alongside existing `CONSOLE` and `ASYNC_LOGSTASH` appenders.
2. In each of the 7 `logback-spring.xml` files, add `<include resource="logback-rolling-include.xml"/>`.

**Verify**: Run batch_100k_v3.py 3× back-to-back. `ls -lh dev-logs/` shows no file > 100 MB.

**Haiku prompt**:
> Read `audit/src/main/resources/logback-spring.xml` and `routing-execution/src/main/resources/logback-spring.xml`. Create `common/src/main/resources/logback-rolling-include.xml` with SizeAndTimeBasedRollingPolicy (100 MB, 14 days, 5 GB cap). Then show the modified logback-spring.xml for audit and routing-execution only (other 5 services follow the same pattern). Do not rename any existing appenders.

---

### Task 1.4 — Settlement throughput fix

**Files**:
- `settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java`
- `settlement/src/main/java/com/clearflow/settlement/service/SettlementService.java`
- `settlement/src/main/java/com/clearflow/settlement/repository/SettlementRepository.java`
- `settlement/src/main/resources/application.yml`

**What to do**:
1. Switch Camel consumer source from JMS to Kafka: `from("kafka:clearflow.payment.routed?groupId=settlement-svc&maxPollRecords=500&autoCommitEnable=false&allowManualCommit=true")`.
2. Add idempotency guard: `settlementRepository.existsByPaymentId(paymentId)` — if true, ack and skip.
3. Add `existsByPaymentId(String paymentId): boolean` to `SettlementRepository`.
4. Set concurrency: `clearflow.settlement.workers=32` in `application.yml`, wire into Camel route as thread pool.
5. JMS publish moves to AFTER the MongoDB write (notify downstream, not trigger processing).

**Verify**: 100K test → ≥ 95K `SETTLEMENT_COMPLETE` events within 5 min of last 202.

**Haiku prompt**:
> Read `settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java`, `service/SettlementService.java`, `repository/SettlementRepository.java`, and `settlement/src/main/resources/application.yml`. Implement task 1.4 from IMPROVEMENT_ROADMAP.md: switch Camel source to Kafka, add existsByPaymentId guard, configure 32 workers. Output the diff for all 4 files.

---

### Task 1.5 — Fix @CircuitBreaker on Mono anti-pattern

**Files**:
- Search all services: `grep -rn "@CircuitBreaker" --include="*.java" .`
- `gateway/src/test/java/com/clearflow/gateway/PaymentArchTest.java`

**What to do**:
1. For every method returning `Mono<T>` or `Flux<T>` annotated with `@CircuitBreaker`: remove the annotation and replace with `.transformDeferred(CircuitBreakerOperator.of(circuitBreaker))` on the reactive chain.
2. Inject `CircuitBreakerRegistry` via constructor and look up by name.
3. Add an ArchUnit rule to `PaymentArchTest.java`: methods returning `Mono`/`Flux` MUST NOT carry `@CircuitBreaker`.

**Verify**: ArchUnit test fails before fix, passes after. `resilience4j_circuitbreaker_calls_total` increments under induced failure.

**Haiku prompt**:
> Run: `grep -rn "@CircuitBreaker" /home/admin-/Desktop/EDI6/clearflow --include="*.java"`. For each hit on a method returning Mono or Flux, read that file and replace the annotation with the `.transformDeferred(CircuitBreakerOperator.of(...))` operator pattern. Then add the ArchUnit rule to `gateway/src/test/java/com/clearflow/gateway/PaymentArchTest.java`. Output one diff per file.

---

## Phase 2 — Resilience & Data Integrity

**Goal**: Every async failure path is observable, bounded, and recoverable.

**Business value**: DORA / operational-resilience story for regulators (EBA, FCA, OCC). Banks must demonstrate bounded RTO/RPO. Real-Time Payment Cascade Intelligence delivers an out-of-the-box DORA-aligned control plane.

**Effort**: L (8–12 engineer-days)

**Success criteria**:
- Every Kafka topic has a `*.dlq` sibling with a Grafana panel.
- Chaos test (pumba kill Kafka 30 s) → all payments reach `SETTLED` or `DLQ` within 60 s. Zero lost.
- Gateway sustains 1500 RPS with p99 < 200 ms; 429 above that.
- 95%+ of pipeline stages have Testcontainers integration tests.

### Task 2.1 — Universal DLQ pattern

**Files**:
- New: `common/src/main/java/com/clearflow/common/messaging/DlqPublisher.java`
- All 6 Kafka consumer error handlers (audit, fraud-scoring, validation-enrichment, aml-compliance, routing-execution, settlement).
- `start_live_traffic.sh` — add `*.dlq` topic creation.

**What to do**: Reusable `DlqPublisher.publish(originalTopic, key, payload, exception)` writes to `${originalTopic}.dlq` with headers: `x-original-topic`, `x-failure-reason`, `x-attempt-count`, `x-trace-id`. Wire into every consumer's terminal error handler.

**Haiku prompt**:
> Read `common/src/main/java/com/clearflow/common/messaging/KafkaTopics.java`. Implement `DlqPublisher` with constructor-injected `KafkaTemplate<String,String>`. Then show me how to wire it into `FraudKafkaConsumer.java` (read that file first). Output the new class + the diff for the fraud consumer only — the other 4 consumers are separate tasks.

---

### Task 2.2 — Gateway back-pressure (Bulkhead + tier-aware 429)

**Files**:
- `gateway/src/main/java/com/clearflow/gateway/controller/PaymentController.java`
- `gateway/src/main/java/com/clearflow/gateway/service/RateLimitingFilter.java`
- `gateway/src/main/resources/application.yml`

**What to do**:
1. Add Resilience4j `Bulkhead` (semaphore, max 1000 concurrent) around `POST /payments`. Rejection → 429 with `Retry-After: 1`.
2. Add Micrometer gauge `clearflow_gateway_inflight`.
3. Tier-aware Bucket4j limits from `X-Client-Tier` header: `free`=10 RPS, `bronze`=100, `silver`=1000, `gold`=10000.

**Verify**: k6 ramp 100→5000 RPS → 429s at tier limit; p99 stays < 200 ms for accepted.

---

### Task 2.3 — Per-stage idempotency guard in all consumers

**Files**:
- New: `common/src/main/java/com/clearflow/common/idempotency/StageIdempotencyGuard.java`
- All 6 consumer classes.

**What to do**: `StageIdempotencyGuard.firstSeen(paymentId, stage)` calls `SETNX payments:processed:{paymentId}:{stage}` with 24 h TTL. Consumer calls guard → if false (already seen) → ack and skip.

---

### Task 2.4 — Saga compensation completeness

**Files**:
- `routing-execution/src/main/java/com/clearflow/routing/camel/SagaCompensationRoute.java`
- New: `routing-execution/src/test/java/com/clearflow/routing/SagaCompensationIT.java`

**What to do**: Write a Testcontainers JUnit5 test — boots Kafka + H2 + ActiveMQ, posts a payment, kills settlement consumer, asserts liquidity row returns to `available` within 30 s.

---

### Task 2.5 — Chaos test harness

**Files**:
- New: `chaos/pumba-kafka-kill.sh`
- New: `chaos/pumba-redis-pause.sh`
- New: `chaos/run-chaos-suite.sh`
- New: `chaos/README.md`

**What to do**: Three Pumba scripts — kill Kafka 30 s, pause Redis 10 s, network-partition Cassandra 20 s. Harness runs `live_payment_sender.py 100` before/during/after, asserts zero payments lost, produces `chaos-report.json` with RTO/RPO.

---

### Task 2.6 — Testcontainers integration test base

**Files**:
- New: `common/src/test/java/com/clearflow/common/IntegrationTestBase.java`
- New: `gateway/src/test/java/com/clearflow/gateway/integration/PaymentE2EIT.java`
- Root `pom.xml`: add `testcontainers-bom`, `testcontainers-kafka`, `testcontainers-redis`.

**What to do**: Base class spins up shared Kafka + Redis via `@Testcontainers` / `@DynamicPropertySource`. First E2E test posts a payment and asserts it appears in 4 successive Kafka topics within 10 s.

---

## Phase 3 — Security & Zero-Trust

**Goal**: Replace cleartext secrets and open endpoints with a zero-trust posture.

**Business value**: Required for PCI-DSS, SOC 2 Type II, ISO 27001, NIS2, GDPR Art. 32. Without this phase, Real-Time Payment Cascade Intelligence cannot pass a vendor security questionnaire.

**Effort**: L (10–14 engineer-days)

**Success criteria**:
- `grep -rni "password.*:.*[a-z0-9]" src/main/resources/` returns zero hits.
- All inter-service HTTP requires valid mTLS cert; MCP requires JWT with `mcp:read` scope.
- GDPR test: raw audit row never reveals full IBAN.
- OWASP dependency-check: zero CVEs ≥ HIGH.

### Task 3.1 — HashiCorp Vault secret migration

**Files**: All 7 `application.yml` + `application-dev.yml`, new `infrastructure/vault/scripts/seed-secrets.sh`, all 7 `pom.xml` (add `spring-cloud-starter-vault-config`), all 7 new `bootstrap.yml`.

**What to do**: Move every secret from YAML into Vault KV-v2. `seed-secrets.sh` is idempotent, uses Vault root token from `infrastructure/vault/.env.local` (never committed). Replace literal values with `${vault.kv.clearflow.<service>.<key>}` references.

**Haiku prompt**:
> Read `gateway/src/main/resources/application.yml` and `application-dev.yml`. List every secret/credential. Then read `infrastructure/vault/` directory. Add `spring-cloud-starter-vault-config` to `gateway/pom.xml` and create `gateway/src/main/resources/bootstrap.yml`. Migrate ONLY the gateway service as a reference. Show diffs only.

---

### Task 3.2 — mTLS via Linkerd service mesh

**Files**: `infrastructure/helm/clearflow/values.yaml`, new `infrastructure/helm/clearflow/templates/peer-authentication.yaml`, all 7 `application.yml` (service URLs http → https:443).

**What to do**: Add `linkerd.io/inject: enabled` annotation in all Helm deployment templates. Add `PeerAuthentication: STRICT` so non-mTLS traffic is rejected. Switch service-to-service calls from `http://` to `https://` — mesh terminates TLS.

---

### Task 3.3 — MCP gateway authentication

**Files**:
- `mcp-readonly-gateway/src/main/java/com/clearflow/mcp/config/MCPSecurityConfig.java`
- New: `mcp-readonly-gateway/src/main/java/com/clearflow/mcp/config/JwtScopeConverter.java`

**What to do**: Replace `anyRequest().permitAll()` with `oauth2ResourceServer(jwt -> jwt.jwtAuthenticationConverter(...))`. Scope map: `mcp:read` → `/mcp/payments/**`, `mcp:chat` → `/mcp/chat`, `mcp:admin` → `/actuator/**`.

**Haiku prompt**:
> Read `mcp-readonly-gateway/src/main/java/com/clearflow/mcp/config/MCPSecurityConfig.java` and `mcp-readonly-gateway/pom.xml`. Confirm `spring-boot-starter-oauth2-resource-server` is on classpath. Replace permitAll with JWT resource server config and implement JwtScopeConverter. Output the diff for both files.

---

### Task 3.4 — GDPR PII masking in logs

**Files**:
- New: `common/src/main/java/com/clearflow/common/security/PiiMaskingConverter.java`
- `common/src/main/resources/logback-rolling-include.xml` (add `<conversionRule>`)

**What to do**: Logback `ClassicConverter` subclass. Rules: IBAN → first-4 + `****` + last-4; PAN → BIN + `****` + last-4; email → `a***@domain`. Register via `<conversionRule conversionWord="mask" .../>`. Apply `%mask` in log pattern.

**Verify**: `grep -E "[A-Z]{2}[0-9]{20,}" dev-logs/*.log` returns zero after any run.

---

### Task 3.5 — SIEM integration via Logstash

**Files**: New `infrastructure/logstash/pipeline/security-pipeline.conf`, `infrastructure/logstash/pipelines.yml`.

**What to do**: Tag events with `MARKER=SECURITY` if they match: auth failure, AML_SANCTIONS_HIT, fraud CRITICAL, PAYMENT_BLOCKED. New parallel Logstash pipeline forwards only those to syslog RFC-5424 at `${SIEM_HOST}:514`.

---

### Task 3.6 — OWASP + CodeQL gate

**Files**: Root `pom.xml`, new `.github/workflows/codeql.yml`.

**What to do**: Add `dependency-check-maven` with `failBuildOnCVSS=7` and `suppressionFile=owasp-suppress.xml`. Add GitHub CodeQL workflow on every PR targeting `main`.

---

## Phase 4 — Observability & SLO Governance

**Goal**: End-to-end distributed tracing, RED+USE dashboards, golden-signal SLOs, paged runbooks.

**Business value**: Day-2 operations is where most fintech platforms collapse. This phase delivers a bank-ops-ready answer to "how do you debug a failed cross-border payment at 03:00".

**Effort**: M (5–7 engineer-days)

**Success criteria**:
- One `paymentId` traces across all 7 services in Grafana Tempo.
- `/grafana/d/clearflow-slo` shows burn rates for 4 SLIs (acceptance, success, p99 latency, audit integrity).
- 8 runbooks covering top alert patterns.
- Synthetic prober runs every 60 s feeding SLIs.

### Task 4.1 — OpenTelemetry auto-instrumentation

**Files**: All 7 `pom.xml` (add `opentelemetry-spring-boot-starter`), root BOM, new `infrastructure/otel/otel-collector-config.yaml`.

**What to do**: Add OTel BOM. Each service exports OTLP to collector, which fans out to Tempo (traces) + Prometheus (metrics). Propagate `traceparent` through Kafka headers (already partially done — verify audit consumer reads it).

---

### Task 4.2 — RED + USE + SLO dashboards

**Files**: New `infrastructure/grafana-dashboards/clearflow-red.json`, `clearflow-use.json`, `clearflow-slo.json`.

**What to do**: RED = Rate/Errors/Duration per service. USE = Kafka lag, Redis ops, Cassandra writes. SLO = burn-rate panels using `clearflow:slo:*` recording rules from Prometheus.

---

### Task 4.3 — SLO burn-rate alerting + runbooks

**Files**: `infrastructure/prometheus/rules/clearflow-slo.yml`, new `docs/runbooks/*.md` (8 files).

**What to do**: Recording rules for 4 SLIs. Google multi-window multi-burn-rate alerts (1h+5m at 14.4×, 6h+30m at 6×). Each alert links to runbook via `runbook_url` annotation. Runbooks cover: kafka-down, redis-down, cassandra-lag, audit-chain-break, settlement-lag, mcp-overload, gateway-429-spike, dlq-growing.

---

### Task 4.4 — Synthetic prober

**Files**: New `infrastructure/synthetic/probe.py`, `Dockerfile`, `infrastructure/helm/clearflow/templates/synthetic-cronjob.yaml`.

**What to do**: Every 60 s posts `X-Synthetic: true` payment, pushes result to Pushgateway as `clearflow_synthetic_*`. Excluded from business KPIs in dashboards.

---

## Phase 5 — Enterprise Differentiation

**Goal**: Ship the features that turn a credible platform into an RFP-winning one.

**Business value**: OpenAPI 3.1 + contract tests = plugs into Open Banking ecosystems. Real LightGBM = ML-driven fraud not rules. Data lineage UI = audit answer in 5 clicks not 5 hours.

**Effort**: XL (15–20 engineer-days)

**Success criteria**:
- `GET /v1/openapi.yaml` validates with Spectral, zero errors.
- Pact contract tests run on every PR.
- LightGBM achieves AUC ≥ 0.85 on holdout.
- k6 proves p99 < 200 ms at 1000 RPS for 30 min.
- Lineage UI renders any `paymentId` graph in < 2 s.

### Task 5.1 — OpenAPI 3.1 + URL versioning

**Files**: All 7 controllers (springdoc annotations), `gateway/src/main/java/com/clearflow/gateway/api/v1/`, new `.spectral.yaml`, root `pom.xml` (springdoc-openapi-maven-plugin).

**What to do**: Move endpoints to `/v1/payments`. Add `@Tag`, `@Operation`, `@ApiResponse` annotations. Add Spectral lint enforcing ISO-20022 naming. `Deprecation`/`Sunset` headers for future v2 migration.

---

### Task 5.2 — Pact consumer-driven contract tests

**Files**: New `gateway/src/test/java/.../contracts/FraudConsumerPactTest.java`, `fraud-scoring/src/test/java/.../contracts/FraudProviderPactTest.java`, `infrastructure/pact-broker/docker-compose.yml`.

**What to do**: Gateway expresses what it expects from fraud-scoring Kafka payload; fraud-scoring verifies. Repeat for routing→settlement. CI publishes pacts on merge to main.

---

### Task 5.3 — Real LightGBM model via MLflow

**Files**: Replace `fraud-scoring/.../LightGBMStubClient.java` with `LightGBMNativeClient.java`. New `ml/training/train_lightgbm.py`, `ml/registry/model.txt`.

**What to do**: Train on PaySim-derived dataset. Use Microsoft LightGBM JNI or ONNX Runtime. Hot-swap via `@RefreshScope` pointing at MLflow registry URL. AUC target ≥ 0.85; p99 inference < 5 ms.

---

### Task 5.4 — k6 SLA suite

**Files**: New `load-tests/k6-sla-suite.js`, `load-tests/sla-thresholds.json`.

**What to do**: Stages: 0→500 RPS (5 min), hold 1000 RPS (30 min), ramp 2000 RPS (5 min), drain. Thresholds: `p(99)<200` for accepted requests, `rate<0.001` errors, `dlq_total==0`. Results archived in `load-tests/reports/`.

---

### Task 5.5 — Data lineage UI

**Files**: New `audit/.../controller/AuditController.java` endpoint `GET /v1/lineage/{paymentId}`, new `LineageService.java`, new `frontend/src/pages/Lineage.tsx`.

**What to do**: Lineage endpoint joins Cassandra audit + Mongo settlement + Kafka topic offsets → directed graph: `INITIATED→VALIDATED→AML_CLEAR→ROUTED→SETTLED`. Each node carries timestamp, service, hash, prev-hash. React UI (react-flow) renders the graph with PII-masked raw event JSON on node click.

---

### Task 5.6 — Compliance report generator

**Files**: New `compliance-reports/templates/fatf-r16.md`, `sox-quarterly.md`, `gdpr-dpia.md`. New `compliance-reports/scripts/generate.py`.

**What to do**: Script calls MCP gateway APIs to pull live metrics, fills templates. Runs monthly via `infrastructure/helm/clearflow/templates/compliance-cronjob.yaml`. Output is a Markdown report with real numbers from the running cluster.

---

## Sequencing Rules

1. **Complete Phase 1 entirely before Phase 2** — DLQ work assumes working outbox.
2. **QW-1 (logback rolling) is non-negotiable on day 1** — without it every test risks disk-fill.
3. **Phase 3 before Phase 5** — banks won't demo lineage UI until secrets are out of YAML.
4. **Phase 4 OTel work pays compounding dividends** — every later phase is easier with full traces.
5. **5.3 LightGBM after Phase 4** — need OTel-level observability to prove model didn't regress p99.

---

## Banker Demo Checklist (end-state)

After all 5 phases, the 30-minute RFP demo runs:

1. `bash demo.sh` — 8 services up in 90 s.
2. `python live_payment_sender.py 1` — trace ID printed → Grafana shows full 7-service trace.
3. `docker stop kafka` — outbox holds; restart → payments drain; **zero loss**.
4. Pull any `paymentId` in lineage UI — 5-node graph renders, hash chain verified inline.
5. `curl /v1/openapi.yaml | spectral lint` — 0 errors.
6. `mvn dependency-check:check` — 0 HIGH CVEs.
7. `k6 run k6-sla-suite.js` — p99 < 200 ms, 0 errors at 1000 RPS.
8. Pull GDPR DPIA report — auto-generated from live cluster.

That demo wins RFPs.

---

## Key File Reference

| Task | File |
|------|------|
| 1.1 Outbox | `gateway/src/main/java/com/clearflow/gateway/messaging/KafkaEventPublisher.java` |
| 1.2 Audit fix | `audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java` |
| 1.3 Log rolling | All 7 `src/main/resources/logback-spring.xml` |
| 1.4 Settlement | `settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java` |
| 1.5 CB Mono fix | `grep -rn "@CircuitBreaker" --include="*.java" .` |
| Common | `common/src/main/java/com/clearflow/common/messaging/KafkaTopics.java` |
| Chaos | `chaos/run-chaos-suite.sh` |
| SLO | `infrastructure/prometheus/rules/clearflow-slo.yml` |
