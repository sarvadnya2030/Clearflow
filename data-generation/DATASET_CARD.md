# ClearFlow-RCA Dataset Card

Draft, Phase 2 of `../BENCHMARK_PLAN.md`. Modeled on the packaging
conventions comparable RCA benchmarks use (RCAEval: microservice RCA
from logs/traces/metrics with an explicit ground-truth root-cause label
per incident; LEMMA-RCA: multi-domain causal-chain tracing) so a reviewer
already familiar with that space finds what they expect here -- not a
copy of their fault taxonomy or data, which are unrelated to ours.

## What this is

Real, live-triggered incidents from a real, running 8-microservice
payments processing stack (Spring Boot + Kafka + ActiveMQ + Elasticsearch,
emulating real bank rails: SWIFT GPI/MT103, Fedwire, CHIPS, SEPA,
TARGET2, CHAPS, BACS, Faster Payments) -- not a synthetic log generator.
Faults are injected into the real running services (process kill/crash,
DB timeout, Kafka consumer lag, CPU saturation, AML hold, idempotency
collision) and the resulting real telemetry (Elasticsearch logs, payment
state transitions) is captured as evidence, with the injector's own
trigger call as ground truth for which service was the real root cause.

## Scale (current, live-extracted set)

- **143 total live-triggered incidents**, of which **101 are "clean"**
  (`injection_time >= 2026-08-29`, within this ES setup's confirmed
  reliable evidentiary shelf-life of a few days -- see Known Limitations)
  and 42 are "stale" (kept, not deleted, but excluded from headline
  scoring; their z-scores degrade to all-zero because live queries hit
  ES's own history-retention behavior, not a labeling error).
- 4,801 real payments across the dataset's live-traffic window.
- 10 fault types across 4 fault families (`infra`, `payment_domain`,
  `cross_domain`, `confounded`).
- 5 possible root-cause services: gateway, validation-enrichment,
  aml-compliance, routing-execution, settlement.

## Schema

`output_live/incidents.csv` (one row per incident):
`incident_id, fault_type, fault_family, root_service, root_component,
root_event_id, propagation_path, propagation_depth, temporal_difficulty,
severity, injection_time, duration_seconds, n_affected_payments, seed,
is_confounder, has_distinguishing_evidence`

`has_distinguishing_evidence` (added 2026-09-02, see
`../RESEARCH_POSITIONING.md`): boolean, derived from the full manual
per-case evidence review (`MANUAL_101_CASE_REVIEW.md`) -- `True` for the
33/101 clean incidents where the raw evidence (z-scores, payment-state
fracs, stall signal) contains a real signal distinguishing the true root
from alternatives; `False` for the 68/101 where it does not (a genuine
evidentiary blackout, not a labeling gap); `NaN`/empty for the 42 stale
incidents (not reviewed). **This is the field that turns "22 unsolvable
cases" from a benchmark flaw into a first-class evaluation axis**: score
methods on AC@1 for `True` rows, and on correct abstention for `False`
rows, rather than penalizing every method equally for guessing wrong on
cases nothing could have solved.

`output_live/clearflow_rca_dataset.csv` (one row per real payment):
`payment_id, created_at, aml_state, liquidity_state, settlement_state,
idempotency_state, retry_count, validation_latency_ms, stalled_service,
amount, currency, saga_compensation_triggered, saga_compensation_released`

`output_live/metrics.csv` (one row per service per 30s bucket):
`timestamp, service, error_rate, p99_latency_ms, kafka_lag, cpu_pct` --
**disclosed limitation**: for the live-extracted set, only `error_rate`
is real; `p99_latency_ms`/`kafka_lag`/`cpu_pct` are empty placeholders
(see Known Limitations).

## Ground truth

`root_service` in `incidents.csv` is the service the fault injector
actually targeted (a real Java `AdminController` kill/restart call, a
real DB-timeout/Kafka-lag injection, etc.) -- not inferred after the
fact. This is the label every RCA method is scored against (AC@1: did
the method's top-ranked guess match `root_service`).

## Splits

Not yet defined. Candidate approach for publication: stratify by
`fault_family` x `temporal_difficulty` rather than a flat random split,
since the 101 clean incidents are unevenly distributed across the 10
fault types (10-19 each) -- a flat random split risks a test fold with
zero examples of a rare type. **Open decision, not yet made** -- flag
for the user before finalizing.

## Known limitations (disclosed, not hidden)

1. **~2/3 of the 101 clean incidents have no evidence distinguishing the
   true root from alternatives**, for either a human or any method tried
   so far -- concentrated almost entirely in 3 settlement-root fault
   families (22/101, exactly 0% solved by every method tried). Root
   cause: a crashed service cannot log its own crash. This is the
   dataset's real, honest difficulty profile, not a flaw to fix before
   publishing -- arguably the most useful part of the benchmark, since it
   tests whether a method can recognize "no real signal" rather than
   confidently guessing wrong.
2. **Live ES evidence has a shelf life of a few days** -- incidents older
   than ~2-4 days show degraded (all-zero) z-scores because evidence is
   queried live at extraction time, not frozen at capture time. The
   101/42 clean/stale split exists specifically to handle this; a
   published version should either re-extract close to injection time
   going forward, or move to frozen per-incident snapshots.
3. **IBANs/BICs are structurally valid but not check-digit verified**
   (`live_payment_sender.py`) -- fine for RCA evidence purposes (the
   pipeline never validates check digits either), disclosed in case a
   downstream user assumes otherwise.
4. **`validation_retry_frac` never fires on live data** (`retry_count` is
   always 0 -- no gateway instrumentation exists for it) and
   `p99_latency_ms`/`kafka_lag`/`cpu_pct` are always empty for
   live-extracted rows (only `error_rate` is populated) -- both disclosed
   dead/placeholder fields in the current schema, not silently unused.
5. **The project's own best deterministic method scores 0.416 AC@1**
   (42/101) as of 2026-09-02 (superseded from an earlier same-day 0.297
   after fixing a miscalibrated tie-break constant, `TOPOLOGY_TIE_MARGIN`
   -- see `../BENCHMARK_PLAN.md` Phase 1 for the full, undeleted history
   of both numbers). This is the honest
   baseline to beat, not a number to spin upward.

## Licensing

Not yet decided -- open item before publication (MIT to match the
comparable-benchmark convention seen in FinRCA-AI-Bench is a reasonable
default, but this is the user's call, not mine to assume).

## Status

Draft. Phase 2 item in `../BENCHMARK_PLAN.md` -- needs a human decision
on splits and licensing before this is publication-ready; everything else
here is verified against the live dataset as of 2026-09-02.
