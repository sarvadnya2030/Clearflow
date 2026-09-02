#!/usr/bin/env python3
"""Rebuilds BASELINE_EVAL_RESULTS.md and ENSEMBLE_EVAL_RESULTS.md from the
current baseline_eval_raw_results.json. No LLM calls -- pure scoring/report
generation, safe to rerun after any in-place update to the raw results.

Scoring rule for "ABSTAIN" (a method explicitly said insufficient_evidence):
counts as CORRECT on evidence-free (confirmed=false) cases -- that's the
right answer there -- and as WRONG on confirmed cases, where a real root
cause exists and abstaining is a genuine miss, not a fair "no signal" call.
"""
import json
from collections import Counter, defaultdict

import eval_baseline_rca as e

METHODS = [("heuristic", "Heuristic (rule-based)"), ("slm", f"SLM ({e.SLM_MODEL})"),
           ("large", f"Large ({e.NIM_MODEL})"), ("nemotron", f"Nemotron ({e.NEMOTRON_MODEL})")]
ENSEMBLE_PRIORITY = ["nemotron", "heuristic", "large", "slm"]


def top1(c, method):
    t = c["methods"][method]["top3"]
    if t == "ABSTAIN":
        return "ABSTAIN"
    return t[0] if t else None


def score(cases, method):
    ac1 = ac3 = n = 0
    for c in cases:
        top3 = c["methods"][method]["top3"]
        n += 1
        if top3 == "ABSTAIN":
            if not c["confirmed"]:
                ac1 += 1
                ac3 += 1
            continue
        if not top3:
            continue
        if top3[0] == c["root_service"]:
            ac1 += 1
        if c["root_service"] in top3:
            ac3 += 1
    return (ac1 / n * 100 if n else 0), (ac3 / n * 100 if n else 0), n


def ensemble_pick(c):
    votes = [top1(c, m) for m in ENSEMBLE_PRIORITY if top1(c, m) not in (None, "ABSTAIN")]
    if not votes:
        # everyone abstained or failed -- ensemble abstains too
        return "ABSTAIN"
    counts = Counter(votes)
    max_votes = max(counts.values())
    tied = [svc for svc, n_ in counts.items() if n_ == max_votes]
    if len(tied) == 1:
        return tied[0]
    for m in ENSEMBLE_PRIORITY:
        t = top1(c, m)
        if t in tied:
            return t
    return tied[0]


def build_baseline_report(results):
    confirmed = [c for c in results if c["confirmed"]]
    unconfirmed = [c for c in results if not c["confirmed"]]

    report = ["# Baseline RCA Evaluation Results\n",
              f"Run against {len(results)} gold cases ({len(confirmed)} confirmed, "
              f"{len(unconfirmed)} evidence-free) via live ES re-query. Gold labels not modified. "
              f"Includes AML_HOLD evidence-filter fix and abstention option (ABSTAIN scores correct "
              f"on evidence-free cases, wrong on confirmed cases).\n",
              "## Headline: AC@1 / AC@3 on confirmed cases (n=%d)\n" % len(confirmed),
              "| Method | AC@1 | AC@3 | n |", "|---|---|---|---|"]
    for m, name in METHODS:
        ac1, ac3, n = score(confirmed, m)
        report.append(f"| {name} | {ac1:.1f}% | {ac3:.1f}% | {n} |")

    report.append("\n## Headline: abstention rate on evidence-free cases (n=%d) -- higher is better\n" % len(unconfirmed))
    report.append("| Method | Correct abstentions | Hallucinated a wrong answer |")
    report.append("|---|---|---|")
    for m, name in METHODS:
        abst = sum(1 for c in unconfirmed if c["methods"][m]["top3"] == "ABSTAIN")
        report.append(f"| {name} | {abst}/{len(unconfirmed)} | {len(unconfirmed)-abst}/{len(unconfirmed)} |")

    report.append("\n## Per fault-type breakdown (AC@1)\n")
    by_ft = defaultdict(list)
    for c in confirmed:
        by_ft[c["fault_type"]].append(c)
    report.append("| Fault type | n | Heuristic | SLM | Large | Nemotron |")
    report.append("|---|---|---|---|---|---|")
    for ft, cases in sorted(by_ft.items()):
        row = [f"{score(cases, m)[0]:.0f}%" for m, _ in METHODS]
        report.append(f"| {ft} | {len(cases)} | " + " | ".join(row) + " |")

    report.append("\n## Evidence-free cases -- per-method verdict\n")
    report.append("| Incident | Heuristic | SLM | Large | Nemotron | Gold (injector-only) |")
    report.append("|---|---|---|---|---|---|")
    for c in unconfirmed:
        row = [str(top1(c, m)) for m, _ in METHODS]
        report.append(f"| {c['incident_id']} | " + " | ".join(row) + f" | {c['root_service']} |")

    report.append("\n## Per-case detail (confirmed cases only)\n")
    report.append("| Incident | Fault type | Gold | Heuristic | SLM | Large | Nemotron |")
    report.append("|---|---|---|---|---|---|---|")
    for c in confirmed:
        row = [str(top1(c, m)) for m, _ in METHODS]
        report.append(f"| {c['incident_id']} | {c['fault_type']} | {c['root_service']} | " + " | ".join(row) + " |")

    with open("BASELINE_EVAL_RESULTS.md", "w") as f:
        f.write("\n".join(report))


def build_ensemble_report(results):
    confirmed = [c for c in results if c["confirmed"]]
    for c in confirmed:
        c["ensemble_pick"] = ensemble_pick(c)

    def ens_ac1(cases):
        n = len(cases)
        correct = sum(1 for c in cases if c["ensemble_pick"] == c["root_service"])
        return correct / n * 100 if n else 0

    report = ["# Ensemble Evaluation (majority vote across 4 methods)\n",
              "Post-hoc, no new LLM calls. Ensemble = majority vote on top1 picks (ABSTAIN votes "
              "excluded from the count; all-abstain cases ensemble-abstain too).\n",
              "## Overall AC@1 (n=%d confirmed cases)\n" % len(confirmed),
              "| Method | AC@1 |", "|---|---|"]
    for m, _ in METHODS:
        report.append(f"| {m} | {score(confirmed, m)[0]:.1f}% |")
    report.append(f"| ensemble | {ens_ac1(confirmed):.1f}% |")

    report.append("\n## Fault-type-wise\n")
    by_ft = defaultdict(list)
    for c in confirmed:
        by_ft[c["fault_type"]].append(c)
    report.append("| Fault type | n | Heuristic | SLM | Large | Nemotron | Ensemble |")
    report.append("|---|---|---|---|---|---|---|")
    for ft, cases in sorted(by_ft.items()):
        row = [f"{score(cases, m)[0]:.0f}%" for m, _ in METHODS]
        report.append(f"| {ft} | {len(cases)} | " + " | ".join(row) + f" | {ens_ac1(cases):.0f}% |")

    with open("ENSEMBLE_EVAL_RESULTS.md", "w") as f:
        f.write("\n".join(report))


if __name__ == "__main__":
    results = json.load(open("baseline_eval_raw_results.json"))
    build_baseline_report(results)
    build_ensemble_report(results)
    print("Rebuilt BASELINE_EVAL_RESULTS.md and ENSEMBLE_EVAL_RESULTS.md")
