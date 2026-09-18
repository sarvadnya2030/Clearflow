# GEAR-RCA — full system description, from scratch

This is a ground-up description of what was actually built, written so that a diagram
(hand-drawn, TikZ, or AI-image-generated) can be constructed from real understanding of
the mechanism rather than from a compressed prompt. Every claim here traces to a real
file, a real script, or a real measured number — nothing is illustrative filler.

---

## 1. The platform being investigated

A live, running 8-service payments processing pipeline, not a diagram and not a demo app:

| Service | Port | Role |
|---|---|---|
| gateway | 8080 | Entry point. Accepts payments, does idempotency checking, issues correlation IDs. |
| fraud-scoring | 8081 | Scores incoming payments for fraud risk (LightGBM model). |
| validation-enrichment | 8082 | Validates payment fields, enriches with reference data. Backed by MongoDB. |
| aml-compliance | 8083 | Screens payments against sanctions lists (AML). Can place a payment on `HOLD`. |
| routing-execution | 8084 | Selects a payment rail and executes routing/liquidity reservation. |
| settlement | 8085 | Finalizes the payment. Backed by Cassandra (via ClickHouse-fronted repository) for settlement records. |
| audit | 8086 | Records an immutable audit trail of every payment's lifecycle. Also Cassandra-backed. |
| mcp-readonly-gateway | 8087 | Read-only MCP-style API surface the RCA agent's tools call into. |

Underlying infrastructure: Spring Boot 3.3.2 / Java 21 for every service, Kafka for
event-driven inter-service messaging (9 topics), ActiveMQ Artemis for JMS coordination,
Elasticsearch for centralized logging (ELK-style ingestion), MongoDB (validation-enrichment's
datastore), Cassandra (settlement + audit datastore), Redis (shared cache / idempotency
keys, used by all 8 services).

While the benchmark runs, a background traffic generator sends real payments through this
pipeline continuously at roughly 3 payments/second, mixing clean transactions with
higher-risk scenario types (salary payments, high-risk-corridor payments, structuring
patterns) so the system is never idle when a fault is injected into it.

## 2. How faults are actually injected

Five distinct real trigger mechanisms (`live_fault_injector.py`), not a simulated failure
flag in any case:

1. **Process kill/restart** — an AdminController endpoint really stops and restarts the
   JVM process of one of 6 killable services (aml-compliance, routing-execution,
   settlement, validation-enrichment, audit, fraud-scoring). Duration: 20–30 seconds
   depending on fault family, then the process is restarted and health-polled back to UP.
2. **Container stop/start** — `docker stop` / `docker start` on a shared infrastructure
   container (Redis, MongoDB, or Cassandra) rather than an application service. Duration:
   60 seconds (Cassandra gets a longer 90-second recovery window because it's slow to
   restart on this host). Recovery is confirmed via `docker inspect`'s own HEALTHCHECK
   status, not assumed the instant `docker start` returns.
3. **Crash with a real gateway decoy** — the same process-kill mechanism as (1), but with a
   concurrent burst of genuinely invalid-currency payments fired at the gateway during the
   outage window. These get real HTTP 400 rejections from the gateway's own `@Valid`
   validation — a real confounding signal on a service that is *not* the root cause,
   engineered rather than asserted.
4. **Idempotency collision** — a real payment is submitted and accepted (HTTP 202), then the
   identical payload is resubmitted 14 more times in a burst. The gateway's real
   idempotency-key logic returns genuine HTTP 409 duplicate-rejection responses.
5. **AML sanctions hold** — a payment is built from an entity drawn from a known
   sanctions-list-matching pool (SDN-style names) and submitted for real. The injector
   polls the live compliance-holds API and only accepts the case as a confirmed `AML_HOLD`
   incident once a real `HELD` status is observed for that payment ID (not every
   SDN-shaped payload triggers a match, so this can take up to 8 tries).

Every injected fault runs concurrently with an **independent health-witness process** that
polls service health with no foreknowledge of what was just injected — this is what lets
ground truth be "confirmed" rather than self-asserted by the injector.

A 240-second cooldown separates incidents so one incident's crash effects (e.g. Kafka
consumer-group lag) don't contaminate the next incident's evidence baseline.

**Result: 110 gold cases.** 97 are `confirmed` (independently verifiable evidence exists
tying the fault to its root cause) and are used for accuracy scoring. The remaining 13 are
evidence-free by design (the injected fault produced no discoverable symptom under current
telemetry) and are kept to test correct abstention rather than accuracy.

