# ClearFlow-RCA Benchmark — Standing Goal (re-read this every iteration)

**Read this file in full before every single action in this loop. Then
re-check STATUS below before deciding what to do next. Do not trust
anything you (a past iteration) wrote here or elsewhere without
re-verifying it against the running system directly — logs, HTTP calls,
`docker compose ps`, real query results. "It said healthy last time" is
not verification.**

## What we are actually building

A public, real (not fully synthetic) financial-payments RCA benchmark:
dataset + infra + baseline methods, for comparing SLM vs larger-model RCA
performance, published on GitHub. Three parts, in order:

1. **Infra**: a real emulation of a bank's technical payment-processing
   stack — Spring Boot microservices, Kafka (event bus), ActiveMQ Artemis
   (JMS coordination/saga compensation), Elasticsearch+Logstash+Kibana
   (logging/observability), MongoDB/Cassandra/Redis (state), payment
   rails modeled after real ones (SWIFT GPI/MT103, Fedwire, CHIPS, SEPA,
   TARGET2, BACS, Faster Payments, CHAPS, BACS — see
   `routing-execution/.../domain/PaymentRail.java`), 8 microservices
   (gateway, fraud-scoring, validation-enrichment, aml-compliance,
   routing-execution, settlement, audit, mcp-readonly-gateway).
2. **Dataset**: real payments sent through that real infra, real faults
   injected (`live_fault_injector.py`), real incidents captured with real
   root-cause labels, real evidence (ES logs, payment state, telemetry)
   extracted per incident (`live_evidence.py`) — see
   `data-generation/output_live/`.
3. **RCA methods + eval**: baselines scored against the real incidents.
   **Phase 1 (does the gold-case set discriminate between methods?) ran
   2026-09-02 by direct instruction, overriding the "not started yet"
   note below — see the dated log at the end of this file. Full-scale
   method scoring against every incident is still future work.**

## Current phase: moved past INFRA + DATASET CORRECTNESS ONLY on 2026-09-02

Originally: fix and verify the dataset and infrastructure first, no model
runs. Per direct instruction on 2026-09-02, a real Phase 1 validation
experiment (4 baseline RCA methods run against all 37 gold cases) was
authorized and executed to answer a more fundamental question first: does
the gold-case set even contain enough causal signal to discriminate
between methods, before investing further in scale? Findings below. The
non-trust protocol and "verify, don't assume" discipline still apply in
full — this is a phase change, not a discipline change.

## Non-trust protocol (standing rule, from `.claude/CLAUDE.md`, applies
double here)

- Never accept "returns HTTP 200" / "no exception thrown" as proof of
  correctness. Read the actual payload, the actual log line, the actual
  row count.
- Never accept a previous session's or previous iteration's written
  claim as true. Re-run the check yourself, this iteration, before acting
  on it. If it still holds, say so explicitly with the fresh evidence,
  don't just cite the old note.
- If a component looks fine in isolation, check it end-to-end: does it
  actually contribute to `data-generation/output_live/*.csv` /
  Elasticsearch data that the RCA methods consume? A perfectly healthy
  service that isn't wired into the real pipeline is worthless for this
  benchmark.
- Every real finding (bug fixed, gap found, thing confirmed genuinely
  working) gets logged: this file's STATUS section, `data-generation/README.md`,
  and the Obsidian note (`clearflow.md`) per standing instruction to
  update it after every real change.

## Iteration procedure

1. Read this file.
2. Read the STATUS checklist below — pick the next `[ ]` or `[?]` item.
3. Verify or fix it for real (commands, not assumptions).
4. Update STATUS (`[x]` verified-working-with-evidence, `[!]`
   found-broken-fixed, `[FLAG]` found-broken-not-fixed-needs-a-decision).
5. Log the finding (brief, honest, no spin) to README.md / Obsidian.
6. Commit if files changed.
7. Move to the next item. If all items are `[x]`/`[FLAG]`, do a fresh
   pass: re-verify a few already-`[x]` items at random (don't trust your
   own past `[x]`), then report the phase as done and stop expanding
   scope — do not start Phase 3 (model runs) without being told.

## STATUS (living checklist — edit this section in place each iteration)

