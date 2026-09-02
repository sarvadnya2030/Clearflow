#!/usr/bin/env python3
"""
ClearFlow-RCA live evidence extraction (Phase 2). Turns
output/live_incidents.csv + output/live_sent_payments.csv (written by
live_fault_injector.py) into the exact same file shapes eval_harness.py's
load() already consumes -- so loudest_metric_baseline, graph_topology_baseline,
and payment_aware_rca run COMPLETELY UNCHANGED against real data instead of
the synthetic generator's CSVs. Only load()'s file source changes (see the
out_dir parameter added to eval_harness.load()).

What's real vs. what's honestly still approximated, per incident:
  - fault_type / root_service / fault_family / injection_time /
    duration_seconds: real, chosen by the harness (Phase 1) -- not measured.
  - error_rate: REAL, computed directly from Elasticsearch (ERROR-level log
    count / total log count per service per 5-min bucket) -- no synthetic
    spike_metrics() involved.
  - aml_state / settlement_state / idempotency_state: REAL, read from
    Elasticsearch logs and (for settlement) the live REST endpoint, per
    payment, for payments actually sent during the incident window.
  - liquidity_state: REAL when available. Sourced from ES log messages
    (LIQUIDITY_RESERVED / LIQUIDITY_CHECK_START event text) rather than the
    new GET /api/v1/liquidity/{paymentId} endpoint, because routing-execution
    runs on in-memory H2 (jdbc:h2:mem:routing) -- an AdminController restart
    (used by every infra/cross_domain/confounded fault) wipes prior
    reservation rows, so the REST endpoint alone would silently go blank for
    exactly the incidents that crash routing-execution. ES logs persist
    independently of any service restart.
  - retry_count: NOT available live (no equivalent instrumentation exists in
    the gateway yet, honestly documented as a gap in README.md) -- defaults
    to 0 for every payment, meaning validation_retry_frac's payment_aware_rca
    signal cannot fire in the live eval. This is a real, disclosed limitation,
    not silently faked.
  - propagation_depth / severity / n_affected_payments: measured POST-HOC
    from real data (see below), not preset -- the honest difference from the
    synthetic generator, which asserts these upfront.

Usage:
    python3 data-generation/live_evidence.py
    python3 data-generation/eval_harness.py --out-dir data-generation/output_live
"""

import csv
import json
import os
import re
import statistics as stats
from datetime import datetime, timedelta, timezone

import requests

ES_URL = "http://localhost:9200"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "output")
LIVE_OUT_DIR = os.path.join(BASE_DIR, "output_live")

SERVICES = ["gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement"]
# A 2-hour lookback (the synthetic generator's own default, safe there because
# its incidents are spread over 30 simulated days with explicit anti-overlap
# scheduling) is WRONG for a live batch where incidents run minutes apart --
# found live: median gap between the first 38 incidents was 47s, so every
# single "pre-incident baseline" was actually contaminated by nearby crash
# tests. live_fault_injector.py now enforces INCIDENT_SPACING_S cooldown
# between incidents specifically so a short lookback here is genuinely clean.
LOOKBACK_HOURS = 0.05  # 3 minutes
SEVERITY_THRESHOLDS = {"low": (0, 20), "medium": (20, 60), "high": (60, 10**9)}  # by n_affected_payments
TEMPORAL_DIFFICULTY = {"infra": "easy", "payment_domain": "medium", "cross_domain": "medium", "confounded": "hard"}


def parse_dt(s):
    # Some real log timestamps carry nanosecond precision (9 fractional
    # digits) -- Python's fromisoformat (3.10 here) only accepts up to 6
    # (microseconds). Truncate rather than fail.
    s = s.replace("Z", "+00:00")
    m = re.match(r"^(.*?\.\d{6})\d*([+-]\d{2}:\d{2})$", s)
    if m:
        s = m.group(1) + m.group(2)
    return datetime.fromisoformat(s)