## 3. The investigating agent

A multi-round (up to 15 rounds) tool-calling loop driving `gpt-oss-20b` via the NVIDIA NIM
API (base URL `https://integrate.api.nvidia.com/v1`), `temperature=0`. The loop is given a
system prompt describing the incident (fault-type-agnostic — the agent is never told what
kind of fault occurred) and repeatedly lets the model choose to call a tool or answer, until
it either produces a final "ROOT CAUSE: <service>" answer or exhausts its round budget (at
which point a forced final-answer call is made with whatever evidence has been gathered).

### 3.1 The seven tools

1. **`get_deterministic_signal`** — a cheap, fast, rule-based funnel-stall heuristic. Called
   first, explicitly labeled to the model as fallible (i.e. "this is a guess, verify it").
2. **`search_live_elasticsearch`** — queries the real Elasticsearch cluster for a
   service/keyword/time-window combination and returns the full result set, not a
   pre-filtered sample. This is the agent's primary raw-evidence tool, used the way a human
   on-call engineer would use Kibana.
3. **`query_knowledge_graph`** — queries a real code-dependency graph (1,294 nodes) built by
   static AST parsing plus semantic extraction over the actual Java service source code
   (not a synthetic or hand-drawn topology). Given a term (e.g. `"settlement"`), it returns
   the real classes/consumers/repositories that service depends on, extracted from the
   codebase itself. Queried mid-investigation against whichever services the evidence
   gathered so far implicates — never consulted once as a precomputed ranking fixed for the
   whole incident.
4. **`get_service_dependencies`** — a live service-dependency endpoint (distinct from the
   code graph; this is the runtime/infra dependency view rather than the code-level view).
5. **Container-health check** — calls real `docker inspect` against infrastructure
   containers, not a mocked health status.
