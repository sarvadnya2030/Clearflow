#!/usr/bin/env python3
"""Groq-backed variant of gear_rca_tt_trace.py, for the DISK/LOSS/MEM/SOCKET expansion
batch specifically. Switched from NVIDIA NIM to Groq (api.groq.com) because NIM was
severely congested (both a sanity check and the initial 60-case batch made zero
progress in 35-45+ minutes).

Real, verified API differences from NIM, confirmed by direct test calls before writing
this file (not assumed):
1. Groq's `openai/gpt-oss-20b` does NOT support `logprobs`/`top_logprobs` -- a real
   `400 Bad Request: "logprobs is not supported with this model"` was returned when
   tested. Per the standing CLAUDE.md rule ("verify support directly... never guess"),
   this run's reasoning_traces_tt_groq/*.json files will have logprobs=None for every
   round -- a genuine backend limitation, not a bug in this harness.
2. The reasoning field is named `reasoning` on the message object, not
   `reasoning_content` like NIM's response -- handled below by checking both.
3. Tool-calling (`tools=[...]`, `tool_choice`) verified working identically to NIM via
   a real function-call test before trusting it.

**Methodological disclosure for any benchmark comparison**: this DISK/LOSS/MEM/SOCKET
batch runs on a different inference backend (Groq) than the CPU/DELAY batch (NVIDIA
NIM), even though both claim to serve "the same" openai/gpt-oss-20b model. Latency,
exact sampling behavior, and even subtle quantization/serving differences between
providers are real possible confounds -- this is disclosed here rather than silently
treating the two batches as identical conditions.
"""
import json
import os
import sys
import time
from pathlib import Path

import openai
import pandas as pd
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from gear_rca_tt_trace import (
    SERVICES, TOOLS, _VALID_TOOL_NAMES, HERE, NVIDIA_MODEL,
    query_metrics_evidence, query_knowledge_graph, mem_recall, mem_record,
    get_llm_client as get_nim_client,
)
from trace_causal_tool_tt import trace_causal_anomaly

RESULTS_PATH = HERE / "gear_rca_tt_trace_results_60new_groq.json"
GROQ_MODEL = "openai/gpt-oss-20b"


def get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


def _is_rate_limit_error(e):
    """Groq's free-tier TPM quota (verified: 8000 tokens/min) is easy to exceed
    mid-case. Real, confirmed error shape: openai.RateLimitError, HTTP 429,
    message containing 'rate_limit_exceeded'. Detect broadly (status code OR
    message content) so a differently-worded quota error still triggers fallback."""
    if isinstance(e, openai.RateLimitError):
        return True
    msg = str(e).lower()
    return "rate_limit" in msg or "429" in msg or "quota" in msg


def _call_llm(groq_client, nim_client, backend_state, **kwargs):
    """Try Groq first (per backend_state['current']); on a real rate-limit/quota
    error, permanently fall back to NIM for the rest of this case (Groq's TPM quota
    is small enough that bouncing back mid-case just re-triggers it). Returns
    (response, backend_used_this_call)."""
    if backend_state["current"] == "groq":
        try:
            resp = groq_client.chat.completions.create(model=GROQ_MODEL, **kwargs)
            return resp, "groq"
        except Exception as e:
            if _is_rate_limit_error(e):
                print(f"    [backend] Groq rate-limited ({e}) -- falling back to NIM for rest of this case", flush=True)
                backend_state["current"] = "nim"
            else:
                raise
    resp = nim_client.chat.completions.create(model=NVIDIA_MODEL, **kwargs)
    return resp, "nim"


