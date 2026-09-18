#!/usr/bin/env python3
"""Trace-based causal-attribution tool for RCAEval RE2 Train Ticket, adapted from
trace_causal_tool.py (built for Online Boutique's gRPC-style operationName strings
like "hipstershop.CurrencyService/Convert", which embed the callee service name).

Train Ticket's traces do NOT follow that convention -- verified directly on real data
(re2tt_ts-order-service_delay_1/traces.parquet): operationName values are internal
method/HTTP-route style strings ("find ts.station", "OrderRepository.findById",
"POST /api/v1/orderservice/order") with no embedded downstream-service name to regex
out. But `serviceName` is already a first-class column per span, so the adapted
mechanism doesn't need to infer a callee from a string -- it directly measures which
SERVICE's own operations show anomalous self-time.

Mechanism, verified on 5 real DELAY cases (one per gold service) before being trusted:
for each (serviceName, operationName) pair, compute mean self-time (span duration minus
child-span duration) in the pre- and post-injection windows, rank pairs by the ratio
(filtering out ones with a trivial absolute post value), take the top-N anomalous pairs.

Two ranking strategies were tried and compared on real data, not assumed equivalent:
- **Vote count** (how many of a service's operations appear in the top-N): 4/5 --
  missed `ts-auth-service` (3 votes, but its top ratio was 129.7x) because
  `ts-inside-payment-service` had more (5) but much weaker (max 2.3x) anomalous
  operations. Vote count rewards breadth over strength.
- **Max ratio per service** (the single largest self-time ratio owned by each service):
  **5/5** -- correctly promotes `ts-auth-service` since its strongest signal (129.7x)
  dominates. This is the ranking used below.

Self-time-by-SERVICE alone (no operation breakdown) does NOT work at all here --
verified on re2tt_ts-order-service_delay_1: gold ranked 4th by raw per-service ratio,
behind ts-preserve-service/ts-security-service/ts-inside-payment-service. The
operation-level breakdown is what actually localizes it; only the aggregation-across-
operations method (vote vs. max) needed tuning.
"""
import pandas as pd


def load_case_traces(case_dir, inject_time, pre_s=300, post_s=300):
    traces = pd.read_parquet(f"{case_dir}/traces.parquet")
    post = traces[(traces["startTimeMillis"] >= inject_time * 1000) &
                  (traces["startTimeMillis"] < (inject_time + post_s) * 1000)].copy()
    pre = traces[(traces["startTimeMillis"] >= (inject_time - pre_s) * 1000) &
                 (traces["startTimeMillis"] < inject_time * 1000)].copy()
    return pre, post


def _add_self_time(df):
    child_sum = df.groupby("parentSpanID")["duration"].sum()
    df = df.copy()
    df["self_duration"] = (df["duration"] - df["spanID"].map(child_sum).fillna(0)).clip(lower=0)
    return df


def trace_causal_anomaly(case_dir, inject_time, top_n_ops=20):
    """Real trace-based evidence for Train Ticket: rank services by the MAX self-time
    ratio any single one of their operations shows among the top-N anomalous
    (service, operation) pairs (verified 5/5 on real DELAY cases -- beats ranking by
    vote count, see module docstring). Returns a ranked list of
    {service, max_ratio, top_operations} -- not a single top pick, so the caller (LLM
    agent) can see the full picture rather than trust one number blindly.
    """
    pre, post = load_case_traces(case_dir, inject_time)
    pre_self, post_self = _add_self_time(pre), _add_self_time(post)

    pre_op = pre_self.groupby(["serviceName", "operationName"])["self_duration"].mean()
    post_op = post_self.groupby(["serviceName", "operationName"])["self_duration"].mean()
    common = post_op.index.intersection(pre_op.index)
    if len(common) == 0:
        return []
    ratio = post_op[common] / pre_op[common].clip(lower=1)
    ratio = ratio[post_op[common] > 100]  # ignore trivially small absolute post self-time
    if len(ratio) == 0:
        return []
    top = ratio.sort_values(ascending=False).head(top_n_ops)

    per_service = {}
    for (svc, op), r in top.items():
        per_service.setdefault(svc, {"votes": 0, "max_ratio": 0.0, "top_operations": []})
        per_service[svc]["votes"] += 1
        per_service[svc]["max_ratio"] = max(per_service[svc]["max_ratio"], float(r))
        per_service[svc]["top_operations"].append({"operation": op, "self_time_ratio": round(float(r), 2)})

    for svc in per_service:
        per_service[svc]["max_ratio"] = round(per_service[svc]["max_ratio"], 2)

    ranked = sorted(
        ({"service": svc, **data} for svc, data in per_service.items()),
        key=lambda x: x["max_ratio"], reverse=True,
    )
    return ranked[:10]


if __name__ == "__main__":
    import json
    cases_gold = {
        "re2tt_ts-order-service_delay_1": "ts-order-service",
        "re2tt_ts-route-service_delay_1": "ts-route-service",
        "re2tt_ts-train-service_delay_1": "ts-train-service",
        "re2tt_ts-travel-service_delay_1": "ts-travel-service",
        "re2tt_ts-auth-service_delay_1": "ts-auth-service",
    }
    for case, gold in cases_gold.items():
        inject_time = int(open(f"{case}/inject_time.txt").read().strip())
        ranked = trace_causal_anomaly(case, inject_time)
        top1 = ranked[0]["service"] if ranked else None
        print(f"{case}: gold={gold} top1={top1} hit={top1 == gold}")
        print(json.dumps(ranked[:3], indent=2))
        print()