### Infra — post-reboot recovery, CRITICAL fix (2026-09-02)
- [x] **Full machine reboot recovery**: all Docker containers and host
      JVM processes were gone. Recovered: `docker compose up -d`
      (elasticsearch cold-start race handled), stopped the containerized
      duplicates of the 8 app services (compose defines them too, but
      the real architecture -- and the fault injector's kill/relaunch-
      by-port mechanism -- needs them as host JVM processes), ran
      `start_live_traffic.sh` (real rebuild + restart, all 8 healthy).
- [x] **CRITICAL bug found and fixed**: `PaymentController.java`'s live
      path synchronously published to a JMS destination
      (`CLEARFLOW.PAYMENT.INITIATED`) with zero real consumers anywhere
      in the codebase. Once it filled, Artemis's producer-side flow
      control blocked the calling thread (not an exception), silently
      stalling Solace, Kafka, the status update, and the
      `PAYMENT_SUBMITTED` log for every real payment -- while the
      client still got HTTP 202. Fixed: removed the dead JMS publish
      from the live path; bumped Artemis globalMaxSize 1GB->4GB as
      defense in depth. Verified: 18/18 health checks, full 5-stage
      real trace. See README v50, memory item #14.
- [x] Health check script itself fixed too: was flagging the
      intentionally-stopped containerized app-service duplicates as a
      false failure; added an explicit exclusion list.

