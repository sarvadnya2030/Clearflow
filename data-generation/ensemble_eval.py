#!/usr/bin/env python3
"""Ensemble analysis over the 4 baseline methods already scored in
baseline_eval_raw_results.json -- no new LLM calls, pure post-hoc analysis.

Ensemble rule: majority vote on each method's top1 pick. Tie broken by
preferring the method with the highest individual AC@1 this run (nemotron >
heuristic > large > slm, from BASELINE_EVAL_RESULTS.md), applied in that
priority order among the tied candidates. Reported fault-type-wise, since
that's where the real question is: does combining methods help on the types
where they disagree, or just average out the ones they already agree on."""
import json
from collections import Counter, defaultdict

METHOD_PRIORITY = ["nemotron", "heuristic", "large", "slm"]  # tiebreak order, best-scoring first


def ensemble_pick(case):
    votes = []
    for m in METHOD_PRIORITY:
        top3 = case["methods"][m]["top3"]
        if top3:
            votes.append(top3[0])
    if not votes:
        return None
    counts = Counter(votes)
    max_votes = max(counts.values())
    tied = [svc for svc, n in counts.items() if n == max_votes]
    if len(tied) == 1:
        return tied[0]
    # tiebreak: first candidate (in tied) that appears in priority order's votes, highest-priority method wins
    for m in METHOD_PRIORITY:
        top3 = case["methods"][m]["top3"]
        if top3 and top3[0] in tied:
            return top3[0]
    return tied[0]


def main():
    results = json.load(open("baseline_eval_raw_results.json"))
    confirmed = [c for c in results if c["confirmed"]]

    for c in confirmed:
        c["ensemble_pick"] = ensemble_pick(c)

    def ac1(cases, key):
        n = len(cases)
        correct = sum(1 for c in cases if key(c) == c["root_service"])
        return correct / n * 100 if n else 0

    methods_keys = {
        "heuristic": lambda c: (c["methods"]["heuristic"]["top3"] or [None])[0],
        "slm": lambda c: (c["methods"]["slm"]["top3"] or [None])[0],
        "large": lambda c: (c["methods"]["large"]["top3"] or [None])[0],
        "nemotron": lambda c: (c["methods"]["nemotron"]["top3"] or [None])[0],
        "ensemble": lambda c: c["ensemble_pick"],
    }

    report = ["# Ensemble Evaluation (majority vote across 4 methods)\n",
              "Post-hoc analysis over the existing 37-case baseline run -- no new LLM calls. "
              "Ensemble = majority vote on each method's top1 pick; ties broken by "
              "nemotron > heuristic > large > slm priority (this run's individual AC@1 ranking).\n",
              "## Overall AC@1 (n=%d confirmed cases)\n" % len(confirmed),
              "| Method | AC@1 |", "|---|---|"]
    for name, key in methods_keys.items():
        report.append(f"| {name} | {ac1(confirmed, key):.1f}% |")

    report.append("\n## Fault-type-wise: does the ensemble help where individual methods disagree?\n")
    by_ft = defaultdict(list)
    for c in confirmed:
        by_ft[c["fault_type"]].append(c)

    report.append("| Fault type | n | Heuristic | SLM | Large | Nemotron | Ensemble | Disagreement? |")
    report.append("|---|---|---|---|---|---|---|---|")
    for ft, cases in sorted(by_ft.items()):
        row = [f"{ac1(cases, methods_keys[m]):.0f}%" for m in ["heuristic", "slm", "large", "nemotron"]]
        ens = f"{ac1(cases, methods_keys['ensemble']):.0f}%"
        # disagreement = did the 4 methods' top1 picks differ on at least one case in this fault type?
        disagree = any(len(set(methods_keys[m](c) for m in ["heuristic", "slm", "large", "nemotron"])) > 1
                        for c in cases)
        report.append(f"| {ft} | {len(cases)} | " + " | ".join(row) + f" | {ens} | {'yes' if disagree else 'no'} |")

    report.append("\n## Per-case detail where the 4 methods disagreed\n")
    report.append("| Incident | Fault type | Gold | Heuristic | SLM | Large | Nemotron | Ensemble | Ensemble correct? |")
    report.append("|---|---|---|---|---|---|---|---|---|")
    for c in confirmed:
        picks = {m: methods_keys[m](c) for m in ["heuristic", "slm", "large", "nemotron"]}
        if len(set(picks.values())) > 1:
            ens = c["ensemble_pick"]
            ens_ok = "yes" if ens == c["root_service"] else "no"
            report.append(f"| {c['incident_id']} | {c['fault_type']} | {c['root_service']} | "
                           f"{picks['heuristic']} | {picks['slm']} | {picks['large']} | {picks['nemotron']} | "
                           f"{ens} | {ens_ok} |")

    with open("ENSEMBLE_EVAL_RESULTS.md", "w") as f:
        f.write("\n".join(report))
    print("Wrote ENSEMBLE_EVAL_RESULTS.md")
    print(f"\nOverall ensemble AC@1: {ac1(confirmed, methods_keys['ensemble']):.1f}%")


if __name__ == "__main__":
    main()
