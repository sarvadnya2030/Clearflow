"""One-off: test nvidia/nemotron-3-super-120b-a12b (extended thinking) on a
real hardest-core case gpt-oss-20b still fails, reusing already-verified
tool functions from gear_rca_rcaeval.py (no re-derivation)."""
import json
import os
import sys
import time

from openai import OpenAI

from gear_rca_rcaeval import (
    load_case_metrics, compute_anomaly_scores, compute_onset_times,
    deterministic_signal, query_metrics_evidence, get_service_dependencies,
    query_knowledge_graph, onset_time_analysis, mem_recall, SERVICES, TOOLS,
)

MODEL = "nvidia/nemotron-3-super-120b-a12b"


def run_nemotron_case(client, case_id, gold):
    df, inject_time = load_case_metrics(case_id)
    scores = compute_anomaly_scores(df, inject_time)
    top3, top_z = deterministic_signal(scores)
    onsets = compute_onset_times(df, inject_time)

    sys_prompt = (
        f"You are investigating a real production incident in the Online Boutique microservices "
        f"system (services: {', '.join(SERVICES)}). A fault was injected. You do NOT know the fault "
        f"type or which service is affected -- find out using the tools.\n\n"
        f"IMPORTANT: a spike in a service's OWN primary resource metric is much stronger evidence "
        f"that IT is the root cause than a spike in a DIFFERENT service's latency/error-rate metric, "
        f"which is usually a propagated symptom of a caller being slowed by a struggling dependency.\n\n"
        f"Budget: at most 8 tool calls. After that, answer in EXACTLY this format: "
        f"'ROOT CAUSE: <service_name>. REASON: <one sentence citing specific evidence>.' "
        f"Valid service names: {', '.join(SERVICES)}."
    )
    messages = [{"role": "user", "content": sys_prompt}]
    graph_done = memory_done = False
    final_text = ""
    for round_num in range(8):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto",
            temperature=1, top_p=0.95, max_tokens=4000,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4000},
        )
        msg = resp.choices[0].message
        print(f"  [round {round_num}] reasoning_len={len(getattr(msg,'reasoning_content','') or '')} "
              f"tool_calls={[tc.function.name for tc in (msg.tool_calls or [])]}", flush=True)
        if not msg.tool_calls:
            final_text = msg.content or ""
            break
        messages.append({"role": "assistant", "content": msg.content,
                          "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            name = tc.function.name
            if name == "get_deterministic_signal":
                result = {"ranked_guess": top3, "z_scores": top_z}
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
            else:
                result = {"error": "unknown tool"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)[:2000]})
    else:
        resp = client.chat.completions.create(
            model=MODEL, messages=messages + [{"role": "user", "content": "Answer NOW with what you have."}],
            tool_choice="none", temperature=1, top_p=0.95, max_tokens=4000,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4000},
        )
        final_text = resp.choices[0].message.content or ""

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
    return pred, final_text


if __name__ == "__main__":
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"))
    case_id = sys.argv[1] if len(sys.argv) > 1 else "re1ob_cartservice_delay_4"
    gold = sys.argv[2] if len(sys.argv) > 2 else "cartservice"
    t0 = time.time()
    pred, text = run_nemotron_case(client, case_id, gold)
    print(f"\n{case_id}: gold={gold} pred={pred} hit={pred==gold} ({time.time()-t0:.1f}s)")
    print("final_text:", text[:400])
