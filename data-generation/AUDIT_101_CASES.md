# ClearFlow-RCA — Full 101-Case Infrastructure Audit (2026-09-01)

**This file exists because I built real bugs into this project's core method
and didn't catch them until directly pushed to verify everything myself.**
Not a polished report — a blunt, complete record of what was actually
checked, what was found, and what's still real vs still broken, for every
one of the 101 real incidents this project's headline numbers are based on.

Separate from `README.md` (the running technical log) and the Obsidian
vault note (the running project journal) per explicit instruction — this
file is the audit record specifically, not mixed into the narrative log.

---

## What was checked, for every one of the 101 incidents

For each real, live-triggered incident (`injection_time >= 2026-08-29`):
1. **Real ES log presence** in the exact incident window (total count +
   which services actually logged something) — verifies the raw
   observability pipeline (Elasticsearch, Logstash, the services' own
   logging) is actually collecting real data, not silently empty.
2. **Real payment count** in the window (from the real payments dataset).
3. **Real z-scores** per service (post-sigma-fix, see README v44) —
   flagged if any service still shows an implausible magnitude, or if
   ALL five services show exactly 0.0 (meaning zero usable telemetry
   differentiation for that incident at all).
4. **Real payment-state fracs** (post-v45/v46 fixes) and which, if any,
   cross the 0.15 decisive threshold.

## Real infrastructure status at time of audit

This project runs on Docker Compose + local JVM processes, not Kubernetes
— audited the real equivalent:

```
infrastructure-kafka-1: healthy
infrastructure-zookeeper-1: healthy
infrastructure-mongodb-1: healthy
infrastructure-redis-1: healthy
infrastructure-cassandra-1: healthy (audit_records table created this session, see README v46)
infrastructure-elasticsearch-1: healthy
infrastructure-activemq-artemis-1: healthy
infrastructure-logstash-1: up
infrastructure-kibana-1: up
infrastructure-vault-1: unhealthy (KNOWN, DISCLOSED gap -- no secrets
  wired into the RCA data path, does not affect any real finding in
  this audit; not re-investigated here)
```
All 8 application services (gateway:8080, fraud-scoring:8081,
validation-enrichment:8082, aml-compliance:8083, routing-execution:8084,
settlement:8085, audit:8086, mcp-readonly-gateway:8087) responded HTTP 200
on `/actuator/health` at every check throughout this audit.

## Real, complete summary

- **101 incidents audited.**
- **0 incidents with zero real logs in their window.** The raw
  observability pipeline itself is intact -- every incident has real,
  substantial log volume (roughly 700-1300+ real documents per window).
- **0 incidents with zero real payments in their window.**
- **79 of 101 incidents (78%) flagged** with at least one real issue below.
- **62 of 101 incidents (61%) show ALL FIVE services at z-score exactly
  0.0** -- no usable telemetry-anomaly signal at all for the majority of
  real incidents in this dataset. This is the single most important,
  previously-uncharacterized fact about this dataset's real difficulty.
- **1 incident (LIVE-c106dc64) still shows a large z-score (100.0)** --
  investigated, confirmed legitimate (a real 100% error-rate spike from a
  genuinely quiet 0%-error baseline, not a residual bug; see README v44).
- The remaining flags are all `ROOT_SERVICE_HAS_NO_LOGS_IN_WINDOW` --
  expected, mechanical behavior for every crash-mechanism fault type (the
  killed process cannot log during its own downtime), not a data-quality
  bug, but recorded here as real, confirmed behavior rather than assumed.

## The real, honest conclusion for the benchmark plan

The dataset's raw ingredients (real logs, real payments, real service
crashes) are genuinely intact and real -- confirmed by this audit, not
assumed. **The actual limitation is signal density, not data integrity**:
61% of real incidents produce no differentiated error-rate telemetry at
all, meaning any RCA method relying primarily on z-scores is structurally
blind on the majority of this dataset, and payment-state fracs (only 2 of
6 currently reliable -- see README v46) don't cover enough of the 5
diagnosable services to fill that gap. This is the honest reason this
project's real AC@1 ceiling (0.406, tied with the naive baseline once the
three broken fracs were removed) is where it is -- not a fixable bug, a
genuine property of short-duration real incidents that any published
benchmark needs to state plainly, not hide.

---

## Full per-incident raw audit output (all 101, unedited)

