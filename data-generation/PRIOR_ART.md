# Prior-Art Comparison — RCA Benchmarks vs. ClearFlow-RCA

Compiled 2026-09-02 from primary sources (repo READMEs, dataset cards, task
specs) via a read-only research pass. Where a source was gated/inaccessible,
that is stated explicitly rather than filled in from secondhand claims.

Nine dimensions extracted per project, per the standing research brief:
fault taxonomy, injection mechanism, observable symptoms, telemetry
modalities, causal propagation structure, ground-truth schema, difficulty
definition, case-generation methodology, and whether faults produce
distinguishable evidence -- with particular attention to silent/kill-based
faults, since that is ClearFlow-RCA's own open problem
(`IDEMPOTENCY_COLLISION_STORM`, 0/4 evidence-free as of this session).

---

## 1. OpenRCA (microsoft/OpenRCA, ICLR'25)

- **Fault taxonomy**: none enumerated. Not an injected-fault benchmark --
  it's retrospective RCA over real historical incidents in 3 real production
  systems (Telecom, Bank, Market). "Root cause reason" is free text pulled
  from the underlying incident record, not a fixed category set.
- **Injection mechanism**: n/a (no injection; real incidents already
  occurred).
- **Observable symptoms**: whatever the real incident's telemetry shows --
  not standardized. FAQ explicitly notes network faults are often NOT
  identifiable from KPIs/metrics alone and need trace parent/child latency
  comparison -- an acknowledgment that single-modality evidence can be
  insufficient for some faults.
- **Telemetry modalities**: logs + metrics + traces, per date per system.
  >68GB total across 335 cases.
- **Causal propagation structure**: not documented in what's inspectable.
- **Ground-truth schema** (confirmed from `task_specification.json`): flat
  `{root cause occurrence time, root cause component, root cause reason}`,
  evaluated via 7 partial-credit task variants (time-only, reason-only,
  component-only, and combinations) scored against `record.csv`.
- **Difficulty definition**: implicit in the 7 scoring variants (some ask
  for less than full attribution), not a per-case difficulty label.
- **Case-generation methodology**: n/a -- curated from real incident
  records, not generated.
- **Distinguishable evidence**: not addressed as a general question beyond
  the single-modality-insufficiency note above. Silent-death faults: **not
  discussed**.
- **Data access**: gated behind a Google Drive download; not independently
  inspected beyond the repo's task-spec and FAQ.

**Transfer verdict**: closest domain match (bank/telecom/market) but
architecturally simpler where checkable -- FAQ describes the Bank system as
flat/pod-level with no vertical deployment structure, thinner than our
8-service payment pipeline with real rail routing, liquidity reservation,
and AML screening. Not reproducible (gated data), not a live-injection
benchmark. **Adopt later**: the 7-variant partial-credit scoring rubric,
once ClearFlow-RCA starts scoring actual RCA methods (Phase 3 -- explicitly
not yet).

---

## 2. OpenRCA 2.0 / OpenRCA 2.0-Lite (huggingface: lincyaw/openrca2-lite-v1)

- **Access status**: **HTTP 401 -- gated, could not be independently
  inspected.**
- Everything below this line for this entry is **secondhand, from the
  original research brief, not independently verified** -- treat as
  unconfirmed claims, not fact:
  - Claimed: 635 curated cases; systems = Hotel Reservation, Online
    Boutique, Train Ticket, Sock Shop, Social Network; faults = CPUStress,
    NetworkPartition, NetworkLatency, NetworkLoss, MemoryStress, IOStress,
    **PodFailure, PodKill, ContainerKill** (kill-based faults, if the claim
    is accurate), MysqlCorrupt, RedisCorrupt; stratified by system x fault
    type x root-cause service x propagation-path skeleton; "causal-chain
    verification" performed.
  - If accurate, this would be the one dataset in the survey with kill
    faults AND a documented causal-chain-verification step -- but this
    could not be confirmed from any primary source reachable this session.

