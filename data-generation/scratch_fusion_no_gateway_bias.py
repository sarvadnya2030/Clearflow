#!/usr/bin/env python3
"""Ablation: scratch_graph_llm_fusion.py's prompt hard-codes a directional
heuristic for the zero-evidence case ("weigh gateway seriously"), written
based on IDEMPOTENCY_COLLISION_STORM's real gateway-only-evidence pattern.
Checked directly against the real 143-incident set's own genuinely-
zero-evidence bucket (max_abs_z==0, no health, no domain-rare, no funnel
stall -- 42 incidents): true_root is 'gateway' only 5/42 (12%) of the
time there; 'aml-compliance' (13/42) and 'settlement' (12/42) are both
more common. The hard-coded heuristic is actively miscalibrated for this
specific bucket's real distribution -- this script tests removing it
(falling back to pure graph-topology reasoning with no directional nudge)
against the same 143-incident set, all else held identical.
"""
import sys
import time

import pandas as pd

sys.path.insert(0, ".")
import scratch_graph_llm_fusion as sgf

NO_BIAS_TASK_SECTION = """=== 3. YOUR TASK ===
Fuse the graph-topology reasoning (section 1) with the structural signals (section 2). The funnel-stage and validation-latency signals, when present, are this analysis's two most reliable priors -- trust them over graph/topology guessing when they fire. When neither fires, use the graph's real downstream-coupling structure plus health-check/domain-log evidence to reason about propagation direction -- do not default to any one specific service out of habit; reason from the graph structure and whatever evidence exists, case by case.

Respond with ONLY a comma-separated list of all 5 service names, most likely root cause first."""


def build_prompt_no_bias(row, real_per_service_scores=None):
    full = sgf.build_prompt(row, real_per_service_scores)
    head = full.split("=== 3. YOUR TASK ===")[0]
    return head + NO_BIAS_TASK_SECTION


def run_incident(row, client):
    prompt = build_prompt_no_bias(row)
    t0 = time.time()
    resp = client.chat.completions.create(model=sgf.eh.NVIDIA_MODEL, messages=[{"role": "user", "content": prompt}],
                                           max_tokens=700, temperature=0, reasoning_effort="low")
    raw = (resp.choices[0].message.content or "").strip()
    elapsed = time.time() - t0
    text_lower = raw.lower()
    found = sorted((svc for svc in sgf.eh.FULL_PIPELINE_ORDER if svc in text_lower), key=lambda svc: text_lower.index(svc))
    pred = found[0] if found else None
    return dict(pred=pred, hit=pred == row.true_root, raw_response=raw, seconds=round(elapsed, 1))


if __name__ == "__main__":
    df = pd.read_csv("fusion_evidence_143.csv").set_index("incident_id")
    baseline = pd.read_csv("scratch_graph_llm_fusion_143_results.csv").set_index("incident_id")
    client = sgf.eh._get_llm_client()

    rows = []
    n = len(df)
    for i, (iid, row) in enumerate(df.iterrows(), 1):
        r = run_incident(row, client)
        base_pred = baseline.loc[iid, "fusion_pred"] if iid in baseline.index else None
        print(f"[{i}/{n}] {iid} ({row.fault_type}) true={row.true_root} "
              f"no-bias={r['pred']} hit={r['hit']} (biased-prompt was {base_pred}) ({r['seconds']}s)", flush=True)
        rows.append({"incident_id": iid, "fault_type": row.fault_type, "true_root": row.true_root,
                     "no_bias_pred": r["pred"], "no_bias_hit": r["hit"],
                     "biased_pred": base_pred, "biased_hit": base_pred == row.true_root})

    out = pd.DataFrame(rows)
    out.to_csv("scratch_fusion_no_gateway_bias_143_results.csv", index=False)
    print()
    print(f"=== n={len(out)} ===")
    print(f"biased prompt (current fusion):  {out.biased_hit.sum()}/{len(out)} = {out.biased_hit.mean():.3f}")
    print(f"no-gateway-bias prompt:          {out.no_bias_hit.sum()}/{len(out)} = {out.no_bias_hit.mean():.3f}")
