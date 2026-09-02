---
name: clearflow-fault-taxonomy
description: "Module 2 deliverable — formal fault taxonomy for ClearFlow-RCA, grounded in the 12 fault types actually implemented in inject_incidents.py / incidents.csv"
type: project
---

# ClearFlow-RCA — Fault Taxonomy (Module 2)

Not invented independently — this is the taxonomy already implemented in
`data-generation/inject_incidents.py` (`FAULT_CATALOG`) and instantiated as
237 incidents in `output/incidents.csv`, written up formally per the Module 2
requirement. Every fault type below is real: it has a generator, a
precondition, a measurable state effect, and a verified detection signal.

## Design principle

Two axes classify every fault:

1. **Family** — where the root cause originates (infrastructure vs. payment-domain
   policy vs. a mix vs. deliberately misleading telemetry).
2. **Precondition** — which of Module 1's payment-state fields (`aml_state`,
   `liquidity_state`, `idempotency_state`, `settlement_state`, `service_state`)
   must hold before the fault is meaningful. A fault with no payment-state
   precondition is pure infrastructure; one gated entirely by payment state is
   the paper's actual research target.

Four families, balanced ~20 incidents/fault-type (237 total, a few short of
target 240 where the window-scheduler couldn't find a free slot — see README):

## A. Infrastructure faults (root cause = technical, no payment-domain precondition)

| Fault type | Root service | Root component | Depth | Detection signal |
|---|---|---|---|---|
| `DB_TIMEOUT` | settlement | `SettlementService.dataSource` | 1 | `error_rate` spike, settlement svc |
| `KAFKA_CONSUMER_LAG` | routing-execution | `RoutingKafkaConsumer.pollLoop` | 1 | `kafka_lag` spike, routing svc |
| `NETWORK_LATENCY` | validation-enrichment | `ValidationKafkaConsumer.camelRoute` | 1 | `p99_latency_ms` spike, validation svc |
| `CPU_SATURATION` | aml-compliance | `AMLScreeningProcessor.threadPool` | 1 | `cpu_pct` spike, AML svc |

Effect on affected payments: `settlement_state` forced to `FAILED` (40%) or
`PENDING` (60%), `liquidity_state` stays `RESERVED`, `finalized=False`. No
AML/idempotency precondition — these faults can hit any in-flight payment
regardless of its risk profile.

## B. Payment-domain faults (root cause IS a payment-state mechanic — this family is the paper's actual subject matter)

| Fault type | Root service | Root component | Depth | Precondition | Effect |
|---|---|---|---|---|---|
| `LIQUIDITY_LOCK_STUCK` | routing-execution | `LiquidityReservationService.release` | 2 | `liquidity_state=RESERVED`, `payment_state=ROUTED` | `settlement_state→PENDING`, liquidity never releases |
| `AML_HOLD_RETRY_STORM` | aml-compliance | `AMLScreeningProcessor.holdGate` | 2 | `aml_state=HOLD` | `retry_count` climbs (+1 to +4), `settlement_state→PENDING` — models a retry loop that doesn't respect the hold |
| `IDEMPOTENCY_COLLISION_STORM` | gateway | `IdempotencyService.setIfAbsent` | 1 | payment already has an `idempotency_key` in flight | `idempotency_state→DUPLICATE_DETECTED`, `retry_count` +1 to +3 |
| `SETTLEMENT_FINALITY_VIOLATION` | settlement | `SettlementService.settlePayment` | 2 | `finalized=True` (payment already `SETTLED`) | forces `settlement_state` back to `PENDING`, `finalized=False` — an attempted state change past the point it should be legally possible |

This family cannot be diagnosed correctly by telemetry alone: `AML_HOLD_RETRY_STORM`'s
service-level symptom (retry traffic) looks identical to `IDEMPOTENCY_COLLISION_STORM`'s
on a metrics dashboard — only the payment-state fields distinguish them. This is
the family the baseline/payment-aware comparison in Module 5's eval harness is
built to score.

## C. Cross-domain faults (infra root cause, but payment state shapes propagation)

| Fault type | Root service | Root component | Depth | Propagation |
|---|---|---|---|---|
| `SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE` | settlement | `SettlementService.dataSource` | 3 | settlement → routing-execution → settlement (liquidity held during DB outage) |
| `AML_SERVICE_DEGRADATION_RETRY_CASCADE` | aml-compliance | `AMLScreeningProcessor.threadPool` | 3 | aml-compliance → routing-execution → settlement |

Root cause is infrastructure, exactly like family A — but the *reason* it
cascades 3 hops instead of resolving locally is that liquidity/AML state holds
the payment open while the fault persists. Tests whether an RCA method needs
payment-state to correctly measure blast radius, even when it doesn't need it
to find the root service itself.

## D. Confounded faults (deliberately misleading — loudest telemetry ≠ root cause)

| Fault type | Root service | Root component | Depth | Symptom service (louder) |
|---|---|---|---|---|
| `SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND` | settlement | `SettlementService.dataSource` | 4 | routing-execution (`kafka_lag`, 2.2x root's spike magnitude) |
| `VALIDATION_SLOWDOWN_GATEWAY_CONFOUND` | validation-enrichment | `EnrichmentProcessor.camelRoute` | 4 | gateway (`p99_latency_ms`, 2.2x root's spike magnitude) |

Verified quantitatively (not just asserted) in `inject_incidents.py`'s QA pass:
all 39/39 confounded incidents have the downstream symptom service's relative
metric deviation exceed the true root service's own. This is the family where
the naive telemetry-only baseline (`eval_harness.py`) scores worst (AC@1=0.23
vs. 0.80 on infra) — the gap a payment-aware method needs to close.

## Severity / duration model (applies to all families)

| Severity | Cohort size (affected payments) | Duration | Weight |
|---|---|---|---|
| low | 8–20 | 5–15 min | 50% |
| medium | 20–60 | 15–60 min | 35% |
| high | 60–150 | 60–180 min | 15% |

## Temporal difficulty (assigned per family, not computed dynamically)

| Family | Difficulty | Rationale |
|---|---|---|
| infra | easy | symptom appears in the same service as the root cause, immediately |
| payment_domain | medium | symptom requires reading payment-state fields, not just service metrics |
| cross_domain | medium | root is infra-obvious, but full blast radius needs payment-state to explain |
| confounded | hard | symptom's loudest signal is on a *different* service than the root |

## What's intentionally NOT in this taxonomy yet

- **Multi-fault incidents** (two simultaneous root causes) — deferred per the
  design review; single-fault first.

## Update 2026-08-25 — Module 4: the two placeholder mechanics are now real

`AML_HOLD_RETRY_STORM` and `SETTLEMENT_FINALITY_VIOLATION` were flagged above
as CSV-mutation placeholders standing in for missing Java mechanics. Built:

- **AML-hold gate** (`aml-compliance`): formal `AmlState` enum
  (CLEAR/HOLD/ESCALATED/REJECTED), replacing the old ad hoc HIT/CLEAR strings.
  `AMLKafkaConsumer` now genuinely gates on it — HOLD/ESCALATED payments never
  reach `AML_SANCTIONS_CLEAR`/routing until a reviewer resolves them via the
  new `ComplianceReviewController` (`GET /api/v1/compliance/holds`,
  `POST /api/v1/compliance/{paymentId}/resolve`), which replays the stored
  original payload forward on a CLEAR decision.
- **Settlement-finality flag** (`settlement`): `SettlementRecord` now has
  `finalized`/`finalizedAt`. `SettlementService.settlePayment()` distinguishes
  a legitimate idempotent retry (identical amount) from an actual finality
  violation (a repeat call with different amount against an already-finalized
  record), throwing `SettlementFinalityViolationException` and logging
  `SETTLEMENT_FINALITY_VIOLATION` for the latter — previously this case was
  silently swallowed by the early-return idempotency check.

**Still not built** (real, honestly remaining, not yet needed to call these
two fault types "real"): the gateway-level retry path doesn't yet check
`AmlState` before allowing a resubmission through, so `AML_HOLD_RETRY_STORM`'s
"retry loop that doesn't respect the hold" scenario has its gate but not yet
its failure mode wired end-to-end; and `SagaCompensationRoute` still only
releases liquidity on settlement failure, it doesn't write a `FAILED`
`SettlementRecord` — so `settlement_state=FAILED` still has no durable record,
only the transient Kafka/status-cache signal from Module 1.

Full multi-module `mvn compile` passes clean after these changes.

## Related
- [[clearflow_payment_state_schema]] — Module 1, the state fields these faults act on
- [[clearflow]] — full project state and research direction