def run_case(groq_client, nim_client, case_id, gold, fault_type, force_nim=False):
    inject_time = int((HERE / case_id / "inject_time.txt").read_text().strip())
    metrics_df = pd.read_parquet(HERE / case_id / "metrics.parquet")
    trace_findings = trace_causal_anomaly(str(HERE / case_id), inject_time)

    sys_prompt = (
        f"You are investigating a real incident in the Train Ticket microservices system "
        f"(a large train-booking platform, {len(SERVICES)} services: {', '.join(SERVICES)}). "
        f"Fault type category: {fault_type} (unknown to you in general, but you have real "
        f"evidence tools). Tools: query_metrics_evidence (resource/latency z-scores per "
        f"service), trace_causal_analysis (real distributed-trace evidence: ranks services "
        f"by their own operations' self-time anomaly), query_knowledge_graph (MANDATORY), "
        f"recall_similar_past_incidents (MANDATORY). Budget: 10 tool calls. Then answer "
        f"EXACTLY: 'ROOT CAUSE: <service_name>. REASON: <one sentence>.' "
        f"Valid services: {', '.join(SERVICES)}."
    )
    messages = [{"role": "user", "content": sys_prompt}]
    graph_done = memory_done = False
    nudges = 0
    final_text = ""
    last_stated_answer = None
    round_log = []
    # per-case: starts on Groq unless force_nim (Groq's daily quota confirmed exhausted
    # 2026-09-18 -- ~199,243/200,000 used -- Groq-first just adds retry overhead before
    # falling back anyway). Groq-first logic kept intact for future use, not removed.
    backend_state = {"current": "nim" if force_nim else "groq"}

    for round_num in range(10):
        resp = None
        backend_used = None
        for attempt in range(3):
            try:
                extra = {} if backend_state["current"] == "groq" else {"logprobs": True, "top_logprobs": 3}
                resp, backend_used = _call_llm(groq_client, nim_client, backend_state,
                                                messages=messages, tools=TOOLS, tool_choice="auto",
                                                temperature=0, max_tokens=800, **extra)
                if resp.choices:
                    break
            except Exception as e:
                print(f"    [round {round_num}] API error (attempt {attempt+1}, backend={backend_state['current']}): {e}", flush=True)
            resp = None
            time.sleep(3 * (attempt + 1))
        if resp is None or not resp.choices:
            final_text = "ROOT CAUSE: unknown. REASON: API failure."
            break
        msg = resp.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
        round_log.append({
            "round": round_num,
            "backend": backend_used,
            "reasoning_content": reasoning,
            "content": msg.content or "",
            "tool_calls": [{"name": tc.function.name, "arguments": tc.function.arguments}
                           for tc in (msg.tool_calls or [])],
            "logprobs": (resp.choices[0].logprobs.model_dump()
                         if backend_used == "nim" and getattr(resp.choices[0], "logprobs", None) else None),
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
                result = {"services_ranked_by_max_self_time_anomaly": trace_findings}
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
            resp, _ = _call_llm(groq_client, nim_client, backend_state,
                                 messages=messages, tool_choice="none", temperature=0, max_tokens=1000)
            fmsg = resp.choices[0].message
            final_text = fmsg.content or getattr(fmsg, "reasoning_content", None) or getattr(fmsg, "reasoning", None) or ""
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


def run_batch(cases, results_path=None, force_nim=False):
    results_path = Path(results_path) if results_path else RESULTS_PATH
    results = json.load(open(results_path)) if results_path.exists() else []
    done = {r["incident_id"] for r in results}
    groq_client = get_groq_client()
    nim_client = get_nim_client()
    traces_dir = HERE / "reasoning_traces_tt_groq"
    traces_dir.mkdir(exist_ok=True)
    for cid, gold, fault in cases:
        if cid in done:
            continue
        t0 = time.time()
        pred, text, round_log = run_case(groq_client, nim_client, cid, gold, fault, force_nim=force_nim)
        elapsed = time.time() - t0
        hit = pred == gold
        backends_used = sorted(set(r["backend"] for r in round_log)) or ["unknown"]
        print(f"{cid}: gold={gold} pred={pred} hit={hit} ({elapsed:.1f}s) backends={backends_used}", flush=True)
        results.append({"incident_id": cid, "root_service": gold, "fault_type": fault,
                         "pred": pred, "hit": bool(hit), "seconds": elapsed, "final_text": text[:1000],
                         "backends_used": backends_used})
        json.dump(results, open(results_path, "w"), indent=2)
        json.dump(round_log, open(traces_dir / f"{cid}.json", "w"), indent=2, default=str)
        mem_record(cid, "tt", fault, gold, pred, hit, text)
    hits = sum(r["hit"] for r in results)
    print(f"\n{hits}/{len(results)} = {100*hits/len(results):.1f}%")
    return results
