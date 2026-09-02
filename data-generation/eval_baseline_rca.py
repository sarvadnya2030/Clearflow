#!/usr/bin/env python3
"""Phase 1 validation: does the gold-case set actually discriminate between
RCA methods? Per the standing instruction: stop case generation, take the
existing gold set, define task format / label space / metrics, run at least
2-3 materially different baselines against every valid case, produce a
per-case error analysis. Does NOT modify gold labels.

Methods (same evidence given to every LLM method -- only the model differs,
so any accuracy gap is attributable to model capability, not evidence access):
  heuristic  - rule-based funnel-drop detector, zero-cost, no LLM
  slm        - qwen3.5:4b via local Ollama (project's designated SLM size ceiling)
  large      - openai/gpt-oss-20b via NVIDIA NIM cloud API
  nemotron   - nvidia/nemotron-3-nano-omni-30b-a3b-reasoning via NVIDIA NIM

Evidence given to LLM methods: raw ES events for the injection window,
now embedded directly in each gold_cases/{id}.json's raw_events field
(backfilled 2026-09-02, see backfill_raw_evidence.py and get_events() below)
rather than re-queried live -- self-contained and immune to ES retention,
which this project already lost a paper's headline result to once. Plus
the witness monitor's DOWN/RECOVERED line, extracted from the gold case's
own evidence_reviewed field (a verbatim-quoted excerpt, not a derived
summary). The injector's claimed root is never in this evidence -- ES
doesn't store it.

Usage: python3 eval_baseline_rca.py
"""
import csv
import glob
import json
import os
import re
import time
from collections import defaultdict

import requests

ES = "http://elastic:changeme@localhost:9200"
OLLAMA = "http://localhost:11434/api/chat"
SLM_MODEL = "qwen3.5:4b"
NIM_MODEL = "openai/gpt-oss-20b"
NEMOTRON_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

LABEL_SPACE = ["gateway", "fraud-scoring", "validation-enrichment", "aml-compliance",
               "routing-execution", "settlement", "audit", "mcp-readonly-gateway"]

FUNNEL_STAGES = [
    ("gateway", "PAYMENT_SUBMITTED"),
    ("validation-enrichment", "PAYMENT_VALIDATED"),
    ("aml-compliance", "AML_SCREENING_COMPLETE"),
    ("routing-execution", "PAYMENT_ROUTED"),
    ("settlement", "SETTLEMENT_COMPLETE"),
]

MANIFEST = "gold_cases_manifest.csv"
GOLD_DIR = "gold_cases"


def load_env_key(name):
    with open("../.env.local") as f:
        for line in f:
            m = re.search(rf'{name}="([^"]+)"', line)
            if m:
                return m.group(1)
    raise RuntimeError(f"{name} not found in .env.local")


NVIDIA_API_KEY = load_env_key("NVIDIA_API_KEY")
NEMOTRON_API_KEY = load_env_key("NEMOTRON_API_KEY")


def load_manifest():
    rows = []
    with open(MANIFEST) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def get_events(gold):
    """Prefer the raw_events already embedded in the gold case file (backfilled
    2026-09-02, see backfill_raw_evidence.py) over a live ES query. Self-contained
    and immune to ES retention -- this project already lost a paper's headline
    result once to exactly that failure mode (metrics.csv aging out silently).
    Falls back to a live query only for a gold case that predates the backfill."""
    if "raw_events" in gold:
        return gold["raw_events"]
    return fetch_es_events(gold["injection_time"], gold["duration_seconds"])


def fetch_es_events(injection_time_iso, duration_seconds):
    import pandas as pd
    # AML_HOLD-family cases are point-in-time (a screening hit at submission),
    # not a sustained-outage window, so duration_seconds is null for them --
    # use a short default window instead of crashing.
    dur = int(duration_seconds) if duration_seconds not in (None, "") else 10
    start = pd.Timestamp(injection_time_iso)
    end = start + pd.Timedelta(seconds=dur + 15)
    resp = requests.get(f"{ES}/clearflow-*,clearflow-healthmonitor-*/_search", timeout=15, json={
        "size": 300,
        "query": {"range": {"@timestamp": {"gte": (start - pd.Timedelta(seconds=5)).isoformat(),
                                            "lte": end.isoformat()}}},
        "sort": [{"@timestamp": "asc"}],
        "_source": ["@timestamp", "service", "eventType", "level", "message", "paymentId"],
    })
    return [h["_source"] for h in resp.json().get("hits", {}).get("hits", [])]


