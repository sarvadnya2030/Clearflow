#!/usr/bin/env python3
"""Full 97-case run of search_live_es_v2 (dual-ended earliest+latest log
fetch, fixing the confirmed bug where v1's most-recent-only sort buried the
actual trigger line -- see search_live_es_v2.py's docstring for the real
LIVE-cd1f76ee example). Same tools/memory/model as the v1 baseline
(agentic_full_benchmark_results.json, 78.4%/83.5%); only search_live_es is
swapped.

Does NOT call ah.record_investigation, same discipline as every other
controlled test in this project.

Resumable -- safe to kill and rerun, skips already-done cases.
"""
import json
import os
import time

import agentic_hardcases as ah
from search_live_es_v2 import search_live_es_v2

ah.search_live_es = search_live_es_v2

RESULTS_FILE = "es_v2_full_benchmark_results.json"


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
    print(f"Full case-wide ES-v2 run: {len(remaining)} cases left of {len(targets)} confirmed total.", flush=True)

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
    print(f"\nFull case-wide ES-v2 result: literal {hits_literal}/{n} = {hits_literal/n*100:.1f}%  "
          f"| fair-credit {hits_credited}/{n} = {hits_credited/n*100:.1f}%")
    print("Baseline (v1 tool, full benchmark): literal 78.4% | fair-credit 83.5%")


if __name__ == "__main__":
    main()
