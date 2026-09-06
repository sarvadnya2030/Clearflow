#!/usr/bin/env python3
"""Real multi-round tool-calling RCA agent, using Claude instead of
gpt-oss-20b as the reasoning model. Every prior agentic attempt in this
project (scratch_agentic_v2/v3/v4, agentic_rca_baseline) used gpt-oss-20b
(20B params) via NVIDIA's API and scored 1-3/10 with real run-to-run
instability (same input, different answer). The open question this script
tests: is that a property of "agentic tool-calling for this task" in
general, or specifically of that one small/weak model plus its bare-bones
harness (no verification step, minimal tool descriptions, no explicit
reasoning guidance)?

Same real tools, same real MCP endpoints, same evidence-gathering as
eval_harness.py's _agentic_tool_loop -- only the model and prompt/tool
framing change. Requires ANTHROPIC_API_KEY in the environment.

Usage:
    export ANTHROPIC_API_KEY=...
    python3 scratch_claude_agentic.py                  # runs the 10 hard cases
    python3 scratch_claude_agentic.py --full            # runs the full 143-incident set
"""
import argparse
import json
import os
import sys
import time

import pandas as pd

sys.path.insert(0, ".")
import eval_harness as eh

CLAUDE_MODEL = "claude-sonnet-4-5"  # override with --model if needed
MAX_TOOL_ROUNDS = 6

# Same 4 real tools as eval_harness.AGENTIC_TOOLS, converted from OpenAI's
# {"type": "function", "function": {...}} shape to Anthropic's flat
# {"name", "description", "input_schema"} shape. Same descriptions,
# same semantics, same real MCP-backed implementations -- only the
# schema envelope differs between the two APIs.
CLAUDE_TOOLS = [
    {"name": t["function"]["name"], "description": t["function"]["description"],
     "input_schema": t["function"]["parameters"]}
    for t in eh.AGENTIC_TOOLS
]

SYSTEM_PROMPT_PREFIX = """You are a senior SRE doing real-time root-cause analysis on a live financial-payments incident, investigating carefully before committing to an answer.

Pipeline order (each stage calls the next): {pipeline}

You have real tools available to investigate specific payments, search logs, and inspect service dependencies -- use them if they would sharpen your diagnosis, but do not call the same tool with the same arguments twice, and do not investigate more than necessary: if the evidence already points clearly at one service, say so rather than padding out tool calls.

Before your final answer, briefly state your reasoning: which evidence was decisive and why. Then, on its own final line, respond with EXACTLY this format (nothing else on that line):
FINAL: <service1>, <service2>, <service3>, <service4>, <service5>
listing all 5 real service names ({pipeline_csv}), most likely root cause first.
"""


def _execute_tool(name, args, start, end, payment_ids, queried_already, token):
    if name in ("get_payment_timeline", "get_payment_compliance"):
        num = args.get("payment_number")
        pid = payment_ids[num - 1] if isinstance(num, int) and 1 <= num <= len(payment_ids) else None
        dedup_key = (name, pid)
        if pid is None:
            return {"error": f"payment_number {num} is out of range -- use a number from the list shown, 1-{len(payment_ids)}."}
        if dedup_key in queried_already:
            return {"note": "You already queried this exact payment/tool -- inspect a DIFFERENT payment or give your final answer."}
        queried_already.add(dedup_key)
        try:
            if name == "get_payment_timeline":
                result = eh._mcp_get(f"/mcp/payments/{pid}/timeline", token)
                eh._annotate_timeline_durations(result)
            else:
                result = eh._mcp_get(f"/mcp/payments/{pid}/compliance", token)
            return result
        except Exception as e:
            return {"error": str(e)}
    elif name == "search_service_logs":
        svc, kw = args.get("service", ""), args.get("keyword")
        dedup_key = (name, svc, kw)
        if dedup_key in queried_already:
            return {"note": "You already ran this exact search -- try a different service or keyword."}
        queried_already.add(dedup_key)
        return eh._search_service_logs(start, end, svc, kw)
    elif name == "get_service_dependencies":
        svc = args.get("service", "")
        dedup_key = (name, svc)
        if dedup_key in queried_already:
            return {"note": "You already looked up this service's dependencies."}
        queried_already.add(dedup_key)
        return eh._get_service_dependencies_readonly(svc)
    return {"error": "unknown tool"}