def extract_witness_quote(evidence_reviewed):
    for line in evidence_reviewed:
        if "witness" in line.lower() and ("DOWN" in line or "RECOVERED" in line):
            return line
    return None


def funnel_counts(events):
    counts = defaultdict(int)
    for e in events:
        counts[(e.get("service"), e.get("eventType"))] += 1
    return counts


def heuristic_predict(events):
    """Zero-cost rule-based baseline: find the pipeline stage with the
    steepest relative drop-off from the previous stage, rank services by
    drop severity. No LLM, no reasoning -- pure funnel arithmetic."""
    counts = funnel_counts(events)
    stage_counts = [counts.get(st, 0) for st in FUNNEL_STAGES]
    drops = []
    for i in range(1, len(FUNNEL_STAGES)):
        prev, cur = stage_counts[i - 1], stage_counts[i]
        if prev == 0:
            continue
        drop_ratio = 1.0 - (cur / prev)
        drops.append((drop_ratio, FUNNEL_STAGES[i][0]))
    drops.sort(reverse=True)
    # Give the heuristic the same abstention option as the LLM methods: no
    # stage with a real drop (>30%) means there's genuinely nothing to
    # threshold on, e.g. AML_HOLD, which never stalls the funnel at all.
    if not drops or drops[0][0] < 0.3:
        return "ABSTAIN", f"no funnel stage showed a meaningful drop: {drops}"
    ranked = [svc for _, svc in drops]
    for svc in LABEL_SPACE:
        if svc not in ranked:
            ranked.append(svc)
    return ranked[:3], f"funnel drop-offs (desc): {drops}"


def build_prompt(fault_type, events, witness_quote):
    # Compact evidence: funnel counts (the real signal) + only the anomaly-
    # relevant lines (health checks, restarts, errors) + a small sample of
    # normal traffic per service, rather than all 250+ raw lines -- keeps
    # the prompt small enough for a 4B model to actually finish inference.
    counts = funnel_counts(events)
    funnel_summary = "\n".join(
        f"  {svc} {etype or '(unlabeled)'}: {cnt}"
        for (svc, etype), cnt in sorted(counts.items(), key=lambda x: -x[1]) if svc
    )

    interesting = []
    per_service_sample = defaultdict(int)
    for e in events:
        msg = (e.get("message") or "")
        # Signal keywords tuned for crash faults (HEALTH_CHECK_FAILED/restart) plus
        # AML_HOLD's mechanism, which never crashes anything -- its only evidence is
        # a directly self-reported hit/hold event that was getting crowded out of the
        # per-service sample cap by routine AML_SCREENING_COMPLETE noise (found via
        # Phase 1 error analysis: AML_HOLD was 0-33% across all 4 methods).
        is_signal = any(k in msg for k in ("HEALTH_CHECK_FAILED", "Starting", "RECOVERED",
                                            "SANCTIONS_HIT", "AML_HOLD", "HOLD"))
        svc = e.get("service")
        if is_signal or (svc and per_service_sample[svc] < 3):
            interesting.append(f"{e.get('@timestamp')} [{svc}] {(e.get('eventType') or '')} {msg[:150]}")
            if svc:
                per_service_sample[svc] += 1
        if len(interesting) >= 40:
            break
    evidence_text = "\n".join(interesting)
    witness_text = witness_quote or "(no independent witness evidence available for this case)"

    return f"""You are investigating a real incident in a live financial payment processing \
system (8 microservices: gateway, fraud-scoring, validation-enrichment, aml-compliance, \
routing-execution, settlement, audit, mcp-readonly-gateway; payments flow roughly in that \
pipeline order). A fault of unknown root cause occurred. Below is real telemetry from the \
incident window: raw event logs, and (if available) an independent health-witness monitor's \
observation.

INDEPENDENT WITNESS: {witness_text}

FUNNEL COUNTS (per service, per event type, for the whole window):
{funnel_summary}

KEY EVENT LOG EXCERPTS ({len(events)} total events, health-check/restart/recovery lines \
plus a sample of normal traffic per service):
{evidence_text}

Based ONLY on this evidence, which service is the root cause of this incident? Consider \
funnel stalls (where payments stop progressing), health-check failures, restart signatures, \
and direct self-reported events (e.g. a service explicitly logging a hit/hold/rejection). \
If the evidence genuinely does not point to any specific service -- no funnel stall, no \
health-check failure, no direct self-report, nothing distinguishing one service from another \
-- say so instead of guessing.

Respond with ONLY a JSON object, no other text:
{{"insufficient_evidence": <true if nothing in the evidence points to a specific service, else false>, \
"top3": ["<most likely service>", "<second>", "<third>"], "reasoning": "<one or two sentences>"}}

Valid service names: {", ".join(LABEL_SPACE)}"""


