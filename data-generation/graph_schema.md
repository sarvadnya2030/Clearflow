---
name: clearflow-graph-schema
description: "Module 3 deliverable — causal knowledge graph schema for ClearFlow-RCA, grounded in the actual payment_events.csv/incidents.csv structure, with a fix for a discovered ground-truth leak"
type: project
---

# ClearFlow-RCA — Graph Schema (Module 3)

## Node types

| Node type | Category | Source | Key |
|---|---|---|---|
| `Service` | Infrastructure | fixed (5 services) | service name |
| `PaymentEvent` | Execution evidence | `payment_events.csv` | `event_id` |
| `Payment` | Payment | `clearflow_rca_dataset.csv` | `payment_id` |
| `Account` | Payment | `accounts.csv` | `account_id` |
| `MetricWindow` | Observability | aggregated from `metrics.csv` | `(service, time_bucket)` |
| `Incident` | Failure | `incidents.csv` | `incident_id` — **ground truth only, see below** |

`MetricWindow` aggregates raw 5-min metric samples into coarser buckets (e.g.
15-30 min) per service — feeding 43,200 raw samples in as individual nodes
would dwarf the 50K-payment graph for no benefit; a graph builder needs
"was this service anomalous in this window," not every sample.

**Why `PaymentEvent` isn't just "Observability":** a node like `LIQUIDITY_RESERVED`
is simultaneously an observation, a payment-state transition, domain
information, and (via `caused_by`) potentially causal evidence — collapsing
all of that into "observability" undersells what the payment-aware RCA method
is actually meant to exploit. Treat it as its own category: **execution
evidence**.

## Edge taxonomy — three kinds, not one

This is the structural point from the design review: don't let a graph
builder treat "two things are related" as one undifferentiated edge type.

### STRUCTURAL (static topology — doesn't change over time)
- `Service --CALLS--> Service` (fixed pipeline order: gateway → validation-enrichment
  → aml-compliance → routing-execution → settlement, matches `PROPAGATION_CHAINS`
  in `inject_incidents.py`)
- `PaymentEvent --OCCURS_AT--> Service`
- `PaymentEvent --BELONGS_TO--> Payment`
- `Payment --INVOLVES--> Account` (debtor and creditor)
- `Service --EMITS--> MetricWindow`

### TEMPORAL (happens-before, from `parent_event_id`)
- `PaymentEvent --NEXT--> PaymentEvent`, within one payment's own chain.
  Directionality: parent → child means "happened before." This is pure
  ordering, carries no causal claim by itself.

### CAUSAL (an actual claim: A produced B)
- `PaymentEvent --CAUSED--> PaymentEvent`, from `caused_by`, **within the same
  payment only** (e.g. an AML decision event causing that same payment's
  BLOCKED transition; a settlement event causing that same payment's
  liquidity-release event). This is legitimate observable evidence — real
  systems do carry this kind of request-lineage/correlation data.

## The leak, and the fix

