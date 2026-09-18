#!/usr/bin/env python3
"""Generalized GEAR-RCA "maxed out" run across all three RCAEval RE1 systems
(Online Boutique, Sock Shop, TrainTicket), all 5 RE1 fault types (cpu, mem,
disk, delay, loss). Extends gear_rca_rcaeval.py's single-system OB/CPU+DELAY
harness with per-system service lists and per-system real graphify graphs
(built this session for all three: OB 822 nodes, SS 956 nodes, TT 4966 nodes
-- see graphify-out-{ob,ss,tt}/GRAPH_REPORT.md).

Disclosed constraint (same as the OB run, verified via cases.parquet):
RE1 has NO logs/traces for any of the three systems -- search_live_elasticsearch
and cross-service trace reconstruction have no analog anywhere in this batch.
Only CPU_SATURATION (cpu) and NETWORK_LATENCY (delay) have a genuine analog in
GEAR-RCA's own fault taxonomy; mem/disk/loss are run and scored the same way
but have NO taxonomy match -- expected to be harder / less interpretable
relative to the paper's own fault types, reported honestly either way.

get_service_dependencies is now REAL per system (derived from each system's
own graphify graph edges), not hand-typed -- generalizes to TrainTicket's 41
services without manual encoding, an improvement over the OB-only script's
static map.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
from openai import OpenAI

HERE = Path(__file__).parent
DB_PATH = HERE / "rcaeval_memory.db"  # shared across systems, same cold-start memory
NVIDIA_MODEL = "openai/gpt-oss-20b"

SYSTEMS = {
    "ob": {"graph": HERE / "graphify-out-ob" / "graph.json", "name": "Online Boutique"},
    "ss": {"graph": HERE / "graphify-out-ss" / "graph.json", "name": "Sock Shop"},
    "tt": {"graph": HERE / "graphify-out-tt" / "graph.json", "name": "TrainTicket"},
}

METRIC_SUFFIXES = ["_cpu", "_mem", "_load", "_latency", "_error", "-50", "-90", "-99"]


def get_llm_client():
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY not set")
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)


def services_from_columns(columns):
    # Real bug found by inspecting raw output: a single-pass suffix strip left
    # compound-suffixed columns like "carts_latency-50" only half-stripped
    # ("carts_latency"), inventing a pseudo-service the LLM then answered
    # with. Strip suffixes repeatedly until none match, so "carts_latency-50"
    # -> "carts_latency" -> "carts".
    svcs = set()
    for c in columns:
        if c == "time":
            continue
        base = c
        stripped_any = False
        changed = True
        while changed:
            changed = False
            for suf in METRIC_SUFFIXES:
                if base.endswith(suf) and len(base) > len(suf):
                    base = base[: -len(suf)]
                    stripped_any = True
                    changed = True
                    break
        if stripped_any:
            svcs.add(base)
    return sorted(svcs)


# ---------------------------------------------------------------------------
# Memory (same cold-start schema as the OB-only script, shared DB across all
# systems -- so a Sock Shop case can in principle recall an earlier Online
# Boutique case if their evidence text overlaps; disclosed, not hidden).
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    system TEXT, fault_type TEXT, root_service TEXT NOT NULL,
    predicted TEXT, hit INTEGER, evidence_text TEXT NOT NULL,
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


def mem_record(incident_id, system, fault_type, root_service, predicted, hit, evidence_text):
    conn = mem_connect()
    conn.execute(
        "INSERT OR IGNORE INTO cases (incident_id, system, fault_type, root_service, predicted, hit, evidence_text) "
        "VALUES (?,?,?,?,?,?,?)",
        (incident_id, system, fault_type, root_service, predicted, int(hit), evidence_text[:4000]),
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
        return {"result": f"No similar past incidents found for: {query_text[:100]}"}
    return {"similar_past_incidents": [
        {"incident_id": r[0], "fault_type": r[1], "confirmed_root_cause": r[2],
         "past_prediction": r[3], "past_prediction_was_correct": bool(r[4]) if r[4] is not None else None}
        for r in rows
    ]}


# ---------------------------------------------------------------------------
# Graph tool (real, per-system)
# ---------------------------------------------------------------------------
_graph_cache = {}


def _load_graph(system):
    if system not in _graph_cache:
        _graph_cache[system] = json.loads(SYSTEMS[system]["graph"].read_text())
    return _graph_cache[system]


def query_knowledge_graph(system, term):
    g = _load_graph(system)
    term_l = term.lower()
    nodes = {n["id"]: n for n in g["nodes"]}
    matches = [nid for nid, n in nodes.items()
               if term_l in nid.lower() or term_l in n.get("label", "").lower()
               or term_l in n.get("source_file", "").lower()]
    if not matches:
        return {"result": f"No node matching '{term}' in the real {SYSTEMS[system]['name']} code graph."}
    matches = matches[:5]
    out = []
    for m in matches:
        edges = [e for e in g["links"] if e["source"] == m or e["target"] == m][:8]
        out.append({"node": nodes[m].get("label", m), "source_file": nodes[m].get("source_file", ""),
                     "edges": [f"{e['source']} --{e.get('relation','')}[{e.get('confidence','')}]--> {e['target']}"
                               for e in edges]})
    return {"matches": out}


def get_service_dependencies(system, service):
    """Real, derived from the actual per-system graphify graph: which other
    services' nodes this service's nodes are directly connected to. Not
    hand-typed -- generalizes to TrainTicket's 41 services automatically."""
    g = _load_graph(system)
    svc_l = service.lower().replace("-", "")
    node_ids = [n["id"] for n in g["nodes"] if svc_l in n["id"].lower().replace("-", "")
                or svc_l in n.get("source_file", "").lower().replace("-", "")]
    if not node_ids:
        return {"service": service, "depends_on": [], "note": "no graph nodes matched this service"}
    node_set = set(node_ids)
    neighbor_files = set()
    for e in g["links"]:
        if e["source"] in node_set:
            tgt = next((n for n in g["nodes"] if n["id"] == e["target"]), None)
            if tgt and tgt.get("source_file"):
                neighbor_files.add(tgt["source_file"])
        if e["target"] in node_set:
            src = next((n for n in g["nodes"] if n["id"] == e["source"]), None)
            if src and src.get("source_file"):
                neighbor_files.add(src["source_file"])
    return {"service": service, "note": "derived from real graph edges, top connected source files",
            "connected_files": sorted(neighbor_files)[:10]}


