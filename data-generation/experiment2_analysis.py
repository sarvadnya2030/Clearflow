#!/usr/bin/env python3
"""
Experiment 2 analysis -- compares Condition A (DB_TIMEOUT, clean
background) vs Condition B (DB_TIMEOUT, AML-held background) on the exact
same measurement pipeline Experiment 1 uses: fetch_error_rate_series /
measure_propagation_depth / fetch_payment_state from live_evidence.py,
_incident_window_exposure from eval_harness.py. Neither condition's
incidents were used to derive any RCA method's logic -- this is a
descriptive comparison of real cascade properties, not an RCA accuracy
evaluation, so no AC@k/McNemar machinery is invoked here.

n=5 (Condition A) vs n=4 (Condition B): far too small for a formal
significance test to mean anything. Reported as raw numbers with ranges,
not a p-value -- fabricating statistical precision this sample can't
support would undercut the whole point of this project's own
methodology discipline.

Usage:
    python3 data-generation/experiment2_analysis.py
"""

import csv
import os
import sys
from datetime import timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_evidence as le
import eval_harness as eh

OUT_DIR = le.OUT_DIR
LIVE_INCIDENTS_CSV = os.path.join(OUT_DIR, "live_incidents.csv")
SENT_CSV = os.path.join(OUT_DIR, "live_sent_payments.csv")
EXP2_CSV = os.path.join(OUT_DIR, "experiment2_incidents.csv")


def load_condition_a():
    df = pd.read_csv(LIVE_INCIDENTS_CSV)
    df = df[df["fault_type"] == "DB_TIMEOUT"].copy()
    df["condition"] = "A_clean_background"
    return df[["incident_id", "condition", "fault_type", "root_service",
               "injection_time", "duration_seconds"]]


def load_condition_b():
    df = pd.read_csv(EXP2_CSV)
    return df[["incident_id", "condition", "fault_type", "root_service",
               "injection_time", "duration_seconds"]]


def main():
    incidents = pd.concat([load_condition_a(), load_condition_b()], ignore_index=True)
    print(f"Condition A (clean): {len(incidents[incidents.condition.str.startswith('A')])} incidents")
    print(f"Condition B (AML-held): {len(incidents[incidents.condition.str.startswith('B')])} incidents")

    sent = []
    if os.path.exists(SENT_CSV):
        with open(SENT_CSV) as f:
            sent = list(csv.DictReader(f))

    all_starts = [le.parse_dt(i) for i in incidents["injection_time"]]
    all_ends = [le.parse_dt(t) + timedelta(seconds=float(d) + 30)
                for t, d in zip(incidents["injection_time"], incidents["duration_seconds"])]
    fetch_start = min(all_starts) - timedelta(hours=le.LOOKBACK_HOURS)
    fetch_end = max(all_ends)
    print(f"\nFetching real error_rate series: {fetch_start} .. {fetch_end}")
    error_series = le.fetch_error_rate_series(fetch_start, fetch_end)
    print(f"  {len(error_series)} (service, bucket) rows")

    payment_cache = {}
    rows = []
    for _, inc in incidents.iterrows():
        start = le.parse_dt(inc["injection_time"])
        end = start + timedelta(seconds=float(inc["duration_seconds"]) + 30)
        window_sent = [p for p in sent if start <= le.parse_dt(p["sent_at"]) <= end]
        n_affected = len(window_sent)
        depth = le.measure_propagation_depth(start, end, inc["root_service"], error_series)

        exposure = 0.0
        for p in window_sent:
            pid = p["payment_id"]
            if pid not in payment_cache:
                payment_cache[pid] = le.fetch_payment_state(pid)
            st = payment_cache[pid]
            amt = st.get("amount")
            cur = st.get("currency") or "USD"
            if amt:
                exposure += amt * eh.FX_TO_USD.get(cur, 1.0)

        rows.append({
            "incident_id": inc["incident_id"], "condition": inc["condition"],
            "n_affected_payments": n_affected, "propagation_depth": depth,
            "exposure_usd": round(exposure, 2),
        })
        print(f"  {inc['incident_id']} ({inc['condition']}): n_affected={n_affected}, "
              f"depth={depth}, exposure=${exposure:,.0f}")

    df = pd.DataFrame(rows)
    out_path = os.path.join(OUT_DIR, "experiment2_results.csv")
    df.to_csv(out_path, index=False)

    print(f"\n{'='*60}\nCOMPARISON (raw numbers, n too small for significance testing)\n{'='*60}")
    for cond in sorted(df["condition"].unique()):
        sub = df[df["condition"] == cond]
        print(f"\n{cond} (n={len(sub)}):")
        print(f"  n_affected_payments: {sub['n_affected_payments'].tolist()}  mean={sub['n_affected_payments'].mean():.1f}")
        print(f"  propagation_depth:   {sub['propagation_depth'].tolist()}  mean={sub['propagation_depth'].mean():.2f}")
        print(f"  exposure_usd:        {[f'{x:,.0f}' for x in sub['exposure_usd']]}  mean=${sub['exposure_usd'].mean():,.0f}")

    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
