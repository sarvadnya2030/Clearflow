#!/usr/bin/env python3
"""Resumable, checkpointed per-case model comparison for all 101 clean
incidents. Per direct user instruction: one case at a time, try every
available model, log real results, never lose progress on interruption.

Usage: python3 run_model_comparison.py [--limit N]
Writes/appends to model_comparison_results.csv (one row per
incident x method). Safe to re-run -- skips (incident, method) pairs
already recorded.
"""
import argparse
import csv
import os
import time

import pandas as pd

import eval_harness as eh

RESULTS_FILE = "model_comparison_results.csv"
FIELDS = ["incident_id", "fault_type", "true_root", "method", "pred_rank1",
          "full_ranking", "hit", "seconds", "error", "timestamp"]

# Deterministic methods (fast, already validated this session) + the two
# real model-backed MCP methods (timed and confirmed working 2026-09-02:
# LLM ~48s/case, SLM ~114s/case). Ordered cheapest/fastest first so a
# batch that gets interrupted still yields the most coverage.
METHODS = [
    ("payment_aware_rca", eh.payment_aware_rca),
    ("graph_topology_baseline", eh.graph_topology_baseline),
    ("loudest_metric_baseline", eh.loudest_metric_baseline),
    ("mcp_llm_rca_baseline", eh.mcp_llm_rca_baseline),
    ("mcp_slm_rca_baseline", eh.mcp_slm_rca_baseline),
]


def load_done():
    done = set()
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            for row in csv.DictReader(f):
                done.add((row["incident_id"], row["method"]))
    return done


def append_row(row):
    new_file = not os.path.exists(RESULTS_FILE)
    with open(RESULTS_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3,
                     help="max (incident, method) pairs to run this invocation -- keep small, this is meant to be called repeatedly by the loop")
    args = ap.parse_args()

    eh.OUT_DIR = "output_live"
    incidents, metrics, incident_payments, payments = eh.load(eh.OUT_DIR)
    incidents["injection_time"] = pd.to_datetime(incidents["injection_time"])
    clean = incidents[incidents["injection_time"] >= pd.Timestamp("2026-08-29", tz="UTC")].sort_values("incident_id")

    done = load_done()
    ran = 0
    for _, inc in clean.iterrows():
        for method_name, method_fn in METHODS:
            key = (inc["incident_id"], method_name)
            if key in done:
                continue
            if ran >= args.limit:
                print(f"Hit --limit={args.limit}, stopping this invocation. "
                      f"{len(done) + ran}/{len(clean) * len(METHODS)} total (incident,method) pairs done.")
                return
            t0 = time.time()
            pred, err = None, ""
            try:
                pred = method_fn(inc, metrics, payments)
            except Exception as e:
                err = repr(e)
            elapsed = round(time.time() - t0, 1)
            true_root = inc["root_service"]
            hit = int(bool(pred) and pred[0] == true_root)
            row = {
                "incident_id": inc["incident_id"], "fault_type": inc["fault_type"],
                "true_root": true_root, "method": method_name,
                "pred_rank1": pred[0] if pred else "", "full_ranking": ";".join(pred or []),
                "hit": hit, "seconds": elapsed, "error": err,
                "timestamp": pd.Timestamp.utcnow().isoformat(),
            }
            append_row(row)
            print(f"{inc['incident_id']} | {method_name} | pred={pred[0] if pred else None} "
                  f"| true={true_root} | {'HIT' if hit else 'miss'} | {elapsed}s"
                  + (f" | ERROR: {err}" if err else ""))
            ran += 1
    print(f"All (incident, method) pairs done: {len(done) + ran}/{len(clean) * len(METHODS)}.")


if __name__ == "__main__":
    main()
