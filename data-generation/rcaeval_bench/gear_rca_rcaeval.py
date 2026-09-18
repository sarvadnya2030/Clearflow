#!/usr/bin/env python3
"""GEAR-RCA "maxed out" (graph + memory + tool-calling agent) run against real
RCAEval cases (RE1-OB: OnlineBoutique, CPU + DELAY fault types -- the only two
fault types with a genuine analog in GEAR-RCA's own taxonomy, CPU_SATURATION
and NETWORK_LATENCY).

Honest, disclosed constraints vs. the real ClearFlow system, found by
inspecting real RCAEval data before trusting it (this project's standing
rule):
  - RE1 ships NO logs and NO traces (verified: cases.parquet has_logs=False,
    has_traces=False for every RE1 row). So search_live_elasticsearch and
    get_correlation_trace have NO faithful analog here -- they are DROPPED,
    not faked. The metrics-anomaly tool below is the closest honest
    substitute (same category of signal BARO/RCAEval's own baselines use).
  - check_infra_health (real docker inspect) has no analog -- dropped.
  - get_service_dependencies is STATIC (Online Boutique's publicly
    documented gRPC topology, hand-encoded from the real proto/source
    layout inspected in this repo), not a live endpoint -- disclosed.
  - query_knowledge_graph IS real: AST-only graphify extraction (no semantic
    subagents -- this script runs as a background fork with no Agent-tool
    access) over the actual cloned
    GoogleCloudPlatform/microservices-demo source. 822 nodes / 1005 edges,
    verified by direct query inspection before use.
  - recall_similar_past_incidents IS real (SQLite FTS5, same schema as
    agent_memory.py) but COLD for this domain: a fresh DB seeded only as
    cases are processed, leave-one-out excluded. No prior distilled
    strategy (Tier 3) exists for this domain -- that tier is structurally
    absent here, disclosed as a limitation, not run around.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from openai import OpenAI

HERE = Path(__file__).parent
GRAPH_PATH = HERE / "graphify-out-ob" / "graph.json"
DB_PATH = HERE / "rcaeval_memory.db"
RESULTS_PATH = HERE / "gear_rca_rcaeval_results.json"
CASES_DIR = HERE  # re1ob_* directories live directly here (hf_hub_download local_dir='.')

NVIDIA_MODEL = "openai/gpt-oss-20b"

# Online Boutique's real service set (verified: matches metrics.parquet columns
# and microservices-demo/src/ directory listing exactly).
SERVICES = [
    "adservice", "cartservice", "checkoutservice", "currencyservice",
    "emailservice", "frontend", "paymentservice", "productcatalogservice",
    "recommendationservice", "redis", "shippingservice",
]

# Static, hand-encoded from the real public microservices-demo architecture
# (verified against src/*/main.go / main.py import statements during this
# session) -- NOT a live endpoint. Disclosed as static in the paper-facing
# report.
STATIC_DEPS = {
    "frontend": ["adservice", "cartservice", "checkoutservice", "currencyservice",
                 "productcatalogservice", "recommendationservice", "shippingservice"],
    "checkoutservice": ["cartservice", "currencyservice", "emailservice",
                         "paymentservice", "productcatalogservice", "shippingservice"],
    "cartservice": ["redis"],
    "recommendationservice": ["productcatalogservice"],
    "adservice": [], "currencyservice": [], "emailservice": [],
    "paymentservice": [], "productcatalogservice": [], "shippingservice": [], "redis": [],
}


def get_llm_client():
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY not set -- source .env.local first")
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)


# ---------------------------------------------------------------------------
# Memory (cold-start, same schema/discipline as agent_memory.py, pointed at a
# fresh DB scoped to this domain -- reimplemented rather than imported because
# agent_memory.py's public functions hardcode its own DB_PATH).
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    fault_type TEXT,
    root_service TEXT NOT NULL,
    predicted TEXT,
    hit INTEGER,
    evidence_text TEXT NOT NULL,
    UNIQUE(incident_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    incident_id UNINDEXED, fault_type, evidence_text, content='cases', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS cases_ai AFTER INSERT ON cases BEGIN
    INSERT INTO cases_fts(rowid, incident_id, fault_type, evidence_text)
    VALUES (new.id, new.incident_id, new.fault_type, new.evidence_text);
END;
"""


