#!/usr/bin/env python3
"""Isolates ONE specific hypothesis the user asked about: does letting the
LLM QUERY the dependency graph itself (as its own tool call, its choice,
0+ times) do better or worse than just pasting the graph in as static text
(scratch_graph_llm_fusion.py, the current best real result)?

Every previous "let the LLM investigate" test (agentic_rca_baseline,
scratch_agentic_v3.py) bundled the graph-lookup tool together with FIVE
other tools (payment timeline, compliance, log search, risk, explain) and
multi-turn free-form investigation -- that combination scored worst of
everything tried (1-3/10). This script isolates the graph-tool piece
alone: identical structural evidence to the fusion prompt (funnel-stage,
validation-latency, z-score, health-check, domain-rare -- all still
pre-computed and handed over, same as fusion), but instead of a static
graph text block, the model gets exactly ONE real tool
(get_service_dependencies) and decides for itself whether to call it
before answering. Everything else held constant for a clean comparison.
"""
import json
import sys
import time

import pandas as pd

sys.path.insert(0, ".")
import eval_harness as eh

GRAPH_TOOL = [t for t in eh.AGENTIC_TOOLS if t["function"]["name"] == "get_service_dependencies"]
MAX_ROUNDS = 3


def build_prompt_no_graph(row):
    """Same as scratch_graph_llm_fusion.build_prompt's Section 2/3, but
    Section 1 offers a TOOL instead of pasting the graph in as text."""
    z_summary = f"  Max error-rate z-score across all 5 services this incident: {row.max_abs_z:.2f} (near 0 = flat/no anomaly, per-service breakdown not retained in this evidence snapshot)"

    if row.funnel_total >= 15 and row.funnel_reached_idx in (1, 2, 3):
        stage_root = {1: "aml-compliance", 2: "routing-execution", 3: "settlement"}[int(row.funnel_reached_idx)]
        funnel_str = (f"FUNNEL-STAGE SIGNAL (strong prior, ~81-100% historical precision): {int(row.funnel_total)} "
                      f"funnel events seen, furthest stage reached is index {int(row.funnel_reached_idx)} -- the "
                      f"funnel never advanced past this point, meaning payments piled up right before '{stage_root}'. "
                      f"This pattern has historically meant '{stage_root}' is the root cause.")
    else:
        funnel_str = f"Funnel-stage signal: no strong prior ({int(row.funnel_total)} events, furthest stage index {row.funnel_reached_idx if pd.notna(row.funnel_reached_idx) else 'n/a'})."

    if pd.notna(row.median_validation_latency_ms) and row.median_validation_latency_ms > 5000 and row.median_validation_latency_ms != 999999:
        lat_str = (f"VALIDATION-LATENCY SIGNAL (strong prior, ~300x separation historically): median "
                   f"validation latency {row.median_validation_latency_ms:.0f}ms, normal is ~100-300ms -- "
                   f"this has historically meant validation-enrichment is the root cause.")
    else:
        lat_str = "Validation-latency signal: not elevated, no strong prior from this signal."

    health_str = "A HEALTH_CHECK_FAILED event was recorded for a specific service this window -- direct, decisive evidence that service crashed." if row.has_health else "No HEALTH_CHECK_FAILED event recorded this window."
    domain_str = "A rare, decisive domain-specific log line (AML_SANCTIONS_HIT / DUPLICATE_DETECTED / WritableServerSelector) was found this window." if row.has_domain_rare else "No rare domain-specific log line found this window."

    return f"""You are a senior SRE doing real-time root-cause analysis on a live financial-payments incident. Pipeline order (each stage calls the next): {' -> '.join(eh.FULL_PIPELINE_ORDER)}

=== 1. TOOL AVAILABLE ===
You have access to `get_service_dependencies(service)`, which returns the REAL measured downstream dependents and code/broker context for one named service. Call it as many times as you find useful (including zero times) before giving your final answer. Use it to understand propagation direction -- a service with more real downstream dependents will show correlated symptoms whenever any of its downstream services fail; a loud symptom on a highly-connected service can be backpressure from something failing further downstream, not the root itself.

=== 2. REAL STRUCTURAL SIGNALS FOR THIS INCIDENT ===
{funnel_str}
{lat_str}
{z_summary}
{health_str}
{domain_str}

=== 3. YOUR TASK ===
The funnel-stage and validation-latency signals, when present, are this analysis's two most reliable priors -- trust them over graph/topology guessing when they fire. When neither fires, use the dependency-graph tool plus health-check/domain-log evidence to reason about propagation direction.

IMPORTANT GENERAL HEURISTIC: some real failure modes (e.g. a duplicate-payment rejection) happen entirely at the HTTP gateway layer, BEFORE any downstream service ever logs anything about that payment -- these are genuinely evidence-free everywhere except at the gateway itself. If you see NO real business-log evidence anywhere (no domain-rare line, no health-check hit), z-scores are flat, and neither structural signal above fired, that absence-of-evidence pattern is itself consistent with a gateway-layer rejection -- do not default to guessing aml-compliance or another "sounds serious" service just because it's not settlement/validation-enrichment; weigh gateway seriously as the answer in that specific situation.

When you are ready, respond with ONLY a comma-separated list of all 5 service names, most likely root cause first. Do not call any more tools once you give this final answer."""