### Infra — agent memory graph (new, 2026-09-02)
- [x] Added Neo4j (`infrastructure/docker-compose.yml`, `neo4j:5.24-community`)
      as a real, queryable knowledge-graph store for this benchmark
      project's own accumulated data (incidents, evidence, per-method
      predictions, real findings) — per direct user request, since a lot
      of interrelated data is being generated at once. Added with
      `depends_on`/`restart: unless-stopped` from the start (learned from
      the Jaeger outage — do not repeat that mistake). Verified: real
      write+read via the Python driver, real ingestion via
      `data-generation/build_agent_memory_graph.py` (idempotent, MERGE-based,
      safe to re-run as `model_comparison_results.csv` grows), numbers
      cross-checked against the flat CSV and matched (one disclosed
      convention difference: the graph doesn't create a PREDICTED_BY edge
      for a timed-out/empty prediction, so its per-method `n` can be 1
      lower than the CSV's, which counts a timeout as a scored miss).
      Browsable at localhost:7474 (neo4j/clearflow-dev-graph). Included
      in `scripts/startup_health_check.py` (18/18 passing now).

### Infra — container/process layer
- [x] All 8 Spring Boot services HTTP 200 on `/actuator/health` (verified
      2026-09-02, all 8 responded 200)
- [x] Kafka, Zookeeper, MongoDB, Redis, Cassandra, Elasticsearch,
      ActiveMQ Artemis: `docker compose ps` all `healthy` (verified
      2026-09-02)
- [x] Kibana: `/api/status` returns `overall.level: available` (verified
      2026-09-02)
- [x] Logstash: `docker compose ps` shows `Up`; port 9600 monitoring API
      doesn't respond (real gap, not investigated further — low
      priority, doesn't block data flow), but confirmed indirectly:
      `clearflow-*` ES indices are receiving fresh docs today, so the
      Kafka->Logstash->ES pipeline is real and working
- [FLAG] Vault: `unhealthy`, not re-investigated this pass (still citing
      prior audit's "not on RCA data path" claim without a fresh check —
      do this next iteration, don't just carry the citation forward again)
- [!] **FOUND AND FIXED 2026-09-02: Jaeger (OTLP collector, :4318) had
      been crashed for ~13h** (`docker ps -a` showed `Exited (1)`) — it
      raced Elasticsearch at boot with no `depends_on`/`restart` policy,
      hit a fatal storage-init error, and never came back. Real,
      measured impact: 15786/15792 (99.96%) of gateway's ERROR-level logs
      today, and similar >95% shares for fraud-scoring/validation-
      enrichment/routing-execution/settlement/aml-compliance, were
      `Failed to export spans` connection-refused noise, not real
      payment errors — this is the exact field
      (`level=ERROR` doc count) `live_evidence.py`'s
      `fetch_error_rate_series` divides to build every z-score in this
      benchmark. Fixed: restarted the container, added
      `depends_on: elasticsearch: condition: service_healthy` +
      `restart: unless-stopped` to `infrastructure/docker-compose.yml`
      so it can't silently stay down again. Verified: 0 new export-fail
      logs and real traces landing in Jaeger for all 7 app services
      after the fix. **Dataset impact**: the outage started with today's
      infra restart (~13h ago), which is AFTER the 101-incident dataset
      (injected 2026-08-29 to 08-31) was captured — that dataset is NOT
      contaminated. Any incident injected in the last ~13h, before this
      fix, would have had a noise-contaminated error-rate baseline —
      none were (no new `output_live` rows dated in that window found),
      so no retroactive damage, but this was actively poisoning the well
      for any NEW incident that would have been captured before this fix
      landed.

### Infra — is data really flowing end-to-end?
- [x] Sent 15 real payments through the gateway (`live_payment_sender.py`,
      2026-09-02): 15/15 HTTP 202. Traced one payment's full 21-doc ES
      history end-to-end: gateway(PAYMENT_SUBMITTED) → audit(chain
      append) → validation-enrichment(PAYMENT_VALIDATED) →
      aml-compliance(AML_SCREENING_COMPLETE) → routing-execution
      (RAIL_SELECTED rail=SWIFT_GPI, real LIQUIDITY_RESERVED with a real
      reservationId, PAYMENT_ROUTED) → settlement(SETTLEMENT_COMPLETE) →
      fraud-scoring(FRAUD_SCORE_COMPUTED) — real, complete, ~90ms
      wall-clock. Real data flow confirmed end-to-end, not assumed.
- [x] Confirmed via the same trace: gateway, audit, validation-enrichment,
      aml-compliance, routing-execution, settlement, fraud-scoring all
      logged real events to ES for this one payment (7/8 — the 8th,
      mcp-readonly-gateway, is a read-only query service not on the
      payment-submission path, so it's expected not to log per-payment
      events; not a gap)
- [x] 9 real Kafka consumer groups confirmed active (routing-liquidity-
      release, fraud-scoring, gateway-status-tracker, logstash-siem-
      consumer, aml-compliance-kafka, audit-service, validation-
      enrichment-kafka, routing-execution-kafka, settlement-service),
      logstash-siem-consumer at 0 lag across all partitions checked —
      real, healthy consumption (verified 2026-09-02)
- [!] **Found, not a bug but a real disclosed gap**: `live_evidence.py`'s
      `fetch_error_rate_series` hardcodes `p99_latency_ms`, `kafka_lag`,
      `cpu_pct` to `""` (empty) for every live-extracted row — only
      `error_rate` is real. `_service_zscores` only reads `.error_rate`
      so this doesn't break current z-scores, but the `metrics.csv`
      schema's other 3 columns are dead placeholders for the live
      dataset (unlike the synthetic one, which populates them). If the
      benchmark is published with this schema, document this explicitly
      rather than let it look like unused real data.
- [!] **Re-verified, correction to memory**: `SagaCompensationRoute` (the
      JMS saga-compensation consumer on `CLEARFLOW.PAYMENT.SETTLEMENT.FAILED`)
      is real, deployed code (confirmed: `Started saga-compensation-route`
      startup log present). But its actual "Saga compensation triggered:
      paymentId=..." per-payment log line has **zero matches across the
      entire ES history** (checked all `clearflow-*` indices, all dates).
      "Liquidity released" (the companion release-on-compensation log) is
      also zero matches. This mechanism has never fired once in this
      dataset's real history — consistent with, and a new independent
      confirmation of, the already-known thesis that settlement-crash
      faults produce no self-evidence anywhere (settlement dies before it
      can even publish to the JMS failed-settlement queue that would
      trigger this route). Real, working safety code, genuinely
      unexercised — same shape as `settlement_failed_frac`'s "never fires
      live" gap already documented in `PAYMENT_STATE_SERVICE_BIAS`.
- [x] Confirmed via the same real-payment trace above: a real
      FR→ES USD 890,000 payment on `SWIFT_MT103` channel got
      `RAIL_SELECTED rail=SWIFT_GPI expectedSettlementTime=P2D`, with a
      real `LIQUIDITY_RESERVED` step before routing — the rail-selection
      engine is genuinely exercised by live traffic, not dead code
      (2026-09-02)

### Dataset — is it real and does it match the infra?
- [x] **RECONCILED 2026-09-02, and it's worse than the flag implied.**
      This item was actually already resolved once, in README.md's own
      "v48" entry (2026-09-02, earlier this same day per timestamps) --
      0.297 (30/101) confirmed as the real number two independent ways,
      0.406/0.446/0.356 declared "never actually reproducible." That
      resolution was never reflected back into this checklist, which is
      why it looked open. Re-verified fresh this session, found something
      bigger: **the paper's own headline held-out result (0.60 AC@1,
      `paper/paper.tex` Section~\ref{sec:eval}) is not just stale, it is
      now provably unreproducible.** Re-ran `eval_harness.py`'s exact
      original held-out slice (incidents 17:42, sorted by injection_time,
      the literal window the paper's table was computed from) against the
      current checked-in code: `payment_aware_rca`, `loudest_metric_baseline`,
      and `graph_topology_baseline` all return byte-identical results
      (0.12 AC@1, n=25, same CI). Root cause: `metrics.csv`'s earliest
      timestamp is 2026-08-29 17:48:30 -- the original held-out window's
      incidents occurred 2026-08-27 14:47-16:33, two full days earlier.
      There is no metrics evidence for that window anymore. This lines up
      exactly with Elasticsearch's own retention floor (`min_ts`
      2026-08-29T17:48:22Z, checked earlier this session) and the
      documented full-machine-reboot recovery -- the underlying evidence
      was wiped and cannot be regenerated. **The paper's 0.60 vs
      0.44/0.48 headline claim cannot be cited going forward.**
      The only real, currently-reproducible number: on the full current
      143-incident dataset (`--dev-count 17`, held-out n=126),
      `payment_aware_rca` AC@1 = **0.357** (95% CI 0.279-0.444) --
      **statistically tied with `loudest_metric_baseline`** (also 0.357,
      McNemar p=1.0, 14 discordant pairs each way). Only clears
      significance against `random_baseline` (p=0.0018). Paper's
      Evaluation section needs rewriting around this, not the old table.
- [ ] Confirm `output_live/incidents.csv` root_service labels are ACTUALLY
      what the injector triggered (spot-check a handful against
      `live_fault_injector.py`'s own trigger call, not just the CSV)
- [ ] Confirm the 8 AML_HOLD incidents with zero `aml_state=HOLD`
      payments in-window (found 2026-09-02,
      `data-generation/MANUAL_101_CASE_REVIEW.md`) — root-cause this,
      it's currently just flagged
- [ ] Confirm dataset scale/composition is adequate for a published
      benchmark (currently 101 clean + 42 stale = 143; is 101 enough,
      does the user want more incidents generated before publishing)

### Known bugs flagged, not yet fixed (from manual review,
`MANUAL_101_CASE_REVIEW.md`)
- [FLAG] Decisive stall override can fire on a single payment (e.g. 1-of-5,
  20%) and beat a genuine large z-score spike (z=4.02 case,
  `LIVE-7e49d55f`) — needs a min-count gate or a strong-telemetry
  carve-out. Do not fix silently — this is a method-logic change, flag
  and let it be decided, same as the pattern already established this
  session for the two prior decisive-override bugs.

## Explicitly out of scope for this phase

- Tuning `payment_aware_rca`'s thresholds/logic (beyond the one flagged
  bug above, which needs a decision, not a silent fix)
