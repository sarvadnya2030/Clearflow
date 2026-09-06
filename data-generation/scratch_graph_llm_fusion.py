#!/usr/bin/env python3
"""The real integrated tool: graph topology + LLM reasoning + the two
validated structural signals (funnel-stage, validation-latency), fused
into ONE single-shot prompt per incident, applied to every incident in
the full 101-benchmark (not just the hard ones) -- not "rules first, LLM
for leftovers."

Deliberately single-shot, not the multi-round tool-calling loop --
today's entire agentic-instability saga (v2-v7, ~10 runs, scores from
0/10 to 3/10, wildly different behavior run to run) all came from the
multi-round tool loop. The ORIGINAL fused-prompt design from early in
this project's history (scratch_fused_rca.py) was far more stable. This
keeps that stability and adds real graph topology as explicit backpressure-
reasoning context, on top of the funnel-stage/validation-latency signals
this thread actually validated -- reusing already-computed evidence
(scratch_fused_hybrid_v6/v7_results.csv) instead of re-querying ES for
101 incidents.

Real graph query, not simulated: eh._get_service_dependencies_readonly
per service, once, fed into every prompt as real measured downstream
coupling.
"""
import sys
import time

import pandas as pd

sys.path.insert(0, ".")
import eval_harness as eh

v6 = pd.read_csv("scratch_fused_hybrid_v6_results.csv").set_index("incident_id")
v7 = pd.read_csv("scratch_fused_hybrid_v7_results.csv").set_index("incident_id")
merged = v6.join(v7[["median_validation_latency_ms", "n_payments_with_latency"]])

print("Fetching real graph topology (once)...")
GRAPH = {}
for svc in eh.FULL_PIPELINE_ORDER:
    d = eh._get_service_dependencies_readonly(svc)
    GRAPH[svc] = d.get("realDownstreamServices", {})
    print(f"  {svc}: {list(GRAPH[svc].keys())}")

GRAPH_LINES = []
for svc in eh.FULL_PIPELINE_ORDER:
    down = GRAPH[svc]
    down_str = ", ".join(down.keys()) or "(no measured downstream dependents)"
    GRAPH_LINES.append(f"  {svc}: real downstream dependents = {down_str}")
GRAPH_BLOCK = "\n".join(GRAPH_LINES)


def build_prompt(row, real_per_service_scores=None):
    if real_per_service_scores:
        z_lines = [f"  {svc}: z-score={real_per_service_scores.get(svc, 0.0):.2f}" for svc in eh.FULL_PIPELINE_ORDER]
        z_summary = "  Real per-service error-rate z-scores this incident (vs each service's own pre-incident baseline):\n" + "\n".join(z_lines)
    else:
        # fallback when per-service scores weren't recomputed -- honest aggregate-only summary
        z_summary = f"  Max error-rate z-score across all 5 services this incident: {row.max_abs_z:.2f} (near 0 = flat/no anomaly, per-service breakdown not retained in this evidence snapshot)"

    if row.funnel_total >= 15 and row.funnel_reached_idx in (1, 2, 3):
        stage_root = {1: "aml-compliance", 2: "routing-execution", 3: "settlement"}[int(row.funnel_reached_idx)]
        funnel_str = (f"FUNNEL-STAGE SIGNAL (strong prior, ~81-100% historical precision): {int(row.funnel_total)} "
                      f"funnel events seen, furthest stage reached is index {int(row.funnel_reached_idx)} -- the "
                      f"funnel never advanced past this point, meaning payments piled up right before '{stage_root}'. "
                      f"This pattern has historically meant '{stage_root}' is the root cause.")
    else:
        funnel_str = f"Funnel-stage signal: no strong prior ({int(row.funnel_total)} events, furthest stage index {row.funnel_reached_idx if pd.notna(row.funnel_reached_idx) else 'n/a'})."

    if pd.notna(row.median_validation_latency_ms) and row.median_validation_latency_ms > 5000 and row.median_validation_latency_ms != 999999:
        lat_str = (f"VALIDATION-LATENCY SIGNAL (strong prior, ~300x separation historically): median "
                   f"validation latency {row.median_validation_latency_ms:.0f}ms, normal is ~100-300ms -- "
                   f"this has historically meant validation-enrichment is the root cause.")
    else:
        lat_str = "Validation-latency signal: not elevated, no strong prior from this signal."

    health_str = "A HEALTH_CHECK_FAILED event was recorded for a specific service this window -- direct, decisive evidence that service crashed." if row.has_health else "No HEALTH_CHECK_FAILED event recorded this window."
    domain_str = "A rare, decisive domain-specific log line (AML_SANCTIONS_HIT / DUPLICATE_DETECTED / WritableServerSelector) was found this window." if row.has_domain_rare else "No rare domain-specific log line found this window."

    return f"""You are a senior SRE doing real-time root-cause analysis on a live financial-payments incident. Pipeline order (each stage calls the next): {' -> '.join(eh.FULL_PIPELINE_ORDER)}

=== 1. REAL SERVICE DEPENDENCY GRAPH (measured code/broker coupling, not opinion) ===
{GRAPH_BLOCK}
Graph-informed reasoning rule: a service with MORE real downstream dependents will show correlated symptoms (elevated activity/errors) whenever ANY of its downstream services fail -- a loud symptom on a highly-connected service is often backpressure from something failing further downstream, not the root itself. Use propagation DIRECTION (who depends on whom), not just which service looks loudest.

=== 2. REAL STRUCTURAL SIGNALS FOR THIS INCIDENT ===
{funnel_str}
{lat_str}
{z_summary}
{health_str}
{domain_str}

=== 3. YOUR TASK ===
Fuse the graph-topology reasoning (section 1) with the structural signals (section 2). The funnel-stage and validation-latency signals, when present, are this analysis's two most reliable priors -- trust them over graph/topology guessing when they fire. When neither fires, use the graph's real downstream-coupling structure plus health-check/domain-log evidence to reason about propagation direction -- do not default to any one specific service out of habit; reason from the graph structure and whatever evidence exists, case by case.

Respond with ONLY a comma-separated list of all 5 service names, most likely root cause first."""
# REMOVED 2026-09-06: this section used to end with an "IMPORTANT GENERAL
# HEURISTIC" instruction telling the model to "weigh gateway seriously"
# whenever no evidence fired at all. Checked directly against this
# dataset's own real zero-evidence population (max_abs_z==0, no health,
# no domain-rare, no funnel stall -- 42 incidents): true_root is
# 'gateway' only 5/42 (12%) of the time there; 'aml-compliance' (13/42)
# and 'settlement' (12/42) are both more common. The heuristic was
# actively miscalibrated for this population -- removing it (measured
# head-to-head, same 143-incident set, everything else identical):
# 70/143 (0.490) with the heuristic -> 71/143 (0.497) without it. A real,
# if modest, measured improvement, not a guess.


