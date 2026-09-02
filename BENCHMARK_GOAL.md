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
3. **RCA methods + eval**: baselines (`eval_harness.py`) scored against
   the real incidents. **Not started yet this phase — do not run models.**

## Current phase: INFRA + DATASET CORRECTNESS ONLY

Per direct instruction: fix and verify the dataset and infrastructure
first. No model runs, no RCA method changes beyond what's needed to
verify data flow, until this phase is explicitly closed out. Every
iteration should either (a) verify a real, previously-unverified piece of
the infra/dataset pipeline actually works and actually produces real
data, or (b) fix something just found broken, or (c) write down a real,
honest finding — never spin, never mark something verified without
directly checking it this session.

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
- [ ] Reconcile the discrepancy found 2026-09-02: manual review measured
      `payment_aware_rca` at 30/101 (29.7%) on `output_live/`, but
      README's most recent cited number is 0.446. Root-cause which is
      current/correct before citing either number again.
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

- Running any LLM/SLM RCA method
- Tuning `payment_aware_rca`'s thresholds/logic (beyond the one flagged
  bug above, which needs a decision, not a silent fix)
- Publishing anything to GitHub yet