def run_incident(row, client):
    messages = [{"role": "user", "content": build_prompt_no_graph(row)}]
    tool_calls_made = []
    final_text = ""
    for _ in range(MAX_ROUNDS):
        resp = client.chat.completions.create(
            model=eh.NVIDIA_MODEL, messages=messages, tools=GRAPH_TOOL,
            tool_choice="auto", temperature=0, max_tokens=700,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            final_text = msg.content or getattr(msg, "reasoning_content", "") or ""
            break
        messages.append({"role": "assistant", "content": msg.content,
                          "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            svc = args.get("service", "")
            tool_calls_made.append(svc)
            result = eh._get_service_dependencies_readonly(svc)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)[:2000]})
    else:
        resp = client.chat.completions.create(model=eh.NVIDIA_MODEL, messages=messages, temperature=0, max_tokens=700)
        final_text = resp.choices[0].message.content or ""

    text_lower = final_text.lower()
    found = sorted((svc for svc in eh.FULL_PIPELINE_ORDER if svc in text_lower), key=lambda svc: text_lower.index(svc))
    pred = found[0] if found else None
    return dict(pred=pred, hit=pred == row.true_root, raw_response=final_text,
                n_tool_calls=len(tool_calls_made), tool_calls=",".join(tool_calls_made))


if __name__ == "__main__":
    hard_ids = [
        "LIVE-02346c6a", "LIVE-ad1e058b", "LIVE-5961ed7b", "LIVE-4745d75e", "LIVE-e02375c2",
        "LIVE-5082610f", "LIVE-2ae40f2d", "LIVE-b82de1ed", "LIVE-a2ceeaba", "LIVE-f2204653",
    ]
    ev = pd.read_csv("fusion_evidence_143.csv").set_index("incident_id")
    fusion_res = pd.read_csv("scratch_graph_llm_fusion_143_results.csv").set_index("incident_id")
    client = eh._get_llm_client()

    rows = []
    for i, iid in enumerate(hard_ids, 1):
        row = ev.loc[iid]
        t0 = time.time()
        r = run_incident(row, client)
        dt = time.time() - t0
        print(f"[{i}/{len(hard_ids)}] {iid} ({row.fault_type}) true={row.true_root} "
              f"fusion_was={fusion_res.loc[iid, 'fusion_pred']} det_was={row.det_pred} "
              f"graph-tool={r['pred']} hit={r['hit']} tool_calls={r['tool_calls'] or '(none)'} ({dt:.1f}s)", flush=True)
        rows.append({"incident_id": iid, "fault_type": row.fault_type, "true_root": row.true_root,
                     "fusion_pred": fusion_res.loc[iid, "fusion_pred"], "det_pred": row.det_pred,
                     "graph_tool_pred": r["pred"], "graph_tool_hit": r["hit"],
                     "n_tool_calls": r["n_tool_calls"], "tool_calls": r["tool_calls"], "seconds": round(dt, 1)})

    df = pd.DataFrame(rows)
    df.to_csv("scratch_graph_tool_only_hard10_results.csv", index=False)
    print()
    print(f"graph-tool-only AC@1 on these 10 hard cases: {df.graph_tool_hit.sum()}/{len(df)}")
    print(f"(fusion already got all 10 of these wrong by construction; det also got all 10 wrong)")