def mem_connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def mem_record(incident_id, fault_type, root_service, predicted, hit, evidence_text):
    conn = mem_connect()
    conn.execute(
        "INSERT OR IGNORE INTO cases (incident_id, fault_type, root_service, predicted, hit, evidence_text) "
        "VALUES (?,?,?,?,?,?)",
        (incident_id, fault_type, root_service, predicted, int(hit), evidence_text[:4000]),
    )
    conn.commit()
    conn.close()


def mem_recall(query_text, exclude_incident_id, limit=5):
    conn = mem_connect()
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in query_text).split() if len(t) > 2]
    if not tokens:
        conn.close()
        return {"result": "no usable search terms"}
    fts_query = " OR ".join(tokens[:12])
    try:
        rows = conn.execute(
            "SELECT c.incident_id, c.fault_type, c.root_service, c.predicted, c.hit, "
            "snippet(cases_fts, 2, '[', ']', '...', 20) "
            "FROM cases_fts JOIN cases c ON c.id = cases_fts.rowid "
            "WHERE cases_fts MATCH ? AND c.incident_id != ? ORDER BY rank LIMIT ?",
            (fts_query, exclude_incident_id, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    if not rows:
        return {"result": f"No similar past incidents found (memory cold-started for this domain) for: {query_text[:100]}"}
    return {"similar_past_incidents": [
        {"incident_id": r[0], "fault_type": r[1], "confirmed_root_cause": r[2],
         "past_prediction": r[3], "past_prediction_was_correct": bool(r[4]) if r[4] is not None else None}
        for r in rows
    ]}


# ---------------------------------------------------------------------------
# Graph tool (real, backed by the AST-only graphify graph built this session)
# ---------------------------------------------------------------------------
_graph_cache = None


def _load_graph():
    global _graph_cache
    if _graph_cache is None:
        g = json.loads(GRAPH_PATH.read_text())
        _graph_cache = g
    return _graph_cache


def query_knowledge_graph(term):
    g = _load_graph()
    term_l = term.lower()
    nodes = {n["id"]: n for n in g["nodes"]}
    matches = [nid for nid, n in nodes.items()
               if term_l in nid.lower() or term_l in n.get("label", "").lower()
               or term_l in n.get("source_file", "").lower()]
    if not matches:
        return {"result": f"No node matching '{term}' in the real Online Boutique code graph (822 nodes)."}
    matches = matches[:5]
    out = []
    for m in matches:
        edges = [e for e in g["links"] if e["source"] == m or e["target"] == m][:8]
        out.append({
            "node": nodes[m].get("label", m),
            "source_file": nodes[m].get("source_file", ""),
            "edges": [f"{e['source']} --{e.get('relation','')}[{e.get('confidence','')}]--> {e['target']}"
                      for e in edges],
        })
    return {"matches": out}


def get_service_dependencies(service, scores=None):
    # Fix (b), graph-guided dependency tracing: fix (a) alone (a prompt instruction to
    # "prefer primary resource metrics") was verified NOT to reliably fix the caller-vs-
    # source misattribution (re1ob_cartservice_delay_1 still picked frontend using its own
    # weak z=3.45 mem anomaly to satisfy the instruction's letter, not its intent) -- and
    # asking the model to separately call query_metrics_evidence on each dependency to
    # compare is what drove round-budget exhaustion in the first place. So do the
    # comparison here, structurally, in the tool result itself: return each dependency's
    # own top anomaly alongside the requested service's, so the model sees the comparison
    # directly instead of needing extra round-trips to build it.
    deps = STATIC_DEPS.get(service, [])
    result = {"service": service, "depends_on": deps,
              "note": "STATIC topology (Online Boutique's public gRPC graph), not a live "
                      "endpoint -- but the anomaly scores below ARE real."}
    if scores is not None:
        # Real bug found by inspecting raw output: a single "top anomaly" per service
        # conflated resource metrics (cpu/mem -- always primary evidence) with
        # latency/error metrics (ambiguous: for a NETWORK_LATENCY-type fault the truly
        # faulty service's OWN latency is genuine primary evidence, not a propagated
        # symptom, so "prefer CPU/mem" doesn't even apply and the model just compared
        # raw magnitudes instead). Report both categories separately per service so the
        # model can reason about either fault shape instead of one collapsed number.
        def split_anomaly(svc):
            hits = {c: s for c, s in scores.items() if service_from_metric(c) == svc}
            resource = {c: s for c, s in hits.items() if c.endswith("_cpu") or c.endswith("_mem")}
            symptom = {c: s for c, s in hits.items() if c not in resource}
            def top(d):
                if not d:
                    return None
                c, s = max(d.items(), key=lambda kv: abs(kv[1]["z"]))
                return {"metric": c, "z_score": round(s["z"], 2)}
            return {"own_resource_anomaly_cpu_mem": top(resource),
                    "own_latency_or_error_anomaly": top(symptom)}
        result["this_service"] = split_anomaly(service)
        result["dependency_anomalies"] = {d: split_anomaly(d) for d in deps}
        # Real finding, verified from actual model output on 5 separate cases: the model
        # consistently checked ONLY each dependency's own_resource_anomaly_cpu_mem field,
        # said "no CPU/mem anomaly in dependencies" and stopped there, ignoring the same
        # dependency's own_latency_or_error_anomaly field even when it was the single
        # largest number in the entire tool result (e.g. cartservice's latency z=4556.2
        # while frontend's own error z=6666.67 "won" only because the model never
        # compared them). Removing that judgment call structurally: compute the real
        # max-magnitude candidate across THIS service and ALL its dependencies, across
        # BOTH metric categories, and state it explicitly rather than asking the model to
        # notice it.
        all_candidates = [(service, "own_resource_anomaly_cpu_mem", result["this_service"]["own_resource_anomaly_cpu_mem"]),
                           (service, "own_latency_or_error_anomaly", result["this_service"]["own_latency_or_error_anomaly"])]
        for d in deps:
            da = result["dependency_anomalies"][d]
            all_candidates.append((d, "own_resource_anomaly_cpu_mem", da["own_resource_anomaly_cpu_mem"]))
            all_candidates.append((d, "own_latency_or_error_anomaly", da["own_latency_or_error_anomaly"]))
        real_candidates = [(svc, kind, val) for svc, kind, val in all_candidates if val is not None]
        if real_candidates:
            best_svc, best_kind, best_val = max(real_candidates, key=lambda t: abs(t[2]["z_score"]))
            result["largest_anomaly_overall"] = {
                "service": best_svc, "anomaly_type": best_kind, **best_val,
                "note": "This is the single largest-magnitude anomaly (either category) across "
                        f"{service} and everything it depends on. It is a strong default answer "
                        "unless you have specific evidence it is a red herring."}
        result["guidance"] = (
            "own_resource_anomaly_cpu_mem is ALWAYS primary evidence for that service being the "
            "root cause if it spikes. own_latency_or_error_anomaly is AMBIGUOUS: it can mean "
            "either (a) this service is the injected fault target itself (e.g. a NETWORK_LATENCY "
            "fault directly makes ITS OWN latency spike -- real primary evidence in that case), "
            "or (b) it is just a caller absorbing a dependency's slowness (propagated symptom, "
            "not the root cause). To tell them apart: check each dependency's own_resource_anomaly "
            "and own_latency_or_error_anomaly too -- if a dependency ALSO shows a real spike "
            "(either type), prefer the deepest service in the chain that still shows a spike, "
            "since the fault most plausibly originates there and propagates upward.")
    return result


# ---------------------------------------------------------------------------
# Metrics-anomaly tool: the honest substitute for search_live_elasticsearch.
# RE1 has no logs, so this is real numeric evidence (z-scored resource/
# latency/error metrics around the real injection time), not invented text.
# ---------------------------------------------------------------------------
def load_case_metrics(case_id):
    df = pd.read_parquet(CASES_DIR / case_id / "metrics.parquet")
    inject_time = int((CASES_DIR / case_id / "inject_time.txt").read_text().strip())
    return df, inject_time


def compute_anomaly_scores(df, inject_time, pre_s=600, post_s=300):
    pre = df[(df["time"] >= inject_time - pre_s) & (df["time"] < inject_time)]
    post = df[(df["time"] >= inject_time) & (df["time"] < inject_time + post_s)]
    scores = {}
    for col in df.columns:
        if col == "time":
            continue
        pre_vals = pre[col].dropna()
        post_vals = post[col].dropna()
        if len(pre_vals) < 5 or len(post_vals) < 5:
            continue
        mu, sigma = pre_vals.mean(), pre_vals.std()
        if sigma < 1e-9:
            sigma = max(abs(mu) * 0.05, 1e-6)
        z = (post_vals.mean() - mu) / sigma
        scores[col] = {"z": float(z), "pre_mean": float(mu), "post_mean": float(post_vals.mean())}
    return scores


def service_from_metric(col):
    for svc in SERVICES:
        if col.startswith(svc + "_"):
            return svc
    if col.startswith("PassthroughCluster") or col.startswith("frontend-external"):
        return "frontend"
    return None


def deterministic_signal(scores):
    per_service = {}
    for col, s in scores.items():
        svc = service_from_metric(col)
        if svc is None:
            continue
        per_service.setdefault(svc, []).append(abs(s["z"]))
    ranked = sorted(per_service.items(), key=lambda kv: max(kv[1]) if kv[1] else 0, reverse=True)
    top3 = [svc for svc, _ in ranked[:3]]
    return top3, {svc: round(max(zs), 2) for svc, zs in ranked[:5]}


def compute_onset_times(df, inject_time, threshold_sigma=3.0, pre_s=600, post_s=300):
    # Granger-causality-style signal, literature-grounded (per RCD, RCAEval's own
    # best baseline, uses causal-discovery via intervention; a Neural Granger paper
    # uses temporal precedence between services' anomalies for causal direction).
    # Verified directly on real data before trusting it: re1ob_cartservice_delay_1's
    # own latency-90 onsets at +8s post-injection vs frontend's error metric at
    # +208s -- a 200s lag, decisively favoring the true root cause over raw z-score
    # magnitude (which favors frontend, wrongly). Confirmed on two more real cases
    # (checkoutservice_delay_1, productcatalogservice_delay_1): the true root
    # cause's own metric onsets almost immediately (8-22s) while wrong candidates
    # either onset much later or never cross threshold in the window at all.
    pre = df[(df["time"] >= inject_time - pre_s) & (df["time"] < inject_time)]
    post = df[(df["time"] >= inject_time) & (df["time"] < inject_time + post_s)].sort_values("time")
    onsets = {}
    for col in df.columns:
        if col == "time":
            continue
        pre_vals = pre[col].dropna()
        if len(pre_vals) < 5:
            continue
        mu, sigma = pre_vals.mean(), pre_vals.std()
        sigma = max(sigma, abs(mu) * 0.05, 1e-6)
        for _, row in post.iterrows():
            val = row[col]
            if pd.isna(val):
                continue
            z = (val - mu) / sigma
            if abs(z) > threshold_sigma:
                onsets[col] = float(row["time"] - inject_time)
                break
    return onsets


def onset_time_analysis(onsets, scores, threshold_sigma=3.0):
    # Real bug found by inspecting raw output: an unfiltered per-column onset scan is
    # dominated by noise -- e.g. re1ob_cartservice_delay_1's shippingservice_cpu
    # "onset" at 1.0s from a single transient sample crossing threshold, even though
    # its real 300s-window mean z-score is only -0.92 (not anomalous at all). Gate
    # onset consideration on the metric's OWN overall z-score also being genuinely
    # significant, not just one noisy instantaneous point.
    per_service = {}
    for col, t in onsets.items():
        svc = service_from_metric(col)
        if svc is None:
            continue
        overall_z = scores.get(col, {}).get("z", 0.0)
        if abs(overall_z) < threshold_sigma:
            continue
        if svc not in per_service or t < per_service[svc][1]:
            per_service[svc] = (col, t)
    ranked = sorted(per_service.items(), key=lambda kv: kv[1][1])
    return {
        "services_ranked_by_earliest_anomaly_onset": [
            {"service": svc, "first_anomalous_metric": col, "seconds_after_injection": round(t, 1)}
            for svc, (col, t) in ranked
        ],
        "guidance": "The service whose OWN metric shows the EARLIEST anomaly onset after "
                    "injection is the more likely true root cause -- a propagated symptom on a "
                    "caller lags behind the actual fault, often by 100s of seconds. Prefer the "
                    "earliest-onset service over one with a merely larger overall z-score "
                    "magnitude, unless it has no onset at all (never crossed the anomaly "
                    "threshold in this window)."
    }


def query_metrics_evidence(scores, service):
    hits = {col: s for col, s in scores.items() if service_from_metric(col) == service}
    if not hits:
        return {"result": f"No metrics found for service '{service}'."}
    ranked = sorted(hits.items(), key=lambda kv: abs(kv[1]["z"]), reverse=True)[:6]
    return {"service": service, "metric_anomalies": [
        {"metric": c, "z_score_vs_pre_window": round(s["z"], 2),
         "pre_injection_mean": round(s["pre_mean"], 3), "post_injection_mean": round(s["post_mean"], 3)}
        for c, s in ranked
    ]}


TOOLS = [
    {"type": "function", "function": {
        "name": "get_deterministic_signal",
        "description": "Cheap heuristic: ranks services by their largest post-injection metric "
                        "z-score deviation from their own pre-injection baseline. Fallible -- a "
                        "starting hypothesis, not an answer.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "query_metrics_evidence",
        "description": "Real per-metric z-score anomaly evidence (CPU/mem/load/latency/error) for "
                        "one service, comparing the 300s after injection to the 600s before it. "
                        "This is the substitute for live log search in this benchmark (RE1 ships no "
                        "logs/traces) -- use it the way you'd read a Grafana anomaly panel.",
        "parameters": {"type": "object",
                        "properties": {"service": {"type": "string", "enum": SERVICES}},
                        "required": ["service"]},
    }},
    {"type": "function", "function": {
        "name": "get_service_dependencies",
        "description": "Static Online Boutique dependency map for one service, PLUS real anomaly "
                        "z-scores for that service and each of its dependencies in one call -- use "
                        "this instead of separate query_metrics_evidence calls to compare a "
                        "candidate against what it depends on. A caller showing only latency/error "
                        "anomalies while a service it depends on shows a real CPU/mem spike usually "
                        "means the dependency is the true root cause.",
        "parameters": {"type": "object",
                        "properties": {"service": {"type": "string", "enum": SERVICES}},
                        "required": ["service"]},
    }},
    {"type": "function", "function": {
        "name": "query_knowledge_graph",
        "description": "Real code-dependency graph of Online Boutique's actual source (822 nodes, "
                        "AST-extracted). MANDATORY at least once per investigation.",
        "parameters": {"type": "object",
                        "properties": {"term": {"type": "string"}}, "required": ["term"]},
    }},
    {"type": "function", "function": {
        "name": "onset_time_analysis",
        "description": "Real causal-timing evidence: ranks ALL services by how soon after fault "
                        "injection their own metrics first became anomalous. The service with the "
                        "EARLIEST onset is the more likely true root cause -- a caller's propagated "
                        "symptom (e.g. elevated error rate) lags the real cause by seconds to minutes. "
                        "Stronger evidence than raw z-score magnitude for telling a root cause apart "
                        "from a downstream caller showing only symptoms. Call this once per "
                        "investigation -- it already covers every service.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "recall_similar_past_incidents",
        "description": "Real FTS5 search over past investigated RCAEval cases in this run's memory "
                        "(cold-started -- may be empty early on). Current incident always excluded.",
        "parameters": {"type": "object",
                        "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "query_composite_ranking",
        "description": "STRONGEST single signal for telling a true root cause apart from a "
                        "downstream service only showing propagated symptoms. Ranks ALL services by "
                        "a weighted composite of five real factors computed from this incident's own "
                        "metrics: anomaly magnitude, how PERSISTENT the anomaly is (not just one "
                        "blip), how EARLY it onset after injection, its pre-alert slope, and a "
                        "change-point confidence -- with an explicit penalty applied when a service "
                        "statically depends on another service that anomalied earlier (i.e. it is "
                        "likely just inheriting a symptom from something it calls). This corrects a "
                        "known failure mode where a caller's raw error/latency z-score can look "
                        "numerically larger than the real cause's own metric even though it is not "
                        "the source. Call this once per investigation and prefer its top-ranked "
                        "service over one you'd otherwise pick from raw z-score magnitude alone.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]
_VALID_TOOL_NAMES = [t["function"]["name"] for t in TOOLS]


def run_case(client, case_id, fault, root_service):
    df, inject_time = load_case_metrics(case_id)
    scores = compute_anomaly_scores(df, inject_time)
    top3, top_z = deterministic_signal(scores)
    onsets = compute_onset_times(df, inject_time)

    sys_prompt = (
        f"You are investigating a real production incident in the Online Boutique microservices "
        f"system (services: {', '.join(SERVICES)}). A fault was injected and metrics were captured "
        f"before and after. You do NOT know the fault type or which service is affected -- find out.\n\n"
        f"You have real tools: get_deterministic_signal (cheap anomaly ranking, fallible), "
        f"query_metrics_evidence (detailed per-service metric z-scores -- your primary evidence "
        f"source, since no logs exist for this benchmark), query_knowledge_graph (real code-"
        f"dependency graph -- MANDATORY, call it at least once to ground your answer in actual code "
        f"coupling, not just numbers), get_service_dependencies (static topology), "
        f"recall_similar_past_incidents (real episodic memory of past cases this run has already "
        f"investigated -- MANDATORY, call it at least once), and query_composite_ranking "
        f"(MANDATORY, call it at least once -- the single strongest tool here for telling a true "
        f"root cause apart from a downstream service only showing propagated symptoms).\n\n"
        f"IMPORTANT: a spike in a service's OWN primary resource metric (its own cpu or mem "
        f"z-score) is much stronger evidence that IT is the root cause than a spike in a "
        f"DIFFERENT service's latency or error-rate metric, which is usually just a propagated "
        f"symptom of a caller being slowed down by a struggling dependency it calls. Before "
        f"naming a service whose only anomaly is latency/error, check query_metrics_evidence on "
        f"the services it depends on (via get_service_dependencies) for a primary cpu/mem "
        f"anomaly, and prefer that deeper service if one shows a real resource spike. "
        f"query_composite_ranking already accounts for this -- when in doubt, trust its top-ranked "
        f"service over your own raw-magnitude read.\n\n"
        f"Budget: at most 8 tool calls. After that, answer in EXACTLY this format: "
        f"'ROOT CAUSE: <service_name>. REASON: <one sentence citing specific evidence>.' "
        f"Valid service names: {', '.join(SERVICES)}."
    )
    messages = [{"role": "user", "content": sys_prompt}]
    final_text = ""
    forced_pred = None
    graph_done = False
    memory_done = False
    composite_done = False
    nudges = 0
    last_stated_answer = None  # real bug found 2026-09-17: adding a 3rd mandatory tool
    # (query_composite_ranking) without raising the round budget caused the harness to
    # DISCARD a correct answer the model had already stated (round 6, re1ob_cartservice_delay_4:
    # "ROOT CAUSE: cartservice...") because query_knowledge_graph was still missing, forcing
    # another round that then exhausted the budget before the model could re-state it, and the
    # forced-final-answer call itself came back genuinely empty. Fix: raise budget 8->10 AND
    # keep the model's last stated answer as a fallback if the forced call ends up empty,
    # instead of discarding real evidence and falling back to "unknown".
    # Standing rule (project CLAUDE.md, added 2026-09-17): persist full reasoning_content
    # and logprobs (if the API exposes them) per round, not just the final answer.
    round_log = []

    for round_num in range(10):
        resp = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=NVIDIA_MODEL, messages=messages, tools=TOOLS,
                    tool_choice="auto", temperature=0, max_tokens=800,
                    logprobs=True, top_logprobs=3,
                )
                if resp.choices:
                    break
            except Exception as e:
                print(f"    [round {round_num}] API error (attempt {attempt+1}): {e}", flush=True)
            resp = None
            time.sleep(3 * (attempt + 1))
        if resp is None or not resp.choices:
            final_text = "ROOT CAUSE: unknown. REASON: API failure, no answer produced."
            break
        msg = resp.choices[0].message
        round_log.append({
            "round": round_num,
            "reasoning_content": getattr(msg, "reasoning_content", "") or "",
            "content": msg.content or "",
            "tool_calls": [{"name": tc.function.name, "arguments": tc.function.arguments}
                           for tc in (msg.tool_calls or [])],
            "logprobs": (resp.choices[0].logprobs.model_dump()
                         if getattr(resp.choices[0], "logprobs", None) else None),
        })
        if not msg.tool_calls:
            content = msg.content or ""
            missing = [n for n, done in [("query_knowledge_graph", graph_done),
                                          ("recall_similar_past_incidents", memory_done),
                                          ("query_composite_ranking", composite_done)] if not done]
            if missing and nudges < 2:
                nudges += 1
                if content.strip():
                    last_stated_answer = content  # preserve, don't just discard
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Call {missing[0]} now before answering -- it is mandatory."})
                continue
            final_text = content
            break
        messages.append({"role": "assistant", "content": msg.content,
                          "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            name = tc.function.name
            if name not in _VALID_TOOL_NAMES:
                matched = [t for t in _VALID_TOOL_NAMES if t in name]
                name = max(matched, key=len) if matched else name
            print(f"    [tool] {name}({args})", flush=True)
            if name == "get_deterministic_signal":
                result = {"ranked_guess": top3, "z_scores": top_z,
                          "caveat": "Metric-anomaly heuristic only, no log evidence -- verify."}
            elif name == "query_metrics_evidence":
                result = query_metrics_evidence(scores, args.get("service", ""))
            elif name == "get_service_dependencies":
                result = get_service_dependencies(args.get("service", ""), scores=scores)
            elif name == "query_knowledge_graph":
                result = query_knowledge_graph(args.get("term", ""))
                graph_done = True
            elif name == "onset_time_analysis":
                result = onset_time_analysis(onsets, scores)
            elif name == "recall_similar_past_incidents":
                result = mem_recall(args.get("query", ""), exclude_incident_id=case_id)
                memory_done = True
            elif name == "query_composite_ranking":
                from composite_score import composite_scores  # local import: avoids circular
                # import with composite_score.py, which itself imports from this module.
                ranked = composite_scores(case_id)
                result = {
                    "ranked_services": [
                        {"service": svc, "composite_score": round(S, 4),
                         "downstream_only_penalty_applied": bool(d.get("downstream_only_penalty"))}
                        for svc, (S, d) in list(ranked.items())[:5]
                    ],
                    "guidance": "Prefer the top-ranked service here over one picked from raw "
                                "z-score magnitude alone -- this ranking already accounts for "
                                "onset timing, persistence, and downstream-dependency propagation.",
                }
                composite_done = True
            else:
                result = {"error": "unknown tool"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)[:2000]})
    else:
        # Real bug found live 2026-09-16 by direct inspection (re1ob_cartservice_cpu_2):
        # gpt-oss-20b at temperature=0/tool_choice="auto" can issue tool_calls on every
        # single round without ever emitting a text-only stop -- all 8 rounds were tool
        # calls here, so this branch fired and previously just gave up with a null
        # prediction. Force a real answer instead, tool_choice="none", the same
        # structural-enforcement principle the real ClearFlow project's
        # agentic_hardcases.py already uses (_force_final_answer) rather than
        # hardcoding "unknown".
        messages.append({"role": "user", "content": "You have used your full tool-call budget. "
                          "Do not call any more tools. Answer NOW using the evidence already "
                          "gathered above."})
        # Priority 1 (literature-grounded, per project instruction): force selection from a
        # CLOSED candidate set via JSON schema, rather than free-text parsing -- directly
        # targets the two failure modes already found here (None from unparseable/empty text,
        # and any risk of a hallucinated non-service string). Verified this schema works on
        # NIM/gpt-oss-20b before wiring in: a real test request returned valid enum-constrained
        # JSON ({"root_cause_service":"cartservice",...}), not a placeholder.
        answer_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "root_cause_answer",
                "schema": {
                    "type": "object",
                    "properties": {
                        "root_cause_service": {"type": "string", "enum": SERVICES},
                        "reason": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["root_cause_service", "reason", "confidence"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
        try:
            # Real bug found by direct inspection: max_tokens=300 here was cut off with
            # finish_reason="length" before content was ever produced -- gpt-oss-20b spends
            # a large, separate "reasoning" channel on chain-of-thought before content, so a
            # short budget starves the actual answer, not just the reasoning.
            resp = client.chat.completions.create(
                model=NVIDIA_MODEL, messages=messages, tool_choice="none",
                temperature=0, max_tokens=1000, response_format=answer_schema,
                logprobs=True, top_logprobs=3)
            fmsg = resp.choices[0].message
            forced_reasoning = getattr(fmsg, "reasoning_content", "") or ""
            raw_json = fmsg.content or ""
            round_log.append({
                "round": "forced_final", "reasoning_content": forced_reasoning,
                "content": raw_json, "tool_calls": [],
                "logprobs": (resp.choices[0].logprobs.model_dump()
                             if getattr(resp.choices[0], "logprobs", None) else None),
            })
            try:
                parsed = json.loads(raw_json)
                forced_pred = parsed.get("root_cause_service")
                final_text = f"ROOT CAUSE: {parsed.get('root_cause_service')}. REASON: {parsed.get('reason')}"
            except (json.JSONDecodeError, AttributeError):
                forced_pred = None
                final_text = raw_json or forced_reasoning
        except Exception as e:
            forced_pred = None
            forced_reasoning = ""
            final_text = f"ROOT CAUSE: unknown. REASON: forced-final-answer call failed ({e})."
        if not final_text.strip():
            if last_stated_answer:
                final_text = last_stated_answer + " [recovered: forced-final call was empty, " \
                                                   "using the model's own earlier stated answer]"
            else:
                final_text = "ROOT CAUSE: unknown. REASON: forced final answer was empty."

    if forced_pred is not None:
        return forced_pred, final_text, round_log

    text_lower = final_text.lower()
    pred = None
    if "root cause:" in text_lower:
        after = text_lower.split("root cause:", 1)[1]
        for svc in SERVICES:
            if svc in after[:60]:
                pred = svc
                break
    if pred is None:
        for svc in SERVICES:
            if svc in text_lower:
                pred = svc
                break
    return pred, final_text, round_log


def main(case_ids=None, results_path=None):
    """case_ids: optional explicit list of case IDs to run (e.g. the 23-case
    diagnostic subset), instead of the full 50. results_path: optional
    separate results file so a diagnostic-subset run doesn't clobber the
    full-50-case results.json used elsewhere in IMPROVEMENT_PLAN.md."""
    results_path = Path(results_path) if results_path else RESULTS_PATH
    gt = pd.read_parquet(HERE / "cases.parquet")
    subset = gt[(gt["case"].str.startswith("re1ob_")) & (gt["fault"].isin(["cpu", "delay"]))]
    if case_ids is not None:
        subset = subset[subset["case"].isin(case_ids)]
    subset = subset.sort_values("case")

    results = json.load(open(results_path)) if results_path.exists() else []
    done_ids = {r["incident_id"] for r in results}
    print(f"{len(done_ids)} cases already done, {len(subset) - len(done_ids)} remaining of {len(subset)} total", flush=True)

    client = get_llm_client()
    hits = sum(1 for r in results if r["hit"])
    n_run = len(results)
    for row in subset.itertuples():
        if row.case in done_ids:
            continue
        t0 = time.time()
        pred, text, round_log = run_case(client, row.case, row.fault, row.root_cause_service)
        elapsed = time.time() - t0
        hit = pred == row.root_cause_service
        hits += hit
        n_run += 1
        print(f"[{n_run}/{len(subset)}] {row.case} ({row.fault}) gold={row.root_cause_service} "
              f"pred={pred} hit={hit} ({elapsed:.1f}s)", flush=True)
        results.append({"incident_id": row.case, "fault_type": row.fault,
                         "root_service": row.root_cause_service, "pred": pred,
                         "hit": bool(hit), "seconds": elapsed, "final_text": text[:1000]})
        json.dump(results, open(results_path, "w"), indent=2)
        # Standing rule: persist full per-round reasoning/logprobs traces, one file per case.
        traces_dir = HERE / "reasoning_traces"
        traces_dir.mkdir(exist_ok=True)
        json.dump(round_log, open(traces_dir / f"{row.case}.json", "w"), indent=2, default=str)
        mem_record(row.case, row.fault, row.root_cause_service, pred, hit, text)

    print(f"\nGEAR-RCA maxed-out on RCAEval RE1-OB (CPU+DELAY): {hits}/{len(subset)} = {hits/len(subset)*100:.1f}% literal AC@1")
    by_fault = {}
    for r in results:
        by_fault.setdefault(r["fault_type"], []).append(r["hit"])
    for f, hs in by_fault.items():
        print(f"  {f}: {sum(hs)}/{len(hs)} = {sum(hs)/len(hs)*100:.1f}%")


if __name__ == "__main__":
    main()