# ---------------------------------------------------------------------------
# Metrics-anomaly tool (identical mechanism to the OB-only script, generalized
# to any service list)
# ---------------------------------------------------------------------------
def load_case_metrics(case_id):
    df = pd.read_parquet(HERE / case_id / "metrics.parquet")
    inject_time = int((HERE / case_id / "inject_time.txt").read_text().strip())
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


def service_from_metric(col, services):
    for svc in sorted(services, key=len, reverse=True):
        if col.startswith(svc + "_") or col.startswith(svc + "-"):
            return svc
    return None


def deterministic_signal(scores, services):
    per_service = {}
    for col, s in scores.items():
        svc = service_from_metric(col, services)
        if svc is None:
            continue
        per_service.setdefault(svc, []).append(abs(s["z"]))
    ranked = sorted(per_service.items(), key=lambda kv: max(kv[1]) if kv[1] else 0, reverse=True)
    top3 = [svc for svc, _ in ranked[:3]]
    return top3, {svc: round(max(zs), 2) for svc, zs in ranked[:5]}


def query_metrics_evidence(scores, service, services):
    hits = {col: s for col, s in scores.items() if service_from_metric(col, services) == service}
    if not hits:
        return {"result": f"No metrics found for service '{service}'."}
    ranked = sorted(hits.items(), key=lambda kv: abs(kv[1]["z"]), reverse=True)[:6]
    return {"service": service, "metric_anomalies": [
        {"metric": c, "z_score_vs_pre_window": round(s["z"], 2),
         "pre_injection_mean": round(s["pre_mean"], 3), "post_injection_mean": round(s["post_mean"], 3)}
        for c, s in ranked
    ]}