def es_search(index_pattern, body):
    r = requests.post(f"{ES_URL}/{index_pattern}/_search", json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_error_rate_series(start, end):
    """Real error_rate per (service, 5-min bucket) directly from ES --
    replaces spike_metrics()'s synthetic multiplier entirely.
    """
    rows = []
    for svc in SERVICES:
        body = {
            "query": {"bool": {"filter": [
                {"term": {"service": svc}},
                {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
            ]}},
            "size": 0,
            "aggs": {
                "by_bucket": {
                    # 5m buckets (the synthetic generator's own resolution)
                    # are far too coarse for a 20-30s crash duration -- an
                    # incident this short barely touches 1-2 buckets, diluting
                    # any real spike into surrounding normal traffic. 30s
                    # buckets actually isolate the incident window; the
                    # LOOKBACK_HOURS=2 baseline still has hundreds of points.
                    "date_histogram": {"field": "@timestamp", "fixed_interval": "30s"},
                    "aggs": {"errors": {"filter": {"term": {"level": "ERROR"}}}},
                }
            },
        }
        try:
            resp = es_search("clearflow-*", body)
        except Exception as e:
            print(f"  WARN: ES query failed for {svc}: {e}")
            continue
        for bucket in resp.get("aggregations", {}).get("by_bucket", {}).get("buckets", []):
            total = bucket["doc_count"]
            errors = bucket["errors"]["doc_count"]
            rows.append({
                "timestamp": bucket["key_as_string"],
                "service": svc,
                "error_rate": round(errors / total, 5) if total > 0 else 0.0,
                "p99_latency_ms": "", "kafka_lag": "", "cpu_pct": "",
            })
    return rows


# The 5 real pipeline stages, in order, and the event that marks each one
# complete -- a process-crash fault (infra/cross_domain/confounded, all
# implemented as AdminController kill+restart) doesn't touch any payment's
# aml_state/liquidity_state/etc at all; it just prevents payments from
# reaching that service's own completion event. This is the ONLY real
# signal available for that whole class of fault -- generalizes the
# validation-latency idea above to all 5 stages.
STAGE_EVENTS = [
    ("gateway", "PAYMENT_SUBMITTED"),
    ("validation-enrichment", "PAYMENT_VALIDATED"),
    ("aml-compliance", "AML_SCREENING_COMPLETE"),
    ("routing-execution", "PAYMENT_ROUTED"),
    ("settlement", "SETTLEMENT_COMPLETE"),
]
MIN_STALL_DWELL_S = 2  # full pipeline normally completes in ~150-200ms


def fetch_payment_state(payment_id):
    """Real per-payment state pulled from ES logs (aml_state, idempotency,
    liquidity) and the settlement REST endpoint.
    """
    state = {
        "payment_id": payment_id, "aml_state": "CLEAR", "settlement_state": "PENDING",
        "liquidity_state": "", "idempotency_state": "NEW", "retry_count": 0,
        "created_at": None,
        # No dedicated validation-stage state field exists anywhere in the
        # schema (documented gap) -- derived here from real event timing
        # instead: how long PAYMENT_SUBMITTED -> PAYMENT_VALIDATED took, or
        # whether validation ever completed at all. A validation-enrichment
        # crash either delays this past normal (~100-300ms observed) or the
        # payment never reaches PAYMENT_VALIDATED within the window at all.
        "validation_latency_ms": None,
        # Generalization of the above to all 5 stages -- see STAGE_EVENTS.
        "stalled_service": "",
        # Real amount/currency, already structured fields on the
        # PAYMENT_SUBMITTED ES document -- for blast-radius / dollar
        # exposure analysis, not previously extracted.
        "amount": None, "currency": "",
        "saga_compensation_triggered": False, "saga_compensation_released": False,
    }
    body = {
        "query": {"bool": {"filter": [{"term": {"paymentId": payment_id}}]}},
        "sort": [{"@timestamp": "asc"}], "size": 100,
    }
    try:
        resp = es_search("clearflow-*", body)
    except Exception:
        return state
    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        return state
    state["created_at"] = hits[0]["_source"].get("@timestamp")
    submitted_ts, validated_ts = None, None
    stage_ts = {}  # event name -> first-seen timestamp
    for h in hits:
        src = h["_source"]
        msg = src.get("message", "") or ""
        event = src.get("eventType") or ""
        screening = src.get("screeningResult")
        if event == "PAYMENT_SUBMITTED" and submitted_ts is None:
            submitted_ts = src.get("@timestamp")
            # amount/currency are structured ES fields on some log call sites
            # but not the regular runtime PAYMENT_SUBMITTED one -- found live,
            # that one only puts them in the free-text message
            # ("...amount=1721326.56 currency=EUR..."). Parse the message as
            # the reliable path; prefer the structured field if present.
            if src.get("amount") is not None:
                state["amount"] = src.get("amount")
                state["currency"] = src.get("currency") or ""
            else:
                m = re.search(r"amount=([\d.]+)\s+currency=(\w+)", msg)
                if m:
                    state["amount"] = float(m.group(1))
                    state["currency"] = m.group(2)
        if event == "PAYMENT_VALIDATED" and validated_ts is None:
            validated_ts = src.get("@timestamp")
        for _, stage_event in STAGE_EVENTS:
            if event == stage_event and stage_event not in stage_ts:
                stage_ts[stage_event] = src.get("@timestamp")
        if screening == "HIT" or event == "AML_SANCTIONS_HIT":
            state["aml_state"] = "HOLD"
        if "amlState=ESCALATED" in msg:
            state["aml_state"] = "ESCALATED"
        if "SETTLEMENT_COMPLETE" in msg or event == "SETTLEMENT_COMPLETE":
            state["settlement_state"] = "SETTLED"
        if "PAYMENT_FAILED" in msg or event == "PAYMENT_FAILED":
            state["settlement_state"] = "FAILED"
        if "LIQUIDITY_RESERVED" in msg:
            state["liquidity_state"] = "RESERVED"
        if "duplicate" in msg.lower() or src.get("service") == "gateway" and "Duplicate" in msg:
            state["idempotency_state"] = "DUPLICATE_DETECTED"
        # Real ActiveMQ/JMS saga-compensation evidence, not inferred: this
        # is SagaCompensationRoute (routing-execution) actually consuming
        # from the real CLEARFLOW.PAYMENT.SETTLEMENT.FAILED JMS queue and
        # releasing the liquidity reservation -- confirms the settlement
        # failure was real infrastructure behavior, not just a log line.
        if "Saga compensation triggered" in msg:
            state["saga_compensation_triggered"] = True
        if "Liquidity released" in msg and "paymentId=" in msg:
            state["saga_compensation_released"] = True

    # Cross-check against the real settlement REST endpoint when available.
    try:
        r = requests.get(f"http://localhost:8085/api/v1/settlement/{payment_id}", timeout=5)
        if r.ok:
            rec = r.json().get("record", {})
            if rec.get("status"):
                state["settlement_state"] = rec["status"]
    except Exception:
        pass
    # Cross-check liquidity via the new REST endpoint (only useful for
    # payments processed since routing-execution's last restart -- see
    # module docstring on the in-memory H2 limitation).
    try:
        r = requests.get(f"http://localhost:8084/api/v1/liquidity/{payment_id}", timeout=5)
        if r.ok:
            st = r.json().get("STATUS")
            # DB column literally stores 'SETTLED' on release (LiquidityReservationService.release()) --
            # a naming collision with payment settlement, not a real liquidity_state
            # value in the schema (RESERVED/RELEASED only). Normalize.
            if st == "SETTLED":
                st = "RELEASED"
            if st:
                state["liquidity_state"] = st
    except Exception:
        pass
    if not state["liquidity_state"]:
        state["liquidity_state"] = "RESERVED" if state["settlement_state"] == "PENDING" else "RELEASED"
    if submitted_ts and validated_ts:
        state["validation_latency_ms"] = (parse_dt(validated_ts) - parse_dt(submitted_ts)).total_seconds() * 1000
    elif submitted_ts and not validated_ts:
        # Never reached PAYMENT_VALIDATED at all -- itself real evidence,
        # not missing data. Represented as a very large latency rather than
        # a separate boolean so a single numeric threshold covers both
        # "slow" and "never happened".
        state["validation_latency_ms"] = float("inf")

    # stalled_service: the service whose own completion event is the next
    # one after the last stage this payment actually reached. Gated on
    # MIN_STALL_DWELL_S so a payment that's simply still in normal async
    # flight (hasn't had time to finish yet) isn't misread as stuck.
    if submitted_ts:
        last_idx = 0
        for i, (_, ev) in enumerate(STAGE_EVENTS):
            if ev in stage_ts:
                last_idx = i
        if last_idx < len(STAGE_EVENTS) - 1:
            dwell_s = (datetime.now(timezone.utc) - parse_dt(submitted_ts)).total_seconds()
            if dwell_s > MIN_STALL_DWELL_S:
                state["stalled_service"] = STAGE_EVENTS[last_idx + 1][0]
    return state


def measure_propagation_depth(incident_start, incident_end, root_service, error_series):
    """Real, if simple, post-hoc measurement: count services besides the
    root whose error_rate meaningfully spiked during the incident window vs.
    their own pre-incident baseline -- an honest observed value, not a
    number copied from the synthetic FAULT_CATALOG.
    """
    # ES's date_histogram key_as_string ("...000Z") and Python's isoformat()
    # ("...+00:00") sort inconsistently as raw strings -- parse both to real
    # datetimes before comparing (found live: this bug silently made every
    # window/baseline split empty, so depth always fell back to 1).
    by_service = {}
    for row in error_series:
        by_service.setdefault(row["service"], []).append(
            (parse_dt(row["timestamp"]), row["error_rate"]))
    lookback_start = incident_start - timedelta(hours=LOOKBACK_HOURS)
    affected = set()
    for svc, rows in by_service.items():
        base = [er for ts, er in rows if lookback_start <= ts < incident_start]
        window = [er for ts, er in rows if incident_start <= ts <= incident_end]
        if len(base) < 2 or not window:
            continue
        mu = stats.mean(base)
        sigma = stats.pstdev(base) or 1e-6
        if (stats.mean(window) - mu) / sigma > 2.0:
            affected.add(svc)
    affected.add(root_service)
    return len(affected)


def main():
    os.makedirs(LIVE_OUT_DIR, exist_ok=True)
    incidents_path = os.path.join(OUT_DIR, "live_incidents.csv")
    sent_path = os.path.join(OUT_DIR, "live_sent_payments.csv")
    if not os.path.exists(incidents_path):
        print(f"No {incidents_path} -- run live_fault_injector.py first.")
        return

    with open(incidents_path) as f:
        incidents = list(csv.DictReader(f))
    sent = []
    if os.path.exists(sent_path):
        with open(sent_path) as f:
            sent = list(csv.DictReader(f))

    dup_path = os.path.join(OUT_DIR, "live_duplicate_confirmations.csv")
    confirmed_duplicate_ids = set()
    if os.path.exists(dup_path):
        with open(dup_path) as f:
            confirmed_duplicate_ids = {row["payment_id"] for row in csv.DictReader(f)}

    if not incidents:
        print("No incidents to process.")
        return

    all_starts = [parse_dt(i["injection_time"]) for i in incidents]
    all_ends = [parse_dt(i["injection_time"]) + timedelta(seconds=float(i["duration_seconds"]) + 30) for i in incidents]
    fetch_start = min(all_starts) - timedelta(hours=LOOKBACK_HOURS)
    fetch_end = max(all_ends)
    print(f"Fetching real error_rate series from ES: {fetch_start} .. {fetch_end}")
    error_series = fetch_error_rate_series(fetch_start, fetch_end)
    print(f"  {len(error_series)} (service, bucket) rows")

    out_incidents = []
    out_payments = {}
    for inc in incidents:
        start = parse_dt(inc["injection_time"])
        end = start + timedelta(seconds=float(inc["duration_seconds"]) + 30)  # +30s propagation buffer
        window_payments = [p for p in sent if start <= parse_dt(p["sent_at"]) <= end]
        n_affected = len(window_payments)
        severity = next((k for k, (lo, hi) in SEVERITY_THRESHOLDS.items() if lo <= n_affected < hi), "low")
        depth = measure_propagation_depth(start, end, inc["root_service"], error_series)

        out_incidents.append({
            "incident_id": inc["incident_id"],
            "fault_type": inc["fault_type"],
            "fault_family": inc["fault_family"],
            "root_service": inc["root_service"],
            "root_component": "",
            "root_event_id": "",
            "propagation_path": "",
            "propagation_depth": depth,
            "temporal_difficulty": TEMPORAL_DIFFICULTY.get(inc["fault_family"], "medium"),
            "severity": severity,
            "injection_time": inc["injection_time"],
            "duration_seconds": inc["duration_seconds"],
            "n_affected_payments": n_affected,
            "seed": "", "is_confounder": inc["fault_family"] == "confounded",
        })

        print(f"  {inc['incident_id']} ({inc['fault_type']}): {n_affected} payments in window, "
              f"measured depth={depth}, severity={severity}")
        for p in window_payments:
            if p["payment_id"] in out_payments:
                continue
            st = fetch_payment_state(p["payment_id"])
            st["created_at"] = st["created_at"] or p["sent_at"]
            if p["payment_id"] in confirmed_duplicate_ids:
                # The only place this evidence exists -- see
                # live_fault_injector.py's trigger_idempotency_collision().
                # A 409 duplicate rejection is never itself indexed into ES
                # with a paymentId, so this can't be reconstructed from logs.
                st["idempotency_state"] = "DUPLICATE_DETECTED"
            out_payments[p["payment_id"]] = st

    # Write incidents.csv
    with open(os.path.join(LIVE_OUT_DIR, "incidents.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_incidents[0].keys()))
        w.writeheader()
        w.writerows(out_incidents)

    # Write metrics.csv
    with open(os.path.join(LIVE_OUT_DIR, "metrics.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "service", "error_rate", "p99_latency_ms", "kafka_lag", "cpu_pct"])
        w.writeheader()
        w.writerows(error_series)

    # Write payments file (clearflow_rca_dataset.csv shape -- only the
    # columns eval_harness.py actually reads, per README's own audit).
    payment_fields = ["payment_id", "created_at", "aml_state", "liquidity_state",
                       "settlement_state", "idempotency_state", "retry_count",
                       "validation_latency_ms", "stalled_service", "amount", "currency",
                       "saga_compensation_triggered", "saga_compensation_released"]
    with open(os.path.join(LIVE_OUT_DIR, "clearflow_rca_dataset.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=payment_fields)
        w.writeheader()
        for st in out_payments.values():
            row = {k: st.get(k, "") for k in payment_fields}
            if row["validation_latency_ms"] in (None, ""):
                row["validation_latency_ms"] = ""
            elif row["validation_latency_ms"] == float("inf"):
                row["validation_latency_ms"] = "999999"  # "never validated" sentinel, see fetch_payment_state
            w.writerow(row)

    # incident_payments.csv -- unused by scoring (display-only per
    # eval_harness.py's own load()), written empty-but-valid for shape parity.
    with open(os.path.join(LIVE_OUT_DIR, "incident_payments.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["incident_id", "payment_id"])

    print(f"\nWrote {len(out_incidents)} incidents, {len(out_payments)} payments to {LIVE_OUT_DIR}/")
    print(f"Run: python3 data-generation/eval_harness.py --out-dir {LIVE_OUT_DIR}")


if __name__ == "__main__":
    main()
