#!/usr/bin/env python3
"""
ClearFlow-RCA evaluation harness -- scores an RCA method's guesses against
incidents.csv ground truth, stratified the way the design review called for
(not just one pooled AC@1 number).

Three methods, each restricted to exactly the evidence tier its name claims
(per graph_schema.md's G0-G4 ladder and method-access matrix) -- none of them
touch incidents.csv, incident_payments.csv, or cross-payment causal edges:

  - `loudest_metric_baseline`  (G2 only)     -- z-score, no topology, no state
  - `graph_topology_baseline`  (G0-G2)       -- adds topology: walks the
                                                 pipeline upstream from
                                                 anomalous services
  - `payment_aware_rca`        (G0-G3)       -- adds payment-state signatures
                                                 of payments active in the
                                                 incident window (via their
                                                 own created_at/state fields,
                                                 NEVER via incident_payments.csv)

Usage:
    python3 eval_harness.py
"""

import math
import statistics as stats
from collections import defaultdict
from datetime import timedelta

import pandas as pd

OUT_DIR = "data-generation/output"
# AC@5 is dropped: there are only 5 possible services, so AC@5 is
# trivially 1.0 for every method on every incident by construction --
# reporting it as if it were informative was itself a mistake (see
# README's "brutal review" entry). AC@1/AC@3 are the only meaningful k's.
K_VALUES = [1, 3]
LOOKBACK_HOURS = 2

FULL_PIPELINE_ORDER = ["gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement"]
PIPELINE_INDEX = {s: i for i, s in enumerate(FULL_PIPELINE_ORDER)}


def load(out_dir=OUT_DIR):
    """out_dir defaults to the synthetic dataset's output/; pass
    data-generation/output_live (written by live_evidence.py) to score the
    exact same three methods against real live-triggered incidents instead
    -- nothing below this function needs to know or care which it is.
    """
    incidents = pd.read_csv(f"{out_dir}/incidents.csv")
    metrics = pd.read_csv(f"{out_dir}/metrics.csv")
    metrics["timestamp"] = pd.to_datetime(metrics["timestamp"])
    incident_payments = pd.read_csv(f"{out_dir}/incident_payments.csv")
    payments = pd.read_csv(f"{out_dir}/clearflow_rca_dataset.csv")
    payments["created_at"] = pd.to_datetime(payments["created_at"])
    return incidents, metrics, incident_payments, payments


MIN_ERROR_RATE_SIGMA = 0.01  # real floor, not arbitrary -- measured
# directly from this dataset: real nonzero baseline error_rate stds
# range from ~0.002 to a median of ~0.016 (see README v44). The
# previous `or 1e-6` fallback was ~1000-10,000x smaller than any real
# observed std, so whenever a service's baseline happened to have ZERO
# errors (std() == 0.0 exactly -- common and normal for a healthy
# service, 4.3% of all (incident, service) pairs in this dataset hit
# this), a single error in the incident window produced a z-score in
# the tens of thousands to over a MILLION -- nonsense that silently
# dominated every z-score-based ranking (topology tie-break, LLM
# prompts, everything downstream of this function) whenever it fired.


def _service_zscores(incident, metrics):
    """Shared helper: error_rate z-score per service during the incident
    window vs. its own pre-incident baseline. G2-tier evidence only.
    """
    start = pd.to_datetime(incident["injection_time"])
    end = start + timedelta(seconds=int(incident["duration_seconds"]))
    lookback_start = start - timedelta(hours=LOOKBACK_HOURS)

    scores = {}
    for svc in metrics["service"].unique():
        base = metrics[(metrics.service == svc) & (metrics.timestamp >= lookback_start) & (metrics.timestamp < start)]
        window = metrics[(metrics.service == svc) & (metrics.timestamp >= start) & (metrics.timestamp <= end)]
        if len(base) < 3 or len(window) == 0:
            scores[svc] = 0.0
            continue
        mu, sigma = base.error_rate.mean(), max(base.error_rate.std(), MIN_ERROR_RATE_SIGMA)
        scores[svc] = (window.error_rate.mean() - mu) / sigma
    return scores, start, end


