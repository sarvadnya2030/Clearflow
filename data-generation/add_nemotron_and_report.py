#!/usr/bin/env python3
"""Adds the nemotron method to an already-completed 3-method
baseline_eval_raw_results.json (heuristic/slm/large), then regenerates
BASELINE_EVAL_RESULTS.md with all 4 methods. Rebuilds each case's evidence
fresh from gold_cases/{id}.json + a live ES re-query (identical to the main
harness), rather than trusting anything cached, per the project's standing
non-trust protocol. Does not modify gold_cases/*.json or the manifest.
"""
import json
import time
from collections import defaultdict

import eval_baseline_rca as e


def main():
    results = json.load(open("baseline_eval_raw_results.json"))
    for i, c in enumerate(results):
        if "nemotron" in c["methods"] and c["methods"]["nemotron"]["top3"]:
            continue  # only skip cases that already got a real prediction; retry failures
        incident_id = c["incident_id"]
        gold = json.load(open(f"gold_cases/{incident_id}.json"))
        events = e.get_events(gold)
        witness = e.extract_witness_quote(gold.get("evidence_reviewed", []))
        prompt = e.build_prompt(c["fault_type"], events, witness)
        top3, reasoning = e.call_nemotron(prompt)
        c["methods"]["nemotron"] = {"top3": top3, "reasoning": reasoning}
        print(f"[{i+1}/{len(results)}] {incident_id}: nemotron -> {top3}"
              + ("" if top3 else f" ({reasoning[:150]})"), flush=True)
        json.dump(results, open("baseline_eval_raw_results.json", "w"), indent=2)
        time.sleep(1.5)

    def score(cases, method):
        ac1 = ac3 = n = 0
        for c in cases:
            top3 = c["methods"][method]["top3"]
            n += 1
            if not top3:
                continue
            if top3[0] == c["root_service"]:
                ac1 += 1
            if c["root_service"] in top3:
                ac3 += 1
        return (ac1 / n * 100 if n else 0), (ac3 / n * 100 if n else 0), n

    confirmed_cases = [c for c in results if c["confirmed"]]
    unconfirmed_cases = [c for c in results if not c["confirmed"]]
    METHODS = [("heuristic", "Heuristic (rule-based, no LLM)"),
               ("slm", f"SLM ({e.SLM_MODEL})"),
               ("large", f"Large ({e.NIM_MODEL})"),
               ("nemotron", f"Nemotron ({e.NEMOTRON_MODEL})")]

    report = ["# Baseline RCA Evaluation Results\n",
              f"Run against {len(results)} gold cases ({len(confirmed_cases)} confirmed, "
              f"{len(unconfirmed_cases)} evidence-free) via live ES re-query. "
              f"Gold labels not modified.\n",
              "## Headline: AC@1 / AC@3 on confirmed cases (n=%d)\n" % len(confirmed_cases),
              "| Method | AC@1 | AC@3 | n |",
              "|---|---|---|---|"]
    for m, name in METHODS:
        ac1, ac3, n = score(confirmed_cases, m)
        report.append(f"| {name} | {ac1:.1f}% | {ac3:.1f}% | {n} |")

    report.append("\n## Per fault-type breakdown (AC@1)\n")
    by_ft = defaultdict(list)
    for c in confirmed_cases:
        by_ft[c["fault_type"]].append(c)
    report.append("| Fault type | n | Heuristic | SLM | Large | Nemotron |")
    report.append("|---|---|---|---|---|---|")
    for ft, cases in sorted(by_ft.items()):
        row = [f"{score(cases, m)[0]:.0f}%" for m, _ in METHODS]
        report.append(f"| {ft} | {len(cases)} | " + " | ".join(row) + " |")

    report.append("\n## Evidence-free cases (confirmed=false) -- does each method correctly "
                   "fail to find signal, or hallucinate a confident wrong answer?\n")
    report.append("| Incident | Heuristic | SLM | Large | Nemotron | Gold label (injector-only) |")
    report.append("|---|---|---|---|---|---|")
    for c in unconfirmed_cases:
        preds = []
        for m, _ in METHODS:
            t = c["methods"][m]["top3"]
            preds.append(t[0] if t else "none")
        report.append(f"| {c['incident_id']} | " + " | ".join(preds) + f" | {c['root_service']} |")

    report.append("\n## Per-case error analysis (confirmed cases only)\n")
    report.append("| Incident | Fault type | Gold | Heuristic | SLM | Large | Nemotron | Diagnosis |")
    report.append("|---|---|---|---|---|---|---|---|")
    for c in confirmed_cases:
        gold = c["root_service"]
        preds = {}
        for m, _ in METHODS:
            t = c["methods"][m]["top3"]
            preds[m] = t[0] if t else "none"
        n_correct = sum(1 for v in preds.values() if v == gold)
        if n_correct == len(METHODS):
            diag = "solved by all -- likely easy/1-hop case"
        elif n_correct == 0:
            diag = "solved by none -- investigate: hard case or bad evidence"
        else:
            diag = f"solved by {n_correct}/{len(METHODS)} -- mixed"
        row = [preds[m] for m, _ in METHODS]
        report.append(f"| {c['incident_id']} | {c['fault_type']} | {gold} | " +
                       " | ".join(row) + f" | {diag} |")

    with open("BASELINE_EVAL_RESULTS.md", "w") as f:
        f.write("\n".join(report))
    print("\nWrote BASELINE_EVAL_RESULTS.md (4 methods) and baseline_eval_raw_results.json")


if __name__ == "__main__":
    main()
