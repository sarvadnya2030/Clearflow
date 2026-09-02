# Ensemble Evaluation (majority vote across 4 methods)

Post-hoc, no new LLM calls. Ensemble = majority vote on top1 picks (ABSTAIN votes excluded from the count; all-abstain cases ensemble-abstain too).

## Overall AC@1 (n=33 confirmed cases)

| Method | AC@1 |
|---|---|
| heuristic | 90.9% |
| slm | 66.7% |
| large | 87.9% |
| nemotron | 90.9% |
| ensemble | 90.9% |

## Fault-type-wise

| Fault type | n | Heuristic | SLM | Large | Nemotron | Ensemble |
|---|---|---|---|---|---|---|
| AML_HOLD | 3 | 0% | 0% | 0% | 0% | 0% |
| AML_SERVICE_DEGRADATION_RETRY_CASCADE | 3 | 100% | 67% | 100% | 100% | 100% |
| CPU_SATURATION | 4 | 100% | 75% | 100% | 100% | 100% |
| DB_TIMEOUT | 4 | 100% | 75% | 100% | 100% | 100% |
| KAFKA_CONSUMER_LAG | 4 | 100% | 75% | 100% | 100% | 100% |
| NETWORK_LATENCY | 4 | 100% | 75% | 100% | 100% | 100% |
| SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | 4 | 100% | 100% | 75% | 100% | 100% |
| SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | 3 | 100% | 67% | 100% | 100% | 100% |
| VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | 4 | 100% | 50% | 100% | 100% | 100% |