Verified directly against the data: for every affected payment in an
incident, its fault-propagation event's `caused_by` points straight at the
incident's `root_event_id` — a **cross-payment** causal pointer. Checked
`INC-0000`: all 8 affected payments' fault events have `caused_by ==
root_event_id`, exactly. That means a method with read access to `caused_by`
solves 100% of incidents by pointer-following, with zero reasoning — which
would make the entire baseline/payment-aware/ablation comparison meaningless
the moment any method gets graph access instead of metrics-only access.

**Fix, to apply before Module 6 builds anything:** split `caused_by` into two
classes at graph-construction time, not at generation time (the generator's
output stays as-is — this is a graph-*building* rule, not a data change):

1. **Within-payment `caused_by`** (`payment_id` of source == `payment_id` of
   target) → always included as a `CAUSED` edge. Legitimate evidence.
2. **Cross-payment `caused_by`** (an affected payment's event pointing at
   another payment's root event) → **excluded from the evidence graph** any
   method under test receives. It is held out exactly like `incidents.csv`
   and `incident_payments.csv` — usable only by the eval harness to grade an
   answer, never as an input feature.

A method that needs to find "these 8 payments share one root cause" has to
*discover* that correlation itself — from shared timing window, shared
downstream service, shared state-transition pattern — not read it off an
edge. That rediscovery is the actual hard part of RCA, and stripping the
cross-payment pointer is what keeps the confounder incidents (Module 2,
family D) meaningful once evaluation moves beyond the telemetry-only
baseline.

**Optional oracle mode:** for debugging/sanity-checking the eval harness
itself (not for reporting a real result), a method may be run *with* the
cross-payment pointer included, as a "graph-oracle ceiling" — this should
always score ~100% and exists only to confirm the harness's scoring logic is
correct, never presented as a real experimental condition.

## What the RCA method under test actually sees vs. what's held out

| Visible (evidence graph) | Held out (scoring only) |
|---|---|
| Service topology (STRUCTURAL) | `Incident` node and all its edges |
| PaymentEvent chains, TEMPORAL edges | Cross-payment `CAUSED` edges |
| Within-payment CAUSAL edges | `incidents.csv`, `incident_payments.csv` |
| Payment-state fields (Module 1) | `root_event_id` as a labeled answer |
| MetricWindow anomaly scores | `fault_type`/`fault_family` labels |

## Evidence tiers (G0-G4) — don't hand every method the same graph

A single "the graph" is the wrong abstraction once methods are being compared
against each other. Define nested evidence views instead, each one strictly
adding to the last:

| Tier | Adds | Cumulative content |
|---|---|---|
| **G0** | Topology only | `Service --CALLS--> Service` |
| **G1** | + Temporal | G0 + `PaymentEvent --NEXT-->` chains |
| **G2** | + Telemetry | G1 + `MetricWindow` anomaly scores |
| **G3** | + Payment state | G2 + Module 1's fields (`aml_state`, `liquidity_state`, `idempotency_state`, `settlement_state`, `finalized`, rail) |
| **G4** | + Within-payment causal | G3 + legitimate `CAUSED` edges (never cross-payment — see leak fix above) |

**Never in any tier:** `Incident` node, `root_event_id`, `fault_type`/`fault_family`
labels, `incident_payments.csv`, cross-payment `CAUSED` edges. Those exist
only for `eval_harness.py` to grade an answer.

## Method-to-tier access matrix

This is the actual experimental design, not just a graph description —
it defines which method is allowed to see which tier, so "payment state
helped" is a controlled claim rather than an artifact of one method simply
getting more information than another:

| Method | G0 topology | G1 temporal | G2 telemetry | G3 payment state | G4 causal |
|---|:---:|:---:|:---:|:---:|:---:|
| `loudest_metric_baseline` (built, see `eval_harness.py`) | ✗ | ✗ | ✓ | ✗ | ✗ |
| Graph RCA (topology-aware baseline) | ✓ | ✓ | ✓ | ✗ | ✗ |
| Payment-aware RCA (proposed method) | ✓ | ✓ | ✓ | ✓ | ✗ |
| Full RCA (ceiling condition) | ✓ | ✓ | ✓ | ✓ | ✓ |

Note: `loudest_metric_baseline` as currently implemented in `eval_harness.py`
does NOT use topology at all (it z-scores each service's own metrics
independently, with no `Service --CALLS-->` traversal) — it's a pure G2
condition, not G0+G1+G2.

**Update:** `graph_topology_baseline` and `payment_aware_rca` are now
implemented (see `eval_harness.py`). First version of the topology heuristic
had a real bug — "prefer most-upstream anomalous service" as a hard override
of z-score rank, which crashed confounded AC@1 to 0.000 (worse than not
using topology at all) because propagation direction isn't reliably
root→downstream (a slow downstream call can spike an upstream caller's own
latency via blocking). Fixed: topology now only breaks ties between services
within a bounded z-score margin, never overrides a clear telemetry signal.
Corrected results:

| family | loudest (G2) | graph_topology (G0-G2) | payment_aware (G0-G3) |
|---|---|---|---|
| infra | 0.800 | 0.775 | 0.787 |
| payment_domain | 0.835 | 0.835 | **0.886** |
| cross_domain | 0.641 | 0.692 | 0.667 |
| confounded | 0.231 | 0.154 | 0.179 |

`payment_domain` shows the predicted signal — the real jump happens
specifically at the G2→G3 step (0.835→0.886), not from adding topology
alone. Confounded stays hard for every method (as designed), but no longer
catastrophically regresses below the naive baseline.

**The result this ladder should produce, stratified by fault family (already
proven possible — see the infra=0.80/confounded=0.23 gap from the telemetry-only
baseline):**

```
                    Metrics-only   Graph RCA (G0-G2)   Payment RCA (G0-G3)   Full (G0-G4)
infra                   high            high                 high               high
payment_domain          low             low                  HIGH               HIGH
cross_domain            medium          medium               higher             higher
confounded              LOW             low-medium           HIGH               HIGH
```

If `payment_domain` and `confounded` rows show the biggest jump specifically
between the G2 and G3 columns, that isolates payment-state as the causal
factor — not "more information in general" (G0/G1 additions should barely
move those rows) and not "graph reasoning in general" (G4 additions should
barely move them either, since the useful signal is the state fields, not
the extra causal edges). That's the negative-control structure the earlier
review asked for, built into the tier ladder itself rather than as a
separate experiment.

## Related
- [[clearflow_payment_state_schema]] — Module 1
- [[clearflow_fault_taxonomy]] — Module 2
- [[clearflow]] — full project state and research direction
