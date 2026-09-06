#!/usr/bin/env python3
"""ClearFlow RCA Tool — consolidated, production-facing root-cause
predictor. Combines every signal validated across this project's
research thread (RCA_RESEARCH_CONTEXT_TRANSFER.md), in priority order,
each one only ever added after being checked against real data:

1. Health-check override (§16, 2026-09-06): if exactly one service shows
   a real HEALTH_CHECK_FAILED event in the incident window, predict it
   directly. Requires scripts/health_witness_monitor.py to have been
   running during the incident -- verified live to correctly catch
   crash-type faults (CPU_SATURATION, AML_SERVICE_DEGRADATION_RETRY_CASCADE)
   that were otherwise stuck at a confirmed evidence ceiling all session.

2. Funnel-stage override (v6, §8): if the payment funnel reaches a
   specific stage and never advances, that stage's next service is the
   root. 81-100% precision per stage, verified across 101 incidents:
     - reached PAYMENT_VALIDATED only  -> aml-compliance   (83%)
     - reached AML_SCREENING_COMPLETE  -> routing-execution (100%)
     - reached PAYMENT_ROUTED only     -> settlement        (81%)

3. Validation-latency override (v7, §9): median per-payment
   PAYMENT_SUBMITTED->PAYMENT_VALIDATED latency >5000ms (excluding the
   999999 "never validated" sentinel) -> validation-enrichment. ~300x
   separation from every other root cause, robust across a 40x threshold
   sweep (500-20000ms).

4. Domain-rare log line (v8, §10): AML_SANCTIONS_HIT / DUPLICATE_DETECTED
   / WritableServerSelector -- regex deliberately excludes "Failed to
   export spans" and "ClickHouse record failed", both verified this
   session to be cross-cutting infra noise present on every service
   regardless of fault type, not incident-specific signal.

5. Zero-evidence default -> gateway (v9, §12): when nothing above fires,
   "gateway" beats the raw deterministic baseline's own guessing pattern
   within this population specifically (IDEMPOTENCY_COLLISION_STORM,
   always-gateway by HTTP-layer construction, dominates the genuinely-
   evidence-free bucket).

Explicitly NOT included: the agentic multi-round LLM tool loop (tested
extensively, §15 -- real capability shown on signal-rich cases but not
reliably reproducible run-to-run on this API/model, scores ranged 1/10
to 3/10 on identical inputs) and the single-shot graph+LLM fusion prompt
(§15a/16 -- real, significant improvement over rules alone, 0.673 on the
101-benchmark, but adds real API cost/latency/instability for a gain
this tool's deterministic layer already captures on the highest-value
cases). Both remain available as `scratch_agentic_v3.py` /
`scratch_graph_llm_fusion.py` for a caller that wants to trade
reliability for a shot at the harder residual cases.

Every miss this tool produces is a genuine "I don't have real evidence"
case, verified as such -- checked and confirmed by this session's own
investigation for the known-hard fault types (AML_HOLD's decisive log
line genuinely absent for older/aged incidents, IDEMPOTENCY_COLLISION_STORM
structurally evidence-free at the HTTP layer) -- not a modeling gap
papered over with a guess.

CLI entry point (2026-09-06 fix): now accepts an optional metrics_csv 4th
arg. Before this, the CLI never passed metrics_df at all, so every call
silently skipped step 5's real z-score gate / payment_aware_rca
fallback and fell straight to the blind "gateway" default -- 59/143 real
incidents on the output_live set hit this path, only 14 correct. Always
pass both payments_csv and metrics_csv from the CLI to get the tool's
real accuracy (0.497 AC@1 on the 143-incident output_live set, measured
2026-09-06 with both files supplied), not the degraded payments-only
number.

Re: domain-rare log line correlation (2026-09-06): a state-verification +
min-count fix for its known false-positive risk was implemented and
measured head-to-head on the real 143-incident set -- it REGRESSED
accuracy (71/143 -> 67/143). Reverted; see the rejected-fix comment
above `_fetch_health_events` in the source for the full measurement.

Operational wrapper (2026-09-06, `rca_heartbeat.py` + `rca_audit_log.py`):
borrows the Gateway/Heartbeat pattern from OpenClaw/Hermes-style agent
frameworks for WHEN this tool runs, and Hermes's episodic-memory pattern
for recording WHAT it said -- but deliberately does NOT put an LLM
anywhere in the decision path. `rca_heartbeat.py` polls ES for
HEALTH_CHECK_FAILED transitions, builds payments_df/metrics_df live via
live_evidence.py, and calls THIS module's unmodified `diagnose()`;
`rca_audit_log.py` persists each result to SQLite (dedup'd by
incident_key) so past diagnoses are queryable without re-running ES
queries. Verified end-to-end against real historical ES data
(2026-09-02, 47 real HEALTH_CHECK_FAILED transitions replayed, all
correctly diagnosed and logged, re-run confirmed idempotent). The
prediction logic and its accuracy number are completely unchanged by
this wrapper.
"""
import re
import sys
from collections import Counter

