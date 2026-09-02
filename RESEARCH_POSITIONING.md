# ClearFlow-RCA — Research Positioning (2026-09-02)

**Premise, stated bluntly**: we cannot win on scale. RCAEval has hundreds
of cases across multiple published datasets, LEMMA-RCA has 100k+
timestamps, FinRCA-AI-Bench has 1,500 failure cases. Trying to compete on
n is a losing move at 101 incidents on a single infra stack. The only
honest path to "research-worthy" is a genuinely different axis those
benchmarks don't test — not a bigger version of the same test.

## What generic microservice RCA benchmarks structurally cannot test

RCAEval/LEMMA-RCA-style benchmarks are anomaly-localization tasks: given
telemetry, find the statistically anomalous service. That's a
well-studied ML problem (change-point detection, causal graph inference
over metrics). A bigger version of that same task, on a payments stack
instead of an e-commerce demo app, is not a new research contribution --
it's the same task with different service names.

**What's actually different about a regulated financial-payments
system, and testable nowhere else in this space:**

### 1. Domain-semantic disambiguation (business-correct vs. genuinely
anomalous)

A payment landing in `aml_state=HOLD` is not a system malfunction --
it's the compliance system working exactly as designed. A pure
statistical method (z-score, anomaly detection) cannot distinguish
"this looks anomalous because the AML engine correctly caught a
sanctioned counterparty" from "this looks anomalous because
aml-compliance's own process crashed." Telling these apart requires
understanding what an AML hold *means*, not just that its rate spiked.
**This is the actual test of whether an LLM's financial-domain knowledge
adds value over telemetry-only reasoning** -- not "is GPT bigger than
qwen," but "does understanding payment-domain semantics beat pure
statistics on a task where the two are provably confusable." No
existing microservice-RCA benchmark can pose this question because none
of them have payment-domain business states in the evidence at all.

### 2. Calibrated abstention under genuine evidentiary blackout

The "22/101 incidents where every method scores 0%" finding (crash
faults produce zero self-evidence because `kill -9` gives no chance to
log) was treated as a flaw to fix. **Reframe: it's a deliberate,
disclosed evaluation axis.** Real financial incident response has cases
with real evidentiary blackouts -- a real bank's on-call engineer
sometimes genuinely doesn't have enough signal yet and has to say so,
not confidently guess. Almost no RCA benchmark scores a method for
*correctly recognizing* it doesn't have enough evidence, vs. confidently
guessing wrong. This benchmark, uniquely, has a real, disclosed,
labeled subset where the correct behavior is arguably "abstain / flag
low confidence," not "guess service X." Scoring AC@1 alone throws this
away; scoring **abstention quality as a first-class metric** (does a
method know when it doesn't know) is a real, publishable axis nothing
else in this space currently measures.

Practically: `is_confounder`/fault-family labels already partially
capture this; extend with an explicit `has_distinguishing_evidence`
field per incident (derivable from the manual-review audit already
done) and score two things, not one: AC@1 on solvable cases, and
abstention precision/recall on unsolvable ones.

### 3. Tiered evidence access as a controlled variable

This project already has a real, working G0-G4 evidence-tier ladder
(`graph_schema.md`) and, as of today, a genuinely new tier: an
independent external health-check witness (`scripts/health_witness_monitor.py`,
verified working -- detects a real process kill within 0.5s via
`/actuator/health` polling, logs it to a separate ES index, completely
independent of the crashed service's own log stream, exactly like a
real load-balancer or k8s liveness probe would). This lets us ask a
controlled question generic benchmarks can't: **does giving a method
access to a strictly more realistic evidence tier (external
health-check signal, not just self-reported logs) change accuracy on
the previously-unsolvable cases, and by how much?** That's a real
ablation with a real causal story, not just a bigger leaderboard.

### 4. Explanation faithfulness for regulatory auditability

Financial RCA in a real bank isn't just "get the right answer" -- SR
11-7 (US model risk management) and the EU AI Act's high-risk
classification for financial services both require an auditable
explanation, not just a correct output. A benchmark that scores whether
a method's stated reasoning actually matches the evidence it had access
to (not just whether the final answer happens to be right) tests
something every other RCA benchmark ignores and that real deployment in
this domain would actually require. Not yet built -- flagged as the
highest-effort, highest-payoff addition if there's time.

## Concrete research framing (what the eventual writeup should claim)

Not: "a bigger/harder RCA benchmark." Instead: **"ClearFlow-RCA tests
three things generic microservice RCA benchmarks structurally cannot:
domain-semantic disambiguation of business-correct vs. genuinely
anomalous behavior, calibrated abstention under real evidentiary
blackout, and controlled evidence-tier ablation with a real external
witness signal -- on live-triggered incidents in a real bank-rail-aware
payments stack, not synthetic logs."** That's a defensible, narrow,
honest claim a small-n benchmark can actually support, unlike "bigger
than RCAEval," which it can't.

## What changes in the plan because of this reframe

- Do NOT try to grow n aggressively to compete on scale -- growth should
  be targeted (a handful of genuinely new finance-specific fault types:
  liquidity-buffer breach, sanctions-list false-positive storm,
  correspondent-bank cutoff miss -- see `BENCHMARK_PLAN.md`), not bulk.
- Add `has_distinguishing_evidence` as an explicit, published field
  (derivable now from `MANUAL_101_CASE_REVIEW.md`'s existing per-case
  `reason` column -- no new data collection needed).
- Score abstention quality as a second, real metric alongside AC@1.
- Run the model-comparison sweep (already in progress) both WITH and
  WITHOUT the new health-witness evidence tier once enough of it is
  captured, as a real ablation, not just a bigger accuracy number.
- The graph-memory work (Neo4j, `build_agent_memory_graph.py`) is
  directly useful here too: a knowledge graph is the natural structure
  for later scoring explanation faithfulness (does the method's stated
  reasoning path match real edges in the incident's evidence graph).

## Honest caveat

This reframe makes a stronger, more defensible research claim, but it
does NOT fix the small-n statistical power problem -- a paper claiming
"calibrated abstention" or "domain-semantic disambiguation" on ~30-70
solvable cases still needs real confidence intervals reported honestly,
not a single point estimate. Keep doing that.