- Publishing anything to GitHub yet
- Full-scale RCA method scoring against every incident (Phase 1 below was
  a 37-case discrimination test, not a comprehensive eval)

## Phase 1 — baseline RCA discrimination test (2026-09-02, by direct instruction)

Goal: before investing further in scale, does the current 37-case gold set
actually contain enough causal signal to discriminate between RCA methods
at all? Full harness in `data-generation/eval_baseline_rca.py` +
`rebuild_reports.py`, results in `data-generation/BASELINE_EVAL_RESULTS.md`
and `ENSEMBLE_EVAL_RESULTS.md`. Ground truth never modified.

**4 methods, same evidence given to all LLM methods** (heuristic funnel-
drop detector / `qwen3.5:4b` SLM via local Ollama / `openai/gpt-oss-20b`
via NVIDIA NIM / `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` via NVIDIA
NIM). Evidence = live ES re-query (injection_time/duration from each gold
case, not the deleted `_pending_` bundles) + funnel counts + witness quote.

**Headline finding — the dataset does NOT yet discriminate on reasoning
difficulty, only on model capability**: AC@1 was heuristic 90.9%, SLM
66.7-69.7%, large 87.9%, nemotron 90.9%. The zero-reasoning rule-based
heuristic ties or beats every LLM on 8 of 9 fault types — because those
fault types are all single-service full crashes producing a funnel-count
cliff a threshold catches trivially. SLM genuinely underperforms on
cascade/confound types (real, replicated capability gap) — that part of
the discrimination is real. The rest is not: no case in the dataset has
ever required weighing genuinely conflicting evidence, because the two
`confounded` fault types were found to be **not actually engineered as
confounds** — `SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND` and
`VALIDATION_SLOWDOWN_GATEWAY_CONFOUND` both called the exact same generic
`trigger_crash()` as every non-confound fault. The misleading secondary
symptom was never engineered, only hoped for, and never once manifested
across 8 reps this session.