def make_tools(services):
    return [
        {"type": "function", "function": {
            "name": "get_deterministic_signal",
            "description": "Cheap heuristic ranking services by largest post-injection metric z-score "
                            "deviation from their own pre-injection baseline. Fallible.",
            "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {
            "name": "query_metrics_evidence",
            "description": "Real per-metric z-score anomaly evidence for one service (no logs exist in "
                            "this benchmark suite).",
            "parameters": {"type": "object",
                            "properties": {"service": {"type": "string", "enum": services}},
                            "required": ["service"]}}},
        {"type": "function", "function": {
            "name": "get_service_dependencies",
            "description": "Real dependency info derived from this system's own code graph.",
            "parameters": {"type": "object",
                            "properties": {"service": {"type": "string", "enum": services}},
                            "required": ["service"]}}},
        {"type": "function", "function": {
            "name": "query_knowledge_graph",
            "description": "Real code-dependency graph of this system's actual source (AST-extracted). "
                            "MANDATORY at least once per investigation.",
            "parameters": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]}}},
        {"type": "function", "function": {
            "name": "recall_similar_past_incidents",
            "description": "Real FTS5 search over past investigated cases in this run's memory "
                            "(cold-started; may be empty early on). Current incident always excluded.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    ]


def run_case(client, system, case_id, fault, root_service, services):
    df, inject_time = load_case_metrics(case_id)
    scores = compute_anomaly_scores(df, inject_time)
    top3, top_z = deterministic_signal(scores, services)
    tools = make_tools(services)
    valid_names = [t["function"]["name"] for t in tools]

    sys_prompt = (
        f"You are investigating a real production incident in the {SYSTEMS[system]['name']} "
        f"microservices system (services: {', '.join(services)}). A fault was injected and metrics "
        f"were captured before and after. You do NOT know the fault type or which service is "
        f"affected -- find out.\n\n"
        f"Tools: get_deterministic_signal (cheap anomaly ranking, fallible), query_metrics_evidence "
        f"(detailed per-service metric z-scores -- primary evidence, no logs exist here), "
        f"query_knowledge_graph (real code-dependency graph -- MANDATORY at least once), "
        f"get_service_dependencies (real, graph-derived), recall_similar_past_incidents (real "
        f"episodic memory of past cases -- MANDATORY at least once).\n\n"
        f"Budget: at most 8 tool calls. Then answer EXACTLY: 'ROOT CAUSE: <service_name>. "
        f"REASON: <one sentence citing specific evidence>.' Valid service names: {', '.join(services)}."
    )
    messages = [{"role": "user", "content": sys_prompt}]
    final_text = ""
    graph_done = memory_done = False
    nudges = 0

    for round_num in range(8):
        resp = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=NVIDIA_MODEL, messages=messages, tools=tools,
                    tool_choice="auto", temperature=0, max_tokens=800)
                if resp.choices:
                    break
            except Exception as e:
                print(f"    [round {round_num}] API error (attempt {attempt+1}): {e}", flush=True)
            resp = None
            time.sleep(3 * (attempt + 1))
        if resp is None or not resp.choices:
            final_text = "ROOT CAUSE: unknown. REASON: API failure."
            break
        msg = resp.choices[0].message
        if not msg.tool_calls:
            content = msg.content or ""
            missing = [n for n, done in [("query_knowledge_graph", graph_done),
                                          ("recall_similar_past_incidents", memory_done)] if not done]
            if missing and nudges < 2:
                nudges += 1
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Call {missing[0]} now before answering -- mandatory."})
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
            if name not in valid_names:
                matched = [t for t in valid_names if t in name]
                name = max(matched, key=len) if matched else name
            print(f"    [tool] {name}({args})", flush=True)
            if name == "get_deterministic_signal":
                result = {"ranked_guess": top3, "z_scores": top_z}
            elif name == "query_metrics_evidence":
                result = query_metrics_evidence(scores, args.get("service", ""), services)
            elif name == "get_service_dependencies":
                result = get_service_dependencies(system, args.get("service", ""))
            elif name == "query_knowledge_graph":
                result = query_knowledge_graph(system, args.get("term", ""))
                graph_done = True
            elif name == "recall_similar_past_incidents":
                result = mem_recall(args.get("query", ""), exclude_incident_id=case_id)
                memory_done = True
            else:
                result = {"error": "unknown tool"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)[:2000]})
    else:
        final_text = "ROOT CAUSE: unknown. REASON: exhausted round budget."

    text_lower = final_text.lower()
    pred = None
    svc_sorted = sorted(services, key=len, reverse=True)
    if "root cause:" in text_lower:
        after = text_lower.split("root cause:", 1)[1]
        for svc in svc_sorted:
            if svc.lower() in after[:80]:
                pred = svc
                break
    if pred is None:
        for svc in svc_sorted:
            if svc.lower() in text_lower:
                pred = svc
                break
    return pred, final_text


