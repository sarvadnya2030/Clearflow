#!/usr/bin/env python3
"""Builds the same evidence columns scratch_graph_llm_fusion.py expects
(from scratch_fused_hybrid_v6/v7_results.csv, originally computed for the
101-incident benchmark) for the full 143-incident output_live set instead,
reusing rca_tool.py's already-validated ES-querying internals rather than
reimplementing them. Lets the real graph+LLM fusion method run against the
current, fresh dataset -- not just the older 101-benchmark it was built
against.
"""
import sys

import pandas as pd

sys.path.insert(0, ".")
import eval_harness as eh
import rca_tool as rt

inc = pd.read_csv("output_live/incidents.csv")
payments = pd.read_csv("output_live/clearflow_rca_dataset.csv")
payments["created_at"] = pd.to_datetime(payments["created_at"], utc=True, errors="coerce")
metrics = pd.read_csv("output_live/metrics.csv")
metrics["timestamp"] = pd.to_datetime(metrics["timestamp"], utc=True, errors="coerce")

rows = []
for i, (_, row) in enumerate(inc.iterrows(), 1):
    start = pd.Timestamp(row["injection_time"])
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    end = start + pd.Timedelta(seconds=float(row["duration_seconds"]) + 30)

    events = rt._fetch_events(start, end)
    down_services = rt._fetch_health_events(start, end)
    has_health = len(down_services) == 1
    domain_hits = rt._fetch_domain_rare_events(start, end)
    has_domain_rare = bool(domain_hits)
    funnel_total, funnel_reached_idx, funnel_stall = rt._funnel_signal(events)
    med_lat = rt._median_validation_latency(payments, start, end)

    max_abs_z = 0.0
    for svc in rt.FULL_PIPELINE_ORDER:
        base = metrics[(metrics.service == svc) & (metrics.timestamp >= start - pd.Timedelta(hours=eh.LOOKBACK_HOURS)) & (metrics.timestamp < start)]
        window = metrics[(metrics.service == svc) & (metrics.timestamp >= start) & (metrics.timestamp <= end)]
        if len(base) < 3 or len(window) == 0:
            continue
        mu, sigma = base.error_rate.mean(), max(base.error_rate.std(), eh.MIN_ERROR_RATE_SIGMA)
        max_abs_z = max(max_abs_z, abs((window.error_rate.mean() - mu) / sigma))

    det_result = rt.diagnose(row["injection_time"], row["duration_seconds"], payments_df=payments, metrics_df=metrics)
    det_pred = det_result["prediction"]

    rows.append({
        "incident_id": row["incident_id"], "fault_type": row["fault_type"], "true_root": row["root_service"],
        "max_abs_z": max_abs_z, "has_health": has_health, "has_domain_rare": has_domain_rare,
        "funnel_total": funnel_total, "funnel_reached_idx": funnel_reached_idx, "funnel_stall": funnel_stall,
        "median_validation_latency_ms": med_lat if pd.notna(med_lat) else rt.SENTINEL_LATENCY_MS,
        "det_pred": det_pred, "det_hit": det_pred == row["root_service"],
        "v6_pred": det_pred, "v6_hit": det_pred == row["root_service"],  # no separate v6-only variant here; det IS the current rules pipeline
    })
    print(f"[{i}/{len(inc)}] {row['incident_id']} built (det_pred={det_pred})", flush=True)

df = pd.DataFrame(rows).set_index("incident_id")
df.to_csv("fusion_evidence_143.csv")
print(f"\nWrote {len(df)} rows to fusion_evidence_143.csv")
print("det AC@1:", df.det_hit.sum(), "/", len(df), "=", round(df.det_hit.mean(), 3))
