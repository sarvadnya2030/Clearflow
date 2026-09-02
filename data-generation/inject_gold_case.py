#!/usr/bin/env python3
"""Inject one real fault with the health witness running, wait for it to
land, and dump the full evidence bundle to a file for blind investigation.

This does NOT write the gold case verdict itself -- that requires a human
(or an agent explicitly instructed to reason blind) reading the evidence
dump and writing a reasoning trace BEFORE looking at the injector's own
claimed root_service, which is included in the dump but should not be
read until after forming a hypothesis. See gold_cases/README.md.

Usage: python3 inject_gold_case.py FAULT_TYPE
Writes gold_cases/_pending_{incident_id}.json (evidence bundle, no
verdict yet) and prints the incident_id.
"""
import json
import subprocess
import sys
import time

import requests

ES = "http://elastic:changeme@localhost:9200"


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 inject_gold_case.py FAULT_TYPE")
        sys.exit(1)
    fault_type = sys.argv[1]

    # Start the independent witness BEFORE injecting -- it must have zero
    # foreknowledge of what's about to happen, same discipline as a real
    # production monitor.
    witness_log = f"/tmp/witness_{fault_type}_{int(time.time())}.log"
    witness = subprocess.Popen(
        ["python3", "../scripts/health_witness_monitor.py", "--duration", "500", "--interval", "0.5"],
        stdout=open(witness_log, "w"), stderr=subprocess.STDOUT,
    )
    time.sleep(2)  # let it start polling before the fault fires

    print(f"Injecting {fault_type}...")
    result = subprocess.run(
        ["python3", "live_fault_injector.py", "--run", fault_type],
        capture_output=True, text=True, timeout=480,
    )
    # DELIBERATELY not printed to stdout -- the injector's own console
    # output includes a line like "=== FAULT_TYPE (root=X, ...) ===" that
    # leaks the ground truth. Anyone polling/tailing this script's output
    # while waiting for it to finish (this session did exactly that on an
    # earlier case, contaminating it) would see the answer before doing
    # the blind investigation. Written to a separate file instead, safe
    # to read only AFTER the blind conclusion is formed.
    with open(f"gold_cases/_injector_raw_stdout_{fault_type}_{int(time.time())}.txt", "w") as f:
        f.write(result.stdout)
    print("Injection subprocess completed (raw output withheld from stdout -- see gold_cases/_injector_raw_stdout_* only after forming a blind hypothesis).")

    witness.wait(timeout=520)

    # Find the real incident just recorded. Filter out any row with a null
    # incident_id/injection_time first -- a stray corrupt/partial row earlier
    # in the file (found live 2026-09-02: a leftover artifact from a manual
    # CSV-repair script) otherwise sorts to the top or bottom and silently
    # takes over "the last incident," crashing this script and losing the
    # evidence-bundle write for a fault that actually ran successfully.
    import pandas as pd
    incidents = pd.read_csv("output/live_incidents.csv")
    # incident_id/injection_time are never legitimately null -- duration_seconds
    # IS legitimately null for point-in-time faults (AML_HOLD), so don't filter
    # on that or the most recent real AML_HOLD incident gets silently skipped.
    incidents = incidents.dropna(subset=["incident_id", "injection_time"])
    incidents["injection_time"] = pd.to_datetime(incidents["injection_time"])
    inc = incidents.sort_values("injection_time").iloc[-1]
    incident_id = inc["incident_id"]
    start = inc["injection_time"]
    dur = inc["duration_seconds"]
    dur = int(dur) if pd.notna(dur) else 10
    end = start + pd.Timedelta(seconds=dur + 15)

    # Pull the full real evidence bundle -- ES logs + witness events, same
    # window a blind investigator would look at. size was 300 -- found live
    # 2026-09-02 (LIVE-125bb06d) that a 20s window can genuinely contain
    # 1300+ events under real background traffic (758 payments/run at 3/s),
    # silently truncating exactly the evidence a point-in-time fault
    # (AML_HOLD) needs since it's not necessarily in the earliest slice.
    # Bumped to 3000 -- generous headroom, not a precisely-derived bound.
    resp = requests.get(f"{ES}/clearflow-*,clearflow-healthmonitor-*/_search", timeout=15, json={
        "size": 3000,
        "query": {"range": {"@timestamp": {"gte": (start - pd.Timedelta(seconds=5)).isoformat(),
                                            "lte": end.isoformat()}}},
        "sort": [{"@timestamp": "asc"}],
        "_source": ["@timestamp", "service", "eventType", "level", "message", "paymentId", "source"],
    })
    events = [h["_source"] for h in resp.json().get("hits", {}).get("hits", [])]

    with open(witness_log) as f:
        witness_output = f.read()

    bundle = {
        "incident_id": incident_id,
        "fault_type": fault_type,
        "injection_time": str(start),
        "duration_seconds": dur,
        # deliberately last in the dict and clearly labeled -- read the
        # events and witness_output first, form a hypothesis, THEN look here
        "_INJECTOR_CLAIMED_ROOT_DO_NOT_READ_UNTIL_AFTER_YOUR_HYPOTHESIS": inc["root_service"],
        "events": events,
        "witness_monitor_output": witness_output,
    }
    out_path = f"gold_cases/_pending_{incident_id}.json"
    with open(out_path, "w") as f:
        json.dump(bundle, f, indent=2, default=str)
    print(f"\nEvidence bundle written: {out_path}")
    print(f"incident_id={incident_id}")


if __name__ == "__main__":
    main()