def main():
    system = sys.argv[1] if len(sys.argv) > 1 else "ss"
    faults = sys.argv[2].split(",") if len(sys.argv) > 2 else ["cpu", "mem", "disk", "delay", "loss"]
    assert system in SYSTEMS, f"unknown system {system}, expected one of {list(SYSTEMS)}"

    gt = pd.read_parquet(HERE / "cases.parquet")
    subset = gt[(gt["suite"] == "RE1") & (gt["system"] == system) & (gt["fault"].isin(faults))]
    subset = subset.sort_values("case")

    # Derive service list from a sample case's real metric columns.
    sample_df = pd.read_parquet(HERE / subset.iloc[0]["case"] / "metrics.parquet")
    services = services_from_columns(sample_df.columns)
    print(f"System={system} ({SYSTEMS[system]['name']}), {len(services)} services detected: {services}", flush=True)

    results_path = HERE / f"gear_rca_re1_{system}_results.json"
    results = json.load(open(results_path)) if results_path.exists() else []
    done_ids = {r["incident_id"] for r in results}
    print(f"{len(done_ids)} cases already done, {len(subset) - len(done_ids)} remaining of {len(subset)} total", flush=True)

    client = get_llm_client()
    hits = sum(1 for r in results if r["hit"])
    n_run = len(results)
    for row in subset.itertuples():
        if row.case in done_ids:
            continue
        if not (HERE / row.case / "metrics.parquet").exists():
            print(f"SKIP {row.case}: metrics.parquet not downloaded yet", flush=True)
            continue
        t0 = time.time()
        try:
            pred, text = run_case(client, system, row.case, row.fault, row.root_cause_service, services)
        except Exception as e:
            print(f"ERROR on {row.case}: {e}", flush=True)
            continue
        elapsed = time.time() - t0
        hit = pred == row.root_cause_service
        hits += hit
        n_run += 1
        print(f"[{n_run}/{len(subset)}] {row.case} ({row.fault}) gold={row.root_cause_service} "
              f"pred={pred} hit={hit} ({elapsed:.1f}s)", flush=True)
        results.append({"incident_id": row.case, "fault_type": row.fault, "system": system,
                         "root_service": row.root_cause_service, "pred": pred,
                         "hit": bool(hit), "seconds": elapsed, "final_text": text[:1000]})
        json.dump(results, open(results_path, "w"), indent=2)
        mem_record(row.case, system, row.fault, row.root_cause_service, pred, hit, text)

    print(f"\n{system} RE1 ({','.join(faults)}): {hits}/{len(subset)} = {hits/max(len(subset),1)*100:.1f}% literal AC@1", flush=True)
    by_fault = {}
    for r in results:
        by_fault.setdefault(r["fault_type"], []).append(r["hit"])
    for f, hs in by_fault.items():
        print(f"  {f}: {sum(hs)}/{len(hs)} = {sum(hs)/len(hs)*100:.1f}%", flush=True)


if __name__ == "__main__":
    main()