**Hallucination vs abstention (evidence-free cases)**: originally all 4
methods hallucinated a confident wrong answer on all 4 evidence-free
cases, zero correct abstentions. Added an explicit `insufficient_evidence`
field to the task schema + gave the heuristic the same option (abstain
when no funnel stage shows >30% drop). After the fix: SLM 1/4, large 2/4,
nemotron 2/4 correct abstentions — real improvement, at a real cost (SLM's
overall AC@1 dropped 69.7%→66.7% since it now sometimes abstains on
confirmed cases it previously got right by guessing — an honest trade-off,
not a regression to hide).

**`AML_HOLD` — 0% AC@1 across all 4 methods, investigated, not just
flagged**: first hypothesis (retrieval failure — the real signal,
`AML_SANCTIONS_HIT`, was being crowded out of the compact evidence by a
per-service sample cap tuned for crash faults) was real and fixed
(added the AML event keywords to the signal filter, verified the evidence
now genuinely contains `AML_SANCTIONS_HIT`/`AML_HOLD` lines). Did not fix
the 0% score. Second finding: this is a **task-framing mismatch, not a
retrieval bug** — `AML_HOLD` isn't a failure to localize, it's the system
working correctly (a real sanctions match), so "find the root cause of
this incident" is the wrong question for this fault type. Needs its own
question framing in any future version, not a data fix.

**Confound engineering — implemented and being verified live**: added
`trigger_crash_with_gateway_decoy()` to `live_fault_injector.py`
(`VALIDATION_SLOWDOWN_GATEWAY_CONFOUND` only, mechanism
`crash_with_gateway_decoy`) — fires a real burst of invalid-currency
payments at gateway during the real validation-enrichment outage.
Gateway's `GlobalExceptionHandler` was silently swallowing all validation
failures (no structured log at all); added a real `PAYMENT_REJECTED`
log line reusing Logstash's existing grok-whitelisted eventType token (no
pipeline changes needed) — confirmed real 400 + real ES-visible
`eventType: PAYMENT_REJECTED` end-to-end.

