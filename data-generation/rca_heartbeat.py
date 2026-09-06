#!/usr/bin/env python3
"""Heartbeat watcher for rca_tool.py -- the Gateway/Heartbeat pattern from
OpenClaw/Hermes, applied WITHOUT putting an LLM in the decision path.
rca_tool.diagnose() is used exactly as-is (same deterministic, no-LLM,
100%-reproducible pipeline already measured at 71/143 = 0.497 AC@1 on the
output_live set); this script only automates *triggering* it and
recording the result, via rca_audit_log.py.

Detection signal: HEALTH_CHECK_FAILED events (requires
scripts/health_witness_monitor.py running) -- the single highest-
precision, independently-validated signal in the whole tool (see
rca_tool.py's own module docstring, item 1). A service crashing is
unambiguous; this is deliberately NOT a general anomaly detector.

Usage:
    python3 rca_heartbeat.py --once              # single pass, for cron/testing
    python3 rca_heartbeat.py --interval 30        # poll every 30s, forever
    python3 rca_heartbeat.py --once --since "2026-09-02T00:00:00Z" --until "2026-09-04T00:00:00Z"
        # backfill/replay a historical window (for verifying the wiring
        # against real past incidents without needing live traffic running)
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

sys.path.insert(0, ".")
import live_evidence as le
import rca_audit_log as log
import rca_tool as rt

ES = rt.ES
RECOVERY_WAIT_S = 300       # how long to look for a matching RECOVERED event
DEFAULT_DURATION_S = 60     # used if no RECOVERED event is found in time
MAX_PAYMENTS_PER_INCIDENT = 200  # bound the live per-payment ES fan-out


def _fetch_health_transitions(since, until):
    """All HEALTH_CHECK_FAILED / HEALTH_CHECK_RECOVERED events in [since, until],
    oldest first."""
    body = {"size": 500, "query": {"bool": {"filter": [
        {"range": {"@timestamp": {"gte": since.isoformat(), "lte": until.isoformat()}}},
        {"terms": {"eventType": ["HEALTH_CHECK_FAILED", "HEALTH_CHECK_RECOVERED"]}},
    ]}}, "sort": [{"@timestamp": "asc"}]}
    r = requests.post(f"{ES}/clearflow-*/_search", json=body, timeout=15)
    r.raise_for_status()
    return [h["_source"] for h in r.json().get("hits", {}).get("hits", [])]


def _fetch_window_payment_ids(start, end, limit=MAX_PAYMENTS_PER_INCIDENT):
    body = {"size": limit, "query": {"bool": {"filter": [
        {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
        {"match_phrase": {"message": "PAYMENT_SUBMITTED"}},
    ]}}, "_source": ["paymentId"]}
    r = requests.post(f"{ES}/clearflow-*/_search", json=body, timeout=15)
    r.raise_for_status()
    ids = {h["_source"].get("paymentId") for h in r.json().get("hits", {}).get("hits", [])}
    return {i for i in ids if i}


def _build_live_payments_df(start, end):
    ids = _fetch_window_payment_ids(start, end)
    if not ids:
        return None
    states = [le.fetch_payment_state(pid) for pid in ids]
    df = pd.DataFrame(states)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
    return df


def _build_live_metrics_df(start, end):
    rows = le.fetch_error_rate_series(start - timedelta(hours=rt.eh.LOOKBACK_HOURS), end)
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["error_rate"] = pd.to_numeric(df["error_rate"], errors="coerce")
    return df


def find_new_incidents(since, until):
    """Pairs each HEALTH_CHECK_FAILED with its matching RECOVERED (or a
    default duration if none arrives within RECOVERY_WAIT_S). Returns a
    list of (incident_key, injection_time, duration_seconds, trigger_service).
    """
    events = _fetch_health_transitions(since, until)
    open_failures = {}  # service -> failed_at (datetime)
    incidents = []
    for e in events:
        svc = e.get("service")
        ts = le.parse_dt(e["@timestamp"])
        if e.get("eventType") == "HEALTH_CHECK_FAILED" and svc not in open_failures:
            open_failures[svc] = ts
        elif e.get("eventType") == "HEALTH_CHECK_RECOVERED" and svc in open_failures:
            failed_at = open_failures.pop(svc)
            duration = (ts - failed_at).total_seconds()
            incidents.append((f"{svc}:{failed_at.isoformat()}", failed_at, duration, svc))
    # Failures still open at the end of the window: use the default duration
    # rather than waiting forever -- diagnose() only needs a window long
    # enough to contain the evidence, not the true recovery time.
    for svc, failed_at in open_failures.items():
        incidents.append((f"{svc}:{failed_at.isoformat()}", failed_at, DEFAULT_DURATION_S, svc))
    return incidents


def run_once(since, until, conn=None, verbose=True):
    conn = conn or log.connect()
    incidents = find_new_incidents(since, until)
    diagnosed = 0
    for incident_key, injection_time, duration, trigger_svc in incidents:
        if log.already_diagnosed(conn, incident_key):
            continue
        payments_df = _build_live_payments_df(injection_time, injection_time + timedelta(seconds=duration + 30))
        metrics_df = _build_live_metrics_df(injection_time, injection_time + timedelta(seconds=duration + 30))
        result = rt.diagnose(injection_time, duration, payments_df=payments_df, metrics_df=metrics_df)
        log.record(conn, incident_key, injection_time, duration, trigger_svc, result)
        diagnosed += 1
        if verbose:
            print(f"[{injection_time.isoformat()}] health-check-triggered by '{trigger_svc}' "
                  f"-> PREDICTION={result['prediction']} SOURCE={result['source']}")
    log.set_state(conn, "last_checked", until.isoformat())
    return diagnosed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=30.0, help="seconds between polls")
    ap.add_argument("--since", type=str, default=None)
    ap.add_argument("--until", type=str, default=None)
    args = ap.parse_args()

    conn = log.connect()
    until = le.parse_dt(args.until) if args.until else datetime.now(timezone.utc)
    since = (le.parse_dt(args.since) if args.since
             else le.parse_dt(log.get_state(conn, "last_checked", (until - timedelta(minutes=5)).isoformat())))

    if args.once:
        n = run_once(since, until, conn)
        print(f"Diagnosed {n} new incident(s) in [{since.isoformat()}, {until.isoformat()}].")
        return

    import time
    while True:
        now = datetime.now(timezone.utc)
        n = run_once(since, now, conn)
        if n:
            print(f"Diagnosed {n} new incident(s).")
        since = now
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
