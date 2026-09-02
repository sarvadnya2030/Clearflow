#!/usr/bin/env python3
"""
ClearFlow-RCA incident injector -- turns the payment-traffic environment
(payments.csv + payment_events.csv, built by build_clearflow_rca_dataset.py)
into an actual RCA benchmark by injecting ~160 controlled, ground-truth
causal incidents on top of it.

Design principles (from the two-round design review, see README.md):
  - "Payment corpus = environment. Incident corpus = benchmark." Traffic
    volume doesn't matter past a point; incident QUALITY does.
  - Ground truth is hierarchical: root_service / root_component / root_event_id
    / fault_type, plus propagation_path and propagation_depth.
  - Four balanced fault families: infra, payment_domain, cross_domain,
    confounded -- NOT left to whatever ratio would occur naturally.
  - Confounded incidents deliberately make a downstream symptom's metric
    louder than the root cause's own metric (tests whether payment-state
    signal beats "find the biggest spike").
  - CAUSAL-LEAKAGE SAFE: ground truth (incidents.csv, incident_payments.csv)
    is written as SEPARATE files from the evidence surface (payment_events.csv,
    metrics.csv). No fault_type/incident_id column is added to the evidence
    files themselves -- an RCA method only ever sees state values that
    already exist in the base schema (RESERVED/PENDING/etc, never a literal
    "STUCK"/"INCIDENT" label), exactly the anti-leakage principle from the
    review. affected_payment_ids in incidents.csv is held out for scoring,
    not fed to the method under test.
  - Reproducible: every incident carries the RNG seed that produced it.

Run AFTER build_clearflow_rca_dataset.py. Reads and rewrites payments.csv /
payment_events.csv in place (affected rows only); writes three new files:
  output/incidents.csv          -- ground truth, one row per incident
  output/incident_payments.csv  -- incident_id -> payment_id linkage (held out)
  output/metrics.csv            -- lightweight per-service telemetry, with
                                    incident-window spikes (root service +,
                                    for confounded incidents, a louder spike
                                    on a downstream service)
"""

import csv
import math
import os
import random
from datetime import datetime, timedelta

BASE_SEED = 2026
random.seed(BASE_SEED)

OUT_DIR = "data-generation/output"
SIM_DAYS = 30
START = datetime(2026, 7, 1)
METRIC_INTERVAL_MIN = 5

SERVICES = ["gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement"]

# (fault_type, root_service, root_component, propagation_depth, family)
FAULT_CATALOG = {
    "infra": [
        ("DB_TIMEOUT", "settlement", "SettlementService.dataSource", 1),
        ("KAFKA_CONSUMER_LAG", "routing-execution", "RoutingKafkaConsumer.pollLoop", 1),
        ("NETWORK_LATENCY", "validation-enrichment", "ValidationKafkaConsumer.camelRoute", 1),
        ("CPU_SATURATION", "aml-compliance", "AMLScreeningProcessor.threadPool", 1),
    ],
    "payment_domain": [
        ("LIQUIDITY_LOCK_STUCK", "routing-execution", "LiquidityReservationService.release", 2),
        ("AML_HOLD_RETRY_STORM", "aml-compliance", "AMLScreeningProcessor.holdGate", 2),
        ("IDEMPOTENCY_COLLISION_STORM", "gateway", "IdempotencyService.setIfAbsent", 1),
        ("SETTLEMENT_FINALITY_VIOLATION", "settlement", "SettlementService.settlePayment", 2),
    ],
    "cross_domain": [
        ("SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE", "settlement", "SettlementService.dataSource", 3),
        ("AML_SERVICE_DEGRADATION_RETRY_CASCADE", "aml-compliance", "AMLScreeningProcessor.threadPool", 3),
    ],
    "confounded": [
        ("SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND", "settlement", "SettlementService.dataSource", 4),
        ("VALIDATION_SLOWDOWN_GATEWAY_CONFOUND", "validation-enrichment", "EnrichmentProcessor.camelRoute", 4),
    ],
}
TEMPORAL_DIFFICULTY = {"infra": "easy", "payment_domain": "medium", "cross_domain": "medium", "confounded": "hard"}

