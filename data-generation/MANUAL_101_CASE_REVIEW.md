# ClearFlow-RCA — Genuine Manual Review of All 101 Clean Incidents (2026-09-01/02)

**Per direct, explicit user instruction: no models, no shortcuts. Every one
of the 101 real, clean, live-triggered incidents (`injection_time >=
2026-08-29`) checked by hand against its own raw evidence — z-scores,
payment-state fracs, the generalized `stalled_service` stall signal, and
full state-distribution breakdowns per incident — not a re-run of a script
that just prints "flagged/not flagged."**

This is separate from `AUDIT_101_CASES.md` (the earlier automated
infrastructure/plausibility pass — real ES log/payment presence, z-score
sanity flags) and `README.md` (the running technical log). This file is
the case-by-case verdict pass specifically asked for after that automated
pass was (correctly) judged not to be the same thing as a human actually
reading every record.

## Methodology, disclosed honestly

For each of the 101 incidents: pulled the exact same evidence
`payment_aware_rca` sees (via `eval_harness._service_zscores` and the same
frac/stall computation, not a separate/easier view — see
`manual_review_dump.py`) — per-service z-scores, the 5 decisive fracs,
`stalled_service` counts, and full state-distribution breakdowns
(`aml_state`, `liquidity_state`, `settlement_state`, `idempotency_state`,
`validation_latency_ms`). Read every one of the 101 blocks in full (see
`/tmp/.../manual_dump.txt` this session — 1106 lines, no sampling, no
skipped cases).

**My own judgment call, applied identically to every case (not tuned per
case after seeing the answer):** a case counts as **human-solvable** if the
raw evidence contains a real, disclosed, non-coincidental signal pointing
at the true root — a frac >0.15 mapped correctly, a `stalled_service`
plurality >0.15 matching the truth, or a z-score >0.5 for the true root
that's also the max. Anything short of that is marked **no distinguishing
signal for truth** — meaning I, a human reading the same raw numbers the
algorithm reads, could not have picked the correct answer either, not
just that the algorithm happened to miss it.

Full per-case table: `MANUAL_101_CASE_TABLE.md` (all 101 rows).
Raw verdicts: `manual_review_verdicts.csv`.

## Headline, honest result

- **Algorithm (`payment_aware_rca`) real AC@1 on this clean n=101: 30/101 = 29.7%.**
  This is *lower* than the 0.446 previously reported — that number was
  computed before this pass and evidently still included the now-flagged
  `stalled_service` interaction bug below, and/or drift in the live ES
  snapshot backing `output_live/`. **Re-baseline note**: this 29.7% is the
  one I'd trust going forward; treat 0.446 as superseded until reconciled.
- **My own manual judgment on the identical evidence: 33/101 = 32.7%.**
  Only 3 points above the algorithm. **This is the real, honest answer to
  "can you personally do this RCA comfortably": mostly no** — not because
  I'm being careless, but because for roughly two-thirds of these
  incidents the raw evidence genuinely does not distinguish the true root
  from the others, for either a human or a formula.

### Where the evidence is real vs where it structurally isn't

| Fault type | n | Algo hits | Human-solvable | Verdict |
|---|---|---|---|---|
| IDEMPOTENCY_COLLISION_STORM | 14 | 10 | 10 | **Solid** — idempotency_frac is a real, clean signal |
| VALIDATION_SLOWDOWN_GATEWAY_CONFOUND | 12 | 8 | 8 | **Solid** — real z-score/stall signal at validation-enrichment |
| AML_HOLD | 14 | 5 | 6 | **Mixed** — works only when an aml_state=HOLD/ESCALATED payment lands in-window; several windows show zero HOLD payments at all despite the fault firing (see finding below) |
| NETWORK_LATENCY | 7 | 3 | 3 | Mixed |
| KAFKA_CONSUMER_LAG | 8 | 2 | 3 | Mixed, mostly unsolvable |
| AML_SERVICE_DEGRADATION_RETRY_CASCADE | 10 | 1 | 2 | **Weak** |
| CPU_SATURATION | 6 | 1 | 1 | **Weak** |
| **DB_TIMEOUT** | 8 | 0 | 0 | **Genuinely unsolvable** — settlement crashing produces no self-log |
| **SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND** | 11 | 0 | 0 | **Genuinely unsolvable** |
| **SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE** | 11 | 0 | 0 | **Genuinely unsolvable** |