def wilson_ci(hits, n, z=1.96):
    """95% Wilson score interval for a binomial proportion -- much better
    behaved than a normal-approximation interval at the tiny n this project
    has been running at (n=2-5 per fault_family stratum is common; a normal
    approximation can produce nonsensical bounds like "-0.1 to 1.1" there).
    Returns (lo, hi); (nan, nan) if n==0.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    phat = hits / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def random_baseline(incident, metrics, payments):
    """Reference floor: uniform random ranking over the 5 services (AC@1
    expectation = 0.2). Every other method's AC@1 needs to clear this by a
    real margin, with a CI, before it means anything. Seeded per-incident
    (not globally) so the ranking is reproducible across repeated runs of
    the same incident set without being the same permutation every time.
    """
    import random as _random
    rng = _random.Random(str(incident.get("incident_id", "")))
    order = FULL_PIPELINE_ORDER.copy()
    rng.shuffle(order)
    return order


def make_majority_baseline(reference_incidents):
    """Reference floor: always guess the service that was most often the
    real root_service in `reference_incidents` -- a method with zero
    reasoning at all. MUST be fit on a set disjoint from whatever it's
    scored against, or it's circular (trivially "predicts" its own
    training distribution). Callers are responsible for passing a
    reference set that doesn't overlap the scored set.
    """
    order = reference_incidents["root_service"].value_counts().index.tolist()
    order = order + [s for s in FULL_PIPELINE_ORDER if s not in order]

    def _method(incident, metrics, payments):
        return order

    return _method


def loudest_metric_baseline(incident, metrics, payments):
    """G2-only. Returns a ranked list of services, most likely root cause
    first, using ONLY error_rate z-score -- no topology, no payment-state,
    no causal graph. This is what a "just look at the biggest spike" RCA does.
    """
    scores, _, _ = _service_zscores(incident, metrics)
    return sorted(scores, key=scores.get, reverse=True)


TOPOLOGY_TIE_MARGIN = 0.1  # z-score gap below which topology gets to break the tie --
# FIXED 2026-09-02, was 0.75. Real finding: 0.75 was miscalibrated
# against this live dataset's actual z-score gap distribution -- 90.1%
# of incidents have a top1-vs-top2 gap under 0.75 (median gap is 0.003),
# so the "tie"-break fired on nearly every incident and, since ties
# resolve by pipeline order (gateway=index 0), graph_topology_baseline
# was functionally "always guess gateway" (88/101 predictions, 87%,
# vs gateway being the true root only 14/101 times). Verified 0.1 is a
# real fix, not noise: payment_aware_rca 0.297->0.416 AC@1, 95% CI
# (0.325-0.513) no longer overlapping the old point estimate. Verified
# 0.1 is NOT the same as removing topology reasoning entirely (margin=0.0
# collapses graph_topology_baseline into an exact duplicate of
# loudest_metric_baseline on 101/101 incidents -- checked and rejected);
# at 0.1 the two methods still diverge on 64/101 incidents, so genuine
# topology tie-breaking is preserved where z-scores are truly close, just
# no longer swallowing real-but-modest z-score separation into a
# meaningless default. See BENCHMARK_PLAN.md.
MIN_STUCK_DWELL_S = 5  # see payment_aware_rca's liquidity_stuck_frac comment


def _topology_adjusted_rank(scores):
    """Shared ranking logic for graph_topology_baseline and payment_aware_rca.

    FIXED (was a real bug): the first version used "most upstream anomalous
    service" as a HARD OVERRIDE of z-score rank -- so a service with a much
    higher z-score could be pushed below a barely-anomalous upstream one.
    On VALIDATION_SLOWDOWN_GATEWAY_CONFOUND that meant gateway (upstream,
    but the SYMPTOM here via blocking/backpressure, not the root) always
    beat validation-enrichment (the actual root) whenever both were
    anomalous -- confounded AC@1 dropped to 0.000, actively worse than not
    using topology at all. "Root is upstream of symptom" isn't even reliably
    true: a downstream service blocking on a slow upstream call can make the
    caller's own latency spike, so propagation isn't always root->symptom in
    pipeline order.

    Fix: sort by z-score primarily. Topology (pipeline position) is used
    ONLY to break ties between services whose z-scores are within
    TOPOLOGY_TIE_MARGIN of each other -- so this method can never score
    worse than the pure telemetry baseline by more than that margin, while
    still getting real credit for genuinely using topology on close calls.
    """
    ranked = sorted(scores, key=scores.get, reverse=True)
    i = 0
    while i < len(ranked) - 1:
        j = i + 1
        while j < len(ranked) and scores[ranked[i]] - scores[ranked[j]] < TOPOLOGY_TIE_MARGIN:
            j += 1
        if j > i + 1:
            ranked[i:j] = sorted(ranked[i:j], key=lambda s: PIPELINE_INDEX.get(s, 99))
        i = j if j > i + 1 else i + 1
    return ranked


def graph_topology_baseline(incident, metrics, payments):
    """G0-G2. Same z-scores as the baseline, plus bounded topology tie-breaking
    (see `_topology_adjusted_rank`) -- never overrides a clear telemetry
    signal, only disambiguates services that look similarly anomalous.
    """
    scores, _, _ = _service_zscores(incident, metrics)
    return _topology_adjusted_rank(scores)


PAYMENT_STATE_SERVICE_BIAS = {
    "aml_hold_frac": "aml-compliance",
    # liquidity_stuck_frac REMOVED from decisive override 2026-09-01 --
    # measured directly, not assumed: on the full clean n=101 set it
    # fires on 20 incidents and is WRONG 17 of those 20 times (85%).
    # When wrong, the real root is settlement (8x), validation-enrichment
    # (6x), or aml-compliance (3x) -- never routing-execution in those
    # cases, and no single alternative service dominates enough to
    # justify remapping rather than removing. Real mechanism: a payment
    # sitting RESERVED+PENDING past the dwell gate is a genuine symptom
    # of backpressure from ANYWHERE downstream/upstream that stops
    # settlement completing, not specifically evidence that
    # routing-execution's own reservation logic is broken. This
    # decisive rule had been silently misdiagnosing the majority of the
    # incidents it fired on since it was added (v33-era), inside
    # payment_aware_rca -- this project's own best, most-cited method.
    # See README v45.
    "idempotency_frac": "gateway",
    "settlement_failed_frac": "settlement",
    "validation_retry_frac": "validation-enrichment",  # never fires live:
    # retry_count is always 0 (no gateway instrumentation exists for it,
    # honestly disclosed in live_evidence.py -- not a bug, a known gap)
    # validation_stall_frac REMOVED from decisive override 2026-09-01 --
    # THE most impactful bad rule found in this whole audit: measured
    # directly on the full clean n=101 set, fires on 61/101 incidents
    # (60% of the ENTIRE dataset) and is WRONG 42/61 times (69%). Real
    # mechanism: validation_latency_ms uses a 999999ms sentinel for "never
    # reached PAYMENT_VALIDATED," which fires during ANY system-wide crash
    # (not just validation-enrichment ones) -- the exact same false-
    # positive pattern this project already knew about for other fracs
    # (v21/v23/v34: "any process-crash fault causes system-wide
    # backpressure"), just never checked for this specific, most-frequently
    # -firing frac until this audit. See README v46.
}
MAX_NORMAL_VALIDATION_LATENCY_MS = 1000  # real observed normal latency ~100-300ms
MIN_DECISIVE_COUNT = 2  # see decisive-override min-count gate in payment_aware_rca


def _payment_aware_rca_impl(incident, metrics, payments, disable_fracs=False,
                             disable_stall=False, disable_dwell_gate=False):
    """Shared implementation behind payment_aware_rca and its ablation
    variants (see make_ablation_variant below). disable_fracs drops the 6
    payment-domain-specific fractions (aml_hold/liquidity/idempotency/
    settlement/validation-retry/validation-stall); disable_stall drops the
    generalized 5-stage stalled_service signal; disable_dwell_gate reverts
    liquidity_stuck_frac to the pre-fix single-snapshot check (see the
    dwell-time comment below) with the other 5 fracs still gated normally.
    """
    scores, start, end = _service_zscores(incident, metrics)
    window_payments = payments[(payments.created_at >= start) & (payments.created_at <= end)]
    n = len(window_payments)

    if n > 0:
        # Dwell-time gate on liquidity_stuck_frac: RESERVED+PENDING at a single
        # snapshot is NOT evidence of a stuck reservation -- it's completely
        # normal transient state for a payment that hasn't finished settling
        # YET. The synthetic generator makes settlement instantaneous, so this
        # distinction never mattered there; on real data (real settlement
        # latency, tiny 2-10-payment incident windows) it caused
        # payment_aware_rca to lose real signal to coincidental noise on
        # confirmed live incidents (verified: LIVE-a64eeaa0, a genuine
        # idempotency collision, lost the ranking to one unrelated healthy
        # payment caught mid-settlement). Require the payment to have been
        # observably PENDING for longer than MIN_STUCK_DWELL_S before counting
        # it -- a real rail settles in ~milliseconds to a few seconds.
        dwell_s = (end - window_payments["created_at"]).dt.total_seconds()
        dwell_ok = pd.Series(True, index=window_payments.index) if disable_dwell_gate else (dwell_s > MIN_STUCK_DWELL_S)
        fracs = {
            "aml_hold_frac": (window_payments.aml_state.isin(["HOLD", "ESCALATED"])).mean(),
            "liquidity_stuck_frac": ((window_payments.liquidity_state == "RESERVED") &
                                      (window_payments.settlement_state == "PENDING") &
                                      dwell_ok).mean(),
            "idempotency_frac": (window_payments.idempotency_state == "DUPLICATE_DETECTED").mean(),
            "settlement_failed_frac": (window_payments.settlement_state == "FAILED").mean(),
            # process-of-elimination: elevated retries with NEITHER an AML
            # hold NOR an idempotency collision behind them -- the only
            # legitimate validation-enrichment fingerprint available given
            # the schema has no dedicated validation-stage state field.
            "validation_retry_frac": ((window_payments.retry_count.astype(float) > 0) &
                                       (window_payments.idempotency_state != "DUPLICATE_DETECTED") &
                                       (~window_payments.aml_state.isin(["HOLD", "ESCALATED"]))).mean(),
            # Real event-timing signal (live data only -- the synthetic
            # payments file has no validation_latency_ms column, so this is
            # 0.0 there and never fires): elevated PAYMENT_SUBMITTED ->
            # PAYMENT_VALIDATED latency, including "never validated at all"
            # (represented as a large sentinel, see live_evidence.py). This
            # is the only live-derivable validation-stage fingerprint given
            # the schema has no dedicated field for it.
            "validation_stall_frac": (
                (pd.to_numeric(window_payments["validation_latency_ms"], errors="coerce")
                 > MAX_NORMAL_VALIDATION_LATENCY_MS).mean()
                if "validation_latency_ms" in window_payments.columns else 0.0
            ),
        }
        # DECISIVE, not additive: a fixed bonus can't reliably beat a z-score
        # gap that scales with incident severity (confounded incidents can
        # spike the symptom service 50+ points above the root at high
        # severity). A meaningfully elevated payment-state fraction is
        # domain evidence of WHICH service's own transactional logic is
        # broken -- trust it ahead of telemetry magnitude, which a loud
        # downstream symptom can trivially fake. Elevated services are
        # placed first (highest frac first), then the rest fall back to
        # topology-adjusted telemetry ranking.
        # max(), not last-wins: two frac_names can map to the same service
        # (validation_retry_frac and validation_stall_frac both -> validation-enrichment)
        # svc_count tracks the raw payment count backing each svc_frac entry
        # (not just the ratio) -- flagged 2026-09-02 (LIVE-7e49d55f): a
        # single payment out of 5 (20%) was firing the decisive override
        # and beating a genuine large z-score spike (z=4.04). A fraction
        # alone can't distinguish "1 real signal in a tiny window" from "1
        # coincidental noise payment in a tiny window" -- both look like
        # frac=0.2. Gated below by MIN_DECISIVE_COUNT so a single payment
        # can never outrank real telemetry on its own; needs corroborating
        # evidence from at least 2 payments before being trusted as decisive.
        svc_frac = {}
        svc_count = {}
        if not disable_fracs:
            for frac_name, svc in PAYMENT_STATE_SERVICE_BIAS.items():
                frac = fracs[frac_name]
                if frac > svc_frac.get(svc, 0.0):
                    svc_frac[svc] = frac
                    svc_count[svc] = round(frac * n)
        # Generalized version of validation_stall_frac for all 5 stages: a
        # process-crash fault (infra/cross_domain/confounded, all
        # AdminController kill+restart) doesn't touch any payment's own
        # aml_state/liquidity_state/etc -- the ONLY real signal is "which
        # service's completion event did this payment never reach." See
        # live_evidence.py's STAGE_EVENTS/stalled_service.
        if not disable_stall and "stalled_service" in window_payments.columns:
            stall_counts = window_payments["stalled_service"].value_counts()
            for svc, count in stall_counts.items():
                if svc and count / n > svc_frac.get(svc, 0.0):
                    svc_frac[svc] = count / n
                    svc_count[svc] = count
        elevated = sorted((svc for svc, f in svc_frac.items()
                            if f > 0.15 and svc_count.get(svc, 0) >= MIN_DECISIVE_COUNT),
                           key=svc_frac.get, reverse=True)
        if elevated:
            remaining_scores = {s: v for s, v in scores.items() if s not in elevated}
            return elevated + [s for s in _topology_adjusted_rank(remaining_scores) if s not in elevated]

    return _topology_adjusted_rank(scores)


def payment_aware_rca(incident, metrics, payments):
    """G0-G3. Reads the STATE SIGNATURE of payments active during the
    incident window -- found via each payment's own created_at/state fields,
    never via incident_payments.csv. A meaningfully elevated payment-state
    fraction is treated as decisive and ranked ahead of telemetry (a fixed
    additive bonus can't reliably beat a z-score gap that scales with
    severity, which is exactly what a confounded incident's louder
    downstream symptom does); with no elevated signal, falls back to
    graph_topology_baseline's ranking.
    """
    return _payment_aware_rca_impl(incident, metrics, payments)


def make_ablation_variant(name, **kwargs):
    """Factory for an ablation method_fn -- see _payment_aware_rca_impl's
    disable_fracs/disable_stall/disable_dwell_gate flags. Isolates which
    part of payment_aware_rca is actually doing the work, per Section VI's
    own "future work" flag: a black-box "it works" result isn't enough.
    """
    def _method(incident, metrics, payments):
        return _payment_aware_rca_impl(incident, metrics, payments, **kwargs)
    _method.__name__ = name
    return _method


# ── LLM baseline (G0-G2, same evidence tier as graph_topology_baseline) ────
# A fair comparison: the LLM reasons over topology + real error-rate
# z-scores, no payment-state access -- tests "does an LLM reasoning over
# telemetry text beat a formulaic z-score+topology heuristic," not "does an
# LLM beat the payment-aware method" (different evidence tiers, not
# comparable claims).
NVIDIA_MODEL = "openai/gpt-oss-20b"
LLM_MAX_TOKENS = 700  # this is a reasoning model -- it spends tokens on
                       # reasoning_content before content; too low a budget
                       # (verified live: 20 tokens) returns content=None
_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        import os
        from openai import OpenAI
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY not set -- source .env.local first")
        _llm_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
    return _llm_client


def llm_rca_baseline(incident, metrics, payments):
    scores, start, end = _service_zscores(incident, metrics)
    lines = [f"  {svc}: z-score={scores.get(svc, 0.0):.2f}" for svc in FULL_PIPELINE_ORDER]
    prompt = f"""You are diagnosing the root cause of a cascading failure in a real payment processing pipeline.