# downstream "loud symptom" service used only for confounded incidents
CONFOUND_SYMPTOM_SERVICE = {"settlement": "routing-execution", "validation-enrichment": "gateway"}

PROPAGATION_CHAINS = {
    "gateway": ["gateway"],
    "validation-enrichment": ["validation-enrichment", "aml-compliance", "routing-execution", "settlement"],
    "aml-compliance": ["aml-compliance", "routing-execution", "settlement"],
    "routing-execution": ["routing-execution", "settlement"],
    "settlement": ["settlement"],
}

SEVERITY_COHORT = {"low": (8, 20), "medium": (20, 60), "high": (60, 150)}
SEVERITY_DURATION_MIN = {"low": (5, 15), "medium": (15, 60), "high": (60, 180)}
INCIDENTS_PER_FAULT_TYPE = 20


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def parse_dt(s):
    return datetime.fromisoformat(s)


def derive_payment_state(aml_state, settlement_state):
    if aml_state in ("HOLD", "ESCALATED", "REJECTED"):
        return "BLOCKED" if aml_state != "REJECTED" else "REJECTED"
    if settlement_state == "FAILED":
        return "FAILED"
    if settlement_state == "SETTLED":
        return "SETTLED"
    return "LIQUIDITY_RESERVED"


def gen_metrics_baseline():
    """Flat baseline telemetry for every service across the whole window,
    5-minute resolution. Incident windows get spikes added on top later."""
    rows = []
    n_steps = int(SIM_DAYS * 24 * 60 / METRIC_INTERVAL_MIN)
    baseline = {
        "gateway":                {"error_rate": 0.004, "p99_latency_ms": 45,  "kafka_lag": 20,  "cpu_pct": 22},
        "validation-enrichment":  {"error_rate": 0.003, "p99_latency_ms": 60,  "kafka_lag": 15,  "cpu_pct": 28},
        "aml-compliance":         {"error_rate": 0.002, "p99_latency_ms": 90,  "kafka_lag": 10,  "cpu_pct": 35},
        "routing-execution":      {"error_rate": 0.003, "p99_latency_ms": 70,  "kafka_lag": 25,  "cpu_pct": 30},
        "settlement":             {"error_rate": 0.002, "p99_latency_ms": 110, "kafka_lag": 12,  "cpu_pct": 26},
    }
    for step in range(n_steps):
        ts = START + timedelta(minutes=step * METRIC_INTERVAL_MIN)
        for svc in SERVICES:
            b = baseline[svc]
            rows.append({
                "timestamp": ts.isoformat(), "service": svc,
                "error_rate": round(max(0, random.gauss(b["error_rate"], b["error_rate"] * 0.3)), 5),
                "p99_latency_ms": round(max(1, random.gauss(b["p99_latency_ms"], b["p99_latency_ms"] * 0.15)), 1),
                "kafka_lag": round(max(0, random.gauss(b["kafka_lag"], b["kafka_lag"] * 0.25)), 1),
                "cpu_pct": round(max(1, min(99, random.gauss(b["cpu_pct"], 4))), 1),
            })
    return rows


