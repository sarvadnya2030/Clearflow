#!/usr/bin/env python3
"""Backfills raw ES evidence directly into every gold_cases/{id}.json file,
so future model testing is self-contained -- no live ES re-query needed,
no dependency on ES retention (which this session proved can silently wipe
evidence a paper's headline result depends on, see BENCHMARK_GOAL.md
2026-09-02 metrics.csv finding). Adds a "raw_events" field (the same event
list eval_baseline_rca.py currently re-queries live) to each gold case.
Does not modify existing fields (evidence_reviewed, reasoning_trace,
blind_conclusion, confirmed, etc.) -- purely additive.
"""
import glob
import json
import time

import eval_baseline_rca as e


def main():
    files = sorted(glob.glob("gold_cases/LIVE-*.json"))
    n_done = n_skipped = n_failed = 0
    for i, path in enumerate(files):
        case = json.load(open(path))
        if "raw_events" in case:
            n_skipped += 1
            continue
        try:
            events = e.fetch_es_events(case["injection_time"], case.get("duration_seconds"))
            case["raw_events"] = events
            case["raw_events_backfilled_at"] = e.__dict__.get("__file__", "") and \
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            json.dump(case, open(path, "w"), indent=2)
            print(f"[{i+1}/{len(files)}] {path}: backfilled {len(events)} events", flush=True)
            n_done += 1
        except Exception as ex:
            print(f"[{i+1}/{len(files)}] {path}: FAILED -- {ex}", flush=True)
            n_failed += 1
        time.sleep(0.2)
    print(f"\nDone. {n_done} backfilled, {n_skipped} already had raw_events, {n_failed} failed.")


if __name__ == "__main__":
    main()