**Transfer verdict**: cannot be assessed responsibly without access. Worth
revisiting only if HF auth becomes available -- don't cite its claimed
kill-fault handling as an established fact until verified directly.

---

## 3. RCABench / OpenRCA2-Lite (huggingface: lincyaw/rca)

- **Access status**: **HTTP 401 -- gated, could not be independently
  inspected.**
- Underlying platform traced to `OperationsPAI/rcabench-platform`, now
  archived/moved into `OperationsPAI/aegis` -- its public README confirms a
  Kubernetes/chaos-mesh-based experiment framework for RCA algorithm
  development (consistent with the generic cloud-native chaos taxonomy
  family), but no case-level schema was retrievable from anything public.
- Secondhand-only claims (unverified): 500 cases with
  question/answer/fault_type/fault_category/ground_truth/difficulty fields,
  normal+abnormal logs/metrics/traces, `injection.json` + `causal_graph.json`
  per case, difficulty tied to root-cause-to-alert path length and system
  graph size.

**Transfer verdict**: cannot be assessed responsibly without access. The
difficulty-by-path-length idea (if accurate) is a reasonable pattern to
independently adopt regardless of whether this specific dataset is ever
accessible -- ClearFlow-RCA could define its own difficulty metric the same
way (e.g. number of hops from root service to the funnel-stall observation
point) without needing this dataset itself.

---

## 4. RCAEval (phamquiluan/RCAEval, WWW'25 / ASE'24 / FSE'26)

- **Fault taxonomy** (fully enumerated, confirmed from repo): RE1/RE2 =
  **CPU, MEM, DISK, DELAY, LOSS**, plus **SOCKET** in RE2 -- six
  fault types total, all continuous resource-degradation. RE3 adds 4-5
  "code-level faults" (F1-F5), diagnosed via stack traces/response codes.
  **Zero kill/crash fault types anywhere in the taxonomy.**
- **Injection mechanism**: repeatable fault-service pairs, 3-5 reps each,
  applied as ongoing degradation (not instantaneous).
- **Observable symptoms**: continuous by construction -- a saturated
  CPU/disk/network keeps emitting metrics for the whole fault duration.
- **Telemetry modalities**: RE1 = metrics only (375 cases). RE2 = metrics +
  logs + traces (270 cases). RE3 = multi-source telemetry, code-level
  faults (90 cases).
- **Causal propagation structure**: not a separate artifact; inferred from
  which service's metrics/logs show the injected fault first.
- **Ground-truth schema** (confirmed, from indexed `cases.parquet`):
  `root_cause_service`, `fault`, `injection_time`, telemetry sizes, plus an
  annotated **"root cause indicator"** -- the specific metric/log field that
  actually reveals the fault. This is a genuinely useful schema discipline
  ClearFlow-RCA's gold cases don't currently have a dedicated field for.
- **Difficulty definition**: not explicit; implicitly via fault type
  (resource faults easier, code-level faults in RE3 harder).
- **Case-generation methodology**: systematic sweep across 3 systems
  (Online Boutique, Sock Shop, Train Ticket) x fault types x services, 3-5
  reps per combination.
- **Distinguishable evidence**: guaranteed by construction -- every fault
  type is a continuous degradation, which is inherently self-evidencing.
  **This is itself the answer to the silent-death question**: RCAEval's
  actual methodological position is "don't use kill faults" rather than
  "solve the silent-kill-evidence problem." 735 cases, the largest and most
  rigorous dataset in this survey, and it simply doesn't have our problem
  because it doesn't have our fault class.

**Transfer verdict**: taxonomy doesn't map to financial domain (no CPU/MEM/
DISK/DELAY/LOSS/SOCKET equivalents that matter for payment processing the
way they do for generic microservices), and it can't help with our actual
open problem since it excludes the fault class that causes it. **Adopt**:
the `root_cause_indicator` schema field -- directly portable, independent
of domain.

---

## 5. ops-lite (huggingface: anon-ops/ops-lite)