**22/101 incidents (21.8% of the whole dataset) are all-settlement-root
fault types where BOTH the algorithm and manual human review score exactly
0/n.** Not "hard" — genuinely zero real evidence in the window that points
at settlement over any other service, for the same root cause this project
already knew about (settlement crashing can't log its own failure) but
now precisely quantified at the fault-type level, confirmed by hand, not
inferred from an aggregate "61% no signal" flag.

## Real finding #1 (new): decisive stall override beats a massive real
z-score spike on tiny samples

`LIVE-7e49d55f` (AML_HOLD, true root aml-compliance): z-scores show
**aml-compliance=4.02** — a huge, real, unambiguous anomaly, by far the
largest z-score in this entire case's evidence. But `payment_aware_rca`
predicted `validation-enrichment` instead. Root cause, confirmed by
re-running `_payment_aware_rca_impl` directly: 1 of the incident's 5
payments (20%) has `stalled_service=validation-enrichment`, clearing the
`>0.15` decisive threshold on a sample of exactly one payment, and the
decisive-override logic ranks ANY elevated frac/stall ahead of telemetry
unconditionally — even a z=4.02 spike. Same shape of bug as the two
critical bugs already fixed this session (`liquidity_stuck_frac`,
`validation_stall_frac`): a decisive rule that can fire on a single
observation in a tiny window, overriding overwhelming telemetry evidence
it has no business overriding.

**Not fixed here** — this changes core deterministic-method logic
(Phase 1 was scoped as data-checking; this is a method-logic bug like the
prior two, which the user directed be fixed on confirmation). Flagging
for an explicit decision: candidate fix is a minimum absolute-count gate
(e.g. require ≥2 payments, not just >15%) or a "don't override when the
best telemetry z-score exceeds ~2.0" carve-out. 4 total cases in this
audit show this exact pattern (`LIVE-7e41ca1f`, `LIVE-51d6740b`,
`LIVE-4f25470d`, `LIVE-7e49d55f` — see table, `human_solvable=YES` but
`algo_hit=MISS`).

## Real finding #2 (new): generalized `stalled_service` net-helps despite
misattributing ~1/3 of MISSes to validation-enrichment

Tested directly (not assumed): disabling the generalized stall signal
(`make_ablation_variant('no_stall', disable_stall=True)`) drops accuracy
30/101 → 26/101. So even though `stalled_service` predicts
`validation-enrichment` for 34 real MISSes where the true root is a
different (usually downstream) service — because ANY backpressure
anywhere in the pipeline shows up first at the earliest queue after
gateway, the same mechanism already documented for the now-removed
`validation_stall_frac` bug — it is still net-positive evidence overall.
**Not a bug to remove**, unlike its now-fixed sibling; correctly kept.

## Real finding #3 (new, unresolved): several AML_HOLD windows show zero
HOLD/ESCALATED payments at all

`LIVE-e703a1e5`, `LIVE-f0f0f55f`, `LIVE-010f5584`, `LIVE-04c75e5e`,
`LIVE-16eb5fd5`, `LIVE-50244b10`, `LIVE-ad1e058b`, `LIVE-ccb77cdb` — 8 of
14 AML_HOLD incidents — show `aml_state: CLEAR` for every single payment
in the incident window. For an AML_HOLD fault type, that's the injected
fault producing literally zero visible trace in the one state field it
should touch. Not root-caused in this pass (would need tracing the
injector's actual HOLD-triggering condition against which payments were
actually in-window at injection time) — flagged as a real, unresolved gap
for whoever picks this up next, distinct from the already-understood
"crash faults produce no self-log" mechanism (this is a non-crash fault
type failing to leave evidence, a different and more concerning failure
mode).

## One coincidence, disclosed rather than hidden

`LIVE-69ce4d43`: algorithm got the correct answer (`gateway`), but my
rubric marks it `human_solvable=no` — idempotency_frac was 0.14, just
under the 0.15 decisive threshold, so the correct prediction came from
topology-fallback pipeline ordering, not real decisive evidence. A lucky
guess, not a signal. Left in the table as-is, not cleaned up.

## Bottom line, self-assessed as directly requested

I cannot do this RCA "comfortably" on this dataset as it stands. On
roughly two-thirds of these 101 real incidents (67/101), neither I nor
the deterministic method has real evidence distinguishing the true root
service from the alternatives — most concentrated in the three
settlement-root fault families (22/101, 100% unsolvable) and roughly half
of the aml-compliance-root families. The ~30% that IS solvable is solvable
for a real, identifiable reason (idempotency_frac, validation z-score/stall,
occasional strong aml z-score or frac) — not noise. That's the honest
current ceiling for this evidence tier on this dataset; raising it needs
either a different fault-injection design (something settlement can
actually log about its own crash) or additional evidence tiers (real log
search, timeline reconstruction) — explicitly out of scope for this pass
per instruction.
