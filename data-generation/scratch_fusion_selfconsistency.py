#!/usr/bin/env python3
"""Self-consistency (run N times, majority vote) applied to the STABLE
single-shot graph+LLM fusion method (scratch_graph_llm_fusion.py, 0.624
on the 101-benchmark, 0.490 on the fresh 143-set) -- not the flaky
multi-tool agentic loop, where this exact idea (scratch_agentic_v4.py)
was already tried and made things WORSE (1/10, because the agent's
errors were a systematic bias toward "settlement"/"gateway", not random
noise voting could average out).

The fusion method has real, demonstrated run-to-run instability too (see
the live LIVE-e02375c2 replay this session: correct in one run, wrong on
an identical immediate rerun) -- but it's a single call with pre-computed
evidence, not a multi-turn tool loop, so its error mode may be closer to
genuine sampling noise around a right answer, which voting is actually
good at fixing, rather than v4's confident-but-wrong systematic bias.
This script tests that directly rather than assuming either way.
"""
import sys
import time
from collections import Counter

import pandas as pd

sys.path.insert(0, ".")
import scratch_graph_llm_fusion as sgf

N_SAMPLES = 3


def run_incident_voted(row, client):
    votes = []
    raw_responses = []
    for _ in range(N_SAMPLES):
        r = sgf.run_incident(row, client)
        votes.append(r["fusion_pred"])
        raw_responses.append(r["raw_response"])
    counts = Counter(v for v in votes if v is not None)
    majority = counts.most_common(1)[0][0] if counts else None
    return dict(votes=votes, majority=majority, hit=majority == row.true_root, raw_responses=raw_responses)


if __name__ == "__main__":
    df = pd.read_csv("fusion_evidence_143.csv").set_index("incident_id")
    single_run = pd.read_csv("scratch_graph_llm_fusion_143_results.csv").set_index("incident_id")
    client = sgf.eh._get_llm_client()

    rows = []
    n = len(df)
    for i, (iid, row) in enumerate(df.iterrows(), 1):
        t0 = time.time()
        r = run_incident_voted(row, client)
        dt = time.time() - t0
        single_pred = single_run.loc[iid, "fusion_pred"] if iid in single_run.index else None
        print(f"[{i}/{n}] {iid} ({row.fault_type}) true={row.true_root} "
              f"votes={r['votes']} majority={r['majority']} hit={r['hit']} "
              f"(single-run was {single_pred}) ({dt:.1f}s)", flush=True)
        rows.append({"incident_id": iid, "fault_type": row.fault_type, "true_root": row.true_root,
                     "votes": "|".join(str(v) for v in r["votes"]), "majority_pred": r["majority"],
                     "majority_hit": r["hit"], "single_run_pred": single_pred,
                     "single_run_hit": single_pred == row.true_root, "seconds": round(dt, 1)})

    out = pd.DataFrame(rows)
    out.to_csv("scratch_fusion_selfconsistency_143_results.csv", index=False)
    print()
    print(f"=== n={len(out)} ===")
    print(f"single-shot fusion (1 sample):        {out.single_run_hit.sum()}/{len(out)} = {out.single_run_hit.mean():.3f}")
    print(f"self-consistency fusion ({N_SAMPLES} samples, vote): {out.majority_hit.sum()}/{len(out)} = {out.majority_hit.mean():.3f}")
    both_right = ((out.majority_hit) & (out.single_run_hit)).sum()
    vote_only = ((out.majority_hit) & (~out.single_run_hit)).sum()
    single_only = ((~out.majority_hit) & (out.single_run_hit)).sum()
    both_wrong = ((~out.majority_hit) & (~out.single_run_hit)).sum()
    print(f"table: both_right={both_right} vote_only={vote_only} single_only={single_only} both_wrong={both_wrong}")