- **Fault taxonomy** (confirmed): multi-dimensional --
  `chaos_family` in {JVM\*, HTTP\*, Network\*, Pod\*, \*Stress, DNS, Time,
  hybrid_clean, **hybrid_kill**}, with `primary_kind` values like
  PodFailure, NetworkDelay, JVMException, CPUStress. **This is the only
  dataset in the survey that explicitly names and tags kill-based faults as
  a distinct category** (`hybrid_kill`, a "kill-leg flag" in case metadata).
- **Injection mechanism**: chaos-engineering style injection across 3
  systems, tagged by chaos_family/primary_kind/subtype.
- **Observable symptoms**: varies by chaos_family; not separately
  documented per symptom type.
- **Telemetry modalities**: 12 metric tables per case, plus
  injection/causal-graph/env/result/label artifacts (see schema below) --
  metrics-centric, logs/traces presence unclear from the dataset card.
- **Causal propagation structure** (confirmed): `causal_graph.json` per
  case, plus metadata fields `longest_path`, `number of services`, `number
  of edges`, `root_services`.
- **Ground-truth schema** (confirmed): `injection.json`, `causal_graph.json`,
  `env.json`, `result.json`, `label.txt`, 12 metric tables, per case.
- **Difficulty definition** (confirmed): via `longest_path` and graph size
  (edges/services) -- a structural difficulty proxy, not a hand-labeled
  one.
- **Case-generation methodology** (confirmed): "detection validation,
  manifest-driven causal graph reasoning, then curation via greedy
  selection with hard filters excluding cyclic graphs and frontend-only
  injections." Notably: cases are generated, checked for whether they
  actually produce a detectable anomaly signal, and **non-detectable cases
  appear to be filtered out of the final curated set during this step**,
  rather than kept and reported as a finding the way ClearFlow-RCA's
  gold-case ledger keeps and documents the 4 evidence-free
  `IDEMPOTENCY_COLLISION_STORM` cases.
- **Distinguishable evidence for kill faults**: named and tracked as a
  category, but the methodology's answer to non-detectable cases is
  exclusion from the dataset, not documentation of the negative result.
  500 cases total (320 Train Ticket, 142 Hotel Reservation, 38 OTel Demo).

**Transfer verdict**: generic k8s chaos taxonomy, not finance-specific.
**Adopt the methodology, not the data**: (1) explicitly flag which fault
types are kill-mechanism-based in our own catalog metadata (we already have
this implicitly via `mechanism="crash"` in `LIVE_FAULT_CATALOG` -- just
needs surfacing); (2) track a per-fault-type "detection-validated rate" the
way ops-lite's curation pipeline does -- we're already doing this
informally via the manifest's confirmed/evidence-free column; this would
formalize it. **Deliberately reject** ops-lite's filter-out-the-negative-
results approach -- ClearFlow-RCA's standing practice of keeping and
documenting evidence-free cases (per `BENCHMARK_GOAL.md`'s non-trust
protocol) is more honest and should not be abandoned to look more like this
dataset.

---

## 6. STAR (CSTCloudOps/STAR)

- **Fault taxonomy**: not independently enumerated in what was fetched;
  datasets are generated by a local script rather than drawn from a fixed
  taxonomy list.
- **Injection mechanism** (confirmed): **fully synthetic** -- generated by
  `generate_data.py`, a local Python script, explicitly described in the
  repo as "synthetic local experiment data... not raw production
  telemetry." No real process, no real crash, no real anything.
- **Observable symptoms**: synthetic anomaly patterns injected into
  generated time series -- by construction, not emergent from a real
  system.
- **Telemetry modalities**: `metrics.csv`, `logs.csv` (**template counts,
  not raw log text**), `traces.csv` -- note logs here are pre-aggregated
  counts, not actual log lines.
- **Causal propagation structure**: `topology.csv` per dataset, used by the
  method's own Temporal/Spatio/Judge agent architecture over compressed
  "anomaly evidence."
- **Ground-truth schema**: `incidents.csv` + `metadata.json`, per dataset
  (D1/D2/D3).
- **Difficulty definition**: not a per-case field; the method itself is
  scored on Hit@1/3/5, MRR, avg rank, avg latency.
