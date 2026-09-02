#!/usr/bin/env python3
"""
Experiment 2 -- State-Conditioned Failure Propagation.

Research question: does the SAME infrastructure fault (same type, same
root service, same severity mechanism) produce a DIFFERENT cascade
depending on what real, persistent payment-domain state exists in the
system at the moment it's triggered?

This is the one experiment in this project that only a LIVE, real system
with real controllable interventions can produce -- every prior-art paper
in Section II of the paper works on passive, already-collected data.
ClearFlow's AML holds are genuinely persistent (a payment stays HOLD until
someone calls the compliance resolve endpoint, which this script never
does) -- that gives a real, controllable "background state" to condition
on, not a synthetic label.

Design:
  Condition A ("clean"): DB_TIMEOUT on settlement triggered against normal
    background traffic only. Uses the 5 DB_TIMEOUT incidents already
    collected in Experiment 1 (data-generation/output/live_incidents.csv)
    -- NOT re-triggered here, reused as-is, because Experiment 1's data
    already IS the clean-background condition for this exact fault type.
  Condition B ("AML-held background"): 2 real AML holds are triggered
    FIRST and deliberately left unresolved (genuinely persistent, real
    system state), THEN the SAME DB_TIMEOUT fault is triggered while those
    holds remain active. Repeated N times.

Ground truth (fault_type/root_service/injection_time) is known the same
way as Experiment 1. What's compared is NOT root-cause accuracy (that's
Experiment 1's frozen question) -- it's real, measured cascade properties:
n_affected_payments, propagation_depth, and $ exposure, using the exact
same measurement pipeline as Experiment 1 (live_evidence.py's
measure_propagation_depth / eval_harness.py's _incident_window_exposure)
so the two conditions are compared on identical instrumentation.

Usage:
    python3 data-generation/experiment2_state_conditioning.py --reps 5
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_fault_injector as lfi

OUT_DIR = lfi.OUT_DIR
EXP2_CSV = os.path.join(OUT_DIR, "experiment2_incidents.csv")
EXP2_FIELDS = ["incident_id", "condition", "fault_type", "root_service",
               "injection_time", "duration_seconds", "aml_hold_payment_ids"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def persist(row):
    file_exists = os.path.exists(EXP2_CSV)
    with open(EXP2_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EXP2_FIELDS)
        if not file_exists:
            w.writeheader()
        w.writerow(row)


def run_condition_b(rep, token, gen):
    """AML-held background: 2 real holds, deliberately unresolved, THEN
    DB_TIMEOUT on settlement while they're still active."""
    print(f"\n=== Condition B rep={rep}: AML holds first, then DB_TIMEOUT ===")
    held_payment_ids = []
    for i in range(2):
        result, err = lfi.trigger_aml_hold(token, gen)
        if err:
            print(f"  AML hold {i} failed: {err}")
            continue
        print(f"  AML hold {i}: payment={result.get('payment_id')} confirmed={result.get('confirmed_held')}")
        if result.get("confirmed_held") and result.get("payment_id"):
            held_payment_ids.append(result["payment_id"])
        time.sleep(3)

    if not held_payment_ids:
        print("  No confirmed AML holds -- skipping this rep, condition B requires real held state")
        return None

    print(f"  {len(held_payment_ids)} payment(s) genuinely held: {held_payment_ids}")
    time.sleep(5)  # let the held state settle before injecting the crash

    result, err = lfi.trigger_crash("settlement", "infra", token, gen)
    if err:
        print(f"  Crash trigger failed: {err}")
        return None
    print(f"  DB_TIMEOUT: {result}")

    return {
        "incident_id": f"EXP2-{lfi.uuid.uuid4().hex[:8]}",
        "condition": "B_aml_held_background",
        "fault_type": "DB_TIMEOUT",
        "root_service": "settlement",
        "injection_time": result["injection_time"],
        "duration_seconds": result["duration_seconds"],
        "aml_hold_payment_ids": ";".join(held_payment_ids),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--traffic-rate", type=float, default=1.0)
    ap.add_argument("--spacing-s", type=float, default=240,
                     help="Cooldown between reps -- same contamination-avoidance reasoning as Experiment 1")
    args = ap.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    token = lfi.traffic.localStorage_token()

    gen = lfi.TrafficGenerator(token, rate_per_s=args.traffic_rate)
    gen.start()
    print(f"Background traffic started at {args.traffic_rate}/s")

    n_done = 0
    try:
        for rep in range(args.reps):
            row = run_condition_b(rep, token, gen)
            if row:
                persist(row)
                n_done += 1
                print(f"  [{n_done} Condition-B incidents persisted]")
            time.sleep(args.spacing_s)
    finally:
        gen.stop()
        print(f"\nBackground traffic stopped. {n_done} Condition-B incidents collected.")

    print(f"\nCondition A (clean background) reuses the 5 existing DB_TIMEOUT incidents "
          f"in {lfi.LIVE_INCIDENTS_CSV} -- not re-triggered.")
    print(f"Next: python3 data-generation/experiment2_analysis.py")


if __name__ == "__main__":
    main()
