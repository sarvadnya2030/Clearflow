# Baseline RCA Evaluation Results

Run against 71 gold cases (61 confirmed, 10 evidence-free) via live ES re-query. Gold labels not modified.

## Headline: AC@1 / AC@3 on confirmed cases (n=61)

| Method | AC@1 | AC@3 | n |
|---|---|---|---|
| Heuristic (rule-based, no LLM) | 73.8% | 73.8% | 61 |
| SLM (qwen3:4b) | 6.6% | 6.6% | 61 |
| Large (openai/gpt-oss-20b) | 68.9% | 68.9% | 61 |

## Per fault-type breakdown (AC@1)

| Fault type | n | Heuristic | SLM | Large |
|---|---|---|---|---|
| AML_HOLD | 6 | 0% | 0% | 0% |
| AML_SERVICE_DEGRADATION_RETRY_CASCADE | 5 | 100% | 0% | 60% |
| CASSANDRA_OUTAGE | 5 | 0% | 0% | 0% |
| CPU_SATURATION | 6 | 100% | 17% | 83% |
| DB_TIMEOUT | 6 | 100% | 0% | 100% |
| KAFKA_CONSUMER_LAG | 6 | 100% | 17% | 100% |
| MONGODB_OUTAGE | 5 | 0% | 20% | 40% |
| NETWORK_LATENCY | 6 | 100% | 0% | 83% |
| SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | 5 | 100% | 0% | 100% |
| SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | 5 | 100% | 0% | 80% |
| VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | 6 | 100% | 17% | 100% |

## Evidence-free cases (confirmed=false) -- does each method correctly fail to find signal, or hallucinate a confident wrong answer?

| Incident | Heuristic top1 | SLM top1 | Large top1 | Gold label (unverifiable) |
|---|---|---|---|---|
| LIVE-fb98b217 | routing-execution | aml-compliance | none | gateway (injector-only, no evidence) |
| LIVE-374da004 | routing-execution | none | A | gateway (injector-only, no evidence) |
| LIVE-fd202168 | routing-execution | none | A | gateway (injector-only, no evidence) |
| LIVE-2a87e1a2 | routing-execution | none | A | gateway (injector-only, no evidence) |
| LIVE-0d5964c1 | routing-execution | none | none | redis (injector-only, no evidence) |
| LIVE-56d4a244 | routing-execution | none | none | redis (injector-only, no evidence) |
| LIVE-166ba8bb | routing-execution | none | settlement | redis (injector-only, no evidence) |
| LIVE-df78118d | routing-execution | none | none | redis (injector-only, no evidence) |
| LIVE-ae2180ff | routing-execution | none | A | gateway (injector-only, no evidence) |
| LIVE-29955d91 | routing-execution | none | none | redis (injector-only, no evidence) |

## Per-case error analysis (confirmed cases only)

| Incident | Fault type | Gold | Heuristic | SLM | Large | Diagnosis |
|---|---|---|---|---|---|---|
| LIVE-cd1f76ee | DB_TIMEOUT | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-158ce68e | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | none | routing-execution | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-c714ec37 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-75f80ed7 | CPU_SATURATION | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-549afd1b | AML_HOLD | aml-compliance | routing-execution | none | none | solved by none -- investigate: hard case or bad evidence |
| LIVE-d29470d5 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-92d99e70 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | none | none | mixed |
| LIVE-0fbc4973 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-8ed9457d | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-e5f57fc7 | DB_TIMEOUT | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-fc3f6e2a | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | none | routing-execution | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-50580610 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | none | none | mixed |
| LIVE-084a3a65 | CPU_SATURATION | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-4e899937 | AML_HOLD | aml-compliance | routing-execution | none | A | solved by none -- investigate: hard case or bad evidence |
| LIVE-c9126bf2 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-86e563f1 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-9608ddd3 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-6e7fe0ef | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-f8458870 | DB_TIMEOUT | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-98435f36 | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | none | routing-execution | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-2e6706a0 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-4d00a0c8 | CPU_SATURATION | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-2b3c53da | AML_HOLD | aml-compliance | routing-execution | none | none | solved by none -- investigate: hard case or bad evidence |
| LIVE-0c057497 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-a41428fd | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | none | none | mixed |
| LIVE-d45c0b73 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-724753fd | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-a1018952 | DB_TIMEOUT | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-1dd87cec | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | none | routing-execution | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-b39b1e5f | NETWORK_LATENCY | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-8b01e57d | CPU_SATURATION | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-b12684e5 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-7e974bac | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-3cf078b4 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-fc3e530b | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment | solved by all -- likely easy/1-hop case |
| LIVE-32fb18f2 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-c15c694b | MONGODB_OUTAGE | mongodb | validation-enrichment | none | mongodb | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-0c342599 | CASSANDRA_OUTAGE | cassandra | routing-execution | audit | audit | solved by none -- investigate: hard case or bad evidence |
| LIVE-5bb250bb | MONGODB_OUTAGE | mongodb | validation-enrichment | none | validation-enrichment | solved by none -- investigate: hard case or bad evidence |
| LIVE-125bb06d | AML_HOLD | aml-compliance | routing-execution | none | A | solved by none -- investigate: hard case or bad evidence |
| LIVE-0e259052 | CASSANDRA_OUTAGE | cassandra | routing-execution | none | none | solved by none -- investigate: hard case or bad evidence |
| LIVE-06e81ed2 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | none | none | mixed |
| LIVE-8adba291 | MONGODB_OUTAGE | mongodb | routing-execution | mongodb | mongodb | mixed |
| LIVE-ee039e30 | CASSANDRA_OUTAGE | cassandra | routing-execution | none | none | solved by none -- investigate: hard case or bad evidence |
| LIVE-471a5319 | AML_HOLD | aml-compliance | routing-execution | none | none | solved by none -- investigate: hard case or bad evidence |
| LIVE-b6970a15 | CASSANDRA_OUTAGE | cassandra | routing-execution | none | audit | solved by none -- investigate: hard case or bad evidence |
| LIVE-2d244bc5 | MONGODB_OUTAGE | mongodb | routing-execution | none | validation-enrichment | solved by none -- investigate: hard case or bad evidence |
| LIVE-e0bb5818 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-930f1eb1 | CASSANDRA_OUTAGE | cassandra | routing-execution | none | audit | solved by none -- investigate: hard case or bad evidence |
| LIVE-91a7a4e1 | CPU_SATURATION | aml-compliance | aml-compliance | none | aml-compliance | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-1a15e740 | DB_TIMEOUT | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-945a2566 | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | none | routing-execution | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-20c7d62a | NETWORK_LATENCY | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-1da629c1 | MONGODB_OUTAGE | mongodb | routing-execution | none | validation-enrichment | solved by none -- investigate: hard case or bad evidence |
| LIVE-1a1dcc24 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-6ca737bb | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-ff0092f0 | DB_TIMEOUT | settlement | settlement | none | settlement | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-7f2b759d | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | routing-execution | routing-execution | solved by all -- likely easy/1-hop case |
| LIVE-8ca37f16 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | none | validation-enrichment | large succeeds, SLM fails -- reasoning-capability-limited |
| LIVE-0d446d08 | CPU_SATURATION | aml-compliance | aml-compliance | aml-compliance | none | SLM succeeds, large fails -- unexpected, worth inspecting |
| LIVE-ab26f7eb | AML_HOLD | aml-compliance | routing-execution | none | none | solved by none -- investigate: hard case or bad evidence |