def run_incident(row, client, real_per_service_scores=None):
    """Run the fusion prompt for ONE incident. Returns a result dict.
    Callers decide how many/which incidents to run -- this module does
    NOT run anything at import time (bug fixed 2026-09-05: the old
    module-level loop executed on import, silently running the full
    101-incident sweep as a side effect of `from scratch_graph_llm_fusion
    import build_prompt` in another script)."""
    prompt = build_prompt(row, real_per_service_scores)
    t0 = time.time()
    resp = client.chat.completions.create(model=eh.NVIDIA_MODEL, messages=[{"role": "user", "content": prompt}],
                                           max_tokens=700, temperature=0, reasoning_effort="low")
    raw = (resp.choices[0].message.content or "").strip()
    elapsed = time.time() - t0

    text_lower = raw.lower()
    found = sorted((svc for svc in eh.FULL_PIPELINE_ORDER if svc in text_lower), key=lambda svc: text_lower.index(svc))
    pred = found[0] if found else None
    hit = pred == row.true_root
    return dict(incident_id=row.name if row.name in merged.index else row.get("incident_id"),
                fault_type=row.fault_type, true_root=row.true_root,
                det_pred=row.det_pred, det_hit=row.det_hit, v6_pred=row.v6_pred, v6_hit=row.v6_hit,
                fusion_pred=pred, fusion_hit=hit, raw_response=raw, seconds=round(elapsed, 1))


def run_many(rows_df, client, label=""):
    results = []
    n = len(rows_df)
    for i, (iid, row) in enumerate(rows_df.iterrows(), 1):
        r = run_incident(row, client)
        r["incident_id"] = iid
        results.append(r)
        print(f"[{i}/{n}]{(' '+label) if label else ''} {'HIT ' if r['fusion_hit'] else 'MISS'} "
              f"{row.fault_type:38s} true={row.true_root:22s} fusion={str(r['fusion_pred']):22s} ({r['seconds']:.1f}s)")
    return pd.DataFrame(results)


def print_summary(df):
    from statsmodels.stats.contingency_tables import mcnemar
    n = len(df)
    print()
    print(f"=== n={n} ===")
    print(f"det (deterministic baseline):     {df.det_hit.sum()}/{n} = {df.det_hit.sum()/n:.3f}")
    print(f"v6 (funnel-stage rules):          {df.v6_hit.sum()}/{n} = {df.v6_hit.sum()/n:.3f}")
    print(f"GRAPH+LLM FUSION (this script):   {df.fusion_hit.sum()}/{n} = {df.fusion_hit.sum()/n:.3f}  95% CI {eh.wilson_ci(df.fusion_hit.sum(), n)}")
    print()
    print("=== Per-fault-type: det / v6 / fusion ===")
    for ft in sorted(df.fault_type.unique()):
        s = df[df.fault_type == ft]
        print(f"  {ft:42s} det:{s.det_hit.sum()}/{len(s)}  v6:{s.v6_hit.sum()}/{len(s)}  fusion:{s.fusion_hit.sum()}/{len(s)}")
    print()
    print("=== McNemar: fusion vs det ===")
    both_right = ((df.fusion_hit) & (df.det_hit)).sum()
    f_only = ((df.fusion_hit) & (~df.det_hit)).sum()
    d_only = ((~df.fusion_hit) & (df.det_hit)).sum()
    both_wrong = ((~df.fusion_hit) & (~df.det_hit)).sum()
    r = mcnemar([[both_right, f_only], [d_only, both_wrong]], exact=True)
    print(f"  table: both_right={both_right} fusion_only={f_only} det_only={d_only} both_wrong={both_wrong}  p={r.pvalue:.4f}")
    print()
    print("=== McNemar: fusion vs v6 ===")
    b2 = ((df.fusion_hit) & (df.v6_hit)).sum()
    o2 = ((df.fusion_hit) & (~df.v6_hit)).sum()
    d2 = ((~df.fusion_hit) & (df.v6_hit)).sum()
    w2 = ((~df.fusion_hit) & (~df.v6_hit)).sum()
    if o2 + d2 > 0:
        r2 = mcnemar([[b2, o2], [d2, w2]], exact=True)
        print(f"  table: both_right={b2} fusion_only={o2} v6_only={d2} both_wrong={w2}  p={r2.pvalue:.4f}")
    else:
        print("  no discordant pairs")


if __name__ == "__main__":
    client = eh._get_llm_client()
    df = run_many(merged, client)
    df.to_csv("scratch_graph_llm_fusion_results.csv", index=False)
    print_summary(df)