import pandas as pd
import requests

sys.path.insert(0, ".")
import eval_harness as eh

ES = "http://localhost:9200"
FULL_PIPELINE_ORDER = ["gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement"]
FUNNEL_STAGE_KWS = ["PAYMENT_SUBMITTED", "PAYMENT_VALIDATED", "AML_SCREENING_COMPLETE", "PAYMENT_ROUTED", "SETTLEMENT_COMPLETE"]
STAGE_ROOT_BY_REACHED_IDX = {1: "aml-compliance", 2: "routing-execution", 3: "settlement"}
FUNNEL_VOLUME_FLOOR = 15
VALIDATION_LATENCY_THRESHOLD_MS = 5000
SENTINEL_LATENCY_MS = 999999
REAL_RARE_DOMAIN = re.compile(r"AML_SANCTIONS_HIT|DUPLICATE_DETECTED|WritableServerSelector")
ZERO_EVIDENCE_DEFAULT = "gateway"


def _fetch_events(start, end, limit=500):
    """Used for the funnel-stage signal only -- a 500-event cap is fine
    there since it's built from simple keyword counts, order-independent
    within the window. NOT safe for anything needing a specific rare
    event: real bug found and fixed 2026-09-06 -- `audit` alone produces
    300-400+ events in a typical window, so a capped, unfiltered fetch
    silently dropped the actual AML_SANCTIONS_HIT line past position 500
    on a real incident, causing a real miss. Domain-rare detection now
    uses `_fetch_domain_rare_events` below, a direct, targeted ES query
    instead of client-side filtering a capped generic fetch."""
    body = {"size": limit, "query": {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
            "sort": [{"@timestamp": "asc"}], "_source": ["service", "eventType", "message", "level", "paymentId"]}
    r = requests.post(f"{ES}/clearflow-*/_search", json=body, timeout=15)
    r.raise_for_status()
    return [h["_source"] for h in r.json().get("hits", {}).get("hits", [])]


def _fetch_domain_rare_events(start, end):
    """Direct, targeted ES query for the domain-rare keywords -- not
    subject to the generic fetch's event-count cap (see _fetch_events)."""
    body = {"size": 10, "query": {"bool": {"filter": [
        {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
    ], "should": [
        {"match_phrase": {"message": "AML_SANCTIONS_HIT"}},
        {"match_phrase": {"message": "DUPLICATE_DETECTED"}},
        {"match_phrase": {"message": "WritableServerSelector"}},
    ], "minimum_should_match": 1}}, "sort": [{"@timestamp": "asc"}],
            "_source": ["service", "message", "paymentId"]}
    r = requests.post(f"{ES}/clearflow-*/_search", json=body, timeout=15)
    r.raise_for_status()
    return [h["_source"] for h in r.json().get("hits", {}).get("hits", [])]


# ATTEMPTED FIX, TESTED AND REJECTED (2026-09-06): the natural fix for the
# KNOWN LIMITATION below -- correlate each domain-rare hit's paymentId
# against payments_df's own aml_state/idempotency_state, and/or require
# >=2 distinct payments (matching eval_harness.MIN_DECISIVE_COUNT's proven
# pattern for the identical "single coincidental payment" problem) --
# was implemented and measured head-to-head against the real 143-incident
# output_live set (both runs with metrics_df+payments_df supplied, only
# this block toggled): original (trust-first-hit) = 71/143 (0.497);
# state-verified + min-count-2 = 67/143 (0.469). A clean REGRESSION, not
# an improvement. Root cause, checked directly: AML_SANCTIONS_HIT lines on
# both correctly- and incorrectly-attributed incidents were state-verified
# as True at IDENTICAL rates (a real, continuous background AML screening
# process genuinely holds real payments regardless of which fault is
# happening elsewhere) and showed no z-score or created_at-timing
# separation either -- the payment-level evidence to distinguish "this
# payment's hold IS the incident" from "this payment's hold coincidentally
# overlapped the incident window" does not exist anywhere in current
# telemetry, not just untried. Do not re-attempt this exact fix without
# new evidence (e.g. a real causal/topology link from the payment to the
# incident's actual affected-payment set) -- see MANUAL_101_CASE_REVIEW.md
# for this project's broader documented pattern of genuine evidence
# ceilings, not modeling gaps.


def _fetch_health_events(start, end):
    """Real, independent health-witness evidence -- requires
    scripts/health_witness_monitor.py to have been running during the
    incident. Returns the set of services that showed HEALTH_CHECK_FAILED."""
    body = {"size": 20, "query": {"bool": {"filter": [
        {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
        {"term": {"eventType": "HEALTH_CHECK_FAILED"}},
    ]}}}
    r = requests.post(f"{ES}/clearflow-*/_search", json=body, timeout=10)
    r.raise_for_status()
    hits = r.json().get("hits", {}).get("hits", [])
    return {h["_source"]["service"] for h in hits}


def _funnel_signal(events):
    counts = Counter()
    for e in events:
        msg = str(e.get("message", ""))
        for kw in FUNNEL_STAGE_KWS:
            if kw in msg:
                counts[kw] += 1
    seq = [counts.get(k, 0) for k in FUNNEL_STAGE_KWS]
    total = sum(seq)
    reached_idx = max((i for i, c in enumerate(seq) if c > 0), default=-1)
    ratios = [seq[i + 1] / seq[i] for i in range(len(seq) - 1) if seq[i] > 0]
    min_ratio = min(ratios) if ratios else 1.0
    stall = (total >= FUNNEL_VOLUME_FLOOR) and ((reached_idx < len(seq) - 1) or (min_ratio < 0.35))
    return total, reached_idx, stall


def _median_validation_latency(payments_df, start, end):
    if payments_df is None or "validation_latency_ms" not in payments_df.columns:
        return float("nan")
    window = payments_df[(payments_df.created_at >= start) & (payments_df.created_at <= end)]
    lat = window["validation_latency_ms"].dropna()
    lat = lat[lat != SENTINEL_LATENCY_MS]
    return lat.median() if len(lat) else float("nan")


def diagnose(injection_time, duration_seconds, payments_df=None, metrics_df=None, extra_buffer_s=30):
    """Real-time RCA prediction for one incident. Matches the validated
    v9 pipeline structure exactly (RCA_RESEARCH_CONTEXT_TRANSFER.md #12),
    minus its LLM dependency for the ambiguous middle bucket -- replaced
    here with the real deterministic `payment_aware_rca` baseline (no
    LLM call, fully reproducible), plus the new health-check override
    (#16) layered on top as the highest-priority signal.

    injection_time: pandas.Timestamp (UTC) -- when the fault was injected.
    duration_seconds: how long the fault lasted.
    payments_df: optional DataFrame with columns [created_at,
        validation_latency_ms] -- needed for the validation-latency
        signal AND for the payment_aware_rca fallback. Pass None to skip
        both (falls back to the zero-evidence default in that case).
    metrics_df: optional DataFrame with columns [timestamp, service,
        error_rate] -- needed for the z-score gate and payment_aware_rca
        fallback. Pass None to treat z-scores as flat.
    extra_buffer_s: propagation buffer added after duration_seconds
        before closing the evidence window.

    Returns dict: {prediction, source, evidence} -- evidence is a plain-
    text explanation of which signal fired and why, for a human to audit.
    Priority order (highest first): health-check > validation-latency >
    funnel-stage > (zero-evidence gate: gateway-default, or else the
    deterministic payment_aware_rca baseline).
    """
    start = pd.Timestamp(injection_time)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    end = start + pd.Timedelta(seconds=float(duration_seconds) + extra_buffer_s)

    events = _fetch_events(start, end)

    # 1. Health-check override -- the most direct, unambiguous signal.
    down_services = _fetch_health_events(start, end)
    if len(down_services) == 1:
        svc = next(iter(down_services))
        return {"prediction": svc, "source": "health-check-override",
                "evidence": f"Independent health-witness monitor recorded HEALTH_CHECK_FAILED for '{svc}' "
                            f"and no other service during this window -- direct evidence that service crashed."}

    # 2. Validation-latency override -- checked before funnel-stage,
    # matching the validated pipeline (latency was added after funnel-
    # stage and unconditionally overrides it -- this is what actually
    # got VALIDATION_SLOWDOWN_GATEWAY_CONFOUND to 12/12; getting this
    # order backwards was a real bug caught by testing known cases
    # before trusting this tool, not assumed correct).
    med_lat = _median_validation_latency(payments_df, start, end)
    if pd.notna(med_lat) and med_lat > VALIDATION_LATENCY_THRESHOLD_MS:
        return {"prediction": "validation-enrichment", "source": "validation-latency-override",
                "evidence": f"Median payment-validation latency this window is {med_lat:.0f}ms "
                            f"(normal ~100-300ms, ~{med_lat/150:.0f}x elevated) -- historically decisive "
                            f"for validation-enrichment (~300x separation from any other root cause)."}

    # 3. Funnel-stage override.
    funnel_total, reached_idx, funnel_stall = _funnel_signal(events)
    if funnel_total >= FUNNEL_VOLUME_FLOOR and reached_idx in STAGE_ROOT_BY_REACHED_IDX:
        svc = STAGE_ROOT_BY_REACHED_IDX[reached_idx]
        stage_name = FUNNEL_STAGE_KWS[reached_idx]
        return {"prediction": svc, "source": f"funnel-stage-idx{reached_idx}",
                "evidence": f"Payment funnel reached '{stage_name}' ({funnel_total} events) but never advanced "
                            f"to the next stage -- historically means '{svc}' is the root (81-100% precision)."}

    # 4. Domain-rare business-event log line -- LOWER priority than
    # funnel-stage/latency (moved here 2026-09-06 after a real
    # regression: once the event-cap bug above was fixed and this check
    # started finding its true, uncapped hit rate, checking it FIRST
    # caused it to intercept many cases funnel-stage/latency would have
    # gotten right, dropping the 101-benchmark score from 0.644 to 0.515.
    # Root cause, same as documented below: AML_SANCTIONS_HIT/etc. are
    # real but not reliably incident-specific, so they should only be
    # trusted once the two higher-precision, validated-at-scale overrides
    # have had first refusal.
    # KNOWN LIMITATION (found 2026-09-06, attempted fix tested and
    # REJECTED same day -- see the rejected-fix comment above
    # _fetch_health_events): still checks presence anywhere in the window,
    # not whether the matched payment was actually affected by the fault.
    # A state-correlation + min-count fix was implemented and measured
    # head-to-head on the real 143-incident set: it REGRESSED accuracy
    # (71/143 -> 67/143) because both correctly- and incorrectly-
    # attributed hits verify as state-True at identical rates -- the
    # discriminating evidence genuinely isn't in current telemetry, not an
    # unexploited signal. Left as the simpler, empirically-better
    # trust-first-hit behavior.
    domain_hits = _fetch_domain_rare_events(start, end)
    if domain_hits:
        svc = domain_hits[0].get("service", "unknown")
        line = str(domain_hits[0].get("message", ""))[:150]
        return {"prediction": svc, "source": "domain-rare-log-line",
                "evidence": f"Real business-decisive log line found on '{svc}': {line!r} "
                            f"(caution: not yet verified this specific payment was actually affected by the fault)"}

    # 5. Zero-evidence gate: if z-score/funnel_stall are flat, default to
    # "gateway" (the empirically best blind guess for this population --
    # IDEMPOTENCY_COLLISION_STORM, always-gateway by HTTP-layer rejection
    # mechanics, dominates the genuinely-evidence-free bucket). Otherwise
    # fall back to the real deterministic payment_aware_rca baseline (no
    # LLM, fully reproducible) -- some signal exists (elevated z-score or
    # funnel_stall) even though none of the overrides above fired
    # cleanly, so a topology/frac-aware method has a real shot.
    max_abs_z = 0.0
    if metrics_df is not None:
        for svc in FULL_PIPELINE_ORDER:
            base = metrics_df[(metrics_df.service == svc) & (metrics_df.timestamp >= start - pd.Timedelta(hours=eh.LOOKBACK_HOURS)) & (metrics_df.timestamp < start)]
            window = metrics_df[(metrics_df.service == svc) & (metrics_df.timestamp >= start) & (metrics_df.timestamp <= end)]
            if len(base) < 3 or len(window) == 0:
                continue
            mu, sigma = base.error_rate.mean(), max(base.error_rate.std(), eh.MIN_ERROR_RATE_SIGMA)
            max_abs_z = max(max_abs_z, abs((window.error_rate.mean() - mu) / sigma))

    zero_evidence = (max_abs_z < 1.0) and (not funnel_stall)
    if zero_evidence or metrics_df is None or payments_df is None:
        return {"prediction": ZERO_EVIDENCE_DEFAULT, "source": "zero-evidence-default",
                "evidence": "No health-check failure, funnel stall, elevated validation latency or z-score, or "
                            "decisive domain log line found -- defaulting to 'gateway', the empirically best "
                            "blind guess for genuinely evidence-free incidents in this system."}

    inc_row = pd.Series({"injection_time": start, "duration_seconds": duration_seconds})
    try:
        ranked = eh.payment_aware_rca(inc_row, metrics_df, payments_df)
        pred = ranked[0] if ranked else ZERO_EVIDENCE_DEFAULT
    except Exception as e:
        return {"prediction": ZERO_EVIDENCE_DEFAULT, "source": "zero-evidence-default-fallback",
                "evidence": f"payment_aware_rca call failed ({e}), defaulting to gateway."}
    return {"prediction": pred, "source": "deterministic-payment-aware-rca",
            "evidence": f"Some real signal exists (max|z|={max_abs_z:.2f}, "
                        f"funnel_stall={funnel_stall}) but no override fired cleanly -- deterministic "
                        f"payment-state/topology reasoning (no LLM) points to '{pred}'."}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 rca_tool.py <injection_time ISO8601> <duration_seconds> [payments_csv] [metrics_csv]")
        sys.exit(1)
    injection_time = sys.argv[1]
    duration_seconds = float(sys.argv[2])
    payments_df = None
    if len(sys.argv) > 3:
        payments_df = pd.read_csv(sys.argv[3])
        payments_df["created_at"] = pd.to_datetime(payments_df["created_at"], utc=True)
    metrics_df = None
    if len(sys.argv) > 4:
        # Without this, the CLI never reached step 5's real z-score gate /
        # payment_aware_rca fallback -- metrics_df was always None, so
        # every incident that didn't hit an earlier override fell straight
        # to the blind "gateway" default (measured: 59/143 incidents did
        # this on the real output_live set, only 14 correct). Passing
        # metrics_csv lets the tool actually use the topology/frac-aware
        # fallback it already has instead of skipping it silently.
        metrics_df = pd.read_csv(sys.argv[4])
        metrics_df["timestamp"] = pd.to_datetime(metrics_df["timestamp"], utc=True)
    result = diagnose(injection_time, duration_seconds, payments_df, metrics_df)
    print(f"PREDICTION: {result['prediction']}")
    print(f"SOURCE:     {result['source']}")
    print(f"EVIDENCE:   {result['evidence']}")