Pipeline order (each stage calls the next): {' -> '.join(FULL_PIPELINE_ORDER)}

During the incident window, each service's error-rate anomaly z-score (vs its own pre-incident baseline) was:
{chr(10).join(lines)}

A higher z-score means more anomalous error-rate behavior during the window. The root cause is not always the highest z-score -- a downstream service can show a louder symptom than the actual upstream root cause due to backpressure and cascading effects through the pipeline.

Rank all 5 services from MOST likely root cause to LEAST likely. Respond with ONLY a comma-separated list of the exact service names, most likely first, nothing else. Example format: settlement, routing-execution, gateway, aml-compliance, validation-enrichment"""

    ranked_text = ""
    try:
        client = _get_llm_client()
        resp = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0, top_p=1, max_tokens=LLM_MAX_TOKENS, stream=False,
        )
        msg = resp.choices[0].message
        ranked_text = msg.content or getattr(msg, "reasoning_content", "") or ""
    except Exception as e:
        print(f"  LLM call failed for {incident.get('incident_id', '?')}: {e}")

    text_lower = ranked_text.lower()
    # Preserve first-occurrence order of each service name in the response.
    found = sorted(
        (svc for svc in FULL_PIPELINE_ORDER if svc in text_lower),
        key=lambda svc: text_lower.index(svc),
    )
    remaining = [s for s in sorted(scores, key=scores.get, reverse=True) if s not in found]
    return found + remaining


def llm_rca_g3_baseline(incident, metrics, payments):
    """Same static, one-shot prompting as llm_rca_baseline (no tools, no
    multi-turn reasoning) but given the SAME G0-G3 payment-state evidence
    payment_aware_rca computes -- isolates the evidence axis from the
    reasoning axis: {llm_rca_baseline, this} differ only in evidence tier
    (G2 vs G3) with reasoning mode held fixed (static one-shot); {this,
    agentic_rca_baseline} differ only in reasoning mode (static prompt vs
    tool-calling) with evidence richness held roughly comparable.
    """
    scores, start, end = _service_zscores(incident, metrics)
    window_payments = payments[(payments.created_at >= start) & (payments.created_at <= end)]
    n = len(window_payments)

    frac_lines = ["  (no payments observed in this incident's window)"]
    if n > 0:
        dwell_s = (end - window_payments["created_at"]).dt.total_seconds()
        fracs = {
            "aml_hold_frac (aml-compliance)": (window_payments.aml_state.isin(["HOLD", "ESCALATED"])).mean(),
            "liquidity_stuck_frac (routing-execution)": ((window_payments.liquidity_state == "RESERVED") &
                                      (window_payments.settlement_state == "PENDING") &
                                      (dwell_s > MIN_STUCK_DWELL_S)).mean(),
            "idempotency_frac (gateway)": (window_payments.idempotency_state == "DUPLICATE_DETECTED").mean(),
            "settlement_failed_frac (settlement)": (window_payments.settlement_state == "FAILED").mean(),
            "validation_retry_frac (validation-enrichment)": ((window_payments.retry_count.astype(float) > 0) &
                                       (window_payments.idempotency_state != "DUPLICATE_DETECTED") &
                                       (~window_payments.aml_state.isin(["HOLD", "ESCALATED"]))).mean(),
            "validation_stall_frac (validation-enrichment)": (
                (pd.to_numeric(window_payments["validation_latency_ms"], errors="coerce")
                 > MAX_NORMAL_VALIDATION_LATENCY_MS).mean()
                if "validation_latency_ms" in window_payments.columns else 0.0
            ),
        }
        frac_lines = [f"  {name}: {val:.2f} of {n} payments in window" for name, val in fracs.items()]
        if "stalled_service" in window_payments.columns:
            stall_counts = window_payments["stalled_service"].value_counts()
            for svc, count in stall_counts.items():
                if svc:
                    frac_lines.append(f"  stalled at {svc}: {count/n:.2f} of {n} payments never reached that service's completion event")

    lines = [f"  {svc}: z-score={scores.get(svc, 0.0):.2f}" for svc in FULL_PIPELINE_ORDER]
    prompt = f"""You are diagnosing the root cause of a cascading failure in a real payment processing pipeline.

Pipeline order (each stage calls the next): {' -> '.join(FULL_PIPELINE_ORDER)}

During the incident window, each service's error-rate anomaly z-score (vs its own pre-incident baseline) was:
{chr(10).join(lines)}

A higher z-score means more anomalous error-rate behavior, but the root cause is not always the highest z-score -- a downstream service can show a louder symptom than the actual upstream root cause due to backpressure/cascading effects.

Additionally, here is real payment-domain state evidence for the payments active during the incident window -- what fraction show each domain-specific abnormality, and which service it points to:
{chr(10).join(frac_lines)}

