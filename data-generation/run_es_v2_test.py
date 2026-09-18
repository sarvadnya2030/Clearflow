#!/usr/bin/env python3
"""Controlled test of search_live_es_v2 (dual-ended earliest+latest fetch,
fixing the confirmed bug where v1's most-recent-only sort buried the actual
trigger line) against the v1 baseline, on the same 16 confirmed
CASSANDRA_OUTAGE + MONGODB_OUTAGE cases used for the graph-v2 test, so
results are directly comparable across module-level changes.

Same tools, same memory, same model as the full benchmark run; only
search_live_es is swapped. Does NOT call ah.record_investigation, same
discipline as every other controlled test in this project -- a v2-tool
investigation must not write into the same memory store the baseline
populated.
"""
import json
import os
import time

import agentic_hardcases as ah
from search_live_es_v2 import search_live_es_v2

ah.search_live_es = search_live_es_v2

RESULTS_FILE = "es_v2_test_results.json"
TARGET_IDS = json.load(open("/tmp/v2_test_subset_ids.json"))


def main():
    rows = ah.base.load_manifest()
    targets = [r for r in rows if r["incident_id"] in TARGET_IDS]
    print(f"ES-v2 controlled test: {len(targets)} cases (CASSANDRA_OUTAGE + MONGODB_OUTAGE confirmed).", flush=True)

    results = []
    done_ids = set()
    if os.path.exists(RESULTS_FILE):
        results = json.load(open(RESULTS_FILE))
        done_ids = {r["incident_id"] for r in results}
        print(f"Resuming -- {len(done_ids)} already done.", flush=True)
    remaining = [r for r in targets if r["incident_id"] not in done_ids]

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
    print(f"\nES-v2 test result: literal {hits_literal}/{n} = {hits_literal/n*100:.1f}%  "
          f"| fair-credit {hits_credited}/{n} = {hits_credited/n*100:.1f}%")
    print("Baseline (v1 tool, same 16 cases): literal 37.5% | fair-credit 68.8%")


if __name__ == "__main__":
    main()