First live test found the decoy signal was real but drowned 78-to-13 by
an unrelated, previously-invisible bug the new logging happened to expose:
**13 of 27 `CLEAN_ENTITIES` (48%) had invalid IBAN checksums** — real
`iban4j` failures, not a minority as an old code comment claimed. Fixed
all 13 (+ 3 in `SDN_ENTITIES`, 1 in `HIGH_RISK_CREDITORS`) by recomputing
correct check digits, verified 0/53 IBANs invalid. Second bug found while
re-verifying: the traffic generator's `CHANNELS` list included
`CHAPS`/`TARGET2`, which don't exist in gateway's `PaymentChannel` enum
(only `SWIFT/SEPA/FEDWIRE/FASTER_PAYMENTS/INTERNAL`) — 10% of traffic was
silently failing Jackson enum deserialization before validation even ran.
Removed both from `batch_realistic_v4.py`'s `CHANNELS`. Verified: 40/40
payments accepted post-fix (was 0/40 fully clean before either fix, worst
case 6/40 rejected mid-fix). **This means every gold case collected this
entire session had a large, silently-reduced real payment volume — not
just noisier evidence, less actual traffic than intended, the whole time.**
Confound decoy retested with clean traffic (`LIVE-3cf078b4`): gateway
`PAYMENT_REJECTED` dropped 91→3, and all 3 verified `fields=[currency]` --
100% genuine decoy, zero IBAN noise left. Ran the full blind-investigation
gold-case methodology on it (38th gold case). **Honest result: still
correctly resolved.** gateway's decoy rejections were real but never
accompanied by a `HEALTH_CHECK_FAILED` or restart -- it stayed healthy and
kept serving 24/27 requests throughout, which is a clean, real
distinguishing signal from validation-enrichment's independently-witnessed
outage. The confound mechanism genuinely works now (produces real,
attributable, clean decoy evidence -- verified, not assumed) but has not
yet produced a rep that actually misleads a careful investigation. Open
question, not yet answered: would a stronger/longer decoy burst (more than
3 landed sends -- `decoy_sent` was being computed but silently dropped
before the CSV write, same bug class as the earlier `confirmed`/
`kafka_lag` fields; now fixed and persisted going forward) change that.
Not chased further this session -- flagging as the natural next
experiment rather than continuing to iterate blind.

**Session total: 39 gold cases** (35 confirmed matching ground truth via
blind investigation, 4 confirmed genuinely evidence-free).

## Push toward 101 gold cases (2026-09-02, ongoing)

Target set at 101 (10/fault-type) after discussion of realistic infra
cost (~8-9 min/case, fixed 500s witness window regardless of fault
duration). Added 3 new fault types from real infra dependency mapping
(grep RedisTemplate/MongoRepository/CassandraRepository across every
service): `REDIS_OUTAGE`, `MONGODB_OUTAGE`, `CASSANDRA_OUTAGE` --
13 fault types total now. All 3 validated live:
- **REDIS_OUTAGE**: real, replicated null result at two durations
  (20s and 60s) -- system genuinely absorbs redis outages with zero
  detectable evidence on any tested path (likely fail-open behavior).
  Not a mechanism bug, a real resilience finding.
- **MONGODB_OUTAGE**: real, replicated positive result (2/2 reps) --
  both validation-enrichment AND aml-compliance independently fail
  with the identical "connecting to server localhost:27017" signature.
  Corrected the original code-grep dependency map: aml-compliance also
  has a direct MongoDB connection, not just validation-enrichment.
- **CASSANDRA_OUTAGE**: real, confirmed (1/1) -- clean single-dependency
  case, only audit affected, direct port-9042 evidence, no funnel-wide
  stall (audit consumes async via Kafka). Matched the original
  dependency map exactly.

**Real bug found and fixed via LIVE-125bb06d (AML_HOLD)**: the ES
evidence query's `size` cap (300) can silently truncate evidence under
real background traffic -- this specific case's 20s window actually
contained **1379 events**, and the one AML_SANCTIONS_HIT/AML_HOLD pair
that mattered was pushed past the first 300 by background traffic
density (758 payments/run). Investigation initially found "zero
evidence" despite the injector's own log claiming `confirmed_held=true`
-- rather than accept a false evidence-free result, checked the named
payment_id directly in ES and found the real evidence existed but was
truncated. Fixed: `size` raised 300->3000 in both `inject_gold_case.py`
and `eval_baseline_rca.py`. **Open item, not yet done**: spot-check
whether any earlier-collected gold case (especially ones with sparse
aml-compliance/validation-enrichment representation) was also silently
truncated by this cap before the fix.

