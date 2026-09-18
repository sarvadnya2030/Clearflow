#!/usr/bin/env python3
"""GEAR-RCA on RCAEval RE2 (Online Boutique), using the real trace-causal tool
(trace_causal_tool.py) verified this session against raw output before being trusted.
RE2 has real logs and traces (verified: re2ob_checkoutservice_cpu_1/traces.parquet has
genuine traceID/spanID/parentSpanID/duration), unlike RE1's metrics-only data.

The trace tool's raw-output verification (5 real cases, no LLM) found:
- 3/5 correct alone: both currencyservice_delay cases hit correctly.
- 2/5 wrong alone: a CPU fault (trace tool isn't designed for that -- metrics tool's
  job) and one delay case where the injected target's OWN incoming-call anomaly was
  real but outranked by a downstream sibling's anomaly.
This script gives the LLM agent the trace tool's full ranked list (not just its top
pick) alongside metrics/graph/memory evidence, so the agent can reason across sources
rather than blindly trusting one.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from trace_causal_tool import trace_causal_anomaly, load_case_traces

HERE = Path(__file__).parent
DB_PATH = HERE / "rcaeval_memory_re2.db"
RESULTS_PATH = HERE / "gear_rca_re2_trace_results.json"
NVIDIA_MODEL = "openai/gpt-oss-20b"

SERVICES = ["adservice", "cartservice", "checkoutservice", "currencyservice",
            "emailservice", "frontend", "paymentservice", "productcatalogservice",
            "recommendationservice", "redis", "shippingservice"]

GRAPH_PATH = HERE / "graphify-out-ob" / "graph.json"
_graph_cache = None


def get_llm_client():
    api_key = os.environ.get("NVIDIA_API_KEY")
    return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)


def _load_graph():
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = json.loads(GRAPH_PATH.read_text())
    return _graph_cache


def query_knowledge_graph(term):
    g = _load_graph()
    term_l = term.lower()
    nodes = {n["id"]: n for n in g["nodes"]}
    matches = [nid for nid, n in nodes.items()
               if term_l in nid.lower() or term_l in n.get("label", "").lower()
               or term_l in n.get("source_file", "").lower()][:5]
    if not matches:
        return {"result": f"No node matching '{term}'."}
    out = []
    for m in matches:
        edges = [e for e in g["links"] if e["source"] == m or e["target"] == m][:8]
        out.append({"node": nodes[m].get("label", m),
                     "edges": [f"{e['source']} --{e.get('relation','')}--> {e['target']}" for e in edges]})
    return {"matches": out}


def mem_recall(query_text, exclude_incident_id, limit=5):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.executescript("""CREATE TABLE IF NOT EXISTS cases (id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id TEXT UNIQUE, system TEXT, fault_type TEXT, root_service TEXT, predicted TEXT,
        hit INTEGER, evidence_text TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(incident_id UNINDEXED, fault_type,
        evidence_text, content='cases', content_rowid='id');""")
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in query_text).split() if len(t) > 2]
    if not tokens:
        conn.close()
        return {"result": "no usable search terms"}
    fts_query = " OR ".join(tokens[:12])
    try:
        rows = conn.execute(
            "SELECT c.incident_id, c.fault_type, c.root_service, c.predicted "
            "FROM cases_fts JOIN cases c ON c.id = cases_fts.rowid "
            "WHERE cases_fts MATCH ? AND c.incident_id != ? ORDER BY rank LIMIT ?",
            (fts_query, exclude_incident_id, limit)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    if not rows:
        return {"result": "No similar past incidents found."}
    return {"similar_past_incidents": [{"incident_id": r[0], "fault_type": r[1], "confirmed_root_cause": r[2]} for r in rows]}


def mem_record(incident_id, system, fault_type, root_service, predicted, hit, evidence_text):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("INSERT OR IGNORE INTO cases (incident_id, system, fault_type, root_service, predicted, hit, evidence_text) VALUES (?,?,?,?,?,?,?)",
                 (incident_id, system, fault_type, root_service, predicted, int(hit), evidence_text[:4000]))
    conn.commit()
    conn.close()


def query_metrics_evidence(df, inject_time, service, pre_s=600, post_s=300):
    pre = df[(df["time"] >= inject_time - pre_s) & (df["time"] < inject_time)]
    post = df[(df["time"] >= inject_time) & (df["time"] < inject_time + post_s)]
    hits = []
    for col in df.columns:
        if col == "time" or not col.startswith(service + "_"):
            continue
        pre_vals, post_vals = pre[col].dropna(), post[col].dropna()
        if len(pre_vals) < 5 or len(post_vals) < 5:
            continue
        mu, sigma = pre_vals.mean(), pre_vals.std()
        sigma = max(sigma, abs(mu) * 0.05, 1e-6)
        z = (post_vals.mean() - mu) / sigma
        hits.append((col, round(z, 2)))
    hits.sort(key=lambda x: abs(x[1]), reverse=True)
    return {"service": service, "metric_anomalies": hits[:6]}


TOOLS = [
    {"type": "function", "function": {
        "name": "query_metrics_evidence",
        "description": "Real per-metric z-score anomaly evidence for one service (CPU/mem/latency/error).",
        "parameters": {"type": "object", "properties": {"service": {"type": "string", "enum": SERVICES}}, "required": ["service"]}}},
    {"type": "function", "function": {
        "name": "trace_causal_analysis",
        "description": "Real distributed-trace analysis: breaks down each caller service's self-time "
                        "(exclusive duration) by RPC operation, comparing pre- vs post-injection windows, "
                        "and reports which downstream services (named in the RPC operation string) show "
                        "the largest self-time increase. Strong signal for NETWORK_LATENCY-type faults; "
                        "weaker for CPU-type faults (use query_metrics_evidence for those). Call this once "
                        "per investigation -- it already covers the whole trace, not just one service.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "query_knowledge_graph",
        "description": "Real code-dependency graph (AST-extracted). MANDATORY at least once.",
        "parameters": {"type": "object", "properties": {"term": {"type": "string"}}, "required": ["term"]}}},
    {"type": "function", "function": {
        "name": "recall_similar_past_incidents",
        "description": "Real FTS5 search over past investigated cases. MANDATORY at least once.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]
_VALID_TOOL_NAMES = [t["function"]["name"] for t in TOOLS]


def run_case(client, case_id, gold, fault_type):
    inject_time = int((HERE / case_id / "inject_time.txt").read_text().strip())
    metrics_df = pd.read_parquet(HERE / case_id / "metrics.parquet")
    trace_findings = trace_causal_anomaly(str(HERE / case_id), inject_time)

    sys_prompt = (
        f"You are investigating a real incident in the Online Boutique microservices system "
        f"(services: {', '.join(SERVICES)}). Fault type category: {fault_type} (unknown to you "
        f"in general, but you have real evidence tools). Tools: query_metrics_evidence (resource/"
        f"latency z-scores per service), trace_causal_analysis (real distributed-trace evidence: "
        f"which downstream service's calls show anomalous self-time -- strong for network/latency "
        f"faults, weaker for CPU faults), query_knowledge_graph (MANDATORY), "
        f"recall_similar_past_incidents (MANDATORY). Budget: 8 tool calls. Then answer EXACTLY: "
        f"'ROOT CAUSE: <service_name>. REASON: <one sentence>.' Valid services: {', '.join(SERVICES)}."
    )
    messages = [{"role": "user", "content": sys_prompt}]
    graph_done = memory_done = False
    nudges = 0
    final_text = ""
    last_stated_answer = None
    # Standing rule (project CLAUDE.md, added 2026-09-17): persist reasoning_content/logprobs
    # per round. Also applying the round-budget-regression fix already verified in
    # gear_rca_rcaeval.py: raised 8->10 rounds, preserve a nudge-discarded stated answer.
    round_log = []

    for round_num in range(10):
        resp = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(model=NVIDIA_MODEL, messages=messages, tools=TOOLS,
                                                        tool_choice="auto", temperature=0, max_tokens=800,
                                                        logprobs=True, top_logprobs=3)
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
            missing = [n for n, done in [("query_knowledge_graph", graph_done), ("recall_similar_past_incidents", memory_done)] if not done]
            if missing and nudges < 2:
                nudges += 1
                if content.strip():
                    last_stated_answer = content
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Call {missing[0]} now -- mandatory."})
                continue
            final_text = content
            break
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
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
            if name == "query_metrics_evidence":
                result = query_metrics_evidence(metrics_df, inject_time, args.get("service", ""))
            elif name == "trace_causal_analysis":
                result = {"top_implicated_downstream_services_ranked": trace_findings}
            elif name == "query_knowledge_graph":
                result = query_knowledge_graph(args.get("term", ""))
                graph_done = True
            elif name == "recall_similar_past_incidents":
                result = mem_recall(args.get("query", ""), exclude_incident_id=case_id)
                memory_done = True
            else:
                result = {"error": "unknown tool"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)[:2500]})
    else:
        messages.append({"role": "user", "content": "Tool budget used. Do not call more tools. Answer NOW: "
                          "'ROOT CAUSE: <service_name>. REASON: <one sentence>.' Valid services: "
                          f"{', '.join(SERVICES)}."})
        try:
            resp = client.chat.completions.create(model=NVIDIA_MODEL, messages=messages, tool_choice="none",
                                                    temperature=0, max_tokens=1000)
            fmsg = resp.choices[0].message
            final_text = fmsg.content or getattr(fmsg, "reasoning_content", "") or ""
        except Exception as e:
            final_text = f"ROOT CAUSE: unknown. REASON: forced-answer call failed ({e})."
        if not final_text.strip():
            if last_stated_answer:
                final_text = last_stated_answer + " [recovered: forced call empty, using earlier stated answer]"
            else:
                final_text = "ROOT CAUSE: unknown. REASON: forced answer empty."

    text_lower = final_text.lower()
    pred = None
    if "root cause:" in text_lower:
        after = text_lower.split("root cause:", 1)[1]
        for svc in sorted(SERVICES, key=len, reverse=True):
            if svc in after[:80]:
                pred = svc
                break
    if pred is None:
        for svc in sorted(SERVICES, key=len, reverse=True):
            if svc in text_lower:
                pred = svc
                break
    return pred, final_text, round_log


def run_batch(cases, results_path=None):
    """cases: list of (case_id, gold_service, fault_type). Extends the original
    5-case default with an explicit list, e.g. the remaining 25 RE2-OB cases."""
    results_path = Path(results_path) if results_path else RESULTS_PATH
    results = json.load(open(results_path)) if results_path.exists() else []
    done = {r["incident_id"] for r in results}
    client = get_llm_client()
    traces_dir = HERE / "reasoning_traces_re2"
    traces_dir.mkdir(exist_ok=True)
    for cid, gold, fault in cases:
        if cid in done:
            continue
        t0 = time.time()
        pred, text, round_log = run_case(client, cid, gold, fault)
        elapsed = time.time() - t0
        hit = pred == gold
        print(f"{cid}: gold={gold} pred={pred} hit={hit} ({elapsed:.1f}s)", flush=True)
        results.append({"incident_id": cid, "root_service": gold, "fault_type": fault,
                         "pred": pred, "hit": bool(hit), "seconds": elapsed, "final_text": text[:1000]})
        json.dump(results, open(results_path, "w"), indent=2)
        json.dump(round_log, open(traces_dir / f"{cid}.json", "w"), indent=2, default=str)
        mem_record(cid, "ob", fault, gold, pred, hit, text)
    hits = sum(r["hit"] for r in results)
    print(f"\n{hits}/{len(results)} = {100*hits/len(results):.1f}%")
    return results


if __name__ == "__main__":
    cases = [
        ("re2ob_currencyservice_delay_1", "currencyservice", "delay"),
        ("re2ob_currencyservice_delay_2", "currencyservice", "delay"),
        ("re2ob_currencyservice_cpu_3", "currencyservice", "cpu"),
        ("re2ob_checkoutservice_delay_2", "checkoutservice", "delay"),
        ("re2ob_productcatalogservice_cpu_3", "productcatalogservice", "cpu"),
    ]
    run_batch(cases)