- **Case-generation methodology** (confirmed): synthetic generation via the
  included script -- 3 datasets: D1 e-commerce (46 instances), **D2
  "banking" (41 instances)**, D3 Online-Boutique-style (10 instances).
- **Distinguishable evidence**: not a meaningful question here -- there is
  no real process to die silently, since nothing is real.

**Important correction to the original research brief**: D2 being labeled
"banking" does **not** mean real bank telemetry or bank behavior -- it's a
topology/scenario label applied to synthetic generated time series. This is
materially weaker domain evidence than the original framing implied and
should not be cited as validating ClearFlow-RCA's financial-domain choice
by association.

**Transfer verdict**: low transfer value for fault mechanisms (nothing real
to transfer) or domain validation (synthetic "banking" isn't real banking
behavior). Not worth building on.

---

## 7. LEMMA-RCA (lemma-rca.github.io)

- **Fault taxonomy**: 4 fault types (Product Review, IT), 6 fault types
  (Cloud Computing, IT), 16 faults (SWaT, OT/water treatment), 9 faults
  (WADI, OT/water distribution) -- specific fault names not retrieved from
  the fetched pages (points to the paper/GitHub for detail, not re-fetched
  given time budget).
- **Injection mechanism**: not confirmed from what was fetched.
- **Observable symptoms**: not confirmed.
- **Telemetry modalities** (confirmed): IT datasets = "Multiple" modality;
  OT datasets (SWaT, WADI) = "Single" modality.
- **Causal propagation structure**: not confirmed.
- **Ground-truth schema**: not confirmed.
- **Difficulty definition**: not confirmed.
- **Case-generation methodology**: not confirmed -- appears to be
  real/collected data (765GB Product Review, 540GB Cloud Computing) rather
  than synthetically generated, but this wasn't independently verified.
- **Distinguishable evidence / silent-death**: no information found either
  way.

**Transfer verdict**: interesting mainly as a domain-transfer analogy --
physical/industrial-control processes (water treatment/distribution) are
structurally similar to how a payment rail's state machine propagates
failures, even though the domain itself doesn't transfer. Not directly
actionable without deeper investigation of the actual dataset (this entry
is genuinely incomplete, not just brief -- flag for a dedicated follow-up
if this direction becomes relevant later).

---

## 8. Coroot RCA Lab (coroot/rca-lab)

- **Fault taxonomy**: not a fixed list -- a growing set of named scenarios
  (`sc-01`, `sc-02`, ... `sc-10`+), each a deliberately real failure
  mechanism, not a synthetic fault-injection flag.
