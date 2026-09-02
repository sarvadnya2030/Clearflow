# Baseline RCA Evaluation Results

Run against 37 gold cases (33 confirmed, 4 evidence-free) via live ES re-query. Gold labels not modified. Includes AML_HOLD evidence-filter fix and abstention option (ABSTAIN scores correct on evidence-free cases, wrong on confirmed cases).

## Headline: AC@1 / AC@3 on confirmed cases (n=33)

| Method | AC@1 | AC@3 | n |
|---|---|---|---|
| Heuristic (rule-based) | 90.9% | 90.9% | 33 |
| SLM (qwen3.5:4b) | 66.7% | 81.8% | 33 |
| Large (openai/gpt-oss-20b) | 87.9% | 87.9% | 33 |
| Nemotron (nvidia/nemotron-3-nano-omni-30b-a3b-reasoning) | 90.9% | 90.9% | 33 |

## Headline: abstention rate on evidence-free cases (n=4) -- higher is better

| Method | Correct abstentions | Hallucinated a wrong answer |
|---|---|---|
| Heuristic (rule-based) | 0/4 | 4/4 |
| SLM (qwen3.5:4b) | 1/4 | 3/4 |
| Large (openai/gpt-oss-20b) | 2/4 | 2/4 |
| Nemotron (nvidia/nemotron-3-nano-omni-30b-a3b-reasoning) | 2/4 | 2/4 |

## Per fault-type breakdown (AC@1)

| Fault type | n | Heuristic | SLM | Large | Nemotron |
|---|---|---|---|---|---|
| AML_HOLD | 3 | 0% | 0% | 0% | 0% |
| AML_SERVICE_DEGRADATION_RETRY_CASCADE | 3 | 100% | 67% | 100% | 100% |
| CPU_SATURATION | 4 | 100% | 75% | 100% | 100% |
| DB_TIMEOUT | 4 | 100% | 75% | 100% | 100% |
| KAFKA_CONSUMER_LAG | 4 | 100% | 75% | 100% | 100% |
| NETWORK_LATENCY | 4 | 100% | 75% | 100% | 100% |
| SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | 4 | 100% | 100% | 75% | 100% |
| SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | 3 | 100% | 67% | 100% | 100% |
| VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | 4 | 100% | 50% | 100% | 100% |

## Evidence-free cases -- per-method verdict

| Incident | Heuristic | SLM | Large | Nemotron | Gold (injector-only) |
|---|---|---|---|---|---|
| LIVE-fb98b217 | routing-execution | None | None | ABSTAIN | gateway |
| LIVE-374da004 | routing-execution | settlement | ABSTAIN | settlement | gateway |
| LIVE-fd202168 | routing-execution | settlement | settlement | ABSTAIN | gateway |
| LIVE-2a87e1a2 | routing-execution | ABSTAIN | ABSTAIN | settlement | gateway |

## Per-case detail (confirmed cases only)

| Incident | Fault type | Gold | Heuristic | SLM | Large | Nemotron |
|---|---|---|---|---|---|---|
| LIVE-cd1f76ee | DB_TIMEOUT | settlement | settlement | None | settlement | settlement |
| LIVE-158ce68e | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | routing-execution | routing-execution | routing-execution |
| LIVE-c714ec37 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment |
| LIVE-75f80ed7 | CPU_SATURATION | aml-compliance | aml-compliance | aml-compliance | aml-compliance | aml-compliance |
| LIVE-549afd1b | AML_HOLD | aml-compliance | routing-execution | ABSTAIN | None | ABSTAIN |
| LIVE-d29470d5 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | None | settlement | settlement |
| LIVE-92d99e70 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | aml-compliance | aml-compliance | aml-compliance |
| LIVE-0fbc4973 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | settlement | settlement | settlement |
| LIVE-8ed9457d | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment |
| LIVE-e5f57fc7 | DB_TIMEOUT | settlement | settlement | settlement | settlement | settlement |
| LIVE-fc3f6e2a | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | routing-execution | routing-execution | routing-execution |
| LIVE-50580610 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | settlement | validation-enrichment | validation-enrichment |
| LIVE-084a3a65 | CPU_SATURATION | aml-compliance | aml-compliance | aml-compliance | aml-compliance | aml-compliance |
| LIVE-4e899937 | AML_HOLD | aml-compliance | routing-execution | ABSTAIN | ABSTAIN | ABSTAIN |
| LIVE-c9126bf2 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | settlement | settlement | settlement |
| LIVE-86e563f1 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | aml-compliance | aml-compliance | aml-compliance |
| LIVE-9608ddd3 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | settlement | settlement | settlement |
| LIVE-6e7fe0ef | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | settlement | validation-enrichment | validation-enrichment |
| LIVE-f8458870 | DB_TIMEOUT | settlement | settlement | settlement | settlement | settlement |
| LIVE-98435f36 | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | settlement | routing-execution | routing-execution |
| LIVE-2e6706a0 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment |
| LIVE-4d00a0c8 | CPU_SATURATION | aml-compliance | aml-compliance | aml-compliance | aml-compliance | aml-compliance |
| LIVE-2b3c53da | AML_HOLD | aml-compliance | routing-execution | ABSTAIN | None | ABSTAIN |
| LIVE-0c057497 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | settlement | settlement | settlement | settlement |
| LIVE-a41428fd | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | settlement | aml-compliance | aml-compliance |
| LIVE-d45c0b73 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | settlement | settlement | settlement |
| LIVE-724753fd | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment |
| LIVE-a1018952 | DB_TIMEOUT | settlement | settlement | settlement | settlement | settlement |
| LIVE-1dd87cec | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | routing-execution | routing-execution | routing-execution |
| LIVE-b39b1e5f | NETWORK_LATENCY | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment | validation-enrichment |
| LIVE-8b01e57d | CPU_SATURATION | aml-compliance | aml-compliance | settlement | aml-compliance | aml-compliance |
| LIVE-b12684e5 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | settlement | settlement | None | settlement |
| LIVE-7e974bac | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | None | validation-enrichment | validation-enrichment |