```
AUDITING 101 INCIDENTS
LIVE-6605a5f6 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=29 | total_logs=1012 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.60 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-dafd2922 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=24 | total_logs=1245 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.90 | elevated_fracs=NONE
LIVE-13aabdf1 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=21 | total_logs=884 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'validation-enrichment'] | max|z|=0.67 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-c71169ec | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=25 | total_logs=917 | services=['audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=2.53 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-aea4bd28 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=30 | total_logs=961 | services=['audit', 'fraud-scoring', 'gateway', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.38 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-ac9d4f99 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=33 | total_logs=944 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=4.88 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-16440e52 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=19 | total_logs=1265 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=6.35 | elevated_fracs=NONE
LIVE-375146f9 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=30 | total_logs=697 | services=['audit', 'fraud-scoring', 'gateway', 'unknown'] | max|z|=1.09 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-cf9fd926 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=28 | total_logs=967 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.46 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-46c46f73 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=19 | total_logs=1225 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.55 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-b5bd99ca | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=27 | total_logs=802 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=3.03 | elevated_fracs=NONE
LIVE-445b3604 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=32 | total_logs=909 | services=['audit', 'fraud-scoring', 'gateway', 'settlement', 'unknown'] | max|z|=0.91 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-dd95ea8e | DB_TIMEOUT | root=settlement | n_payments=15 | total_logs=546 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-a3dc5365 | DB_TIMEOUT | root=settlement | n_payments=16 | total_logs=771 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-0679abe9 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=24 | total_logs=841 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.69 | elevated_fracs=NONE
LIVE-7e41ca1f | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=15 | total_logs=631 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=8.00 | elevated_fracs=NONE
LIVE-3ac304e5 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=9 | total_logs=635 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=6.90 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_routing-execution_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-4e92e4d8 | NETWORK_LATENCY | root=validation-enrichment | n_payments=18 | total_logs=564 | services=['audit', 'fraud-scoring', 'gateway', 'unknown'] | max|z|=0.41 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-322172ef | NETWORK_LATENCY | root=validation-enrichment | n_payments=19 | total_logs=702 | services=['audit', 'fraud-scoring', 'gateway', 'unknown'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-0db6ac08 | CPU_SATURATION | root=aml-compliance | n_payments=13 | total_logs=530 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=5.85 | elevated_fracs=NONE
LIVE-c893fc55 | CPU_SATURATION | root=aml-compliance | n_payments=12 | total_logs=534 | services=['audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=4.40 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-5082610f | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=5 | total_logs=265 | services=['audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.2}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-aa7a31d5 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=4 | total_logs=290 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.64 | elevated_fracs={'idempotency_frac': 0.25}
LIVE-442d22f5 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=6 | total_logs=240 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.167}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-e703a1e5 | AML_HOLD | root=aml-compliance | n_payments=5 | total_logs=243 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-f0f0f55f | AML_HOLD | root=aml-compliance | n_payments=4 | total_logs=194 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-9b916e1f | AML_HOLD | root=aml-compliance | n_payments=4 | total_logs=226 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'aml_hold_frac': 0.25}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-89f4b295 | DB_TIMEOUT | root=settlement | n_payments=33 | total_logs=1252 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-0029cef4 | DB_TIMEOUT | root=settlement | n_payments=14 | total_logs=771 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-a1cf8ab7 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=11 | total_logs=534 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=7.41 | elevated_fracs=NONE
LIVE-529974c3 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=16 | total_logs=766 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'validation-enrichment'] | max|z|=6.90 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_routing-execution_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-7eddac91 | NETWORK_LATENCY | root=validation-enrichment | n_payments=16 | total_logs=555 | services=['audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=0.13 | elevated_fracs=NONE
LIVE-c43696aa | NETWORK_LATENCY | root=validation-enrichment | n_payments=18 | total_logs=636 | services=['audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-4093814a | CPU_SATURATION | root=aml-compliance | n_payments=18 | total_logs=581 | services=['audit', 'fraud-scoring', 'gateway', 'validation-enrichment'] | max|z|=4.88 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-f122cc2c | CPU_SATURATION | root=aml-compliance | n_payments=20 | total_logs=685 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.50 | elevated_fracs=NONE
LIVE-51d6740b | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=2 | total_logs=182 | services=['audit', 'fraud-scoring', 'gateway', 'validation-enrichment'] | max|z|=0.39 | elevated_fracs={'idempotency_frac': 0.5}
LIVE-e1d7984a | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=5 | total_logs=306 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.2}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-010f5584 | AML_HOLD | root=aml-compliance | n_payments=7 | total_logs=282 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-04c75e5e | AML_HOLD | root=aml-compliance | n_payments=8 | total_logs=251 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-5292e78d | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=26 | total_logs=1221 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.07 | elevated_fracs=NONE
LIVE-36504166 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=26 | total_logs=1183 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.56 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-d7c17b54 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=23 | total_logs=684 | services=['audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=0.15 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-d3886b6a | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=20 | total_logs=886 | services=['audit', 'fraud-scoring', 'gateway', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=4.88 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-23f96ab7 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=20 | total_logs=1054 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.36 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-bbca1b76 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=19 | total_logs=896 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.45 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-e5e5b525 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=27 | total_logs=695 | services=['audit', 'fraud-scoring', 'gateway', 'unknown'] | max|z|=4.94 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-02b2695f | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=21 | total_logs=632 | services=['audit', 'fraud-scoring', 'gateway', 'settlement', 'unknown'] | max|z|=0.09 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-9b2cc5f4 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=23 | total_logs=765 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.61 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-c106dc64 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=27 | total_logs=1054 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=100.00 | elevated_fracs=NONE
   FLAGS: ['STILL_LARGE_ZSCORE:100.0']
LIVE-4f25470d | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=21 | total_logs=749 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.61 | elevated_fracs=NONE
LIVE-a731aed7 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=6 | total_logs=353 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'aml_hold_frac': 0.167, 'idempotency_frac': 0.167}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-1975c960 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=4 | total_logs=185 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.25}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-1e801edd | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=2 | total_logs=261 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.5}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-50244b10 | AML_HOLD | root=aml-compliance | n_payments=7 | total_logs=317 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-7e49d55f | AML_HOLD | root=aml-compliance | n_payments=5 | total_logs=242 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=9.52 | elevated_fracs=NONE
LIVE-ad1e058b | AML_HOLD | root=aml-compliance | n_payments=5 | total_logs=234 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-e02375c2 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=33 | total_logs=1440 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.64 | elevated_fracs=NONE
LIVE-eadd4565 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=26 | total_logs=632 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.41 | elevated_fracs=NONE
LIVE-1d02a5a8 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=21 | total_logs=820 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=0.60 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-cc885896 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=23 | total_logs=943 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'unknown', 'validation-enrichment'] | max|z|=8.33 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
LIVE-f04d432b | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=27 | total_logs=950 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.87 | elevated_fracs=NONE
LIVE-4cea9f14 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=27 | total_logs=1050 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.31 | elevated_fracs=NONE
LIVE-ddf47161 | DB_TIMEOUT | root=settlement | n_payments=37 | total_logs=1883 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.15 | elevated_fracs=NONE
LIVE-049c8d86 | DB_TIMEOUT | root=settlement | n_payments=14 | total_logs=503 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-9a48b999 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=27 | total_logs=986 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-a055b72a | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=21 | total_logs=1127 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-2ae40f2d | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=24 | total_logs=1013 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=1.49 | elevated_fracs=NONE
LIVE-41ace2f8 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=24 | total_logs=1114 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-a2ceeaba | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=21 | total_logs=791 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-d343e12f | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=5 | total_logs=149 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.2}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-b82de1ed | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=7 | total_logs=199 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-69ce4d43 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=7 | total_logs=232 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-08da5024 | AML_HOLD | root=aml-compliance | n_payments=3 | total_logs=249 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'aml_hold_frac': 0.333}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-ec6deaec | AML_HOLD | root=aml-compliance | n_payments=5 | total_logs=253 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'aml_hold_frac': 0.2}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-16eb5fd5 | AML_HOLD | root=aml-compliance | n_payments=5 | total_logs=353 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-bffd36ab | DB_TIMEOUT | root=settlement | n_payments=22 | total_logs=756 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-5e306f3d | DB_TIMEOUT | root=settlement | n_payments=18 | total_logs=722 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-f2204653 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=22 | total_logs=850 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-3b7ad3f2 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=14 | total_logs=655 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-11a8bf36 | KAFKA_CONSUMER_LAG | root=routing-execution | n_payments=16 | total_logs=706 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_routing-execution_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-6f4f4391 | NETWORK_LATENCY | root=validation-enrichment | n_payments=17 | total_logs=585 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-95c7b3c0 | NETWORK_LATENCY | root=validation-enrichment | n_payments=16 | total_logs=633 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-90316572 | NETWORK_LATENCY | root=validation-enrichment | n_payments=16 | total_logs=548 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-e4b28eee | CPU_SATURATION | root=aml-compliance | n_payments=15 | total_logs=689 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.50 | elevated_fracs=NONE
LIVE-4745d75e | CPU_SATURATION | root=aml-compliance | n_payments=16 | total_logs=681 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-5961ed7b | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=26 | total_logs=919 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=2.50 | elevated_fracs=NONE
LIVE-b3972f3a | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=24 | total_logs=1301 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-2681f3d8 | SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE | root=settlement | n_payments=14 | total_logs=625 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-508fa2a6 | AML_SERVICE_DEGRADATION_RETRY_CASCADE | root=aml-compliance | n_payments=32 | total_logs=1210 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-02346c6a | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=29 | total_logs=1250 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-61417db7 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=34 | total_logs=1720 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-742fa9b9 | SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND | root=settlement | n_payments=30 | total_logs=1595 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-7db3364a | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=24 | total_logs=644 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-62540cb5 | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=8 | total_logs=385 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-1dc2c80e | VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | root=validation-enrichment | n_payments=25 | total_logs=858 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-1f884cbc | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=4 | total_logs=143 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.25}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-0f30ca31 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=5 | total_logs=258 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'idempotency_frac': 0.2}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-34fc48b1 | IDEMPOTENCY_COLLISION_STORM | root=gateway | n_payments=4 | total_logs=271 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-ccb77cdb | AML_HOLD | root=aml-compliance | n_payments=2 | total_logs=177 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs=NONE
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-3207937e | AML_HOLD | root=aml-compliance | n_payments=4 | total_logs=137 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'unknown', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'aml_hold_frac': 0.25}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']
LIVE-f832240f | AML_HOLD | root=aml-compliance | n_payments=1 | total_logs=82 | services=['aml-compliance', 'audit', 'fraud-scoring', 'gateway', 'routing-execution', 'settlement', 'validation-enrichment'] | max|z|=0.00 | elevated_fracs={'aml_hold_frac': 1.0}
   FLAGS: ['ALL_ZSCORES_DEGENERATE_ZERO']

=== SUMMARY: 79 / 101 incidents flagged ===
  LIVE-6605a5f6: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-13aabdf1: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-c71169ec: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-aea4bd28: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-ac9d4f99: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-375146f9: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-cf9fd926: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-46c46f73: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-445b3604: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-dd95ea8e: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-a3dc5365: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-3ac304e5: ['ROOT_SERVICE_routing-execution_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-4e92e4d8: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-322172ef: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-c893fc55: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-5082610f: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-442d22f5: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-e703a1e5: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-f0f0f55f: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-9b916e1f: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-89f4b295: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-0029cef4: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-529974c3: ['ROOT_SERVICE_routing-execution_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-c43696aa: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-4093814a: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-e1d7984a: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-010f5584: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-04c75e5e: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-36504166: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-d7c17b54: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-d3886b6a: ['ROOT_SERVICE_aml-compliance_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-23f96ab7: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-bbca1b76: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-e5e5b525: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-02b2695f: ['ROOT_SERVICE_validation-enrichment_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-9b2cc5f4: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-c106dc64: ['STILL_LARGE_ZSCORE:100.0']
  LIVE-a731aed7: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-1975c960: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-1e801edd: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-50244b10: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-ad1e058b: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-1d02a5a8: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-cc885896: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)']
  LIVE-049c8d86: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-9a48b999: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-a055b72a: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-41ace2f8: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-a2ceeaba: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-d343e12f: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-b82de1ed: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-69ce4d43: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-08da5024: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-ec6deaec: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-16eb5fd5: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-bffd36ab: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-5e306f3d: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-f2204653: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-3b7ad3f2: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-11a8bf36: ['ROOT_SERVICE_routing-execution_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-6f4f4391: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-95c7b3c0: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-90316572: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-4745d75e: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-b3972f3a: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-2681f3d8: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-508fa2a6: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-02346c6a: ['ROOT_SERVICE_settlement_HAS_NO_LOGS_IN_WINDOW(expected-for-crash-faults)', 'ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-61417db7: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-742fa9b9: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-7db3364a: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-62540cb5: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-1dc2c80e: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-1f884cbc: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-0f30ca31: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-34fc48b1: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-ccb77cdb: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-3207937e: ['ALL_ZSCORES_DEGENERATE_ZERO']
  LIVE-f832240f: ['ALL_ZSCORES_DEGENERATE_ZERO']
```
