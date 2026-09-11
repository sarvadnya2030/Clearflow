#!/usr/bin/env python3
"""GALA-inspired baseline: same 11 hard cases, MEMORY_ENABLED=False.
Graph-guided exploration + live telemetry + trace reconstruction, zero
cross-incident memory -- the fair external-comparison + memory-ablation run."""
import json
import time

import agentic_hardcases as ah
ah.MEMORY_ENABLED = False
ah._TRACE = True

RESULTS_FILE = "gala_inspired_results.json"


def main():
    rows = ah.base.load_manifest()
    targets = [r for r in rows if r["incident_id"] in ah.TARGET_IDS]
    results = []
    hits = 0
    for i, row in enumerate(targets):
        gold = json.load(open(f"{ah.base.GOLD_DIR}/{row['incident_id']}.json"))
        t0 = time.time()
        pred, text = ah.run_case(row, gold)
        elapsed = time.time() - t0
        gold_svc = row["root_service"]
        hit = pred == gold_svc
        hits += hit
        print(f"[{i+1}/{len(targets)}] {row['incident_id']} ({row['fault_type']}) "
              f"gold={gold_svc} pred={pred} hit={hit} ({elapsed:.1f}s)", flush=True)
        results.append({"incident_id": row["incident_id"], "fault_type": row["fault_type"],
                         "root_service": gold_svc, "pred": pred, "hit": bool(hit),
                         "seconds": elapsed, "final_text": text[:1200]})
        json.dump(results, open(RESULTS_FILE, "w"), indent=2)

    print(f"\nGALA-inspired (no memory) on 11 hard cases: {hits}/{len(targets)} = {hits/len(targets)*100:.1f}%")


if __name__ == "__main__":
    main()
