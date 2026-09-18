#!/usr/bin/env python3
"""GALA-inspired baseline (MEMORY_ENABLED=False) + the log-retrieval ES-v2
fix, FULL 97-case benchmark. The missing quadrant of the memory on/off x
tool-fix ablation: es_v2_full_benchmark_results.json already covers
ES-fix + memory ON (87.6%/95.9%); this is ES-fix + memory OFF, so the two
can be compared on equal footing (same tools, only memory differs) instead
of comparing the ES-fixed memory-ON arm against the *original-tool*
memory-OFF baseline.

Does NOT call ah.record_investigation, same discipline as every other
controlled test in this project. Resumable -- safe to kill and rerun.
"""
import json
import os
import time

import agentic_hardcases as ah
from search_live_es_v2 import search_live_es_v2

ah.MEMORY_ENABLED = False
ah.search_live_es = search_live_es_v2

RESULTS_FILE = "gala_inspired_es_v2_full_results.json"


def main():
    rows = ah.base.load_manifest()
    targets = [r for r in rows if r["confirmed"] == "true"]

    results = []
    done_ids = set()
    if os.path.exists(RESULTS_FILE):
        results = json.load(open(RESULTS_FILE))
        done_ids = {r["incident_id"] for r in results}
        print(f"Resuming -- {len(done_ids)} cases already done, skipping them.", flush=True)
    remaining = [r for r in targets if r["incident_id"] not in done_ids]
    print(f"GALA-inspired + ES-v2 full run: {len(remaining)} cases left of {len(targets)} confirmed total.", flush=True)

    CASSANDRA_DEPENDENTS = {"audit", "settlement"}

    def credited(pred, gold):
        return pred == gold or (gold == "cassandra" and pred in CASSANDRA_DEPENDENTS)

    hits_literal = sum(1 for r in results if r["hit"])
    hits_credited = sum(1 for r in results if credited(r["pred"], r["root_service"]))
    for i, row in enumerate(remaining):
        gold = json.load(open(f"{ah.base.GOLD_DIR}/{row['incident_id']}.json"))
        t0 = time.time()
        pred, text = ah.run_case(row, gold)
        elapsed = time.time() - t0
        gold_svc = row["root_service"]
        hit = pred == gold_svc
        cred = credited(pred, gold_svc)
        hits_literal += hit
        hits_credited += cred
        print(f"[{len(done_ids)+i+1}/{len(targets)}] {row['incident_id']} ({row['fault_type']}) "
              f"gold={gold_svc} pred={pred} hit={hit} credited={cred} ({elapsed:.1f}s)", flush=True)
        results.append({"incident_id": row["incident_id"], "fault_type": row["fault_type"],
                         "root_service": gold_svc, "pred": pred, "hit": bool(hit),
                         "seconds": elapsed, "final_text": text[:1200]})
        json.dump(results, open(RESULTS_FILE, "w"), indent=2)

    n = len(targets)
    print(f"\nGALA-inspired (no memory) + ES-v2 full result: literal {hits_literal}/{n} = {hits_literal/n*100:.1f}%  "
          f"| fair-credit {hits_credited}/{n} = {hits_credited/n*100:.1f}%")
    print("For comparison -- ES-fix + memory ON (already run): literal 87.6% | fair-credit 95.9%")


if __name__ == "__main__":
    main()