6. **Cross-service payment-trace reconstruction** — given a correlation ID, pulls every log
   line across all 8 services for that one payment, sorted by time, into a single causal
   timeline (the way a distributed tracer like Jaeger would show one request's journey).
7. **`recall_similar_past_incidents`** — the memory-recall tool (see Section 4). Present
   only when the memory-enabled flag is on; absent from the tool list entirely in the
   memory-off ablation arm.

### 3.2 Structural enforcement

Early versions of the agent had an instruction in the system prompt marked "MANDATORY"
telling the model it must call the graph-query and memory-recall tools before answering.
This was routinely ignored once the model was under round-budget pressure — it would spend
its whole budget on log search and answer without ever touching the graph or memory. The
fix: the loop itself tracks, in code, whether each required tool has actually been called.
If the model tries to answer (or exhausts its round budget) without having called a
required tool, the *next* API call is made with that tool forced via the API's own
`tool_choice` parameter — not repeated as a text instruction, but structurally guaranteed
by how the call is made.

## 4. The three-tier memory

**Tier 1 — known issues.** A small, static, curated list of confirmed recurring noise
sources unrelated to the fault being diagnosed. Currently one entry: a persistent
background error on the settlement service that twice misled independent human
investigations before it was documented. This tier is hand-written, not learned, and never
changes based on new cases.

**Tier 2 — episodic case recall.** A SQLite database with full-text search (FTS5) over the
real evidence text of every past investigated case. When the agent's evidence-gathering
surfaces a distinctive log signature, it can call `recall_similar_past_incidents` to query
this store and get back matching past cases along with their *confirmed* root causes (not
the agent's own past guesses — the verified gold label). Because every gold case is also
pre-seeded into this same store, a naive implementation would let the agent retrieve its
own answer key during evaluation; this was found to actually happen (one case returned as
its own top match) and fixed with an explicit exclusion of the current incident's own
identifier from every recall query (leave-one-out), then re-verified.

**Tier 3 — distilled strategy.** Following the schema used by Google's ReasoningBank
(title / one-sentence description / 3–5 sentences of concrete guidance), each fault type's
accumulated case history — both successful *and* failed past investigations, explicitly
labeled as which — is distilled into one reusable strategy. This strategy text is injected
directly into the system prompt at the start of the investigation, not offered as something
the model has to choose to call. Coverage is 11 of 13 fault types; two fault types
(`REDIS_OUTAGE`, `IDEMPOTENCY_COLLISION_STORM`) have too few confirmed cases (judged unsafe
to generalize a strategy from) and get no Tier 3 content at all — and this is the single
clearest piece of evidence in the whole study that Tier 3, not the tool set alone, is what
drives memory's measured benefit: `REDIS_OUTAGE` scores 0% even with memory nominally "on."

A real data-integrity bug was found and fixed in this system: the case-memory store's
uniqueness constraint originally keyed on incident identifier alone, so an agent's own
investigation of a case already pre-seeded in memory silently failed to persist. Before this
was caught (triggered by a collaborator asking how memory storage actually worked, not by
an automated check), only 1 of 28 completed agentic investigations had actually been
recorded. Fixed with a composite (incident identifier, source) key; all accuracy numbers in
the paper are unaffected because predictions come from live tool calls against real
evidence, not from memory lookup, but one earlier causal claim about memory "compounding"
within a single run was retracted once this was found.

## 5. What gets measured, and how

**Literal AC@1** — does the agent's predicted root-cause service exactly match the gold
label.

**Fair-credit AC@1** — a prediction of `audit` or `settlement` is also credited correct when
the gold label is the underlying datastore `cassandra`, because build-manifest verification
confirms those are the *only* two services with a real Cassandra dependency — naming the
affected service is diagnosing the real failure propagation correctly even without naming
the datastore itself. This rule is not extended to other datastores (e.g. MongoDB) without
equivalent verification.

**The controlled ablation** — one boolean flag disables all three memory tiers and removes
`recall_similar_past_incidents` from the tool list entirely, leaving the graph, live
telemetry, trace reconstruction, and structural enforcement all identical between arms.
This configuration (graph-guided exploration, tool use, no cross-incident memory) is
architecturally the closest reimplementation of GALA+'s described methodology available,
since GALA+'s own code is not public.

## 6. The headline numbers (97 confirmed cases)

| Condition | Literal AC@1 | Fair-credit AC@1 |
|---|---|---|
| Memory ON (full system) | 78.4% (76/97) | 83.5% (81/97) |
| Memory OFF (ablation) | 66.0% (64/97) | 74.2% (72/97) |
| **Effect** | **+12.4 points** | **+9.3 points** |

On the 11 historically hardest cases (every method tried before this system scored 0% on
these): memory ON reaches 45.5% literal / 81.8% fair-credit; memory OFF reaches 27.3% /
72.7% — a +18.2 / +9.1 point effect.

## 7. What this all implies for a diagram

A faithful diagram of this system has exactly three layers that matter, and the
relationship between them is the whole point of the paper:

1. **The live platform** is the thing being investigated — it sits *outside* the agent, and
   evidence flows from it into the agent's tools, never the reverse.
2. **The LLM tool-calling loop** is the only component that touches both the platform (via
   the seven tools) and the memory (via the system prompt and the recall tool). It is the
   single point of integration, not a peer alongside the graph or the memory.
3. **The three memory tiers** are not one blob — they are ordered, structurally distinct,
   and individually falsifiable (which is exactly how the paper isolates Tier 3 as the
   locus of memory's effect). A diagram that draws "memory" as one box loses the paper's
   actual finding.

The code graph deserves its own visual weight distinct from the other six tools, because
it's queried *live* against evidence-implicated services rather than consulted once — a
diagram that draws it as just one icon in a row of seven equal icons undersells that it's
structurally different from, say, a container-health check.

## 8. The three diagrams actually in the paper

The paper ships three figures, built as native TikZ/pgfplots (so they compile as vector
graphics inside the LaTeX source, not embedded images). Each one answers a different
question a reader would otherwise have to reconstruct from prose alone.

### Figure 1 — System Architecture (`fig:architecture`, Section III)

**Question it answers:** what is GEAR-RCA, mechanically, end to end?

**What it shows, top to bottom:**
- A single wide gray box at the top: the live 8-service payments platform itself (named
  services and datastores, plus the ~3 payments/sec traffic rate), representing the
  *environment*, not the agent.
- A dashed-border cluster of seven small blue boxes directly below it, labeled "Seven
  tools": the funnel-stall heuristic, live Elasticsearch, the code graph, the
  service-dependency endpoint, container health, trace reconstruction, and memory recall.
  Two arrows connect this cluster to the platform above it (down = "evidence", up = "tool
  calls" from the loop below), and one arrow down to the loop (labeled "tool results").
- A large green box in the middle: the LLM tool-calling loop itself
  (`gpt-oss-20b`, up to 15 rounds), with its structural-enforcement guarantee written
  directly inside the box as a sub-line, since that's a property of the loop, not a
  separate component.
- A dashed-border cluster of three small orange boxes below the loop, labeled "Three-tier
  memory": Tier 1, Tier 2, Tier 3 side by side, with a single arrow up into the loop
  labeled "system prompt" (deliberately *one* arrow, not three, because all three tiers'
  content lands in the same place — the system prompt — regardless of how differently each
  tier is produced).
- A small red box to the right of the loop: "Root-cause prediction", the loop's output.

**The one idea the figure has to get across:** the LLM loop is the *only* component that
touches both the live platform (via seven tools) and the memory (via the system prompt) —
everything else is a leaf. If a viewer takes away nothing else, they should see that the
loop is the hub, not one box among equals.

### Figure 2 — Graph and Memory Detail (`fig:graphmem`, Section III-A)

**Question it answers:** the architecture figure treats "code graph" and "three-tier
memory" as single boxes — what does each one actually look like inside?

**What it shows, as two side-by-side halves:**
- *Left half, "Code-dependency graph (1,294 nodes)":* a worked example, not an abstract
  icon. A monospace box `query_knowledge_graph("settlement")` points to a node
  `SettlementService`, which has three real outgoing edges to `ClickHouseRepository`,
  `SettlementEventConsumer`, and `LiquidityReservationService` — an actual small subgraph
  of what a real query returns, with a caption underneath: "real dependency edges from
  static AST parsing, not a guess." This is deliberately concrete (real class names from
  the actual codebase) rather than a generic "graph icon," because the paper's whole point
  about the graph is that it is *real*, not illustrative.
- *Right half, "Three-tier memory":* the three tiers stacked vertically as wide boxes, each
  with its actual mechanism spelled out inside the box rather than just a tier number —
  Tier 1's static note, Tier 2's "query → SQLite FTS5 → matching confirmed cases
  (leave-one-out)", Tier 3's "accumulated cases (win and fail) → one distilled strategy" —
  connected by simple top-to-bottom arrows showing they're consulted/injected in that
  order.
- *Bottom, spanning both halves:* a single green "Agent system prompt / context for this
  round" box, with one arrow arriving from the graph side and one from the memory side —
  the same convergence point as Figure 1, but now the reader has seen what's actually
  flowing into it from each side.

**The one idea the figure has to get across:** the graph and the memory are structured
completely differently (a live queryable graph vs. a three-stage injection pipeline) but
end up in the same place. This is also where a reader sees, concretely, why leave-one-out
matters (Tier 2's label says it explicitly) and why Tier 3 is called "distilled" rather than
"stored" (its label shows the win/fail accumulation happening before injection).

### Figure 3 — Memory On/Off Ablation (`fig:ablation`, Section V-B)

**Question it answers:** does memory actually help, and by how much, under every scoring
convention and every evaluation subset the paper reports?

**What it shows:** a grouped bar chart, not a table restated as a picture. Four x-axis
groups — Memory ON (11 hardest), Memory OFF (11 hardest), Memory ON (full 97), Memory OFF
(full 97) — each with two bars (Literal in blue, Fair-credit in orange), value labels
printed directly above each bar. This is the only one of the three figures that is
data-driven rather than schematic, built with `pgfplots` directly from the same numbers in
Table III so the figure and the table can never drift apart.

**The one idea the figure has to get across:** memory helps in *every* condition shown (all
four ON bars sit above their matched OFF bar), and the visual gap size communicates at a
glance what the prose spends a paragraph explaining — that the effect is real but not
uniform, larger under literal scoring on the hardest cases than anywhere else.

**Note for anyone regenerating these as AI-generated images instead of vector diagrams:**
Figures 1 and 2 are schematic and safe to regenerate as illustrations (see the prompts
already written for them). Figure 3 should **not** be regenerated by an image model — bar
charts are exactly the case where generative image models reliably get numeric heights
wrong, and this figure's entire job is to be numerically trustworthy. Keep Figure 3 as a
real rendered chart (the existing `pgfplots` code, or the same eight numbers plotted in any
real charting tool) and only re-skin Figures 1 and 2.

---

## 9. Session update — three module fixes, tested honestly, not assumed

Everything below was built and tested *after* the original paper draft was complete, as a
direct follow-on to the question "is the graph tool being fully used?" Same standing rule
as everywhere else in this project: inspect the real output before trusting a component,
measure a change against a real baseline before claiming it helps.

### 9.1 The three fixes

**Graph tool (`query_knowledge_graph` → hybrid version).** Two real, confirmed problems in
the original: (1) substring-only matching returns nothing for a term that doesn't literally
appear in a node label (e.g. "duplicate submission" vs. `IdempotencyService`); (2) results
were capped at 5 matched nodes / 8 edges each, silently truncating the real fan-out of any
shared dependency (Redis, Cassandra) touched by many classes. Fixed by unioning substring
matches with local sentence-embedding vector search (`all-MiniLM-L6-v2`, fully offline, no
API cost), raising the caps (8 nodes / 15 edges), adding a second traversal hop, and
sorting edges so real AST-extracted ones always win over lower-confidence LLM-inferred ones
under the cap. A further extension surfaces each matched node's real community label
(graphify already computes 101 of these via clustering — e.g. "AML Screening Core" — but
the original tool never used them) plus 2–3 co-located sibling classes. 76 of the 101
communities never got a real LLM-generated name (still just "Community N"); the fix falls
back to listing siblings without the useless number in that case, rather than showing fake
information that looks real.

**Elasticsearch tool (`search_live_elasticsearch` → dual-ended fetch).** One real, confirmed
bug: the tool sorted results most-recent-first and kept only the top 15. In a cascading
failure, the actual trigger event (usually the *earliest* one) can get buried under later
downstream noise and never appear in the 15 shown. Verified directly on a real historical
`DB_TIMEOUT` incident (`LIVE-cd1f76ee`): the original tool's window contained only repeated
WARN spam from four minutes after injection; the real trigger line,
`HEALTH_CHECK_FAILED service=settlement consecutiveFailures=1`, logged one second after the
first real error, never appeared at all. A second function in the same codebase
(`_fetch_sample_logs_for_agentic`, used to build the base evidence sample) already sorted
ascending specifically to avoid this — its own code comment explains why. The live-ES tool,
which the agent's own prompt calls the *more* authoritative source, had the worse
convention. Fixed by fetching both the earliest and latest events in the window instead of
one arbitrary slice sorted the wrong way.

**Memory recall (`recall_similar_incidents` → rarity-weighted retrieval).** One real,
confirmed precision bug: the tool OR-joined all query tokens with equal weight. Querying
"ClickHouse connection refused settlement" returned only `REDIS_OUTAGE`/`MONGODB_OUTAGE`
cases — zero Cassandra-related hits — even though a genuinely relevant case
(`LIVE-1a1dcc24`, `SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE`) matches "clickhouse" cleanly on
its own. Root cause, measured directly: "settlement" matches 57 of ~150 stored cases (it's
a service name, near-ubiquitous) while "clickhouse" matches only 10 — the common word's
sheer match volume dominated the distinctive one in bm25 ranking. Fixed by ranking query
tokens by real document frequency and preferring the rarest ones first (AND-style),
falling back to the original OR-all-tokens query only if the selective one returns nothing.
Confirmed it surfaces the previously-invisible relevant case; a documented, real remaining
limitation is that stored `evidence_text` is full agent reasoning transcripts, which can
genuinely co-occur with many services during exploration, so even strict rare-term matching
isn't a complete fix.

### 9.2 Controlled test results (16-case subset: confirmed `CASSANDRA_OUTAGE` +
`MONGODB_OUTAGE`, the two fault types Section V already diagnoses as evidence-resolution-
limited rather than memory-coverage-limited)

| Fix | Literal AC@1 | Fair-credit AC@1 | Case-level pattern |
|---|---|---|---|
| Baseline (original tools) | 37.5% (6/16) | 68.8% (11/16) | — |
| Graph tool (vector search + traversal) | 43.8% (+6.3) | 87.5% (+18.7) | 6 improved, 2 regressed, ~333s/case (slower) |
| Elasticsearch tool (dual-ended fetch) | 50.0% (+12.5) | **100.0% (+31.2)** | improvements only, **zero regressions** |
| Memory recall (rarity-weighted) | not yet benchmarked | not yet benchmarked | confirmed one specific fix, no full run yet |

The Elasticsearch fix is the strongest and cleanest of the three: every case that was
already correct stayed correct, and several previously-missed cases got fixed. The graph
fix is a real net improvement but a genuine trade (it also introduced 2 new mistakes on
cases the original tool had right).

**Efficiency note, a real mistake caught and fixed in-session:** the first attempt at a
full 97-case run for the Elasticsearch fix started from scratch, about to needlessly
re-run all 16 already-tested cases. Caught before much time was lost, killed, merged the
16 known results into the full-run's results file, and restarted — it now correctly skips
those 16 and only runs the remaining 80, saving roughly 80 minutes of redundant runtime.

**What's still running as of this writing:** the Elasticsearch fix's full 97-case run,
unattended, in the background (`run_es_v2_full_benchmark.py`, results in
`es_v2_full_benchmark_results.json`). Projected ~80 more cases at the observed pace. The
remaining 80 cases are mostly fault types that were *already* at 88–100% fair-credit under
the original tools (DB_TIMEOUT, KAFKA_CONSUMER_LAG, NETWORK_LATENCY, AML_HOLD,
CPU_SATURATION, both SETTLEMENT_DB_FAILURE confound types, VALIDATION_SLOWDOWN_GATEWAY_
CONFOUND, AML_SERVICE_DEGRADATION_RETRY_CASCADE) plus the 3 `REDIS_OUTAGE` cases still at
0%. The real question for this run isn't "does it help more" (most of these are near
ceiling already) — it's whether the fix introduces regressions on cases that were already
working, the same way the graph fix did. `REDIS_OUTAGE` is not expected to move: the
ablation already attributes its 0% to a Tier 3 memory-coverage gap (too few cases to
distill a strategy), not to evidence resolution, so a log-retrieval fix shouldn't touch it
— if it does move, that would itself be a notable, worth-flagging surprise.

### 9.3 GALA+ legitimacy check (verified directly, not assumed)

Checked before continuing to build against it as a comparison point: GALA+ (the paper we
reimplement as our memory-off ablation arm) is accepted at **ASE '26** (41st IEEE/ACM
International Conference on Automated Software Engineering, Munich, Oct 2026) — a real,
competitively peer-reviewed top-tier software engineering venue, not a self-published
preprint. The "GALA+" paper (arXiv:2608.08968, Aug 2026) is confirmed to be a real extended
follow-up to an earlier "GALA" preprint (arXiv:2508.12472, Aug 2025) by the same core
author team (Yifang Tian, Yaming Liu, Zichun Chong, Zihang Huang, Hans-Arno Jacobsen, plus
one added author) — a genuine research lineage, not a naming coincidence. Near-zero
citations currently is purely a recency artifact (the conference hasn't happened yet as of
this writing), not a quality signal.

### 9.4 Testing against GALA+'s actual benchmark (OnlineBoutique/TrainTicket) — scoped, not started

Explicitly discussed and deliberately not pursued yet. What it would actually require:
stand up OnlineBoutique (the more tractable of the two — TrainTicket is larger and less
standardized) as a separate environment; build a new code graph for its codebase via
graphify; build a *new* fault injector, since GALA+'s own injection code is not public —
meaning any test would be *our* reconstruction of *their* benchmark, carrying the same
"not a faithful reproduction" caveat this paper already discloses about the reverse
direction (our memory-off arm as a reconstruction of *their* agent); and start GEAR-RCA's
memory cold, with zero case history on that domain. Realistically a multi-session
benchmark-build, not a same-week test. Decision: hold as documented future work rather than
rush a comparison that would still carry the same fundamental caveat on the other foot.

### 9.5 Whether to add harder benchmark cases — deferred, with reasoning

Explicitly discussed and deliberately deferred. The benchmark already has graduated
difficulty (the 11 historically-hardest cases, and three confound fault types that inject a
real decoy signal specifically to confuse the agent). Genuinely *new* difficulty — two
simultaneous unrelated faults, deliberately weak/noisy evidence windows, a fault whose
symptom mimics a different fault type — would be real new benchmark engineering, the same
scope as building the original benchmark, not a quick add. Reasoning for deferring: two real
weaknesses were just found this session (the graph fix's 2 regressions; the ES fix's
remaining 80 cases not yet fully characterized for regressions) that aren't fully understood
yet. Building harder cases before finishing the current full-97 runs would mean designing
new tests against a system whose current failure modes haven't finished being mapped —
testing blind. Recommended next step: let the current runs finish, look at exactly which
cases (if any) regressed, and let *that* real data drive what "harder" should target.