**Operational note**: one injection (second CASSANDRA_OUTAGE rep) was
killed mid-fault by the harness, leaving cassandra stopped and `audit`
unhealthy until manually restarted -- recovered cleanly, no data loss,
but confirms these live-injection loops need a live human/agent
watching for exactly this failure mode, not just fire-and-forget.

46 gold cases as of this entry (40 confirmed, 6 evidence-free), still
running toward 101.

## Real payment_aware_rca fixes + a major structural finding (2026-09-02)

Per direct instruction to genuinely improve the paper's numbers (not
tune to the held-out set): two real, principled fixes, plus a bigger
finding that explains why a third obvious "fix" doesn't actually help.

**Fix 1 — min-count gate on the decisive override** (`MIN_DECISIVE_COUNT
= 2` in `eval_harness.py`): a single payment out of 5 (20%) was firing
the decisive override and beating a genuine large z-score spike
(flagged, not yet fixed, from `LIVE-7e49d55f`). Fixed by requiring at
least 2 corroborating payments before a fraction counts as decisive.
Honest result: made the headline number slightly *worse* (0.357->0.333
on the then-current held-out set) — reported as-is, not reverted to
keep a better-looking number.

**Fix 2 — much bigger: the entire pre-2026-08-29 incident batch (42 of
143 incidents) has zero real metrics data**, same root cause as the
paper's headline-number disaster above (the reboot). Every one of these
42 "stale" incidents silently defaults every method to ranking
`gateway` first (tie-break on all-zero z-scores, `gateway` being first
in `FULL_PIPELINE_ORDER`), contaminating not just the original 25-case
held-out set but the *entire* `--dev-count 17` split used for every
number in this file and the paper -- the "dev set" was drawing
literally 100% from dead data too. **The only correct evaluation
protocol going forward: filter to `injection_time >= 2026-08-29`
(101 "clean" incidents) BEFORE any dev/held-out split.** On this
properly-filtered data (dev=20/held-out=81): `payment_aware_rca` =
**0.370** (95% CI 0.273-0.479), `loudest_metric_baseline` = 0.358 (tied,
McNemar p=1.0), `graph_topology_baseline` = 0.321 (ahead but not
significant, p=0.34, n_disc=10), `random_baseline` = 0.148 (significant,
p=0.0029). Modest, honest, and — critically — actually reproducible.

**The bigger finding, from tracing why `settlement`/`aml-compliance`
incidents specifically misdiagnose (confusion matrix showed
settlement correct only 2/38 times pre-filter, mispredicted as
`gateway`/`validation-enrichment` almost 50/50)**: quantified across
all 101 clean incidents by root service, the generalized stall-fallback
signal (`stalled_service`, used when no payment-domain fraction fires --
i.e. every crash-based fault) points to `validation-enrichment` as the
"first stalled stage" **27/30 times for settlement-root incidents (90%),
8/8 for routing-execution-root (100%), 23/30 for aml-compliance-root
(77%), even 9/14 for gateway-root (64%)** -- validation-enrichment is a
real, universal backpressure chokepoint in this system's actual
threading/queueing architecture: when *any* downstream service crashes,
resource exhaustion propagates upstream and payments visibly stall at
validation-enrichment first, regardless of where the real root is. This
is not a data bug -- verified via real per-payment stage-completion
timestamps, not assumed. Tested the obvious fix (disable the stall
fallback entirely, `disable_stall=True`): made the overall number worse
(0.370->0.321), because it makes `payment_aware_rca` collapse to being
byte-identical to `graph_topology_baseline` on every family -- the
signal is net-positive despite the chokepoint bias, so removing it
outright is the wrong call (unlike the two frac features correctly
removed on 2026-09-01, which were net-negative). A real fix would need
to distinguish *which* service's degradation started **first**
chronologically from which one has the **most** stalled payments (the
downstream root should degrade before the upstream chokepoint does) --
a genuine engineering task, not implemented this session.

**Recommendation**: this chokepoint characterization is a real,
quantified, honestly-obtained finding about a real system's failure
propagation behavior -- arguably a stronger and more defensible paper
contribution than the original decisive-override story, since it's
reproducible, mechanistically explained, and independently verifiable
from raw payment timestamps rather than resting on a single held-out
accuracy number.
