#!/usr/bin/env python3
"""Retries the 'large' method (gpt-oss-20b) for any case that got an empty
response in the first pass, using the now-hardened call_nim (retry + backoff
+ visible error on non-'choices' responses). In-place update of
baseline_eval_raw_results.json, does not touch gold_cases/*.json or the
manifest."""
import json
import time

import eval_baseline_rca as e


def main():
    results = json.load(open("baseline_eval_raw_results.json"))
    n_retried = 0
    for i, c in enumerate(results):
        if c["methods"]["large"]["top3"]:
            continue
        incident_id = c["incident_id"]
        gold = json.load(open(f"gold_cases/{incident_id}.json"))
        events = e.get_events(gold)
        witness = e.extract_witness_quote(gold.get("evidence_reviewed", []))
        prompt = e.build_prompt(c["fault_type"], events, witness)
        top3, reasoning = e.call_large(prompt)
        c["methods"]["large"] = {"top3": top3, "reasoning": reasoning}
        print(f"retry {incident_id}: large -> {top3}" + ("" if top3 else f" ({reasoning[:150]})"), flush=True)
        n_retried += 1
        json.dump(results, open("baseline_eval_raw_results.json", "w"), indent=2)
        time.sleep(1.5)
    print(f"\nRetried {n_retried} cases.")


if __name__ == "__main__":
    main()