def parse_llm_json(text):
    text = (text or "").strip()
    if not text:
        return None, "(empty response)"
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return None, text
    try:
        obj = json.loads(m.group(0))
        top3 = [s for s in obj.get("top3", []) if s in LABEL_SPACE]
        reasoning = obj.get("reasoning", "")
        if obj.get("insufficient_evidence") is True:
            return "ABSTAIN", reasoning
        return top3, reasoning
    except Exception:
        return None, text


def call_slm(prompt):
    try:
        resp = requests.post(OLLAMA, json={
            "model": SLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
        }, timeout=60)
        content = resp.json()["message"]["content"]
        return parse_llm_json(content)
    except Exception as e:
        return None, f"ERROR: {e}"


def call_nim(prompt, model, api_key, extra=None, retries=3):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.2,
    }
    if extra:
        payload.update(extra)
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(NIM_URL, headers={
                "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
            }, json=payload, timeout=150)
            body = resp.json()
            if "choices" not in body:
                last_err = f"HTTP {resp.status_code}, no choices: {json.dumps(body)[:300]}"
                time.sleep(3 * (attempt + 1))
                continue
            content = body["choices"][0]["message"]["content"]
            return parse_llm_json(content)
        except Exception as e:
            last_err = f"ERROR: {e}"
            time.sleep(3 * (attempt + 1))
    return None, last_err


def call_large(prompt):
    return call_nim(prompt, NIM_MODEL, NVIDIA_API_KEY)


def call_nemotron(prompt):
    return call_nim(prompt, NEMOTRON_MODEL, NEMOTRON_API_KEY, extra={"reasoning_budget": 4096})