def run_incident(row, metrics, payments, client, model_name):
    import anthropic
    scores, start, end = eh._service_zscores(row, metrics)
    window_payments = payments[(payments.created_at >= start) & (payments.created_at <= end)]
    payment_ids = window_payments["payment_id"].tolist() if "payment_id" in window_payments.columns else []
    fracs = eh._compute_payment_state_fracs_readonly(window_payments, end)
    sample_logs = eh._fetch_sample_logs_for_agentic(start, end)
    token = eh._get_mcp_token()

    pipeline = " -> ".join(eh.FULL_PIPELINE_ORDER)
    system = SYSTEM_PROMPT_PREFIX.format(pipeline=pipeline, pipeline_csv=", ".join(eh.FULL_PIPELINE_ORDER))
    # Reuse the exact real-evidence body eval_harness already builds for
    # the gpt-oss-20b agentic prompt (z-scores, fracs, sample logs,
    # payment list) -- only the system framing/tool schema differ here.
    evidence_body = eh._agentic_system_prompt(scores, payment_ids, fracs, sample_logs)

    messages = [{"role": "user", "content": evidence_body}]
    queried_already = set()
    tool_call_log = []
    final_text = ""

    for round_i in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=model_name, max_tokens=2000, system=system,
            tools=CLAUDE_TOOLS, messages=messages,
        )
        text_blocks = [b.text for b in resp.content if b.type == "text"]
        tool_blocks = [b for b in resp.content if b.type == "tool_use"]

        if not tool_blocks:
            final_text = "\n".join(text_blocks)
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for tb in tool_blocks:
            result = _execute_tool(tb.name, tb.input, start, end, payment_ids, queried_already, token)
            tool_call_log.append(f"{tb.name}({tb.input})")
            tool_results.append({"type": "tool_result", "tool_use_id": tb.id,
                                  "content": json.dumps(result, default=str)[:2000]})
        messages.append({"role": "user", "content": tool_results})
    else:
        final_text = "\n".join(b.text for b in resp.content if b.type == "text")

    pred = None
    for line in final_text.splitlines():
        if line.strip().upper().startswith("FINAL:"):
            names = [s.strip() for s in line.split(":", 1)[1].split(",")]
            pred = next((n for n in names if n in eh.FULL_PIPELINE_ORDER), None)
            break
    if pred is None:  # fallback: first real service name mentioned anywhere
        low = final_text.lower()
        found = sorted((s for s in eh.FULL_PIPELINE_ORDER if s in low), key=lambda s: low.index(s))
        pred = found[0] if found else None

    return dict(pred=pred, hit=pred == row.get("true_root", row.get("root_service")),
                raw_response=final_text, n_tool_calls=len(tool_call_log),
                tool_calls="; ".join(tool_call_log))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="run all 143 incidents instead of the 10 hard cases")
    ap.add_argument("--model", default=CLAUDE_MODEL)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set -- export it first.")
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic()

    payments = pd.read_csv("output_live/clearflow_rca_dataset.csv")
    payments["created_at"] = pd.to_datetime(payments["created_at"], utc=True, errors="coerce")
    metrics = pd.read_csv("output_live/metrics.csv")
    metrics["timestamp"] = pd.to_datetime(metrics["timestamp"], utc=True, errors="coerce")

    if args.full:
        inc = pd.read_csv("output_live/incidents.csv")
    else:
        hard_ids = ["LIVE-02346c6a", "LIVE-ad1e058b", "LIVE-5961ed7b", "LIVE-4745d75e", "LIVE-e02375c2",
                    "LIVE-5082610f", "LIVE-2ae40f2d", "LIVE-b82de1ed", "LIVE-a2ceeaba", "LIVE-f2204653"]
        all_inc = pd.read_csv("output_live/incidents.csv")
        inc = all_inc[all_inc.incident_id.isin(hard_ids)]

    rows = []
    for i, (_, row) in enumerate(inc.iterrows(), 1):
        t0 = time.time()
        try:
            r = run_incident(row, metrics, payments, client, args.model)
        except Exception as e:
            r = dict(pred=f"ERROR:{e}", hit=False, raw_response="", n_tool_calls=0, tool_calls="")
        dt = time.time() - t0
        print(f"[{i}/{len(inc)}] {row['incident_id']} ({row['fault_type']}) true={row['root_service']} "
              f"claude={r['pred']} hit={r['hit']} tool_calls={r['n_tool_calls']} ({dt:.1f}s)", flush=True)
        rows.append({"incident_id": row["incident_id"], "fault_type": row["fault_type"],
                     "true_root": row["root_service"], "claude_pred": r["pred"], "claude_hit": r["hit"],
                     "n_tool_calls": r["n_tool_calls"], "tool_calls": r["tool_calls"], "seconds": round(dt, 1)})

    df = pd.DataFrame(rows)
    out = "scratch_claude_agentic_full_results.csv" if args.full else "scratch_claude_agentic_hard10_results.csv"
    df.to_csv(out, index=False)
    print()
    print(f"Claude agentic AC@1: {df.claude_hit.sum()}/{len(df)} = {df.claude_hit.mean():.3f}")


if __name__ == "__main__":
    main()