- **Injection mechanism** (confirmed, the key differentiator): **real
  mechanisms only, by explicit design principle** -- e.g. a memory-leak
  scenario is a real bad code deploy that actually leaks, reverted by
  rolling back the image, not a toggle inside the app. Uses Chaos Mesh for
  some scenarios (e.g. `sc-02`'s MongoDB primary pod kill) alongside real
  application-level failure modes.
- **Observable symptoms** (confirmed via 2 examples):
  - `sc-02` (MongoDB primary pod killed): replica-set **election event** --
    a brief no-primary window, write failures/spikes, then recovery; the
    killed member's status flips unavailable -> recovering.
  - `sc-10` (OOMKill / exit 137, real memory leak): RSS/heap sawtooth
    pattern **before** the kill, plus downstream gRPC error spikes on
    dependent services **during** the restart.
- **Telemetry modalities**: full OpenTelemetry instrumentation -- traces,
  metrics, logs -- across a real polyglot stack (Python/Go/Java/Node/Rust/
  PHP) with real production-grade DB operators (Postgres/MySQL/MongoDB via
  Percona operators, Kafka via Strimzi).
- **Causal propagation structure**: implicit in the real system's actual
  dependency graph (real service calls, real DB replication topology) --
  not a separately-generated artifact, it emerges from the real
  infrastructure the way ours does.
- **Ground-truth schema** (confirmed): an `expectedSymptoms` list per
  scenario, deliberately **not visible to the tool under test** -- scenario
  and pod naming is kept opaque so a tool can't guess the answer from
  names. **This is the same sealed-label discipline as ClearFlow-RCA's
  `_INJECTOR_CLAIMED_ROOT_DO_NOT_READ_UNTIL_AFTER_YOUR_HYPOTHESIS` field**,
  independently arrived at.
- **Difficulty definition**: not a formal field; implicit in scenario
  complexity.
- **Case-generation methodology**: hand-authored, real-mechanism scenarios,
  not generated at scale -- this is a lab you run and extend, not a static
  dataset you download.
- **Distinguishable evidence for kill faults -- THE answer to our open
  problem**: don't look for evidence from the process that died. Look for
  evidence from everything else that noticed it was gone -- orchestrator/
  control-plane events (replica elections, pod restart events, member
  status transitions) and downstream caller-side symptoms (dependents
  timing out or erroring against the now-dead thing). Both evidence
  channels exist independent of whether the dying process logged anything
  about its own death.

**Transfer verdict**: **highest-value find of the whole survey.** Domain is
generic e-commerce/polyglot microservices, not finance -- but the
methodology (real mechanisms only, opaque grading labels, orchestrator/
downstream evidence for kill faults) transfers directly to ClearFlow-RCA
regardless of domain mismatch, because it's a methodology, not a dataset.

---

## Cross-cutting summary

| Project | Real infra? | Live injection? | Kill faults? | Solves silent-death? | Financial domain? |
|---|---|---|---|---|---|
| OpenRCA | Yes (historical) | No (retrospective) | n/a | Not addressed | Yes (Bank system, but simpler topology, gated data) |
| OpenRCA 2.0-Lite | Unverified | Unverified | Claimed, unverified | Unverified | No |
| RCABench/OpenRCA2-Lite | Unverified | Unverified | Unverified | Unverified | No |
| RCAEval | Yes | Yes | **No, excluded by design** | N/A (avoids the class) | No |
| ops-lite | Yes | Yes | Yes, tagged | Filters out, doesn't solve | No |
| STAR | No (synthetic) | No | n/a | N/A (nothing real) | "Banking" label only, not real |
| LEMMA-RCA | Likely (unconfirmed) | Unconfirmed | Unconfirmed | Unconfirmed | No (IT/OT, not finance) |
| Coroot RCA Lab | Yes | Yes | **Yes** | **Yes -- real answer** | No |
| **ClearFlow-RCA (ours)** | **Yes** | **Yes** | **Yes** | **Open problem, being fixed** | **Yes** |

**The actual finding**: no existing benchmark is simultaneously real-infra,
live-injected, and financial-domain. That combination is ClearFlow-RCA's
genuine differentiator, not a gap to apologize for. The one real
methodological debt is the silent-death evidence problem, and the fix for
it (Coroot's caller/orchestrator-evidence pattern) is identified and
actionable, not a fundamental limitation of the approach.

## Concrete actions taken / planned as a result

1. **Planned**: wire caller-side evidence (from `live_payment_sender.py` /
   traffic generator) into `IDEMPOTENCY_COLLISION_STORM` investigations,
   per Coroot's pattern -- test on the next rep.
2. **Planned**: add a `root_cause_indicator` field to the gold case schema
   (RCAEval pattern), backfilled onto existing cases from their
   `evidence_reviewed` fields.
3. **Planned**: surface `mechanism == "crash"` as a tracked cohort (ops-lite
   pattern), but keep ClearFlow-RCA's practice of documenting evidence-free
   cases rather than filtering them out (explicitly rejecting ops-lite's
   curation approach on this point).
4. **Deferred to Phase 3**: OpenRCA's 7-variant partial-credit scoring
   rubric, once actual RCA methods are being scored against gold cases.
5. **Deferred, needs a user decision**: the scale gap (36 gold cases vs.
   RCAEval's 735 / OpenRCA's 335) -- stay small-and-rigorous vs. invest in
   parallelized injection infrastructure to close the count gap.
