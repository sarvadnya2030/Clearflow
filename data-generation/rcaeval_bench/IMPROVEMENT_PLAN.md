# GEAR-RCA on RCAEval: Improvement Plan and Methodology

Status as of 2026-09-17. This is a living document — append results and
decisions as they happen, don't rewrite history.

## Public data sources (not redistributed in this repo)

This directory holds only the harness code and final result summaries.
The underlying benchmark data and target-system source code are third-party
and public; fetch them directly instead of expecting a local copy:

- **RCAEval benchmark** (cases, metrics/logs/traces): [phamquiluan/RCAEval](https://github.com/phamquiluan/RCAEval) (GitHub), mirrored on [Hugging Face](https://huggingface.co/datasets/phamquiluan/RCAEval)
- **Online Boutique** (target system for RE1/RE2-OB): [GoogleCloudPlatform/microservices-demo](https://github.com/GoogleCloudPlatform/microservices-demo)
- **Sock Shop** (target system for RE1-SS): [microservices-demo/microservices-demo](https://github.com/microservices-demo/microservices-demo)
- **Train Ticket** (target system for RE2-TT): [FudanSELab/train-ticket](https://github.com/FudanSELab/train-ticket)

## 1. Where we actually are (verified, not estimated)

| Run | Scope | Accuracy | Notes |
|---|---|---|---|
| Baseline | OnlineBoutique/RE1, CPU+DELAY, 50 cases | 37/50 = 74.0% (CPU 76%, DELAY 72%) | Pre-fix harness |
| Fixed re-run | Same 50 cases | 37/50 = 74.0% (CPU 88%, DELAY 60%) | Round-budget fix + dependency-tracing fix. Net zero at aggregate: 6 cases newly fixed, 6 different cases newly broken |
| RE2 trace tool | 5 targeted cases | 4/5 = 80% | Operation-name-grouping causal trace fix, verified through the real LLM agent |

**Two real harness bugs found and fixed** (both verified before/after):
1. Round-budget exhaustion never forced a real answer (fixed with a `tool_choice="none"` forced-final-answer call).
2. That fix's own `max_tokens=300` truncated the answer before it reached `content`, because `gpt-oss-20b` consumes a large internal `reasoning_content` budget first (fixed: `max_tokens=1000` + fallback).

**The core open problem:** caller-vs-source misattribution (agent names a downstream *caller* like `frontend` instead of the real upstream cause). Three fix attempts tried and verified:
- (a) Prompt-only resource-metric bias — insufficient, model satisfies the instruction's letter not its intent.
- (b) Inline dependency-anomaly comparison — real but modest (1/9 fixed on targeted subset), and in the full 50-case run traded one failure mode for a different one of equal size (overshoots into wrong sibling services).
- (c) Onset-timing / Granger-causality-style temporal precedence — correctly favors the true cause on 2/3 cases tested, but hits a genuine data-resolution ceiling on the flagship case (`cartservice_delay_1`): the true causal lag is under RCAEval's 1-second metric sampling interval, so timing alone can't always resolve it.

**Real RCAEval scope audit** (verified against `cases.parquet` directly):
- 240 total CPU+DELAY cases across all suites/systems (only 50 used so far, ~21%).
- 165 DISK+SOCKET cases (DB_TIMEOUT-analog), untouched.
- RE1 confirmed metrics-only (no logs/traces).
- RE2 confirmed to have real logs and real distributed traces (verified by downloading and reading actual `logs.parquet`/`traces.parquet` content).

## 2. Literature grounding

Independent web research (this session) plus a detailed external write-up
the user provided both converge on the same diagnosis: **raw anomaly
magnitude is not a valid cross-metric-type or cross-service ranking
signal**, and the RCAEval benchmark's own published baselines hit the
same wall we did:

- **BARO** (FSE'24): strong on resource faults (DISK, MEM), weak on
  network faults (DELAY, LOSS) — the identical split observed here.
- **RCD** (NeurIPS'22, best average Avg@5=0.54 in the benchmark): uses
  causal discovery via intervention — finds which node's own conditional
  distribution changed independent of its parents, not which node has
  the largest raw anomaly.
- **TraceRCA / PDiagnose**: strongest published performance specifically
  on DELAY faults (Avg@5 0.88 / 0.87 on Train Ticket), both trace-based —
  consistent with our own finding that the trace-based fix (RE2) works
  where the metrics-only fix (RE1) hits a real ceiling.
- The external write-up's core recommendation — **use the LLM as a
  reranker over structured, candidate-list-constrained evidence, not as
  a free-form first-stage detector** — directly explains our own
  `None`/hallucinated-service failures, which are a known failure mode
  of the approach we've been using, not something specific to gpt-oss-20b.

Full source list: RCAEval paper (arXiv:2412.17015), RCD paper (NeurIPS
2022), BARO paper (ACM FSE'24), Neural Granger Causal Discovery
(arXiv:2402.01140), RCAEval GitHub (phamquiluan/RCAEval).

## 3. Implementation plan, priority order

**Explicit framing: this augments GEAR-RCA's own graph+memory+tool
architecture and the trace fix already found; it does not replace them
with a generic reimplementation of BARO/TraceRCA.** RCAEval has zero
business-domain-state fault types (no AML-hold or idempotency-collision
analog), which remains GEAR-RCA's actual differentiator and is untouched
by any of this work.

### Priority 1 — constrained candidate-list output (cheap, high-value)
Restructure the agent's final-answer step to select from a fixed
candidate list (the known services in scope) and return structured JSON
(candidate, evidence references, uncertainty) instead of free-form text.
Directly targets the two observed failure classes: round-budget `None`
outputs and hallucinated/wrong service names. Test on known-failing
cases first, verify raw output before/after.

### Priority 2 — formalized temporal composite score
Replace the binary onset-precedence check with a real weighted score:

```
S_i = w_a * AnomalyMagnitude_i
    + w_p * Persistence_i
    + w_o * OnsetPrecedence_i
    + w_s * PreAlertSlope_i
    + w_c * ChangePointConfidence_i
    - w_d * DownstreamOnlyPenalty_i
```

Compute each term from real data, verify each component's actual value
on the flagship cases before combining, tune weights on a held-out
subset (never on the same cases used for the reported number).

### Priority 3 — BARO-style normalized fallback (only if 1+2 insufficient)
```
final = 0.45 * resource_anomaly_score
      + 0.25 * onset_score
      + 0.15 * persistence_score
      + 0.10 * topology_score
      + 0.05 * fault_match_score
```
Requires robust per-service median/MAD normalization as a prerequisite
(not raw z-score, which is the root of the cross-metric-type
incomparability problem already found). Verify normalization actually
flips the frontend-vs-cartservice ranking correctly on the flagship case
before wiring in the rest.

### Explicitly out of scope for now (real future work, not silently dropped)
Full multi-source fusion (metrics+logs+traces weighted combination),
supervised reranking (LightGBM/XGBoost trained on development cases),
RE3 code-level fault handling (stack-trace extraction pipeline), full
reimplementation of external baselines (BARO/TraceRCA/PDiagnose) for a
head-to-head comparison. Each is legitimate multi-session work.

## 4. Standing discipline (non-negotiable, applies to every step above)

1. **Implement** a specific, scoped change.
2. **Test** — run it and capture raw output.
3. **Verify** the raw output actually shows what's claimed, by reading it directly, not skimming or assuming.
4. **Reason** about why it worked or didn't, only after verification.
5. **Improve** based on that reasoning.
6. **Repeat.**

Zero trust, including of prior claims in this same document — if
something recorded above was asserted rather than directly inspected in
this session, re-verify it before building on it. Every future run
persists full `reasoning_content` per round and `logprobs`/`top_logprobs`
if the API actually supports them (see the standing rule added to the
project's `.claude/CLAUDE.md`).

## 5. Intelligent case selection, not brute-force expansion

Running all 240 CPU+DELAY cases (let alone the full 735) every time a
fix changes is wasteful given the observed ~78-1700s/case NIM latency —
it burns hours to re-learn the same lesson a well-chosen 30-40 case
subset would show in a fraction of the time. Select cases for
*information value*, not coverage:

**Core diagnostic set (must include, ~20-25 cases):**
- All 12 cases that flipped (6 newly-fixed, 6 newly-broken) between the
  baseline and fixed re-run (Section 1) — these are the highest-signal
  cases for telling whether a new fix actually resolves the
  caller-vs-source tradeoff or just moves it again.
- The original 9-case targeted misattribution subset.
- Any case already confirmed correct in both baseline and fixed runs, a
  handful (3-5) as a **regression check** — a fix that breaks a previously
  easy, always-correct case is a real regression signal, not something
  to discover only after a full run.

**Stratified sample for generalization (~10-15 cases):**
- A handful of cases per fault type (CPU, DELAY) not already in the core
  set, prioritizing services/fault combinations not yet seen (a `DISK`
  or `SOCKET` case once those are in scope, a case from `adservice` or
  `emailservice` rather than only the already-heavily-tested
  `cartservice`/`currencyservice`/`checkoutservice`/`productcatalogservice`).
- At least 1-2 cases from Sock Shop or TrainTicket once/if those systems'
  graphs are built, to check the fix generalizes across codebases, not
  just across fault types within OnlineBoutique.

Only expand to the full 240 (or beyond, to DISK/SOCKET and other
systems) once a fix has already shown a clean, verified improvement on
this smaller, high-signal set — full-scale runs are for confirming a
result already believed to be real, not for discovering whether it is.

## 6. Ensemble testing across methods, not a single winner-takes-all fix

Priorities 1-3 (Section 3) and the existing RE2 trace fix are not
mutually exclusive alternatives to pick one from — combine them as
independent evidence signals and fuse the result, the same way the
literature review's Section 9/10 (rank fusion, fault-dependent ensembles)
recommends and the same way GEAR-RCA's own architecture already treats
graph/memory/tools as complementary rather than a single method:

- **Per case, compute a score from each available method independently**:
  the existing agent's raw answer, the temporal composite score
  (Priority 2), the trace-based operation-name signal (RE2 cases only,
  where traces exist), and the BARO-style normalized score (Priority 3,
  if implemented). Not every method applies to every case (trace-based
  only works where RE2 data exists) — that's expected, not a bug.
- **Fuse via reciprocal rank fusion** (`S(v) = sum over methods of
  weight_m / (rank_m(v) + c)`) rather than averaging raw scores directly,
  since the methods' scores are not on comparable scales — this was
  explicitly the mechanism identified as the actual bug in the very
  first misattribution case (raw magnitudes from different metric types
  aren't comparable; the same principle applies across methods, not just
  across metrics).
- **Verify the fusion on the core diagnostic set (Section 5) case-by-case**
  before trusting an aggregate: for each of the 12 flip cases, print which
  method(s) got it right, whether fusion recovers the correct answer, and
  whether fusion ever makes a case worse than every individual method
  would have on its own (a real risk with naive fusion, worth checking
  for directly rather than assuming fusion is monotonically an improvement).
- Report per-method accuracy AND fused accuracy on the diagnostic set,
  not just the final fused number — losing the ability to attribute which
  method actually contributed defeats the disclosure standard this
  project holds itself to everywhere else.

## 6c. Priority 2 implemented and verified (2026-09-17, continuation session)

Implemented in `composite_score.py`, reusing `gear_rca_rcaeval.py`'s
already-verified `load_case_metrics`/`compute_anomaly_scores`/
`compute_onset_times`/`STATIC_DEPS` rather than re-deriving them. All
five terms (AnomalyMagnitude, Persistence, OnsetPrecedence, PreAlertSlope,
ChangePointConfidence) plus DownstreamOnlyPenalty are pragmatic proxies
computed from real per-metric time series -- documented as such in the
module docstring, not oversold as a full statistical model (ChangePointConfidence
is a bounded Welch's-t-stat proxy, not real CUSUM/BOCPD -- that remains
real future work). **Weights are a documented starting point, NOT tuned
on a held-out split yet** -- this is an honest gap, not a finished result.

**Verified directly against real data, zero LLM cost, on 5 real cases:**

| case | gold | composite top-1 | correct? |
|---|---|---|---|
| cartservice_delay_1 (flagship) | cartservice | **cartservice** (S=0.9652 vs frontend 0.9567) | YES -- narrow margin (+0.0085) |
| checkoutservice_delay_1 | checkoutservice | **checkoutservice** (0.9653 vs 0.3955) | YES -- decisive |
| productcatalogservice_delay_1 | productcatalogservice | recommendationservice (0.9211 vs 0.9176) | **NO** -- razor-thin miss (-0.0035) |
| adservice_cpu_1 (regression check) | adservice | **adservice** (0.94 vs 0.26) | YES -- decisive |
| currencyservice_delay_2 | currencyservice | **currencyservice** (0.9148 vs 0.58) | YES -- decisive |

**Composite score alone: 4/5 correct, real and disclosed miss on
`productcatalogservice_delay_1` by a razor-thin margin (essentially a
coin flip at these weights).**

**Reciprocal rank fusion tested against Section 6's own warning:**
fusing composite-score-rank with the existing raw-z-score
(`deterministic_signal`) ranking via RRF gives 4/5 too, but **flips which
case fails** -- fixes `productcatalogservice_delay_1` but breaks
`cartservice_delay_1` back to `frontend` (the exact bug composite score
was built to fix), because the raw z-score method is itself the known-flawed
signal. This is precisely the risk Section 6 flagged ("check whether
fusion ever makes a case worse than any individual method alone") --
confirmed real here. **Conclusion: composite score alone outperforms
composite+raw-z-score fusion; don't fuse with a component already known
to be unreliable.** A more promising fusion partner (not yet tested) would
be the RE2 trace-based signal on cases where trace data exists, or a
second, independent temporal signal rather than the flawed magnitude-only
one.

**Reasoning-trace/logprobs logging (standing CLAUDE.md rule): implemented
and verified live, including a real correction to the open question it
raised.** `reasoning_content` was already real per round (verified
earlier). Initial check found `logprobs` came back `None` -- but this was
because the API call never requested them, not because NIM/gpt-oss-20b
lacks support. Verified directly: passing `logprobs=True, top_logprobs=3`
returns real token-level logprobs (including the model's raw
`<|channel|>`/`<|message|>` special tokens, confirming its reasoning and
content channels are literally interleaved in the raw token stream).
Wired `logprobs=True, top_logprobs=3` into both the main tool-calling
loop and the forced-final-answer call in `gear_rca_rcaeval.py`, and
**re-verified it works together with live tool-calling** (not just plain
completions) on a real case (`re1ob_adservice_cpu_2`): all 8 rounds
returned real, non-null logprobs alongside real reasoning_content and a
correct prediction. Per-round `round_log` (reasoning_content, content,
tool_calls, logprobs) is now returned from `run_case` and persisted to
`reasoning_traces/<case_id>.json` by `main()`'s per-case loop (write
mechanism verified via roundtrip test; not yet observed via an actual
`main()` execution, since that requires a full batch run -- low risk,
mechanical wiring around already-verified data).

**Not yet done (honest gap, real future work):** none of the above has
been run through the actual LLM agent end-to-end -- only the standalone
scoring logic is verified. Wiring `composite_scores()` into
`gear_rca_rcaeval.py` as a callable tool and re-testing the 23-case
diagnostic set through the real agent (with the new structured
JSON-candidate-list output from Priority 1 also applied) is the direct
next step, not completed in this session due to real per-case LLM
latency (observed 78-1700s/case) making a full 23-case LLM run a
multi-hour commitment on its own. Weight tuning on a held-out split is
also not done -- the 5 cases above are a spot-check, not a training run.

## 6a. The disciplined 3+ iteration hardest-cases loop (user directive, 2026-09-17)

Mirrors the real ClearFlow paper's own methodology: it isolated an
11-hardest-cases subset (every prior method scored 0% on those) and used
that as the real stress test, rather than trusting an aggregate number
alone. Do the same here:

1. **Identify the true hardest core** from the 23-case diagnostic set:
   specifically the cases where caller-vs-source misattribution has
   resisted every fix tried so far (dependency comparison, onset timing) —
   e.g. `cartservice_delay_1/4/5`, still predicting `frontend`. This is
   the real stress-test set.
2. **Test each approach INDIVIDUALLY on the hardest core first** —
   Priority 1 (structured JSON), Priority 2 (composite score), the RE2
   trace fix, Nemotron (Section 7) — one at a time, through the real
   agent, before combining anything. Report real hit/miss per case, no
   averaging together yet.
3. **Report both AC@1 and AC@5.** Real gap found: the harness only
   outputs a single top-1 prediction today. Fix this first — have the
   agent/scoring mechanism output a ranked top-5 candidate list with a
   score/confidence per candidate, verify the ranking is real and
   sensible on a test case, then both metrics can be computed properly
   (matching how RCAEval and BARO/RCD/TraceRCA report results).
4. **Run at least 3 real implement→test→evaluate iterations**, not one
   pass — each iteration should be informed by the real failures of the
   previous one, not a repeat of the same attempt.
5. **Bar for "keep this fix": not marginal.** A 1-2 case flip on a small
   set is noise. Recall: even the real paper's own +9.1/+9.3 point memory
   ablation did not clear McNemar's significance at n=97 (Section 1 /
   the paper itself) — a genuine win here needs to be clearly larger than
   a few points on a small set, or replicated across multiple cases,
   before being called real. State the actual bar being used explicitly
   when reporting, don't leave it implicit.
6. **Only fuse approaches that individually cleared step 5's bar.**
   Already learned the hard way (Section 1c) that fusing a good signal
   with a known-flawed one (raw z-score) made results worse, not better —
   don't repeat that by fusing with anything unproven.
7. **Only after a combination clears the bar on the hardest core does a
   fuller run make sense** — first the 23-case diagnostic set, only then
   the 240-case set. Do not brute-run before that.

Time is limited on the user's end — keep moving through real iterations
rather than over-polishing any single step, but never skip the
verification step to go faster. That exact shortcut is what caused real,
expensive damage earlier in this project (the live Elasticsearch
sort-order bug, and the code-graph `deriveModule()` bug in
`.claude/CLAUDE.md`'s own standing rule) — both were caught only by
direct inspection, not by anything running without error.

## 7. Bigger-model experiment (Nemotron), for the hardest-still-failing cases only

Added 2026-09-17. `nvidia/nemotron-3-super-120b-a12b` (120B params,
extended-thinking mode, `reasoning_budget` up to 16384 tokens) is
available via the same NVIDIA NIM endpoint/API key already in use
(`https://integrate.api.nvidia.com/v1`, OpenAI-compatible client — see
project memory `llm_nvidia_nemotron.md` for the exact client setup).
This is a real alternative to `gpt-oss-20b` (20B), not a hypothetical.

**Scope this narrowly — do not swap the whole harness to Nemotron.**
Use it only as a targeted diagnostic: on the hardest-core cases (Section
6/the hardest subset identified for the 3-iteration loop) that resist
every fix tried so far on `gpt-oss-20b` (dependency comparison, onset
timing, composite score), re-run those specific cases with Nemotron
instead, same tools and evidence, to answer one question: **is the
remaining failure a capability/reasoning-depth limit of the smaller
model, or a genuine architectural/data limit** (as already found for the
sub-second onset-timing ceiling)? If Nemotron also fails on the same
cases for the same underlying reason (e.g. still can't beat the
sub-second timing resolution ceiling, since that's a data problem, not a
reasoning problem), that's a real, useful negative result — it further
confirms the ceiling is architectural, not a matter of model size. If
Nemotron succeeds where `gpt-oss-20b` didn't, that's equally real and
worth reporting, but comes with a cost/latency tradeoff to disclose
(120B is slower per call than 20B, on top of the already-severe NIM
congestion observed).

Verify the client setup works at all (a simple real call, read the raw
response) before wiring it into the benchmark harness. Report real
before/after per case, not an aggregate guess.

## 7a. Real results against the plan above (2026-09-17, continuation)

**Hardest core, identified and verified precisely against real data**
(correcting the plan's example: `cartservice_delay_1` is now FIXED by
fix (b), not still-failing -- excluded below, replaced by the real
current failures, checked directly against `gear_rca_rcaeval_results.json`):

```
re1ob_cartservice_delay_3           gold=cartservice           (was pred=checkoutservice)
re1ob_cartservice_delay_4           gold=cartservice           (was pred=frontend)
re1ob_cartservice_delay_5           gold=cartservice           (was pred=frontend)
re1ob_currencyservice_cpu_3         gold=currencyservice       (was pred=emailservice)
re1ob_currencyservice_delay_4       gold=currencyservice       (was pred=checkoutservice)
re1ob_productcatalogservice_cpu_4   gold=productcatalogservice (was pred=cartservice)
```

**Bar, stated explicitly before results were seen:** this set is 0/6 by
construction. Require >=4/6 (67%) AC@1 to call a result real rather than
noise at this sample size -- matching the paper's own standard that
small-n wins need to be clearly larger than the claimed effect, not
merely nonzero (its own ablation didn't clear McNemar's significance at
n=97).

**Iteration 1 -- Priority 2 composite score, ALONE, zero LLM cost, on all
6 hardest-core cases:**

| case | gold | top-1 | AC@1 | gold in top-5? |
|---|---|---|---|---|
| cartservice_delay_3 | cartservice | **cartservice** | YES | YES |
| cartservice_delay_4 | cartservice | **cartservice** | YES | YES |
| cartservice_delay_5 | cartservice | **cartservice** | YES | YES |
| currencyservice_cpu_3 | currencyservice | **currencyservice** | YES | YES |
| currencyservice_delay_4 | currencyservice | checkoutservice | NO | YES (rank 2) |
| productcatalogservice_cpu_4 | productcatalogservice | **productcatalogservice** | YES | YES |

**AC@1 = 5/6 (83%), AC@5 = 6/6 (100%). Clears the 67% bar decisively.**
This is the single strongest, most inspectable result of the whole
investigation (every score component was printed and verified per case,
not a black-box coincidence) -- see Section 6a for the full per-component
breakdown on the flagship case.

**Iteration 2 -- Nemotron-3-Super-120B (extended thinking), same tools, on
one hardest-core case (`cartservice_delay_4`):** client/tool-calling
compatibility verified live first (a real function-call test, read the
raw response) before trusting it. **Result: still wrong -- `frontend`,
84.6s.** Its own stated reasoning: "Frontend exhibited the earliest
anomaly onset... while its dependencies showed only latency anomalies
without comparable resource spikes" -- the identical propagated-symptom
trap already diagnosed on `gpt-oss-20b`, just from a 6x larger model with
extended thinking. **This directly answers the open question: the
remaining ceiling is an evidence/tool-design problem, not a
reasoning-depth or model-size limitation.** A bigger model does not fix
it; the composite score already does. Recommend NOT pursuing further
model swaps for this specific problem.

**Iteration 3 -- not completed, honestly flagged:** wiring
`composite_scores()` as an actual callable tool inside the real
`gpt-oss-20b` agent loop (so the LLM uses this evidence directly rather
than it being scored offline) and re-testing the hardest core through the
live agent is the clear next iteration, informed directly by iterations
1-2's real results. Not done here -- each live LLM round-trip in this
session took 60-85+ seconds even for a single exchange; a full 6-case
run through the live agent, verified properly (not just kicked off), is
a genuine 15-40+ minute commitment not safely completed within this
session's remaining time without cutting the verification steps this
project depends on.

**AC@5 capability:** demonstrated via `composite_scores()`'s already-
ranked output (used directly above). **Not yet done:** extending the
LLM-facing Priority 1 JSON schema (`gear_rca_rcaeval.py`) from a single
`root_cause_service` enum to a ranked `top_5` list with per-candidate
confidence, and verifying that produces a real, sensible, non-degenerate
ranking (not just N copies or an unordered set). Real gap, not silently
dropped.

**Fusion:** correctly not attempted -- only Iteration 1 clears the
stated bar; Iteration 2 (bigger model) does not, so per the plan's own
rule (only fuse bar-clearing approaches), there is nothing yet to fuse
composite score WITH. The next real comparison, once Iteration 3 exists,
is composite-score-as-tool vs. composite-score-as-standalone-scorer, not
a fusion question yet.

**Done, same session: `composite_scores()` wired into `gear_rca_rcaeval.py`
as a real, MANDATORY tool (`query_composite_ranking`) in the live agent's
tool list**, with the system prompt updated to point the model at it
explicitly. Verified with a real import check (no circular-import issue
despite `composite_score.py` itself importing from `gear_rca_rcaeval.py`
-- resolved with a local import inside the dispatch branch) and then with
real live agent runs.

**Live-agent verification, hardest-core cases, tool-equipped gpt-oss-20b
(not composite score standalone -- the actual agent using it as one of
its tools):**

| case | gold | pred | hit |
|---|---|---|---|
| cartservice_delay_4 | cartservice | **cartservice** (x2, independently re-run) | YES |
| cartservice_delay_3 | cartservice | **cartservice** | YES |
| cartservice_delay_5 | cartservice | **cartservice** | YES |
| currencyservice_cpu_3 | currencyservice | **currencyservice** | YES |
| currencyservice_delay_4 | currencyservice | checkoutservice | **NO** |
| productcatalogservice_cpu_4 | productcatalogservice | **productcatalogservice** | YES |

**Final, verified: 5/6 (83%) on the full hardest core through the real,
tool-equipped live agent -- clears the 67% bar.** One honest miss
(`currencyservice_delay_4`), not hidden.

**A zero-trust check by the coordinator caught a real gap in HOW this was
verified, worth recording precisely:** `rcaeval_memory.db`'s `cases`
table (which `mem_record()` writes to) still showed the OLD wrong
predictions after these runs. Root cause, confirmed by reading the code
directly: `mem_record()` is called only inside `main()`'s batch loop
(line ~706), NOT inside `run_case()` itself -- every verification test in
this session called `run_case()` directly for fast, isolated iteration,
which correctly bypasses the DB/results-JSON persistence `main()` does.
This is expected behavior given how the tests were invoked, not evidence
of a fabricated result, but it meant the initial "4/4 confirmed" claim
had no independently-checkable artifact behind it beyond this document's
own table. **Fixed by producing real, on-disk, checkable evidence for
every claimed case:**
- `cartservice_delay_3`, `cartservice_delay_5`, `currencyservice_cpu_3`:
  `/tmp/claude-1000/.../tasks/bnmnpfn6u.output` (background-task stdout capture)
- `currencyservice_delay_4`, `productcatalogservice_cpu_4`: `/tmp/last2_hardest.out`
- `cartservice_delay_4`: independently re-run a second time with output
  redirected to `verification_log_cartservice_delay_4_rerun.txt` in this
  same `rcaeval_bench/` directory (not /tmp, more durable) -- same result
  both times (`cartservice`, correct), with the model's own reasoning
  text explicitly citing `query_composite_ranking`'s output as the
  deciding factor, not a coincidence.

`cartservice_delay_4` is the exact same case Nemotron-3-Super-120B failed
on with the identical `frontend`-favoring reasoning (Section 7a,
Iteration 2) -- the small 20B model, given this one additional tool, gets
it right, twice independently, where the much larger model with extended
thinking did not. This remains the clearest real-world confirmation of
the stated principle: the fix was a better tool, not a bigger model.

**Concrete recommendation for the next session:** run the full 23-case
diagnostic set through this now-tool-equipped agent via `main()` itself
(so results persist to `gear_rca_rcaeval_results.json` and the memory DB
automatically, avoiding the direct-`run_case()` verification gap found
here) for a complete, aggregate, durably-recorded before/after -- the
natural next step before considering the 240-case set.

## 7b. Meta-methodology: a capable reasoner solves it first, then the fix is exposed as a tool for the small model

User directive, 2026-09-17, and it's directly consistent with 7a's real
finding: Iteration 2 already proved that swapping to a bigger model
(Nemotron-120B) does NOT fix the caller-vs-source problem, because the
bigger model reasons from the same raw, uncalibrated evidence and falls
into the identical trap. That result points at the actual right move,
which is not "try an even bigger model" but:

**When a fix attempt fails, have a genuinely capable reasoning system
(not the benchmark's own small agent, and not just a bigger version of
the same architecture) work the specific failing case directly, by hand,
with full access to the raw evidence, and figure out what reasoning
process actually gets it right.** Then **encode that reasoning as an
explicit tool, heuristic, or scoring function exposed to the small model
(`gpt-oss-20b`) as a callable tool** — the same pattern already used
successfully in this project: `composite_scores()` and the operation-name
trace fix are exactly this pattern already, discovered by a capable
agent (this project's own coordinator/fork Claude sessions) reasoning
through raw data by hand, then operationalized as a deterministic
function the small model can call, rather than asking the small model to
discover that reasoning itself from scratch inside its own limited
context/reasoning budget.

**Practice, going forward, whenever a fix attempt fails:**
1. Take the specific failing case's raw evidence (metrics, traces, logs —
   whatever's available) and reason through it directly and carefully,
   the way a skilled engineer would, not the way the benchmark's agent
   currently does.
2. Identify the concrete signal or reasoning step that actually
   distinguishes the true root cause from the propagated symptom in that
   case — verify it against the raw data before trusting the insight.
3. Turn that into a deterministic, callable tool/function (like
   `composite_scores()`, `onset_time_analysis()`, the trace
   operation-name grouping) rather than a prompt instruction hoping the
   small model reasons its way there on its own — prompt instructions
   already failed once (fix (a), Section 1) for exactly this reason.
4. Only then test whether exposing that tool to the small model actually
   improves its real accuracy — same implement→test→verify discipline as
   everywhere else in this project.

This is a better use of a capable model's reasoning than swapping the
production/benchmark model to something bigger and more expensive per
call — the capable reasoner's job is to do the hard thinking ONCE, offline,
and hand the small model a cheap, reliable tool, not to sit in the
benchmark's own inference loop.

## 7c. Real bug found mid-run: 3rd mandatory tool regressed round budget (2026-09-17)

While running the 23-case diagnostic set through `main()` (per the
coordinator's explicit request, so persistence would happen automatically
and be independently checkable via `rcaeval_memory.db`, not just log
files -- addressing the exact gap flagged in Section 7a/7b), two cases
that had been independently verified CORRECT earlier in this same session
(`re1ob_cartservice_delay_1`, `re1ob_cartservice_delay_4`) came back as
`pred=None` in this run. This was flagged and investigated immediately
rather than reported as-is or hand-waved as non-determinism.

**Root cause, found by reading the actual per-round trace, not assumed:**
at round 6, the model produced the fully correct answer as free text
("ROOT CAUSE: cartservice...") with no tool calls. But `query_knowledge_graph`
(a separate, unrelated mandatory tool) had not yet been called, so the
existing nudge logic discarded that valid answer and forced another
round. By the time the model complied (round 7), the 8-round budget was
exhausted, triggering the forced-final-answer path -- which this time
came back with genuinely empty content (a second, distinct failure mode
not seen in this session's earlier isolated tests). Net effect: a correct
answer, already stated by the model, was thrown away by budget pressure
introduced by adding a 3rd mandatory tool (`query_composite_ranking`,
Section 7a) without raising the round budget to compensate -- a real
regression, exactly the kind of thing this project's own standing rule
about verifying every change exists to catch.

**Fix applied in `gear_rca_rcaeval.py`:** (1) round budget raised 8->10 to
give room for 3 mandatory tools plus evidence-gathering plus a final
answer; (2) the model's last stated answer (even one discarded by a
nudge) is now preserved as `last_stated_answer` and used as a fallback if
the forced-final-answer call itself comes back empty, instead of falling
back to "unknown" and losing real evidence that was already produced.

**Handling of the in-progress 23-case run:** the background process
already had the pre-fix code loaded in memory and 17/23 cases done by the
time this was found -- restarting would discard real, already-verified
progress. Decision: let it finish with the old code (documented as a
known, disclosed limitation of that specific run), then separately
re-verify the affected cases with the fixed code as an isolated
before/after, the same pattern already used for every other fix in this
project.

**Confirmed: the raw 23-case run (pre-fix code) finished at 18/23 = 78.3%.**
Misses were 3 known round-budget-regression `None` cases
(`cartservice_delay_1`, `cartservice_delay_4`, `productcatalogservice_delay_4`)
plus 2 genuine wrong answers (`currencyservice_delay_4`,
`productcatalogservice_delay_1`).

**Fix verified on all 3 affected cases, independently re-run with the
fixed code (8->10 rounds + preserved last-stated-answer fallback), each
producing a real, correct, non-empty answer citing `query_composite_ranking`:**

| case | pre-fix | post-fix | log |
|---|---|---|---|
| cartservice_delay_1 | None | **cartservice** | `fix_roundbudget_verify.log` |
| cartservice_delay_4 | None | **cartservice** | `fix_roundbudget_verify.log` |
| productcatalogservice_delay_4 | None | **productcatalogservice** | `fix_roundbudget_verify3.log` |

**Final, confirmed 23-case diagnostic-set result (results patched into
`gear_rca_rcaeval_results_hybrid_diagnostic23.json` with the re-verified
values, remaining 2 genuine misses left as-is, not chased further per
Section 8's own priority ordering): 21/23 = 91.3%**, vs. the original
74.0% 50-case baseline. Not a marginal result -- three independently
reproduced, mechanistically-explained fixes plus the pre-existing 5/6
hardest-core hybrid-tool result (Section 7a), not one or two lucky flips.
**This clears Section 5's gate for the next-tier expansion.**

Two genuine remaining misses, disclosed and NOT chased further right now
per explicit instruction (smaller problem than the round-budget
regression, shouldn't block reporting): `currencyservice_delay_4`
(predicted `checkoutservice`) and `productcatalogservice_delay_1`
(the same near-coin-flip case the standalone composite score already
found razor-thin in Section 6c).

## 7d. Priority pivot to RE2-OB expansion (2026-09-17)

After the RE1-OB result was confirmed (21/23=91.3% on the diagnostic
subset), the user reprioritized: rather than grinding out RE1-OB's
remaining 27 cases (a weaker fix with 2 known genuine misses even at
best), prioritize RE2-OB's remaining 25 cases (30 total, only 5
previously tested) with the trace-based fix, which is the cleaner,
better-performing result so far (4/5, no residual misattribution
pattern, real causal trace evidence rather than an approximation).

**Real correction found and disclosed along the way:** "OnlineBoutique's
240-case CPU+DELAY pool" was a miscommunication -- verified directly
against `cases.parquet`: OnlineBoutique's real total across both suites
is 80 (RE1: 50, RE2: 30), not 240. 240 is the sum across all THREE
systems (OB+SockShop+TrainTicket), which was explicitly out of scope.
Flagged before acting on the wrong number rather than silently
launching a mismatched run.

**RE1-OB's remaining 27 cases**: identified precisely (`remaining_27_ids.json`,
zero overlap with the 23-case diagnostic set, verified programmatically),
a background run was started through `main()` with the round-budget fix
applied, then paused (not abandoned) mid-flight to avoid API contention
with the higher-priority RE2-OB work, per explicit instruction. Resume
later if time allows -- not yet done.

**RE2-OB's remaining 25 cases**: identified precisely (`re2ob_remaining25.json`,
verified against `cases.parquet` directly, zero overlap with the 5
already-tested cases). `gear_rca_re2_trace.py` extended with: (1) the
same standing-rule reasoning/logprobs persistence added to
`gear_rca_rcaeval.py` (per-round `reasoning_traces_re2/<case>.json`),
(2) the same round-budget-regression fix already verified there (8->10
rounds, preserved last-stated-answer fallback), (3) a reusable
`run_batch()` function replacing the old hardcoded 5-case-only `__main__`
block. Verified with a real sanity-check case
(`re2ob_checkoutservice_cpu_1`, correct, 7 real rounds with real
reasoning_content and confirmed logprobs) before launching the full
25-case batch in the background. Real result pending at time of writing
-- checkpoint and report once cases complete, per the same discipline as
every other run in this project.

## 7e. RE2-OB batch: real bug found and fixed, now running clean

The first attempt at the 25-case RE2-OB batch crashed after 1 case
(`FileNotFoundError` on `re2ob_checkoutservice_cpu_2/inject_time.txt`) --
verified directly: only 6 of 30 RE2-OB case directories had ever actually
been downloaded to disk (the 5 originally-tested cases plus one sanity
check), not all 30. Found `RCAEval.utility.download_re2ob_dataset` exists
in the installed package but points at the same dead Zenodo URL already
disclosed as broken (Section 7). Fixed by pulling the real HuggingFace
mirror (`phamquiluan/RCAEval`, confirmed via `HfApi.list_repo_files` to
have real `re2ob_*/{inject_time.txt,metrics.parquet,logs.parquet,
traces.parquet}` files) for all 25 missing case directories -- verified
all 25 downloaded with zero failures, all 30 RE2-OB directories now
present. Batch relaunched and running clean (in progress at time of
writing).

## 7f. RE3 investigation: real findings from real data, per instruction

Before designing any extraction tool, pulled and read two real RE3-OB
cases' actual `logs.parquet` (same real HF mirror, confirmed real
schema: `timestamp, container_name, message`, matching RE2's format).

**Case 1 (`re3ob_cartservice_f1_1`, fault type F1 "incorrect parameter
values", real root cause = cartservice):** the true root-cause service's
own log contains a specific, named exception in every occurrence:
`"Error status code 'FailedPrecondition' with detail 'Can't access cart
storage. System.OverflowException: Value was either too large or too
small'"` (a real .NET gRPC error). The caller (`frontend`) logs only a
generic, paired `"request error"` with zero exception detail for the
same failed calls (303 error-ish lines total, 1:1 paired pattern
confirmed by direct inspection).

**Case 2 (`re3ob_adservice_f4_1`, fault type F4, real root cause =
adservice):** the pattern generalizes and is even richer -- `adservice`'s
own log contains a full real Java stack trace: `java.lang.
NullPointerException: Cannot invoke "java.util.Collection.toArray()"
because "<parameter1>" is null`, with stack frames literally naming
`hipstershop.AdService$AdServi...` (the actual faulty class, matching the
gold service name exactly). `frontend` again logs only a generic
`"failed to retrieve ads"`, zero exception detail.

**Real, generalizable distinguishing signal found by hand, before
building anything:** the true root-cause service's own logs contain a
SPECIFIC NAMED exception type (and often a stack frame chain naming its
own class/package), while a downstream caller's logs contain only a
generic, non-specific failure message with no exception detail at all.
This is a cleaner signal than anything used for the metrics-only (RE1)
or trace-based (RE2) fixes -- for code-level faults, the exception
itself, if present, essentially names the answer directly, which is
consistent with the RCAEval paper's own statement that stack traces are
the primary indicator for this fault class (already cited, Section 2).

**Proposed extraction mechanism (reasoned through, not yet built as a
tool):** per service, scan post-injection log lines for known
exception-signature patterns (a named `Exception`/`Error` type string, a
`SEVERE:`/`ERROR:` severity marker, a stack-frame line matching
`\bat\s+[\w.$]+\(`), extract the exception class name and, where present,
the innermost stack frame's package/class token. Rank services by
whether they show this specific signal at all (most won't -- only the
true source typically does) rather than by log line volume, which would
just favor whichever service is chattiest.

**Not yet done, explicitly deferred (per instruction, this needed real
data understanding first, which is now done):** building this as a real
callable tool, verifying it against more RE3 cases (including F2/F3/F5
fault types not yet inspected -- do not assume the pattern holds for
those without checking), and wiring it into an agent loop the same way
`composite_scores()` and `trace_causal_analysis` were. This is a
genuinely new, separate build (a third distinct evidence tool for a
third distinct fault category), not a quick extension. **On hold per
explicit instruction -- do not resume without direction.**

## 7g. RE2-OB full 30-case result: CONFIRMED FINAL

**30/30 complete. 23 hits = 76.7%.** Independently cross-checked by the
coordinator against the raw results file and matches exactly.

**7 misses, real breakdown:**

| case | gold | pred | fault |
|---|---|---|---|
| checkoutservice_delay_2 | checkoutservice | None | delay |
| checkoutservice_cpu_3 | checkoutservice | adservice | cpu |
| checkoutservice_delay_1 | checkoutservice | productcatalogservice | delay |
| checkoutservice_delay_3 | checkoutservice | productcatalogservice | delay |
| currencyservice_cpu_2 | currencyservice | None | cpu |
| productcatalogservice_cpu_1 | productcatalogservice | cartservice | cpu |
| recommendationservice_cpu_2 | recommendationservice | None | cpu |

**Two honest observations from the real breakdown, not glossed over:**
1. **4 of 7 misses (57%) are `checkoutservice`** -- a real, disclosable
   pattern, not noise. `checkoutservice` has the most outbound
   dependencies of any Online Boutique service (per `STATIC_DEPS`,
   Section 1), which plausibly makes it the hardest case for any
   caller-vs-source disambiguation approach, trace-based or not -- worth
   investigating specifically if this fix is revisited, not chased now.
2. **3 of 7 misses are still `None`** despite the round-budget fix
   (8->10 rounds + preserved-answer fallback) already verified working
   on RE1's harness. This fix was ported to `gear_rca_re2_trace.py` and
   sanity-checked on one case before the batch, but evidently does not
   fully eliminate the failure mode on RE2's harness/tool set -- a real,
   disclosed gap, not fully resolved by porting the same fix, worth
   investigating if this line of work resumes.

**Status: holding here per explicit instruction.** Not starting the RE3
tool build, not touching Train Ticket (a separate fork already has real
graphs built for all three systems -- Online Boutique 822 nodes, Sock
Shop 956 nodes, Train Ticket 4966 nodes/7508 edges -- and is handling
that work; not duplicating it).

## 7h. Train Ticket RE2 expansion (2026-09-17, parallel fork)

Started per user directive: Train Ticket RE2 is the one system/suite the RCAEval paper
actually publishes baseline comparison numbers for (BARO, TraceRCA, PDiagnose, RCD,
CIRCA -- Table 6, Train Ticket only, verified by fetching and reading the paper
directly). Online Boutique and Sock Shop have zero published per-baseline numbers, so
this is the only path to a real, citable comparison.

**Reused, not rebuilt:** real graphify graph already existed on disk
(`graphify-out-tt/graph.json`, 4,966 nodes, 7,508 links) and the real Train Ticket repo
(`train-ticket/`, FudanSELab/train-ticket, canonical source) was already cloned from a
prior session. Verified both are real and usable (loaded the graph, checked real node
labels like `SecurityServiceImplTest.java`) before trusting them, per standing rule --
did not blindly assume freshness.

**Real data downloaded and verified:** all 30 RE2-TT CPU+DELAY cases pulled from the
HuggingFace mirror (`phamquiluan/RCAEval`, same mirror already confirmed working for
OB after the official Zenodo link was found dead). 29/30 have real logs, 30/30 have
real traces (one case, `ts-auth-service_cpu_1`, genuinely lacks logs per `cases.parquet`
-- matches expectation, not a download failure). 27 real services identified directly
from `traces.parquet`'s `serviceName` column across all 30 cases.

**Real structural difference found and adapted for, not assumed away:** Train Ticket's
`operationName` strings do NOT follow OB's gRPC "hipstershop.<Service>/<Method>"
convention that the original trace tool's regex depends on (real values here are
things like `"find ts.orders"`, `"OrderRepository.findById"` -- no embedded callee
name). But `serviceName` is already a first-class column per span here, so the
adapted mechanism (`trace_causal_tool_tt.py`) doesn't need to infer a callee at all --
it directly measures which service's OWN operations show anomalous self-time.

**Two ranking strategies compared on real data before choosing one, not assumed:**
vote-count (how many of a service's operations land in the top-20 anomalous pairs) got
4/5 on real DELAY cases, missing `ts-auth-service` because a weaker-but-broader
competitor won on breadth. Max-ratio-per-service (the single strongest anomaly a
service owns) got **5/5** on the same cases, correctly promoting `ts-auth-service`'s
129x anomaly over the competitor's 2.3x. Max-ratio is what's implemented. Also spot-
checked 2/2 real CPU cases correctly with the same mechanism (small sample, not a
strong claim, but notably the trace signal isn't uniformly CPU-weak here the way it
was on OB).

**Live-agent sanity check (2 real cases, not just standalone scoring) before
committing to the full batch:** `ts-order-service_delay_1` -- correct, real reasoning
citing the trace tool's ranking. `ts-auth-service_cpu_2` -- a genuine, disclosed miss
(predicted `ts-food-service`); harness ran mechanically clean (7 real rounds, real
reasoning_content and logprobs captured), the miss is a real accuracy data point, not
a bug.

**Full 30-case RE2-TT batch launched in the background** (`gear_rca_tt_trace.py`,
results to `gear_rca_tt_trace_results.json`, reasoning traces to
`reasoning_traces_tt/<case>.json` per the standing persistence rule) -- not yet
complete at the time of writing this entry. Report the real aggregate once it
finishes; do not extrapolate from the 2-case sanity check above.

## 7i. Train Ticket RE2 expansion to DISK/LOSS/MEM/SOCKET (2026-09-17)

Per user directive: reporting only CPU+DELAY when the RCAEval paper's published Table
6 covers all 6 RE2 fault types risks looking selective to a reviewer. Real published
AC@1 to compare against once results land (Train Ticket RE2, from the paper directly):

| Fault | BARO | TraceRCA |
|---|---|---|
| MEM | 93% | 63% |
| DISK | 100% | 64% |
| SOCKET | 60% | 60% |
| LOSS | 53% | 57% |

**CPU+DELAY batch (Section 7h) confirmed final while this was in progress: 26/30 =
86.7%.** Real misses: 3 are `None` predictions (the same round-budget-exhaustion
failure class documented for OB, not yet re-diagnosed for TT specifically -- a real,
disclosed gap), 1 is the genuine `ts-food-service` miss found in the original sanity
check.

**Real data downloaded and verified for the new 60 cases** (15 each of DISK/LOSS/MEM/
SOCKET, Train Ticket, HuggingFace mirror) -- all confirmed present with real logs and
traces per `cases.parquet`.

**Whether the existing trace tool applies, checked before assuming -- surprising,
strong result:** ran `trace_causal_tool_tt.py` (built for CPU/DELAY) standalone,
zero LLM cost, against all 60 new cases directly:

| Fault | Standalone AC@1 |
|---|---|
| DISK | 13/15 (86.7%) |
| MEM | 15/15 (100%) |
| SOCKET | 15/15 (100%) |
| LOSS | 15/15 (100%) |

**58/60 = 96.7% standalone, before any LLM involvement.** LOSS working perfectly is a
real, notable surprise -- the literature review explicitly warned "do not treat high
latency as sufficient evidence for packet loss," and a naive latency-based signal
should not distinguish LOSS's true cause from a propagated symptom the same way
DELAY's does. The likely explanation, not yet independently confirmed against raw
LOSS-specific trace content: this tool doesn't measure generic latency, it measures
per-operation SELF-TIME anomaly (exclusive processing time), and RCAEval's LOSS
injection on Train Ticket may manifest as elevated retry/reprocessing self-time
specifically on the true faulty service's own operations, which this mechanism still
correctly isolates. Flagging this as a real, disclosed open question rather than
overclaiming the mechanism is validated for LOSS in general.

**Live-agent sanity check attempted (2 cases, one per new fault type: LOSS and
SOCKET) before committing to the full 60 -- did not return a result within this
session's time budget** (NIM latency; the process was still in flight when the
decision below was made). Given (a) the harness is otherwise byte-identical to the
already-live-verified CPU/DELAY version (only the fault types being fed to it
differ), and (b) the standalone signal for these 4 fault types is stronger than
CPU/DELAY's was, proceeded to launch the full 60-case live-agent batch without a
completed sanity confirmation -- a disclosed judgment call under time pressure, not a
skipped verification of the underlying tool itself (which was thoroughly verified
above). **Full 60-case batch launched in the background**
(`gear_rca_tt_trace_results_60new.json`, same reasoning-trace persistence as
everywhere else) -- real result not yet known at time of writing.

## 7j. Backend switch to Groq for the DISK/LOSS/MEM/SOCKET batch (2026-09-17)

NVIDIA NIM was severely congested (a sanity check and the initial 60-case batch made
zero progress in 35-45+ minutes). User provided a Groq API key as an alternative.

**Real, verified API differences found before writing any code, not assumed:**
1. Groq's `openai/gpt-oss-20b` does **not support `logprobs`/`top_logprobs`** --
   initially confirmed via a real `400 Bad Request: "logprobs is not supported with
   this model"`, then re-verified per direct instruction against Groq's actual
   official documentation (not memory or a summary) at
   console.groq.com/docs/api-reference: the docs state, verbatim, for both
   parameters, **"This is not yet supported by any of our models"** -- a
   platform-wide limitation across all Groq models, not specific to `gpt-oss-20b`,
   not a streaming-vs-non-streaming quirk, not a wrong parameter name translated
   from NIM's convention. The `reasoning` field (chain-of-thought) IS real and
   working on Groq -- confirmed separately and not in question; only the
   token-level `logprobs` output is unavailable. Per the standing CLAUDE.md
   persistence rule, this batch's reasoning-trace files have `logprobs: null` for
   every Groq-served round -- a genuine, now doubly-confirmed backend limitation,
   disclosed, not a bug in this harness or an under-investigated guess.
2. The reasoning field is named `reasoning` on Groq's response, not
   `reasoning_content` like NIM's -- handled by checking both attribute names.
3. Tool-calling verified working identically to NIM via a real function-call test
   before trusting it.
4. **Groq's free-tier quota is real and low** (confirmed via an actual `429`:
   `tokens per minute (TPM): Limit 8000`) -- easily exceeded mid-case given this
   harness's multi-round tool-calling. Confirmed live: a real sanity-check case hit
   this limit mid-investigation.

**Fallback built and verified, per instruction:** `gear_rca_tt_trace_groq.py` tries
Groq first per case; on a caught rate-limit/quota error (`openai.RateLimitError`,
or `429`/`rate_limit`/`quota` in the error text), permanently falls back to NIM for
the remainder of that specific case (bouncing back mid-case just re-triggers the same
small quota). Every round's actual serving backend (`groq` or `nim`) is logged in
`reasoning_traces_tt_groq/<case>.json`, and each case's result record includes a
`backends_used` list -- so which cases used which backend(s) is independently
checkable, not asserted.

**Methodological disclosure for any benchmark comparison table:** the DISK/LOSS/MEM/
SOCKET batch (this section) runs on a different, and for rate-limited cases mixed,
inference backend than the CPU/DELAY batch (NIM only, Section 7h). Even the "same"
model (`openai/gpt-oss-20b`) can behave differently across providers (serving
infra, exact quantization, subtle sampling differences) -- this is disclosed here
rather than treating both batches as identical conditions when reporting results.

**Full 60-case batch relaunched via Groq+NIM-fallback**, results to
`gear_rca_tt_trace_results_60new_groq.json` (superseding the earlier NIM-only attempt
that made zero progress). Not complete at time of writing -- real aggregate to be
reported once it finishes, broken out by fault type per the original request.

## 7k. Standing rule: after a fix, re-run only the failures, not the full set

User directive, 2026-09-17. Once a batch has a confirmed baseline result,
any subsequent fix attempt should be tested by re-running ONLY the cases
that missed in that baseline -- not the full set again. Rationale: cases
that already passed aren't informative about whether a new fix helps
(they were already correct, a fix can't be credited for them), and given
the real per-case cost observed throughout this project (45s-1700s
depending on backend/congestion), re-running an already-passing case is
pure waste.

Practice going forward:
1. After any full batch completes, save the list of failed case IDs
   explicitly (not just the aggregate hit count) -- this is often already
   done (e.g. Section 7j's per-miss table) but make it a deliberate,
   reusable artifact, not just prose in a report.
2. When testing a fix, run it ONLY against that failure list.
3. Report the fix's result as: how many of the N failures it recovers,
   and explicitly confirm (spot-check at minimum) that it does not
   regress any of the previously-passing cases -- this can't be fully
   verified without ever touching the passing set again, so a targeted
   sanity check on a small sample of previously-passing cases is still
   warranted after a fix, per the earlier lesson from Section 1 (a fix
   that helps hard cases while quietly breaking easy ones is a real,
   previously-observed failure mode, not a hypothetical one).
4. Only fold a verified-improved failure-subset result back into a claimed
   full-set aggregate once both the recovery on failures AND the
   non-regression spot-check are confirmed.

## 7l. Groq daily quota exhausted mid-batch -- switched remainder to NIM-only (2026-09-18)

At 28/60 cases, Groq's daily quota was confirmed exhausted (~199,243/200,000 used per
the account's own usage log), so the Groq-first attempt on each remaining case was
adding pure retry/wait overhead before falling back to NIM anyway. Added a `force_nim`
flag to `run_case`/`run_batch` in `gear_rca_tt_trace_groq.py` -- when set, `backend_state`
starts on `"nim"` directly, skipping the Groq attempt entirely. **The Groq-first logic
itself was NOT removed**, only bypassed for the remainder of this run, so it's
available again once/if the quota resets. Killed the stalled process (confirmed clean,
no orphan), relaunched with `force_nim=True` -- `run_batch`'s existing dedup-by-
incident_id logic correctly resumes from the 28 already-completed cases without
re-running them. `backends_used` will now show `["nim"]` for all remaining cases,
consistent with what actually served them -- no backend fabrication.

## 7m. Train Ticket RE2 DISK/LOSS/MEM/SOCKET: FINAL result, real recovery loop applied

**Initial completed batch: 53/60 = 88.3%** (DISK 11/15, LOSS 14/15, MEM 15/15,
SOCKET 13/15). Compared against the real published Table 6 numbers (Section 7i):
already beat both BARO and TraceRCA on MEM/SOCKET/LOSS; below BARO but above TraceRCA
on DISK. Not "poor" by the stated bar, but 7 misses, and inspection showed **6 of the
7 were `None` predictions**, not genuine wrong guesses.

**Root cause found, not assumed:** those 6 cases had stale result entries recorded
from the ORIGINAL Groq-first run (which failed via unrecovered NIM `504` gateway
timeouts before the `force_nim` switch, Section 7l). Because `run_batch`'s resume
logic dedupes by `incident_id` already present in the results file, the `force_nim`
relaunch correctly skipped them as "already done" -- they were never actually retried
on NIM despite the intent. This is a real, disclosable resume-logic gap, not a signal
or tool problem.

**Applied Section 7k's practice directly:** saved the 7 failed case IDs explicitly
(`failed_case_ids_60new.json`), re-ran ONLY those 7 (not the full 60) via
`force_nim=True`, into a separate results file (`retry_60new_results.json`) for a
clean before/after. **5 of 7 recovered** on retry. Regression spot-check judged
unnecessary here and explicitly noted as such -- this was a retry of a resume
artifact, not an algorithmic change to the trace tool or scoring logic, so it cannot
regress a previously-passing case by construction.

**FINAL merged result (`gear_rca_tt_trace_results_60new_FINAL.json`): 58/60 = 96.7%**

| Fault | Ours (final) | BARO | TraceRCA |
|---|---|---|---|
| MEM | **100%** (15/15) | 93% | 63% |
| DISK | **86.7%** (13/15) | 100% | 64% |
| SOCKET | **100%** (15/15) | 60% | 60% |
| LOSS | **100%** (15/15) | 53% | 57% |

Now beats or ties both published baselines on 3 of 4 fault types, and beats TraceRCA
(though still below BARO) on DISK. **2 genuine remaining misses, both real wrong
predictions (not `None`), both DISK**: `ts-auth-service_disk_1` (predicted
`ts-order-service` consistently across two independent attempts) and
`ts-route-service_disk_3` (predicted `ts-order-other-service`). Not chased further
given this is already a strong result and the two misses are a small, disclosed
remainder rather than a systemic pattern -- a legitimate stopping point per the
"not poor, no improvement loop required" branch of the instruction that authorized
this check in the first place.

**Combined with the CPU+DELAY batch (Section 7h/7j, 26/30 = 86.7%, NIM-only), the
full real coverage across all 6 RE2 fault types on Train Ticket, all backends
disclosed:** 84/90 = 93.3% overall, addressing the original concern that reporting
only 2 of 6 fault types would look selective.

## 8. Success criteria

Not "beat X% on RCAEval" as a headline. The deliverable is: (a) a
verified, working fix for the caller-vs-source problem on at least the
RE2 (trace-available) path, already achieved at 4/5; (b) an honest,
literature-corroborated account of where the metrics-only (RE1) path
hits a real ceiling and why; (c) real numbers from an expanded case set
once the priority 1-3 fixes are tested, reported with the same before/after
rigor as every other result in this project — a mixed or negative result
reported honestly is a valid outcome, not a failure to hide.
