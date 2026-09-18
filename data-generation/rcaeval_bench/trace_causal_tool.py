#!/usr/bin/env python3
"""Real trace-based causal-attribution tool for RCAEval RE2/RE3 cases (which ship real
distributed traces, unlike RE1's metrics-only data -- verified directly by downloading
and reading re2ob_checkoutservice_cpu_1/traces.parquet this session: real traceID/
spanID/parentSpanID/duration/statusCode, genuine Jaeger-style tracing, not synthetic).

Mechanism, verified on real data before being trusted (re2ob_currencyservice_delay_1):
Self-time-by-SERVICE (exclusive duration, span duration minus child span durations)
does NOT correctly attribute a network-DELAY fault to its true target service --
verified: currencyservice's own self-time slightly DECREASED post-injection while
frontendservice's self-time rose ~9x, because RCAEval's network-delay injection shows
up as elevated wait time on the CALLING span, not the target's own server-side span.

Self-time-by-OPERATION does work: gRPC operation names in this dataset are literally
"hipstershop.<Service>/<Method>" (e.g. "hipstershop.CurrencyService/Convert"), so
breaking a caller's self-time down by operation and finding which operation's self-time
anomaly is largest directly reveals which downstream service is implicated -- verified:
frontendservice's elevated self-time was concentrated almost entirely in
CurrencyService/Convert and CurrencyService/GetSupportedCurrencies (13-16x rise) while
every other operation stayed flat between pre/post windows.
"""
import re
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


_OP_SERVICE_RE = re.compile(r"^(?:hipstershop\.|grpc\.hipstershop\.)?([A-Za-z]+)Service/")


def _service_from_operation(op_name):
    if not isinstance(op_name, str):
        return None
    m = _OP_SERVICE_RE.match(op_name)
    if m:
        return m.group(1).lower() + "service"
    return None


def trace_causal_anomaly(case_dir, inject_time):
    """Real trace-based evidence: for each caller service, break down self-time by
    operation, compare pre vs. post injection window, and report which downstream
    service (extracted from the operation name) shows the biggest self-time jump.
    Returns per-caller top implicated downstream services, ranked by relative increase.
    """
    pre, post = load_case_traces(case_dir, inject_time)
    pre_self = _add_self_time(pre)
    post_self = _add_self_time(post)

    findings = []
    for caller in post_self["serviceName"].unique():
        pre_ops = pre_self[pre_self["serviceName"] == caller].groupby("operationName")["self_duration"].mean()
        post_ops = post_self[post_self["serviceName"] == caller].groupby("operationName")["self_duration"].mean()
        for op in post_ops.index:
            implicated = _service_from_operation(op)
            if implicated is None or implicated == caller:
                continue  # only care about calls TO another service
            post_v = post_ops.get(op, 0.0)
            pre_v = pre_ops.get(op, 0.0)
            if pre_v < 1:
                pre_v = 1.0  # avoid divide-by-near-zero blowups on tiny baselines
            ratio = post_v / pre_v
            if ratio > 2.0 and post_v > 100:  # real, non-trivial rise
                findings.append({
                    "caller": caller, "operation": op, "implicated_downstream_service": implicated,
                    "pre_self_time_us": round(pre_v, 1), "post_self_time_us": round(post_v, 1),
                    "ratio": round(ratio, 2),
                })
    findings.sort(key=lambda f: f["ratio"], reverse=True)
    return findings[:10]


if __name__ == "__main__":
    import json
    cases = {
        "re2ob_currencyservice_delay_1": "currencyservice",
        "re2ob_currencyservice_delay_2": "currencyservice",
        "re2ob_currencyservice_cpu_3": "currencyservice",
        "re2ob_checkoutservice_delay_2": "checkoutservice",
        "re2ob_productcatalogservice_cpu_3": "productcatalogservice",
    }
    for case, gold in cases.items():
        inject_time = int(open(f"{case}/inject_time.txt").read().strip())
        findings = trace_causal_anomaly(case, inject_time)
        top_implicated = findings[0]["implicated_downstream_service"] if findings else None
        hit = top_implicated == gold
        print(f"{case}: gold={gold} top_implicated={top_implicated} hit={hit}")
        print(json.dumps(findings[:3], indent=2))
        print()