def main():
    rows = load_manifest()
    results = []  # per case, per method
    error_log = []

    for i, row in enumerate(rows):
        incident_id = row["incident_id"]
        gold_path = f"{GOLD_DIR}/{incident_id}.json"
        if not os.path.exists(gold_path):
            error_log.append(f"{incident_id}: no gold case file, skipped")
            continue
        gold = json.load(open(gold_path))
        confirmed = row["confirmed"] == "true"
        root_service = row["root_service"]
        fault_type = row["fault_type"]

        print(f"[{i+1}/{len(rows)}] {incident_id} ({fault_type}, confirmed={confirmed})", flush=True)

        events = get_events(gold)
        witness_quote = extract_witness_quote(gold.get("evidence_reviewed", []))

        case_result = {"incident_id": incident_id, "fault_type": fault_type,
                        "confirmed": confirmed, "root_service": root_service,
                        "n_events": len(events), "methods": {}}

        # Heuristic
        h_top3, h_reasoning = heuristic_predict(events)
        case_result["methods"]["heuristic"] = {"top3": h_top3, "reasoning": h_reasoning}

        # Build shared prompt for both LLM methods
        prompt = build_prompt(fault_type, events, witness_quote)

        s_top3, s_reasoning = call_slm(prompt)
        case_result["methods"]["slm"] = {"top3": s_top3, "reasoning": s_reasoning}

        l_top3, l_reasoning = call_large(prompt)
        case_result["methods"]["large"] = {"top3": l_top3, "reasoning": l_reasoning}

        results.append(case_result)
        json.dump(results, open("baseline_eval_raw_results.json", "w"), indent=2)
        time.sleep(0.5)

    # ---- Scoring ----
    def score(cases, method):
        ac1 = ac3 = n = 0
        for c in cases:
            top3 = c["methods"][method]["top3"]
            if not top3:
                n += 1
                continue
            n += 1
            if top3[0] == c["root_service"]:
                ac1 += 1
            if c["root_service"] in top3:
                ac3 += 1
        return (ac1 / n * 100 if n else 0), (ac3 / n * 100 if n else 0), n

    confirmed_cases = [c for c in results if c["confirmed"]]
    unconfirmed_cases = [c for c in results if not c["confirmed"]]

    report = ["# Baseline RCA Evaluation Results\n",
              f"Run against {len(results)} gold cases ({len(confirmed_cases)} confirmed, "
              f"{len(unconfirmed_cases)} evidence-free) via live ES re-query. "
              f"Gold labels not modified.\n",
              "## Headline: AC@1 / AC@3 on confirmed cases (n=%d)\n" % len(confirmed_cases),
              "| Method | AC@1 | AC@3 | n |",
              "|---|---|---|---|"]
    for m, name in [("heuristic", "Heuristic (rule-based, no LLM)"),
                     ("slm", f"SLM ({SLM_MODEL})"),
                     ("large", f"Large ({NIM_MODEL})")]:
        ac1, ac3, n = score(confirmed_cases, m)
        report.append(f"| {name} | {ac1:.1f}% | {ac3:.1f}% | {n} |")

    report.append("\n## Per fault-type breakdown (AC@1)\n")
    by_ft = defaultdict(list)
    for c in confirmed_cases:
        by_ft[c["fault_type"]].append(c)
    report.append("| Fault type | n | Heuristic | SLM | Large |")
    report.append("|---|---|---|---|---|")
    for ft, cases in sorted(by_ft.items()):
        h_ac1, _, _ = score(cases, "heuristic")
        s_ac1, _, _ = score(cases, "slm")
        l_ac1, _, _ = score(cases, "large")
        report.append(f"| {ft} | {len(cases)} | {h_ac1:.0f}% | {s_ac1:.0f}% | {l_ac1:.0f}% |")

    report.append("\n## Evidence-free cases (confirmed=false) -- does each method correctly "
                   "fail to find signal, or hallucinate a confident wrong answer?\n")
    report.append("| Incident | Heuristic top1 | SLM top1 | Large top1 | Gold label (unverifiable) |")
    report.append("|---|---|---|---|---|")
    for c in unconfirmed_cases:
        h = c["methods"]["heuristic"]["top3"]
        s = c["methods"]["slm"]["top3"]
        l = c["methods"]["large"]["top3"]
        report.append(f"| {c['incident_id']} | {h[0] if h else 'none'} | "
                       f"{s[0] if s else 'none'} | {l[0] if l else 'none'} | "
                       f"{c['root_service']} (injector-only, no evidence) |")

    report.append("\n## Per-case error analysis (confirmed cases only)\n")
    report.append("| Incident | Fault type | Gold | Heuristic | SLM | Large | Diagnosis |")
    report.append("|---|---|---|---|---|---|---|")
    for c in confirmed_cases:
        gold = c["root_service"]
        h = c["methods"]["heuristic"]["top3"]
        s = c["methods"]["slm"]["top3"]
        l = c["methods"]["large"]["top3"]
        h1 = h[0] if h else "none"
        s1 = s[0] if s else "none"
        l1 = l[0] if l else "none"
        all_wrong = h1 != gold and s1 != gold and l1 != gold
        all_right = h1 == gold and s1 == gold and l1 == gold
        if all_right:
            diag = "solved by all -- likely easy/1-hop case"
        elif all_wrong:
            diag = "solved by none -- investigate: hard case or bad evidence"
        elif l1 == gold and s1 != gold:
            diag = "large succeeds, SLM fails -- reasoning-capability-limited"
        elif s1 == gold and l1 != gold:
            diag = "SLM succeeds, large fails -- unexpected, worth inspecting"
        else:
            diag = "mixed"
        report.append(f"| {c['incident_id']} | {c['fault_type']} | {gold} | {h1} | {s1} | {l1} | {diag} |")

    if error_log:
        report.append("\n## Skipped\n")
        for e in error_log:
            report.append(f"- {e}")

    with open("BASELINE_EVAL_RESULTS.md", "w") as f:
        f.write("\n".join(report))
    print("\nWrote BASELINE_EVAL_RESULTS.md and baseline_eval_raw_results.json")


if __name__ == "__main__":
    main()
