| Incident | Fault Type | True Root | Algo Pred | Algo | Human-Solvable | Reason |
|---|---|---|---|---|---|---|
| LIVE-6605a5f6 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-dafd2922 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-13aabdf1 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-c71169ec | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-aea4bd28 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-ac9d4f99 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | aml-compliance | MISS | no | no distinguishing signal for truth |
| LIVE-16440e52 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.16 |
| LIVE-375146f9 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-cf9fd926 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-46c46f73 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-b5bd99ca | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | z:validation-enrichment=0.71 |
| LIVE-445b3604 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.19 |
| LIVE-dd95ea8e | DB_TIMEOUT | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-a3dc5365 | DB_TIMEOUT | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-0679abe9 | KAFKA_CONSUMER_LAG | routing-execution | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-7e41ca1f | KAFKA_CONSUMER_LAG | routing-execution | validation-enrichment | MISS | YES | z:routing-execution=0.56 |
| LIVE-3ac304e5 | KAFKA_CONSUMER_LAG | routing-execution | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-4e92e4d8 | NETWORK_LATENCY | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-322172ef | NETWORK_LATENCY | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-0db6ac08 | CPU_SATURATION | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-c893fc55 | CPU_SATURATION | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-5082610f | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.20 |
| LIVE-aa7a31d5 | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.25 |
| LIVE-442d22f5 | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.17 |
| LIVE-e703a1e5 | AML_HOLD | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-f0f0f55f | AML_HOLD | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-9b916e1f | AML_HOLD | aml-compliance | aml-compliance | HIT | YES | frac:aml-compliance=0.25 |
| LIVE-89f4b295 | DB_TIMEOUT | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-0029cef4 | DB_TIMEOUT | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-a1cf8ab7 | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | HIT | YES | z:routing-execution=0.69 |
| LIVE-529974c3 | KAFKA_CONSUMER_LAG | routing-execution | routing-execution | HIT | YES | z:routing-execution=0.64 |
| LIVE-7eddac91 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.31 |
| LIVE-c43696aa | NETWORK_LATENCY | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.17 |
| LIVE-4093814a | CPU_SATURATION | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-f122cc2c | CPU_SATURATION | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-51d6740b | IDEMPOTENCY_COLLISION_STORM | gateway | validation-enrichment | MISS | YES | frac:gateway=0.50 |
| LIVE-e1d7984a | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.20 |
| LIVE-010f5584 | AML_HOLD | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-04c75e5e | AML_HOLD | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-5292e78d | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-36504166 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-d7c17b54 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-d3886b6a | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | aml-compliance | HIT | YES | z:aml-compliance=3.03 |
| LIVE-23f96ab7 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-bbca1b76 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-e5e5b525 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | z:validation-enrichment=4.45 |
| LIVE-02b2695f | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-9b2cc5f4 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-c106dc64 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | routing-execution | MISS | no | no distinguishing signal for truth |
| LIVE-4f25470d | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | gateway | MISS | YES | z:aml-compliance=1.05 |
| LIVE-a731aed7 | IDEMPOTENCY_COLLISION_STORM | gateway | aml-compliance | MISS | no | no distinguishing signal for truth |
| LIVE-1975c960 | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.25 |
| LIVE-1e801edd | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.50 |
| LIVE-50244b10 | AML_HOLD | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-7e49d55f | AML_HOLD | aml-compliance | validation-enrichment | MISS | YES | z:aml-compliance=4.02 |
| LIVE-ad1e058b | AML_HOLD | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-e02375c2 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-eadd4565 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.15 |
| LIVE-1d02a5a8 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-cc885896 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-f04d432b | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-4cea9f14 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.19 |
| LIVE-ddf47161 | DB_TIMEOUT | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-049c8d86 | DB_TIMEOUT | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-9a48b999 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-a055b72a | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-2ae40f2d | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-41ace2f8 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-a2ceeaba | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-d343e12f | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.20 |
| LIVE-b82de1ed | IDEMPOTENCY_COLLISION_STORM | gateway | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-69ce4d43 | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | no | no distinguishing signal for truth |
| LIVE-08da5024 | AML_HOLD | aml-compliance | aml-compliance | HIT | YES | frac:aml-compliance=0.33 |
| LIVE-ec6deaec | AML_HOLD | aml-compliance | aml-compliance | HIT | YES | frac:aml-compliance=0.20 |
| LIVE-16eb5fd5 | AML_HOLD | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-bffd36ab | DB_TIMEOUT | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-5e306f3d | DB_TIMEOUT | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-f2204653 | KAFKA_CONSUMER_LAG | routing-execution | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-3b7ad3f2 | KAFKA_CONSUMER_LAG | routing-execution | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-11a8bf36 | KAFKA_CONSUMER_LAG | routing-execution | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-6f4f4391 | NETWORK_LATENCY | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.24 |
| LIVE-95c7b3c0 | NETWORK_LATENCY | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-90316572 | NETWORK_LATENCY | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-e4b28eee | CPU_SATURATION | aml-compliance | aml-compliance | HIT | YES | z:aml-compliance=2.50 |
| LIVE-4745d75e | CPU_SATURATION | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-5961ed7b | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-b3972f3a | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-2681f3d8 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | settlement | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-508fa2a6 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | aml-compliance | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-02346c6a | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-61417db7 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-742fa9b9 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | settlement | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-7db3364a | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.17 |
| LIVE-62540cb5 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | validation-enrichment | HIT | YES | stall:validation-enrichment=0.38 |
| LIVE-1dc2c80e | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | validation-enrichment | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-1f884cbc | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.25 |
| LIVE-0f30ca31 | IDEMPOTENCY_COLLISION_STORM | gateway | gateway | HIT | YES | frac:gateway=0.20 |
| LIVE-34fc48b1 | IDEMPOTENCY_COLLISION_STORM | gateway | validation-enrichment | MISS | no | no distinguishing signal for truth |
| LIVE-ccb77cdb | AML_HOLD | aml-compliance | gateway | MISS | no | no distinguishing signal for truth |
| LIVE-3207937e | AML_HOLD | aml-compliance | aml-compliance | HIT | YES | frac:aml-compliance=0.25 |
| LIVE-f832240f | AML_HOLD | aml-compliance | aml-compliance | HIT | YES | frac:aml-compliance=1.00 |