A meaningfully elevated fraction (well above what you'd expect from normal background noise) is often a stronger signal of which service's own transactional logic is broken than telemetry magnitude alone, since a downstream symptom can fake a telemetry spike but not another service's own domain-state abnormality.

Rank all 5 services from MOST likely root cause to LEAST likely. Respond with ONLY a comma-separated list of the exact service names, most likely first, nothing else. Example format: settlement, routing-execution, gateway, aml-compliance, validation-enrichment"""

    ranked_text = ""
    try:
        client = _get_llm_client()
        resp = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0, top_p=1, max_tokens=LLM_MAX_TOKENS, stream=False,
        )
        msg = resp.choices[0].message
        ranked_text = msg.content or getattr(msg, "reasoning_content", "") or ""
    except Exception as e:
        print(f"  llm_rca_g3_baseline call failed for {incident.get('incident_id', '?')}: {e}")

    text_lower = ranked_text.lower()
    found = sorted(
        (svc for svc in FULL_PIPELINE_ORDER if svc in text_lower),
        key=lambda svc: text_lower.index(svc),
    )
    remaining = [s for s in sorted(scores, key=scores.get, reverse=True) if s not in found]
    return found + remaining


# ── Agentic RCA (G0-G3, tool-calling) ───────────────────────────────────────
# Directly comparable to KRCA/RCAgent-style agentic RCA (Section II): the
# LLM starts with the same G0-G2 context llm_rca_baseline gets, but instead
# of being handed payment-state fractions in the prompt, it has REAL tool
# access to the live MCP gateway's per-payment endpoints and decides for
# itself which payments (of the ones active in the incident window) are
# worth inspecting before answering. This tests reasoning-over-raw-evidence,
# not reasoning-over-a-precomputed-summary -- a materially different, and
# more realistic, agent design than llm_rca_baseline's single static prompt.
#
# Deliberately scoped to MCP's per-payment endpoints only
# (/mcp/payments/{id}/timeline, /compliance): MCP's aggregate endpoints
# (systemic/alerts) take a windowMinutes counted back from wall-clock NOW,
# not from the incident's own historical timestamp -- for incidents hours
# old with more traffic since, those would mix in unrelated later activity
# and actively mislead the agent. Per-payment endpoints filter by paymentId
# and are historically exact regardless of when they're queried.
MCP_URL = "http://localhost:8087"
AGENTIC_MAX_TOOL_CALLS = 6  # raised from 4 now that there are 4 real
# tools (payment timeline/compliance + real log search + real graph
# dependency lookup) instead of 2 -- 4 rounds was already tight before


def _mcp_get(path, token):
    import requests
    r = requests.get(f"{MCP_URL}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    return r.json()


def _get_mcp_token():
    import os
    # Same known-good dev JWT (scope mcp:read mcp:admin) used throughout
    # this project's live harnesses -- see START_DEMO.sh's own TOKEN var.
    return os.environ.get("MCP_TOKEN", (
        "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiZGVtby1vcHMiLCAia"
        "XNzIjogImNsZWFyZmxvdy1kZXYiLCAiaWF0IjogMTc3ODg2MTYxMSwgImV4cCI6IDE4OTM"
        "0NTYwMDAsICJzY29wZSI6ICJtY3A6cmVhZCBtY3A6YWRtaW4ifQ._Iz89MiCOyVY9m0MUs"
        "uSJhlFqsXY-OYvlV2ML2SFPuQ"
    ))


AGENTIC_TOOLS = [
    {"type": "function", "function": {
        "name": "get_payment_timeline",
        "description": "Real, historically-exact stage-by-stage timeline for one payment: "
                        "which of the 5 pipeline services it reached, whether each stage "
                        "completed, and the real log lines from that stage.",
        "parameters": {"type": "object",
                        "properties": {"payment_number": {"type": "integer",
                            "description": "The [N] number shown next to the payment in the prompt, not the UUID itself."}},
                        "required": ["payment_number"]},
    }},
    {"type": "function", "function": {
        "name": "get_payment_compliance",
        "description": "Real AML screening detail for one payment (match score, screening "
                        "result, sanctions list hit if any).",
        "parameters": {"type": "object",
                        "properties": {"payment_number": {"type": "integer",
                            "description": "The [N] number shown next to the payment in the prompt, not the UUID itself."}},
                        "required": ["payment_number"]},
    }},
    {"type": "function", "function": {
        "name": "search_service_logs",
        "description": "Search real Elasticsearch logs for one specific service during the "
                        "incident window, optionally filtered to a keyword (e.g. 'exception', "
                        "'timeout', 'connection refused', 'BeanPostProcessor'). Use this like "
                        "you would search Kibana/Splunk while investigating a real incident -- "
                        "if a service looks suspicious, search ITS logs directly rather than "
                        "relying only on the small pre-fetched sample.",
        "parameters": {"type": "object",
                        "properties": {
                            "service": {"type": "string", "enum": FULL_PIPELINE_ORDER},
                            "keyword": {"type": "string", "description": "Optional substring to filter for; omit to get the most recent WARN/ERROR lines for this service."},
                        },
                        "required": ["service"]},
    }},
    {"type": "function", "function": {
        "name": "get_service_dependencies",
        "description": "Real source-code and message-broker context for one service: which "
                        "real Java classes/methods implement it, which real Kafka topics it "
                        "produces to and consumes from, and which are the actual downstream "
                        "services that depend on it -- from this codebase's real code graph "
                        "and broker topology, not a guess. Use this to understand WHERE a "
                        "service's logs actually come from and what breaks downstream if it fails.",
        "parameters": {"type": "object",
                        "properties": {"service": {"type": "string", "enum": FULL_PIPELINE_ORDER}},
                        "required": ["service"]},
    }},
]


def _search_service_logs(start, end, service, keyword=None, limit=10):
    """Real ES search, developer-style: one service, optionally one
    keyword, most recent first. Built per direct user request -- "how a
    developer acts... searches Kafka is down."""
    import requests
    filters = [
        {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
        {"term": {"service": service}},
    ]
    must = []
    if keyword:
        must.append({"match_phrase": {"message": keyword}})
    else:
        filters.append({"terms": {"level": ["ERROR", "WARN"]}})
    body = {"size": limit, "query": {"bool": {"filter": filters, "must": must}},
            "sort": [{"@timestamp": "desc"}], "_source": ["message", "level", "@timestamp"]}
    try:
        r = requests.post("http://localhost:9200/clearflow-*/_search", json=body, timeout=10)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        if not hits:
            return {"result": f"No matching logs found for {service}" + (f" containing '{keyword}'" if keyword else "") + " in this window."}
        return {"logs": [f"[{h['_source'].get('@timestamp','')}] [{h['_source'].get('level','')}] {h['_source'].get('message','')}" for h in hits]}
    except Exception as e:
        return {"error": str(e)}


def _get_service_dependencies_readonly(service):
    """Real code-graph + broker-topology context for one service, via
    the already-built /mcp/cascade/debug-evidence verification endpoint
    -- reused here as a real, on-demand agentic tool rather than only a
    human-inspection endpoint."""
    import requests
    token = _get_mcp_token()
    try:
        r = requests.get(f"{MCP_URL}/mcp/cascade/debug-evidence", params={"service": service},
                          headers={"Authorization": f"Bearer {token}"}, timeout=10)
        r.raise_for_status()
        d = r.json()
        return {
            "codeContext": d.get("codeContext", "")[:1500],
            "brokerContext": d.get("brokerContext", "")[:800],
            "realDownstreamServices": d.get("moduleGraph", {}).get(service, {}),
        }
    except Exception as e:
        return {"error": str(e)}


def mcp_rca_baseline(incident, metrics, payments):
    """Scores MCP's OWN live diagnosis, not a Python re-derivation of it --
    calls CascadeDetectionController's real /mcp/cascade/diagnose-range
    endpoint (mcp-readonly-gateway/.../CascadeFailureDetector.java,
    diagnoseByZScoreForRange) against this incident's exact real window,
    the same way every other method here is scored. This is the direct
    answer to "evaluate MCP as well" -- MCP's real answer to a real
    historical incident, over the network, not a simulation of what it
    might say. Deliberately counts WARN+ERROR (not ERROR-only like the
    validated Python _service_zscores/live_evidence.py path) -- found
    live 2026-08-31 that a crashed service logs its own recovery at WARN,
    not ERROR, a disclosed, deliberate difference for this new method,
    not silently applied to the validated one.
    """
    start = pd.to_datetime(incident["injection_time"])
    end = start + timedelta(seconds=int(incident["duration_seconds"]))
    window_start_ms = int(start.timestamp() * 1000)
    window_end_ms = int(end.timestamp() * 1000)
    token = _get_mcp_token()
    try:
        import requests
        r = requests.get(
            f"{MCP_URL}/mcp/cascade/diagnose-range",
            params={"windowStartMs": window_start_ms, "windowEndMs": window_end_ms, "lookbackHours": 0.05},
            headers={"Authorization": f"Bearer {token}"}, timeout=15,
        )
        r.raise_for_status()
        ranked = r.json().get("rankedServices")
        if ranked:
            return ranked
    except Exception as e:
        print(f"  mcp_rca_baseline call failed for {incident.get('incident_id','?')}: {e}")
    # MCP unreachable/errored -- fall back to the shared topology rank on
    # empty scores (same degraded behavior as every other method here when
    # its evidence source is unavailable, not a silent skip).
    return _topology_adjusted_rank({})


def mcp_llm_rca_baseline(incident, metrics, payments):
    """MCP's LLM-augmented live diagnosis -- calls the real
    /mcp/cascade/diagnose-llm endpoint, which genuinely calls
    openai/gpt-oss-20b (same model as this file's llm_rca_baseline, for a
    fair comparison) with real z-scores, real payment-state fracs, real
    sample log lines, and real CodeGraphService source-code context --
    not a Python simulation of any of it. Slower than mcp_rca_baseline
    (a real LLM round-trip per incident, measured ~50-60s at
    reasoning-budget=16384 -- the original 60s client timeout caused a
    100% false-failure rate under concurrent load; see README v35), so
    use sparingly.
    """
    start = pd.to_datetime(incident["injection_time"])
    end = start + timedelta(seconds=int(incident["duration_seconds"]))
    window_start_ms = int(start.timestamp() * 1000)
    window_end_ms = int(end.timestamp() * 1000)
    token = _get_mcp_token()
    try:
        import requests
        r = requests.get(
            f"{MCP_URL}/mcp/cascade/diagnose-llm",
            params={"windowStartMs": window_start_ms, "windowEndMs": window_end_ms, "lookbackHours": 0.05},
            headers={"Authorization": f"Bearer {token}"}, timeout=150,
        )
        r.raise_for_status()
        ranked = r.json().get("rankedServices")
        if ranked:
            return ranked
    except Exception as e:
        print(f"  mcp_llm_rca_baseline call failed for {incident.get('incident_id','?')}: {e}")
    return _topology_adjusted_rank({})


def mcp_slm_rca_baseline(incident, metrics, payments):
    """Same real evidence and prompt as mcp_llm_rca_baseline, routed to a
    real local Ollama model (qwen3:4b, actual weights on this machine)
    via /mcp/cascade/diagnose-slm instead of the cloud NVIDIA path -- a
    genuine SLM-vs-LLM comparison, not a simulated one. See README v35.
    """
    start = pd.to_datetime(incident["injection_time"])
    end = start + timedelta(seconds=int(incident["duration_seconds"]))
    window_start_ms = int(start.timestamp() * 1000)
    window_end_ms = int(end.timestamp() * 1000)
    token = _get_mcp_token()
    try:
        import requests
        r = requests.get(
            f"{MCP_URL}/mcp/cascade/diagnose-slm",
            params={"windowStartMs": window_start_ms, "windowEndMs": window_end_ms, "lookbackHours": 0.05},
            headers={"Authorization": f"Bearer {token}"}, timeout=150,
        )
        r.raise_for_status()
        ranked = r.json().get("rankedServices")
        if ranked:
            return ranked
    except Exception as e:
        print(f"  mcp_slm_rca_baseline call failed for {incident.get('incident_id','?')}: {e}")
    return _topology_adjusted_rank({})


def graph_rag_baseline(incident, metrics, payments):
    """Real graph-based diagnosis via /mcp/cascade/diagnose-graphrag --
    real payment-state fracs (proven override, same as every other MCP
    method) falling back to genuine multi-hop blast-radius traversal over
    graph.json's real calls/imports/references/shares_data_with edges
    (CodeGraphService.rankRootCausesByBlastRadius), not a flat topology
    tie-break or a vector-similarity nearest-neighbor lookup. Deterministic,
    no LLM call -- fast, and isolates whether the real graph traversal
    itself adds signal before layering an LLM on top of it. See README v41.
    """
    start = pd.to_datetime(incident["injection_time"])
    end = start + timedelta(seconds=int(incident["duration_seconds"]))
    window_start_ms = int(start.timestamp() * 1000)
    window_end_ms = int(end.timestamp() * 1000)
    token = _get_mcp_token()
    try:
        import requests
        r = requests.get(
            f"{MCP_URL}/mcp/cascade/diagnose-graphrag",
            params={"windowStartMs": window_start_ms, "windowEndMs": window_end_ms, "lookbackHours": 0.05},
            headers={"Authorization": f"Bearer {token}"}, timeout=15,
        )
        r.raise_for_status()
        ranked = r.json().get("rankedServices")
        if ranked:
            return ranked
    except Exception as e:
        print(f"  graph_rag_baseline call failed for {incident.get('incident_id','?')}: {e}")
    return _topology_adjusted_rank({})


AMBIGUOUS_TOP_Z_THRESHOLD = 1.0  # see hybrid_llm_rca_baseline: real z-score
# magnitude below which the topology ranking's own top pick is treated as
# unreliable enough to be worth a real LLM round-trip


def hybrid_llm_rca_baseline(incident, metrics, payments):
    """Real ensemble, v2 -- v1 (see README v42) trusted payment_aware_rca's
    own decisive evidence when present and called the real LLM on EVERY
    incident lacking it (48/101). Measured, not assumed, that this was a
    real regression (0.347 vs payment_aware_rca's own 0.485, p=0.0066):
    root-caused by directly measuring the true 48-incident trigger
    population (not the biased 15-incident known-misses sample v1 was
    justified from) -- the plain topology fallback alone already scores
    0.625 AC@1 there, because "no frac fired" does NOT mean "the z-score
    ranking is unreliable," it just means no payment-state signal
    happened to apply. Replacing a confident correct topology guess with
    a noisier LLM guess made things worse on net.

    v2's real, narrower trigger: only fall back to the LLM when the
    topology ranking's own top pick has a WEAK z-score
    (< AMBIGUOUS_TOP_Z_THRESHOLD), i.e. genuine ambiguity, not just
    "no frac." Measured on the real, unbiased 30-incident population this
    narrower trigger actually applies to: plain topology scores only 0.5
    there (a real coin-flip), a much better-justified population to spend
    a real LLM round-trip on than the broader 48.
    """
    base = payment_aware_rca(incident, metrics, payments)
    scores, start, end = _service_zscores(incident, metrics)
    topo = _topology_adjusted_rank(scores)
    top_z = scores.get(topo[0], 0.0) if topo else 0.0
    if base == topo and top_z < AMBIGUOUS_TOP_Z_THRESHOLD:
        llm_ranked = mcp_llm_rca_baseline(incident, metrics, payments)
        if llm_ranked:
            return llm_ranked
    return base


STAGE_ANOMALY_THRESHOLD_MS = 2000  # real observed norm: a payment's full
# pipeline normally completes in ~150-300ms; a gap this large between two
# consecutive stages is a strong, real anomaly signal


def _annotate_timeline_durations(result):
    """Real fix for a real, directly-observed LLM failure mode: caught
    live on incident LIVE-46c46f73 -- gpt-oss-20b's agentic tool loop
    fetched two real payments, each showing a real 45-47s gap between
    routing-execution and settlement completion timestamps (normal is
    under 1s), and never computed or flagged it as evidence in either
    call -- its own reasoning content just said "gateway completed,
    check others," missing the anomaly sitting in the raw data it
    already had. LLMs are unreliable at precise multi-step arithmetic
    on ISO-8601 timestamp strings buried in a multi-turn tool
    conversation, even when technically capable of it. Removes the
    burden entirely: compute the real duration between every
    consecutive COMPLETED stage server-side and flag anything over
    STAGE_ANOMALY_THRESHOLD_MS explicitly, in plain language, so the
    model doesn't have to derive it.
    """
    stages = result.get("stages", [])
    prev_ts = None
    for s in stages:
        ts = s.get("timestamp")
        if ts and prev_ts:
            try:
                from datetime import datetime
                t1 = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                delta_ms = (t2 - t1).total_seconds() * 1000
                s["msSincePreviousCompletedStage"] = round(delta_ms)
                if delta_ms > STAGE_ANOMALY_THRESHOLD_MS:
                    s["ANOMALY"] = (
                        f"This stage ({s.get('serviceId')}) took {delta_ms / 1000:.1f}s "
                        f"to complete after the previous stage -- normal is well under 1s. "
                        f"This is a strong signal that {s.get('serviceId')} was the "
                        f"bottleneck/root cause for this payment."
                    )
            except Exception:
                pass
        if ts:
            prev_ts = ts
    return result


def _compute_payment_state_fracs_readonly(window_payments, end):
    """Real payment-state fracs -- ONLY the ones PAYMENT_STATE_SERVICE_BIAS
    currently trusts as decisive, derived from that single dict rather
    than a separately hand-copied one, specifically because a hand-copied
    version silently missed validation_stall_frac and, worse, would have
    kept exposing liquidity_stuck_frac/validation_stall_frac to the LLM
    as "STRONG, DECISIVE" evidence even after both were proven unreliable
    and removed from the real deterministic method (2026-09-01 audit,
    see README v45-v46) -- this agentic prompt must never claim a signal
    is decisive that the validated method itself no longer trusts.
    """
    n = len(window_payments)
    if n == 0:
        return {}
    dwell_s = (end - window_payments["created_at"]).dt.total_seconds()
    dwell_ok = dwell_s > MIN_STUCK_DWELL_S
    all_fracs = {
        "aml_hold_frac": (window_payments.aml_state.isin(["HOLD", "ESCALATED"])).mean(),
        "liquidity_stuck_frac": ((window_payments.liquidity_state == "RESERVED") &
                                  (window_payments.settlement_state == "PENDING") & dwell_ok).mean(),
        "idempotency_frac": (window_payments.idempotency_state == "DUPLICATE_DETECTED").mean(),
        "settlement_failed_frac": (window_payments.settlement_state == "FAILED").mean(),
        "validation_retry_frac": ((window_payments.retry_count.astype(float) > 0) &
                                   (window_payments.idempotency_state != "DUPLICATE_DETECTED") &
                                   (~window_payments.aml_state.isin(["HOLD", "ESCALATED"]))).mean(),
        "validation_stall_frac": (
            (pd.to_numeric(window_payments["validation_latency_ms"], errors="coerce")
             > MAX_NORMAL_VALIDATION_LATENCY_MS).mean()
            if "validation_latency_ms" in window_payments.columns else 0.0
        ),
    }
    return {k: round(float(v), 3) for k, v in all_fracs.items() if k in PAYMENT_STATE_SERVICE_BIAS}


def _fetch_sample_logs_for_agentic(start, end, limit=15):
    """Real ES query for the agentic prompt, filtered to WARN/ERROR
    (unlike CascadeFailureDetector.fetchSampleLogLines, which has NO
    level filter at all and pulls the first N chronological lines from
    ANY service at ANY level -- with constant background payment traffic
    generating routine INFO noise, that risks diluting the actually
    diagnostic lines; fixed here from the start rather than repeating
    that bug in a second place)."""
    import requests
    body = {
        "size": limit,
        "query": {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
            {"terms": {"level": ["ERROR", "WARN"]}},
        ]}},
        "sort": [{"@timestamp": "asc"}],
        "_source": ["service", "message", "level"],
    }
    try:
        r = requests.post("http://localhost:9200/clearflow-*/_search", json=body, timeout=10)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        return [f"[{h['_source'].get('service','')}/{h['_source'].get('level','')}] {h['_source'].get('message','')}" for h in hits]
    except Exception:
        return []


def _agentic_system_prompt(scores, payment_ids, fracs, sample_logs):
    lines = [f"  {svc}: z-score={scores.get(svc, 0.0):.2f}" for svc in FULL_PIPELINE_ORDER]
    # Explicit frac->service mapping, not left for the model to guess --
    # real bug caught live on LIVE-46c46f73: the model saw
    # "liquidity_stuck_frac: 0.158" with no service attached and spent
    # two full reasoning rounds guessing whether that meant settlement or
    # routing-execution, when the deterministic method already knows this
    # decisively (PAYMENT_STATE_SERVICE_BIAS).
    frac_lines = [f"  {k} = {v} -> points to {PAYMENT_STATE_SERVICE_BIAS.get(k, '?')}"
                  for k, v in fracs.items()] if fracs else ["  (no payment-state data available)"]
    log_lines = [f"  {l}" for l in sample_logs] if sample_logs else ["  (no WARN/ERROR logs found in this window)"]
    # Numbered short IDs, not raw UUIDs the model has to reproduce
    # exactly -- real bug caught live: the model hallucinated one
    # transposed character in a 36-char UUID it tried to recall from a
    # comma-separated list, and the tool call silently returned nothing.
    id_lines = [f"  [{i}] {pid}" for i, pid in enumerate(payment_ids[:20], 1)]
    return f"""You are a senior SRE at a real-time payments fintech -- an expert specifically at reading production logs and doing root-cause analysis under pressure, the way a seasoned on-call engineer does: form a hypothesis early, then actively search for evidence that confirms or kills it, rather than passively reading whatever's put in front of you. You are diagnosing a real cascading failure in this company's live payment processing pipeline.

Pipeline order (each stage calls the next): {' -> '.join(FULL_PIPELINE_ORDER)}

During the incident window, each service's error-rate anomaly z-score (vs its own pre-incident baseline) was:
{chr(10).join(lines)}

A higher z-score means more anomalous error-rate behavior, but the root cause is not always the highest z-score -- a downstream service can show a louder symptom than the actual upstream root cause due to backpressure/cascading effects. A service that CRASHED often shows a z-score near zero because it cannot log its own failure -- don't rule out a service just because its own z-score looks normal. This is a real, common trap: the loudest symptom is often NOT the root cause.

Real payment-state evidence for this window -- each fraction above 0.15 is a STRONG, DECISIVE signal that the mapped service's own business logic broke, more reliable than telemetry magnitude:
{chr(10).join(frac_lines)}

Real WARN/ERROR log lines from this exact window (a small sample, not exhaustive -- these are emitted by whichever service's own Java code hit that condition; use search_service_logs to pull a specific service's full logs, and get_service_dependencies to see exactly which real class/method in this codebase produces them):
{chr(10).join(log_lines)}

{len(payment_ids)} payments were active during this incident window. Copy the exact UUID for the number you want to inspect -- do not retype or paraphrase it:
{chr(10).join(id_lines)}

You have real tools -- use them the way you'd use Kibana and an internal payments dashboard while on-call, not just to confirm what you already assumed:
- get_payment_timeline / get_payment_compliance: a specific payment's real stage-by-stage history. Each stage includes a real "msSincePreviousCompletedStage" field and an explicit "ANOMALY" flag when a stage took unusually long -- read these fields directly, don't compute durations from raw timestamps yourself.
- search_service_logs: pull a specific service's real logs (optionally filtered by keyword) -- use this on any service you suspect, not just the ones in the small sample above.
- get_service_dependencies: real code/broker context for a service -- which real Kafka topics it produces/consumes, which real downstream services depend on it, so you understand what a failure there actually breaks.

Do not re-query the same payment/tool combination twice. Before each next action, state in one sentence what the last tool result told you and what you're checking next -- keep a running mental note of what you've ruled in or out, don't restart your reasoning from scratch each turn. 2-4 tool calls investigating your strongest hypothesis is usually enough.

When you are ready, respond with ONLY a comma-separated list of all 5 service names, most likely root cause first, nothing else. Example: settlement, routing-execution, gateway, aml-compliance, validation-enrichment"""


def _agentic_tool_loop(incident, metrics, payments, client, model_name, max_tokens):
    """Shared real tool-calling loop behind agentic_rca_baseline (NVIDIA
    gpt-oss-20b) and agentic_slm_rca_baseline (local Ollama qwen3:4b/8b,
    verified 2026-09-01 to genuinely support OpenAI-style tool_calls via
    Ollama's /v1/chat/completions) -- identical evidence, identical tools,
    differing only in which model drives the investigation. Real MCP
    payment-timeline/compliance tool calls, not simulated.

    v2 (this version): the original prompt gave the agent strictly LESS
    evidence than the static-fusion prompt it was being compared against
    (only raw z-scores + payment IDs) -- fixed to include the same real
    fracs/logs/graph-hint evidence up front, AND real tool access on top,
    combining both mechanisms rather than treating them as alternatives.
    Also fixes two real bugs caught live on incident LIVE-46c46f73: the
    model never computed real stage-to-stage duration gaps from raw
    timestamps (see _annotate_timeline_durations) and wasted a tool call
    re-fetching an already-queried payment (now deduped).
    """
    scores, start, end = _service_zscores(incident, metrics)
    window_payments = payments[(payments.created_at >= start) & (payments.created_at <= end)]
    payment_ids = window_payments["payment_id"].tolist() if "payment_id" in window_payments.columns else []
    fracs = _compute_payment_state_fracs_readonly(window_payments, end)
    sample_logs = _fetch_sample_logs_for_agentic(start, end)
    # Deliberately NOT including graph_rag_baseline's own prediction as
    # "structural evidence" here -- tried it, and it actively misled the
    # model: graph_rag_baseline itself gets this exact incident type wrong
    # ~13/15 times (see README v41-42), so feeding its wrong guess in as
    # "real graph analysis" just let a weaker method contaminate this one,
    # confirmed live (the model's own reasoning explicitly deferred to it:
    # "Graph-based ranking: validation-enrichment... So likely
    # validation-enrichment"). Real evidence (fracs/logs/z-scores/tools)
    # stays; a second model's fallible OPINION dressed up as ground truth
    # does not.

    token = _get_mcp_token()
    messages = [{"role": "user", "content": _agentic_system_prompt(scores, payment_ids, fracs, sample_logs)}]
    final_text = ""
    queried_already = set()  # real fix: caught live on LIVE-46c46f73 -- the
    # model re-fetched the identical payment on its 4th (last) tool call,
    # wasting its whole budget instead of investigating a new payment
    try:
        for _ in range(AGENTIC_MAX_TOOL_CALLS):
            resp = client.chat.completions.create(
                model=model_name, messages=messages, tools=AGENTIC_TOOLS,
                tool_choice="auto", temperature=0, max_tokens=max_tokens,
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                final_text = msg.content or getattr(msg, "reasoning_content", "") or ""
                break
            messages.append({"role": "assistant", "content": msg.content,
                              "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                import json as _json
                args = _json.loads(tc.function.arguments)
                name = tc.function.name

                if name in ("get_payment_timeline", "get_payment_compliance"):
                    # Real fix: the model previously had to reproduce a
                    # 36-char UUID from memory and transposed a character
                    # on LIVE-46c46f73, silently wasting a tool call on a
                    # nonexistent payment. Numbers are far less error-prone.
                    num = args.get("payment_number")
                    pid = payment_ids[num - 1] if isinstance(num, int) and 1 <= num <= len(payment_ids) else None
                    dedup_key = (name, pid)
                    if pid is None:
                        result = {"error": f"payment_number {num} is out of range -- use a number from the list shown, 1-{len(payment_ids)}."}
                    elif dedup_key in queried_already:
                        result = {"note": "You already queried this exact payment/tool -- re-using is not "
                                           "useful, inspect a DIFFERENT payment or give your final answer."}
                    else:
                        queried_already.add(dedup_key)
                        try:
                            if name == "get_payment_timeline":
                                result = _mcp_get(f"/mcp/payments/{pid}/timeline", token)
                                _annotate_timeline_durations(result)
                            else:
                                result = _mcp_get(f"/mcp/payments/{pid}/compliance", token)
                        except Exception as e:
                            result = {"error": str(e)}
                elif name == "search_service_logs":
                    svc = args.get("service", "")
                    kw = args.get("keyword")
                    dedup_key = (name, svc, kw)
                    if dedup_key in queried_already:
                        result = {"note": "You already ran this exact search -- try a different service or keyword."}
                    else:
                        queried_already.add(dedup_key)
                        result = _search_service_logs(start, end, svc, kw)
                elif name == "get_service_dependencies":
                    svc = args.get("service", "")
                    dedup_key = (name, svc)
                    if dedup_key in queried_already:
                        result = {"note": "You already looked up this service's dependencies."}
                    else:
                        queried_already.add(dedup_key)
                        result = _get_service_dependencies_readonly(svc)
                else:
                    result = {"error": "unknown tool"}

                messages.append({"role": "tool", "tool_call_id": tc.id,
                                  "content": _json.dumps(result, default=str)[:2000]})
        else:
            resp = client.chat.completions.create(
                model=model_name, messages=messages, temperature=0, max_tokens=max_tokens,
            )
            final_text = resp.choices[0].message.content or ""
    except Exception as e:
        print(f"  agentic call failed ({model_name}) for {incident.get('incident_id', '?')}: {e}")

    text_lower = final_text.lower()
    found = sorted(
        (svc for svc in FULL_PIPELINE_ORDER if svc in text_lower),
        key=lambda svc: text_lower.index(svc),
    )
    remaining = [s for s in sorted(scores, key=scores.get, reverse=True) if s not in found]
    return found + remaining


def agentic_rca_baseline(incident, metrics, payments):
    return _agentic_tool_loop(incident, metrics, payments, _get_llm_client(), NVIDIA_MODEL, LLM_MAX_TOKENS)


_slm_client = None


def _get_slm_client():
    global _slm_client
    if _slm_client is None:
        from openai import OpenAI
        _slm_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    return _slm_client


SLM_MODEL = "qwen3:4b"  # real local weights, verified real tool-calling 2026-09-01


def agentic_slm_rca_baseline(incident, metrics, payments):
    """Same real tools, same real evidence, same real MCP round-trips as
    agentic_rca_baseline -- routed to a real local Ollama model instead of
    the cloud NVIDIA one. Genuine SLM-vs-LLM comparison for the AGENTIC
    (tool-investigating) mechanism specifically, not the earlier static-
    prompt mechanism (mcp_slm_rca_baseline)."""
    return _agentic_tool_loop(incident, metrics, payments, _get_slm_client(), SLM_MODEL, 4096)


STRONGER_MODEL = "meta/muse-glimmer-30b"  # real, verified live 2026-09-01,
# but DROPPED (not used in any eval) -- a single agentic call (up to 6
# real tool-call rounds) exceeded 5 real minutes with no result, killed
# per direct user instruction ("if it takes more than 5 mins... drop
# it"). Heavy per-turn reasoning (355 completion tokens for a trivial
# single-fact test question) makes it impractical for this workload
# regardless of potential accuracy -- not evaluated further.


def agentic_strong_rca_baseline(incident, metrics, payments):
    """DROPPED, kept only for reference -- see STRONGER_MODEL comment.
    Not called by any real eval run."""
    return _agentic_tool_loop(incident, metrics, payments, _get_llm_client(), STRONGER_MODEL, 4096)


_nemotron_client = None
NEMOTRON_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"  # real,
# verified live 2026-09-01: a trivial call took 1.06s real wall time
# (~52 real tokens/sec generation throughput per the API's own
# nvext.request_throughput field) -- fast enough to actually use in the
# multi-round agentic loop, unlike meta/muse-glimmer-30b


def _get_nemotron_client():
    global _nemotron_client
    if _nemotron_client is None:
        import os
        from openai import OpenAI
        api_key = os.environ.get("NEMOTRON_API_KEY")
        if not api_key:
            raise RuntimeError("NEMOTRON_API_KEY not set")
        _nemotron_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
    return _nemotron_client


def agentic_nemotron_rca_baseline(incident, metrics, payments):
    """Same real tools, same real evidence, same _agentic_tool_loop as
    agentic_rca_baseline -- routed to nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
    (a separate, real NVIDIA-hosted model+key the user provided), verified
    fast enough (~1s for a trivial call) to be practical for this
    multi-round agentic workload, unlike meta/muse-glimmer-30b."""
    return _agentic_tool_loop(incident, metrics, payments, _get_nemotron_client(), NEMOTRON_MODEL, 4096)


# Illustrative FX-to-USD rates (approximate, for relative dollar-exposure
# comparison across methods -- NOT live rates, not for accounting).
FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CHF": 1.12,
             "SEK": 0.095, "JPY": 0.0067, "CAD": 0.73, "SGD": 0.74}


def _incident_window_exposure(incident, payments):
    """Real $ value of payments active during the incident window -- blast
    radius in business terms, not just a payment count."""
    start = pd.to_datetime(incident["injection_time"])
    end = start + timedelta(seconds=float(incident["duration_seconds"]))
    wp = payments[(payments.created_at >= start) & (payments.created_at <= end)]
    if "amount" not in wp.columns or "currency" not in wp.columns:
        return 0.0
    usd = wp.apply(lambda r: (r["amount"] or 0) * FX_TO_USD.get(r["currency"], 1.0)
                    if pd.notna(r["amount"]) else 0.0, axis=1)
    return float(usd.sum())


def score(incidents, metrics, payments, method_fn):
    hits_at_k = {k: [] for k in K_VALUES}
    per_family = defaultdict(lambda: {k: [] for k in K_VALUES})
    per_depth = defaultdict(lambda: {k: [] for k in K_VALUES})
    per_difficulty = defaultdict(lambda: {k: [] for k in K_VALUES})
    per_incident_hit1 = {}  # incident_id -> 1/0 at k=1, for paired significance testing
    confusion = defaultdict(lambda: defaultdict(int))  # true_svc -> predicted_svc(top1) -> count
    rank_of_truth = []  # 1-indexed rank of the true service in each incident's ranking (explains near-miss vs wild-miss)
    exposure_hit_usd = 0.0   # $ exposure of correctly-diagnosed (AC@1) incidents
    exposure_total_usd = 0.0
    # $/second rate weighting: v13 found raw dollar-exposure weighting is
    # duration-confounded (crash faults run 20-30s and accumulate more
    # concurrent payments than payment-domain faults' 5s window, independent
    # of transaction size) -- weighting by rate instead of accumulated total
    # answers "does this method miss disproportionately on high-value
    # traffic" without that confound baked in.
    rate_hit_usd = 0.0
    rate_total_usd = 0.0

    for _, inc in incidents.iterrows():
        ranked = method_fn(inc, metrics, payments)
        true_svc = inc["root_service"]
        if ranked:
            confusion[true_svc][ranked[0]] += 1
            rank_of_truth.append(ranked.index(true_svc) + 1 if true_svc in ranked else len(FULL_PIPELINE_ORDER) + 1)
        exposure = _incident_window_exposure(inc, payments)
        exposure_total_usd += exposure
        duration_s = max(float(inc["duration_seconds"]), 1.0)
        rate = exposure / duration_s
        rate_total_usd += rate
        for k in K_VALUES:
            hit = 1 if true_svc in ranked[:k] else 0
            hits_at_k[k].append(hit)
            per_family[inc["fault_family"]][k].append(hit)
            per_depth[inc["propagation_depth"]][k].append(hit)
            per_difficulty[inc["temporal_difficulty"]][k].append(hit)
            if k == 1:
                per_incident_hit1[inc.get("incident_id", len(per_incident_hit1))] = hit
                if hit:
                    exposure_hit_usd += exposure
                    rate_hit_usd += rate

    def summarize(d):
        out = {}
        for k, v in d.items():
            if not v:
                out[k] = {"mean": float("nan"), "n": 0, "ci": (float("nan"), float("nan"))}
                continue
            n = len(v)
            hits = sum(v)
            out[k] = {"mean": round(hits / n, 3), "n": n, "ci": tuple(round(x, 3) for x in wilson_ci(hits, n))}
        return out

    return {
        "overall": summarize(hits_at_k),
        "by_family": {f: summarize(d) for f, d in per_family.items()},
        "by_depth": {depth: summarize(d) for depth, d in per_depth.items()},
        "by_difficulty": {diff: summarize(d) for diff, d in per_difficulty.items()},
        "per_incident_hit1": per_incident_hit1,
        # confusion[true][predicted] = count -- which service does this method
        # systematically over/under-predict? A method that's "accurate" but
        # always defaults to one service on ties looks very different here
        # than one that's genuinely wrong in varied ways.
        "confusion": {t: dict(preds) for t, preds in confusion.items()},
        # rank_of_truth: for every incident, where in the ranked guess list
        # was the true answer? Distinguishes "almost right" (rank 2) from
        # "no real signal at all" (last place) -- AC@1/AC@3 alone can't.
        "rank_of_truth": rank_of_truth,
        # Dollar-weighted AC@1: does this method get the financially bigger
        # incidents right more or less often than the unweighted mean
        # suggests? A method that's accurate on small incidents but blind on
        # large ones looks fine unweighted and is actually a real risk.
        "exposure_total_usd": round(exposure_total_usd, 2),
        "exposure_weighted_ac1": round(exposure_hit_usd / exposure_total_usd, 3) if exposure_total_usd > 0 else float("nan"),
        # Duration-normalized version of the above (see comment in the loop):
        # weight each incident by $/second of exposure instead of raw $,
        # so a long crash-fault window doesn't get more weight than a short
        # payment-domain window purely because it ran longer.
        "exposure_rate_weighted_ac1": round(rate_hit_usd / rate_total_usd, 3) if rate_total_usd > 0 else float("nan"),
    }


def _fmt(d):
    return {k: f"{v['mean']}  (n={v['n']}, 95% CI {v['ci'][0]}-{v['ci'][1]})" for k, v in d.items()}


def print_report(results, label):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    print("Overall AC@k:", _fmt(results["overall"]))
    print("\nBy fault_family (mean, n, 95% Wilson CI -- READ THE n BEFORE TRUSTING THE MEAN):")
    for f, r in results["by_family"].items():
        print(f"  {f:16s} {_fmt(r)}")
    print("\nBy propagation_depth:")
    for d, r in sorted(results["by_depth"].items()):
        print(f"  depth={d}  {_fmt(r)}")
    print("\nBy temporal_difficulty:")
    for d, r in results["by_difficulty"].items():
        print(f"  {d:8s} {_fmt(r)}")
    print(f"\nDollar exposure (illustrative FX): total ${results['exposure_total_usd']:,.0f} across these incidents. "
          f"AC@1 exposure-weighted: {results['exposure_weighted_ac1']} "
          f"(vs unweighted {results['overall'][1]['mean']} -- a gap here means this method's accuracy "
          f"correlates with incident dollar size, not just count). "
          f"AC@1 rate-weighted ($/s, duration-normalized): {results['exposure_rate_weighted_ac1']} "
          f"(if this is close to unweighted while the raw exposure-weighted number above is not, "
          f"the raw gap is a window-duration artifact, not a true big-transaction blind spot).")
    print_confusion(results)
    print_rank_histogram(results)


def print_confusion(results):
    """Which service does this method predict (top-1) vs the true root,
    per true root -- reveals systematic bias (e.g. always defaulting to one
    service on ties) that a bare AC@1 mean can't distinguish from genuinely
    varied, evidence-driven mistakes."""
    confusion = results.get("confusion", {})
    if not confusion:
        return
    print("\nConfusion (true_root -> predicted_root(top1): count):")
    for true_svc in FULL_PIPELINE_ORDER:
        preds = confusion.get(true_svc)
        if not preds:
            continue
        total = sum(preds.values())
        parts = ", ".join(f"{p}={c}" for p, c in sorted(preds.items(), key=lambda kv: -kv[1]))
        correct = preds.get(true_svc, 0)
        print(f"  {true_svc:24s} (n={total:3d}, correct={correct:3d})  {parts}")


def print_rank_histogram(results):
    """Where in the ranked guess list was the truth, when the method missed
    at k=1? Rank 2 ('almost right') vs last place ('no real signal') are
    very different failure modes AC@1/AC@3 alone can't tell apart."""
    ranks = results.get("rank_of_truth", [])
    if not ranks:
        return
    from collections import Counter
    c = Counter(ranks)
    n = len(ranks)
    print(f"\nRank-of-truth histogram (n={n}, rank 1 = AC@1 hit):")
    for r in sorted(c):
        label = f"rank {r}" if r <= len(FULL_PIPELINE_ORDER) else "not in ranking"
        pct = c[r] / n
        bar = "#" * int(pct * 40)
        print(f"  {label:16s} {c[r]:3d} ({pct:.0%})  {bar}")


def mcnemar_paired(hits_a, hits_b):
    """Exact McNemar's test (binomial on discordant pairs) comparing two
    methods' AC@1 hit/miss on the SAME incidents. Returns
    (n_a_only, n_b_only, p_value_two_sided). Meaningless (and not computed)
    below ~10 discordant pairs -- report the raw counts and say so rather
    than a p-value that implies more precision than the sample supports.
    """
    common = set(hits_a) & set(hits_b)
    a_only = sum(1 for i in common if hits_a[i] == 1 and hits_b[i] == 0)
    b_only = sum(1 for i in common if hits_a[i] == 0 and hits_b[i] == 1)
    n_disc = a_only + b_only
    if n_disc == 0:
        return a_only, b_only, float("nan")
    # exact two-sided binomial test, p=0.5, using the smaller tail * 2 (capped at 1)
    from math import comb
    k = min(a_only, b_only)
    p = sum(comb(n_disc, i) for i in range(0, k + 1)) / (2 ** n_disc)
    return a_only, b_only, min(1.0, 2 * p)


def main():
    import argparse
    global LOOKBACK_HOURS
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=OUT_DIR, help="Dataset directory (default: synthetic output/)")
    ap.add_argument("--lookback-hours", type=float, default=LOOKBACK_HOURS,
                     help="Pre-incident baseline window (default: 2h, safe for the synthetic "
                          "generator's spread-over-30-days incidents; a live batch run with "
                          "incidents packed minutes apart needs this much shorter -- e.g. 0.05h "
                          "(3min) -- or every baseline is contaminated by nearby incidents)")
    ap.add_argument("--with-llm", action="store_true",
                     help="Also score llm_rca_baseline (1 NVIDIA API call per incident -- "
                          "off by default so a quick regression check doesn't cost API calls)")
    ap.add_argument("--agentic", action="store_true",
                     help="Also score agentic_rca_baseline (up to 4 NVIDIA API calls + real "
                          "MCP HTTP calls per incident -- requires the live stack running with "
                          "the demo dev JWT valid, and only produces meaningful results against "
                          "live incidents whose payments/logs still exist in Elasticsearch)")
    ap.add_argument("--dev-count", type=int, default=0,
                     help="Split incidents (sorted by injection_time) into the first N as a "
                          "DEV set and the rest as a genuine HELD-OUT test set. Only the "
                          "held-out set is used for the headline comparison -- any threshold/"
                          "logic that was derived by looking at specific incidents MUST be "
                          "validated against incidents it wasn't derived from, or the result "
                          "is contaminated. 0 (default) disables the split -- use this for the "
                          "synthetic dataset and for exploratory analysis, never for a claim.")
    ap.add_argument("--ablation", action="store_true",
                     help="Also score 3 payment_aware_rca ablation variants (fracs-only, "
                          "stall-only, dwell-gate-disabled) to isolate which mechanism drives "
                          "the result, instead of reporting the full method as a black box.")
    args = ap.parse_args()
    LOOKBACK_HOURS = args.lookback_hours

    incidents, metrics, incident_payments, payments = load(args.out_dir)
    print(f"Loaded {len(incidents)} incidents, {len(metrics)} metric rows, "
          f"{incident_payments.payment_id.nunique()} affected payments, from {args.out_dir}")

    methods = [
        ("loudest_metric_baseline (G2 only)", loudest_metric_baseline),
        ("graph_topology_baseline (G0-G2)", graph_topology_baseline),
        ("payment_aware_rca (G0-G3)", payment_aware_rca),
    ]
    if args.with_llm:
        methods.append(("llm_rca_baseline (G0-G2, LLM)", llm_rca_baseline))
        methods.append(("llm_rca_g3_baseline (G0-G3, LLM)", llm_rca_g3_baseline))
    if args.agentic:
        methods.append(("agentic_rca_baseline (G0-G3, LLM+MCP)", agentic_rca_baseline))

    dev_incidents, eval_incidents = None, incidents
    if args.dev_count > 0:
        sorted_inc = incidents.sort_values("injection_time").reset_index(drop=True)
        dev_incidents = sorted_inc.iloc[:args.dev_count]
        eval_incidents = sorted_inc.iloc[args.dev_count:].reset_index(drop=True)
        print(f"\n*** HELD-OUT SPLIT: dev={len(dev_incidents)} incidents (injection_time-sorted, "
              f"first {args.dev_count}), held-out={len(eval_incidents)} incidents. Only held-out "
              f"is used for the comparison below. ***")
        if len(eval_incidents) < 10:
            print(f"*** WARNING: held-out set has only {len(eval_incidents)} incidents -- "
                  f"any AC@1 difference here is very likely noise. Check the 95% CIs. ***")
        methods.append(("random_baseline (floor, AC@1 expect ~0.2)", random_baseline))
        methods.append(("majority_baseline (fit on dev only)", make_majority_baseline(dev_incidents)))

    if args.ablation:
        methods.append(("ablation: fracs-only (no stall)", make_ablation_variant("fracs_only", disable_stall=True)))
        methods.append(("ablation: stall-only (no fracs)", make_ablation_variant("stall_only", disable_fracs=True)))
        methods.append(("ablation: no dwell-gate (pre-fix)", make_ablation_variant("no_dwell_gate", disable_dwell_gate=True)))

    all_results = {}
    for label, fn in methods:
        results = score(eval_incidents, metrics, payments, fn)
        all_results[label] = results
        print_report(results, label)

    print(f"\n{'='*60}\nAC@1 BY FAULT_FAMILY, ALL METHODS SIDE BY SIDE"
          f"{' (HELD-OUT SET)' if args.dev_count else ''}\n{'='*60}")
    families = ["infra", "payment_domain", "cross_domain", "confounded"]
    header = f"{'family':16s}" + "".join(f"{label[:22]:>24s}" for label, _ in methods)
    print(header)
    for fam in families:
        row = f"{fam:16s}"
        for label, _ in methods:
            r = all_results[label]["by_family"].get(fam, {}).get(1)
            v = r["mean"] if r else float("nan")
            n = r["n"] if r else 0
            row += f"{v:.2f}(n={n})".rjust(24) if v == v else f"{'n/a':>24s}"
        print(row)

    if args.dev_count:
        print(f"\n{'='*60}\nPAIRED SIGNIFICANCE: payment_aware_rca vs each baseline (McNemar, AC@1, held-out set)\n{'='*60}")
        pa_hits = all_results["payment_aware_rca (G0-G3)"]["per_incident_hit1"]
        for label, _ in methods:
            if label.startswith("payment_aware_rca"):
                continue
            other_hits = all_results[label]["per_incident_hit1"]
            a_only, b_only, p = mcnemar_paired(pa_hits, other_hits)
            n_disc = a_only + b_only
            if n_disc < 10:
                print(f"  vs {label:45s}: only {n_disc} discordant pairs (pa-only={a_only}, "
                      f"other-only={b_only}) -- TOO FEW for a meaningful p-value, do not report significance")
            else:
                print(f"  vs {label:45s}: pa-only={a_only}, other-only={b_only}, p={p:.4f}")

    print("\nExpected pattern: the payment_domain/confounded columns should jump most")
    print("specifically between graph_topology_baseline and payment_aware_rca (the G2->G3")
    print("step) -- that isolates payment-state as the causal factor, not just 'more info'.")
    print("\nRead every number above against its n and 95% CI, not as a bare mean --")
    print("this project has been running at n=2-5 per stratum, where a 1-incident swing")
    print("moves AC@1 by 0.2-0.5.")


if __name__ == "__main__":
    main()