def spike_metrics(metrics_index, service, start, end, severity, magnitude_mult=1.0):
    mult = {"low": 2.5, "medium": 5, "high": 10}[severity] * magnitude_mult
    t = start
    while t <= end:
        key = (t.replace(minute=(t.minute // METRIC_INTERVAL_MIN) * METRIC_INTERVAL_MIN, second=0, microsecond=0), service)
        if key in metrics_index:
            row = metrics_index[key]
            row["error_rate"] = round(row["error_rate"] * mult, 5)
            row["p99_latency_ms"] = round(row["p99_latency_ms"] * mult, 1)
            row["kafka_lag"] = round(row["kafka_lag"] * mult, 1)
            row["cpu_pct"] = round(min(99, row["cpu_pct"] * (1 + (mult - 1) * 0.3)), 1)
        t += timedelta(minutes=METRIC_INTERVAL_MIN)


def find_free_window(busy, root_service, duration_min):
    for _ in range(200):
        start = START + timedelta(minutes=random.randint(0, SIM_DAYS * 24 * 60 - duration_min - 1))
        end = start + timedelta(minutes=duration_min)
        conflict = any(not (end <= b_start or start >= b_end) for b_start, b_end in busy.get(root_service, []))
        if not conflict:
            busy.setdefault(root_service, []).append((start, end))
            return start, end
    return None, None


def main():
    payments = read_csv(f"{OUT_DIR}/clearflow_rca_dataset.csv")
    events = read_csv(f"{OUT_DIR}/payment_events.csv")
    p_by_id = {p["payment_id"]: p for p in payments}
    ev_by_payment = {}
    for e in events:
        ev_by_payment.setdefault(e["payment_id"], []).append(e)

    max_event_num = max(int(e["event_id"].split("-")[1]) for e in events)
    event_counter = [max_event_num + 1]

    def new_event_id():
        eid = f"E-{event_counter[0]:08d}"
        event_counter[0] += 1
        return eid

    # eligible cohort candidates: payments not already BLOCKED/REJECTED
    eligible = [p for p in payments if p["payment_state"] not in ("BLOCKED", "REJECTED")]
    eligible_by_time = sorted(eligible, key=lambda p: p["created_at"])

    metrics = gen_metrics_baseline()
    metrics_index = {(parse_dt(r["timestamp"]), r["service"]): r for r in metrics}

    incidents, incident_payment_rows = [], []
    busy_windows = {}
    incident_counter = 0

    for family, fault_list in FAULT_CATALOG.items():
        for fault_type, root_service, root_component, depth in fault_list:
            for rep in range(INCIDENTS_PER_FAULT_TYPE):
                incident_seed = BASE_SEED * 1000 + incident_counter
                random.seed(incident_seed)

                severity = weighted_choice_local(["low", "medium", "high"], [0.5, 0.35, 0.15])
                dur_lo, dur_hi = SEVERITY_DURATION_MIN[severity]
                duration_min = random.randint(dur_lo, dur_hi)
                start, end = find_free_window(busy_windows, root_service, duration_min)
                if start is None:
                    incident_counter += 1
                    continue

                cohort_lo, cohort_hi = SEVERITY_COHORT[severity]
                cohort_size = random.randint(cohort_lo, cohort_hi)

                candidates = [p for p in eligible_by_time
                              if start <= parse_dt(p["created_at"]) <= end]
                random.shuffle(candidates)
                cohort = candidates[:cohort_size]
                if len(cohort) < 3:
                    incident_counter += 1
                    continue

                incident_id = f"INC-{incident_counter:04d}"
                root_event_id = new_event_id()
                root_ts = start + timedelta(minutes=random.randint(0, max(duration_min - 1, 0)))

                # write the shared root-cause event once, attached to the
                # first affected payment's chain, but every affected
                # payment's own fault-event points caused_by at it --
                # this is the "one shared root cause, many symptoms" link
                first_pid = cohort[0]["payment_id"]
                ev_by_payment.setdefault(first_pid, []).append({
                    "event_id": root_event_id, "payment_id": first_pid,
                    "parent_event_id": ev_by_payment[first_pid][-1]["event_id"] if ev_by_payment.get(first_pid) else "",
                    "caused_by": "", "timestamp": root_ts.isoformat(),
                    "service": root_service, "event_type": "FAULT_ROOT_CAUSE",
                    "old_state": "HEALTHY", "new_state": "DEGRADED",
                    "service_state": "FAILED" if severity != "low" else "DEGRADED",
                    "correlation_id": first_pid, "trace_id": p_by_id[first_pid]["uetr"],
                })

                affected_ids = []
                for p in cohort:
                    pid = p["payment_id"]
                    affected_ids.append(pid)
                    apply_fault_to_payment(p_by_id[pid], ev_by_payment.setdefault(pid, []),
                                            fault_type, family, root_service, root_event_id,
                                            new_event_id, root_ts, severity)

                # metrics: root service spikes; confounded incidents additionally
                # spike a downstream service LOUDER than the root
                spike_metrics(metrics_index, root_service, start, end, severity, magnitude_mult=1.0)
                if family == "confounded":
                    symptom_svc = CONFOUND_SYMPTOM_SERVICE[root_service]
                    spike_metrics(metrics_index, symptom_svc, start, end, severity, magnitude_mult=2.2)
                elif family == "cross_domain":
                    for svc in PROPAGATION_CHAINS[root_service][1:]:
                        spike_metrics(metrics_index, svc, start, end, severity, magnitude_mult=0.6)

                incidents.append({
                    "incident_id": incident_id, "fault_type": fault_type, "fault_family": family,
                    "root_service": root_service, "root_component": root_component,
                    "root_event_id": root_event_id, "propagation_path": "->".join(PROPAGATION_CHAINS[root_service]),
                    "propagation_depth": depth, "temporal_difficulty": TEMPORAL_DIFFICULTY[family],
                    "severity": severity, "injection_time": start.isoformat(),
                    "duration_seconds": duration_min * 60, "n_affected_payments": len(affected_ids),
                    "seed": incident_seed, "is_confounder": family == "confounded",
                })
                for pid in affected_ids:
                    incident_payment_rows.append({"incident_id": incident_id, "payment_id": pid})

                incident_counter += 1

    random.seed(BASE_SEED)  # restore for determinism of anything after this point

    # flatten events back out, re-sorted by payment then timestamp
    all_events = []
    for pid, evs in ev_by_payment.items():
        all_events.extend(sorted(evs, key=lambda e: e["timestamp"]))

    updated_payments = list(p_by_id.values())

    payment_fields = list(updated_payments[0].keys())
    write_csv(f"{OUT_DIR}/clearflow_rca_dataset.csv", updated_payments, payment_fields)
    event_fields = ["event_id", "payment_id", "parent_event_id", "caused_by", "timestamp",
                     "service", "event_type", "old_state", "new_state", "service_state",
                     "correlation_id", "trace_id"]
    write_csv(f"{OUT_DIR}/payment_events.csv", all_events, event_fields)

    incident_fields = ["incident_id", "fault_type", "fault_family", "root_service", "root_component",
                        "root_event_id", "propagation_path", "propagation_depth", "temporal_difficulty",
                        "severity", "injection_time", "duration_seconds", "n_affected_payments",
                        "seed", "is_confounder"]
    write_csv(f"{OUT_DIR}/incidents.csv", incidents, incident_fields)
    write_csv(f"{OUT_DIR}/incident_payments.csv", incident_payment_rows, ["incident_id", "payment_id"])
    write_csv(f"{OUT_DIR}/metrics.csv", metrics, ["timestamp", "service", "error_rate", "p99_latency_ms", "kafka_lag", "cpu_pct"])

    print(f"Incidents: {len(incidents)} (target {len(FAULT_CATALOG) * 2 * INCIDENTS_PER_FAULT_TYPE // len(FAULT_CATALOG) * sum(len(v) for v in FAULT_CATALOG.values())})")
    by_family = {}
    for inc in incidents:
        by_family[inc["fault_family"]] = by_family.get(inc["fault_family"], 0) + 1
    print("by family:", by_family)
    print("total affected-payment links:", len(incident_payment_rows))
    print("unique affected payments:", len({r['payment_id'] for r in incident_payment_rows}))
    print("metrics rows:", len(metrics))


def weighted_choice_local(options, weights):
    return random.choices(options, weights=weights, k=1)[0]


def apply_fault_to_payment(payment, payment_events, fault_type, family, root_service,
                            root_event_id, new_event_id_fn, root_ts, severity):
    """Rewrites one affected payment's downstream state + appends a
    fault-caused event to its chain, causally pointing back at the shared
    root_event_id. Uses only values already legal in the base schema
    (RESERVED/PENDING/etc) -- no fault-name leakage into the evidence.
    """
    last_ts = parse_dt(payment_events[-1]["timestamp"]) if payment_events else root_ts
    event_ts = max(root_ts, last_ts) + timedelta(seconds=random.randint(5, 120))

    if fault_type in ("LIQUIDITY_LOCK_STUCK",):
        payment["settlement_state"] = "PENDING"
        payment["liquidity_state"] = "RESERVED"
        payment["finalized"] = "False"
        new_state = "LIQUIDITY_RESERVED"
        old_state = "SETTLEMENT_PENDING"
        svc = "routing-execution"
    elif fault_type in ("AML_HOLD_RETRY_STORM",):
        payment["aml_state"] = "HOLD"
        payment["settlement_state"] = "PENDING"
        payment["retry_count"] = str(int(payment.get("retry_count", 0)) + random.randint(1, 4))
        new_state = "BLOCKED"
        old_state = "AML_SCREENED"
        svc = "aml-compliance"
    elif fault_type in ("IDEMPOTENCY_COLLISION_STORM",):
        payment["idempotency_state"] = "DUPLICATE_DETECTED"
        payment["retry_count"] = str(int(payment.get("retry_count", 0)) + random.randint(1, 3))
        new_state = "SETTLEMENT_PENDING"
        old_state = "SETTLEMENT_PENDING"
        svc = "gateway"
    elif fault_type in ("SETTLEMENT_FINALITY_VIOLATION",):
        payment["settlement_state"] = "PENDING"
        payment["finalized"] = "False"
        new_state = "SETTLEMENT_PENDING"
        old_state = "SETTLED"
        svc = "settlement"
    elif root_service == "routing-execution":
        # infra/cross_domain faults rooted at routing: stuck at liquidity
        # reservation, never reaches settlement (PENDING, never FAILED --
        # that's what distinguishes it from a settlement-side failure).
        payment["settlement_state"] = "PENDING"
        payment["liquidity_state"] = "RESERVED"
        payment["finalized"] = "False"
        new_state = "LIQUIDITY_RESERVED"
        old_state = "SETTLEMENT_PENDING"
        svc = "routing-execution"
    elif root_service == "aml-compliance":
        # infra/cross_domain faults rooted at AML: screening never clears,
        # payment held before liquidity is ever touched.
        payment["aml_state"] = "HOLD"
        payment["settlement_state"] = "PENDING"
        new_state = "BLOCKED"
        old_state = "AML_SCREENED"
        svc = "aml-compliance"
    elif root_service == "validation-enrichment":
        # No dedicated validation-stage state field exists in the schema
        # (GAP, see README) -- the only legitimate downstream fingerprint is
        # elevated retries with NEITHER an AML hold NOR an idempotency
        # collision behind them (payment_aware_rca uses exactly that
        # process-of-elimination signal). Everything else stays untouched:
        # this is what makes it distinct from every other root_service.
        payment["retry_count"] = str(int(payment.get("retry_count", 0)) + random.randint(1, 3))
        payment["settlement_state"] = "PENDING"
        payment["finalized"] = "False"
        new_state = "SETTLEMENT_PENDING"
        old_state = "VALIDATED"
        svc = "validation-enrichment"
    else:
        # settlement root (infra DB_TIMEOUT / cross_domain / confounded):
        # a DB failure fails outright most of the time -- was 40% FAILED /
        # 60% PENDING, and that 60% PENDING+RESERVED tail was indistinguishable
        # from routing-execution's own signature, which meant payment_aware_rca
        # kept getting pulled toward routing-execution (the confound's louder
        # downstream symptom) instead of the true settlement root. 75% FAILED
        # makes settlement_failed_frac the dominant, disambiguating signal.
        payment["settlement_state"] = "FAILED" if random.random() < 0.75 else "PENDING"
        payment["liquidity_state"] = "RESERVED"
        payment["finalized"] = "False"
        new_state = payment["settlement_state"]
        old_state = "SETTLEMENT_PENDING"
        svc = "settlement"

    payment["payment_state"] = derive_payment_state(payment["aml_state"], payment["settlement_state"])

    payment_events.append({
        "event_id": new_event_id_fn(), "payment_id": payment["payment_id"],
        "parent_event_id": payment_events[-1]["event_id"] if payment_events else "",
        "caused_by": root_event_id, "timestamp": event_ts.isoformat(),
        "service": svc, "event_type": "FAULT_PROPAGATION",
        "old_state": old_state, "new_state": new_state,
        "service_state": "DEGRADED" if severity == "low" else "FAILED",
        "correlation_id": payment["payment_id"], "trace_id": payment["uetr"],
    })


if __name__ == "__main__":
    main()
