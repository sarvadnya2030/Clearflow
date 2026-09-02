#!/usr/bin/env python3
"""Reruns only the cases affected by the two Phase-1 fixes (AML_HOLD signal
filter, abstention option) -- the 3 AML_HOLD cases and 4 evidence-free
cases, across all 4 methods. Updates baseline_eval_raw_results.json in
place, regenerates both BASELINE_EVAL_RESULTS.md and ENSEMBLE_EVAL_RESULTS.md.
Does not touch gold_cases/*.json or the manifest."""
import json
import time

import eval_baseline_rca as e

TARGET_FAULT_TYPES = {"AML_HOLD"}


def main():
    results = json.load(open("baseline_eval_raw_results.json"))
    targets = [c for c in results if c["fault_type"] in TARGET_FAULT_TYPES or not c["confirmed"]]
    print(f"Rerunning {len(targets)} cases across 4 methods with the improved prompt/heuristic...")

    for i, c in enumerate(targets):
        incident_id = c["incident_id"]
        gold = json.load(open(f"gold_cases/{incident_id}.json"))
        events = e.get_events(gold)
        witness = e.extract_witness_quote(gold.get("evidence_reviewed", []))
        prompt = e.build_prompt(c["fault_type"], events, witness)

        h_top3, h_reasoning = e.heuristic_predict(events)
        c["methods"]["heuristic"] = {"top3": h_top3, "reasoning": h_reasoning}

        s_top3, s_reasoning = e.call_slm(prompt)
        c["methods"]["slm"] = {"top3": s_top3, "reasoning": s_reasoning}

        l_top3, l_reasoning = e.call_large(prompt)
        c["methods"]["large"] = {"top3": l_top3, "reasoning": l_reasoning}

        n_top3, n_reasoning = e.call_nemotron(prompt)
        c["methods"]["nemotron"] = {"top3": n_top3, "reasoning": n_reasoning}

        print(f"[{i+1}/{len(targets)}] {incident_id} ({c['fault_type']}, confirmed={c['confirmed']}): "
              f"H={h_top3} S={s_top3} L={l_top3} N={n_top3}", flush=True)
        json.dump(results, open("baseline_eval_raw_results.json", "w"), indent=2)
        time.sleep(1)

    print("\nDone. Now regenerate reports with: python3 rebuild_reports.py")


if __name__ == "__main__":
    main()
