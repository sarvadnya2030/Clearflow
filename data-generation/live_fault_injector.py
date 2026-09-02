#!/usr/bin/env python3
"""
ClearFlow-RCA live fault injector -- Module 7 done for real. Triggers ACTUAL
faults against the live 8-service stack (not the synthetic generator in
inject_incidents.py) and records the ground truth a harness genuinely
controls. Everything else (n_affected_payments, propagation_path,
propagation_depth, severity) is measured POST-HOC by live_evidence.py from
real Elasticsearch/MCP data -- never preset here, unlike the synthetic
generator which can assert it upfront.

Live-triggerable set (mapped 1:1 onto data-generation/fault_taxonomy.md's
families, restricted to what Phase-0 research confirmed is actually
reachable through the running system):

  infra            -- kill+restart via AdminController (real process crash)
                       on aml-compliance / routing-execution /
                       validation-enrichment / settlement (the same 4 roots
                       the synthetic FAULT_CATALOG["infra"] already uses)
  payment_domain   -- IDEMPOTENCY_COLLISION_STORM (duplicate submission,
                       same instructionId+amount+debtorIban within TTL) and
                       AML_HOLD (SDN-matching debtor name -> real HOLD/
                       ESCALATED, confirmed live end-to-end in a prior
                       session)
  cross_domain     -- same crash mechanism on settlement / aml-compliance,
                       with sustained background traffic so the cascade is
                       real backpressure, not a hand-coded metric spike
  confounded       -- same crash mechanism on settlement /
                       validation-enrichment, same background-traffic
                       requirement

NOT included, on purpose (see data-generation/README.md "v6 -- live
injection" section for the reasoning):
  SETTLEMENT_FINALITY_VIOLATION -- confirmed unreachable via real traffic;
    StageIdempotencyGuard + settlementRepository.existsByPaymentId() both
    short-circuit before SettlementService's finality check ever runs.
  LIQUIDITY_LOCK_STUCK -- needs a hand-constructed Kafka-level message,
    no REST path exists yet; deferred, not attempted here.
  AML_HOLD_RETRY_STORM's "storm" half -- the hold itself fires for real,
    but the gateway retry path doesn't check AmlState before resubmission
    yet, so the retry-storm dynamic specifically can't be triggered live.

Usage:
    python3 data-generation/live_fault_injector.py --list
    python3 data-generation/live_fault_injector.py --run DB_TIMEOUT
    python3 data-generation/live_fault_injector.py --run-all --reps 3
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
import batch_realistic_v4 as traffic  # reuse the proven payload builder + token fetch

GATEWAY = "http://localhost:8080"
MCP = "http://localhost:8087"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
LIVE_INCIDENTS_CSV = os.path.join(OUT_DIR, "live_incidents.csv")
LIVE_SENT_CSV = os.path.join(OUT_DIR, "live_sent_payments.csv")

ADMIN_KILLABLE = {"aml-compliance", "routing-execution", "settlement", "validation-enrichment",
                   "audit", "fraud-scoring"}

# (fault_type, root_service, family, mechanism)
LIVE_FAULT_CATALOG = [
    ("DB_TIMEOUT", "settlement", "infra", "crash"),
    ("KAFKA_CONSUMER_LAG", "routing-execution", "infra", "crash"),
    ("NETWORK_LATENCY", "validation-enrichment", "infra", "crash"),
    ("CPU_SATURATION", "aml-compliance", "infra", "crash"),
    ("IDEMPOTENCY_COLLISION_STORM", "gateway", "payment_domain", "idempotency"),
    ("AML_HOLD", "aml-compliance", "payment_domain", "aml_hold"),
    ("SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE", "settlement", "cross_domain", "crash"),
    ("AML_SERVICE_DEGRADATION_RETRY_CASCADE", "aml-compliance", "cross_domain", "crash"),
    ("SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND", "settlement", "confounded", "crash"),
    # Was plain "crash" identically to every non-confound fault -- found live
    # (Phase-1 baseline eval, 2026-09-02) that this meant the "confound" was
    # never actually engineered, just hoped for as a side effect, and it
    # never once manifested across 8 reps. "crash_with_gateway_decoy" fires a
    # real burst of gateway-side PAYMENT_REJECTED events (invalid-currency
    # payloads, genuinely rejected by gateway's own @Valid validation)
    # concurrent with the real validation-enrichment outage -- a real decoy
    # signal on a service that is NOT the root cause, not a synthetic flag.
    ("VALIDATION_SLOWDOWN_GATEWAY_CONFOUND", "validation-enrichment", "confounded", "crash_with_gateway_decoy"),
]

CRASH_DURATION_S = {"infra": 20, "cross_domain": 30, "confounded": 30}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def append_sent_payment(payment_id, scenario):
    """Trigger functions (AML hold, idempotency) submit payments directly,
    outside TrafficGenerator's own loop -- without this, those payment_ids
    never appear in live_sent_payments.csv, so live_evidence.py never even
    looks at them (found live: this silently made every idempotency-collision
    incident's own trigger payment invisible to evidence extraction).
    """
    if not payment_id:
        return
    path = os.path.join(OUT_DIR, "live_sent_payments.csv")
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["payment_id", "sent_at", "scenario"])
        w.writerow([payment_id, now_iso(), scenario])


class TrafficGenerator:
    """Sends steady realistic traffic in a background thread and records
    every paymentId actually issued a real HTTP 202, with timestamps -- this
    is the persisted-payment-ID gap batch_realistic_v4.py itself has today.
    """

    def __init__(self, token, rate_per_s=3):
        self.token = token
        self.rate_per_s = rate_per_s
        self._stop = threading.Event()
        self._thread = None
        self.sent = []  # list of (payment_id, timestamp, scenario)
        self._lock = threading.Lock()

    def _loop(self):
        scenarios = ["clean"] * 7 + ["salary", "high_risk_corridor", "structuring"]
        while not self._stop.is_set():
            scenario = traffic.random.choice(scenarios)
            payload = traffic.build(scenario)
            try:
                r = requests.post(f"{GATEWAY}/api/v1/payments", json=payload,
                                   headers={"Authorization": f"Bearer {self.token}",
                                            "Content-Type": "application/json"},
                                   timeout=10)
                if r.status_code == 202:
                    pid = r.json().get("paymentId")
                    with self._lock:
                        self.sent.append((pid, now_iso(), scenario))
                    append_sent_payment(pid, scenario)  # persisted immediately, not just in-memory
            except Exception:
                pass
            time.sleep(1.0 / self.rate_per_s)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


def admin_call(action, service_id, token):
    r = requests.post(f"{MCP}/mcp/admin/service/{service_id}/{action}",
                       headers={"Authorization": f"Bearer {token}"}, timeout=15)
    return r.status_code, (r.json() if r.ok else r.text)


def wait_for_service_up(service_id, port, timeout_s=90):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{port}/actuator/health", timeout=3)
            if r.status_code == 200 and r.json().get("status") in ("UP", None):
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


SERVICE_PORTS = {"gateway": 8080, "fraud-scoring": 8081, "validation-enrichment": 8082,
                  "aml-compliance": 8083, "routing-execution": 8084, "settlement": 8085,
                  "audit": 8086, "mcp-readonly-gateway": 8087}

# Real Kafka consumer-group names per service (docker exec infrastructure-kafka-1
# kafka-consumer-groups --bootstrap-server localhost:9092 --list). Not every
# service has a 1:1 group -- gateway's status-tracking consumer and
# routing-execution's liquidity-release consumer are separate groups from
# their main processing group; kept minimal (just the main group) rather
# than guessing at every consumer a service runs.
SERVICE_CONSUMER_GROUPS = {
    "gateway": "gateway-status-tracker",
    "fraud-scoring": "fraud-scoring",
    "validation-enrichment": "validation-enrichment-kafka",
    "aml-compliance": "aml-compliance-kafka",
    "routing-execution": "routing-execution-kafka",
    "settlement": "settlement-service",
    "audit": "audit-service",
}


def sample_kafka_lag(consumer_group):
    """Real, CURRENT total lag for a consumer group -- not a historical time
    series (Kafka doesn't retain that; this is a live snapshot only, unlike
    Elasticsearch's queryable log history). Meaningful specifically when
    sampled right after a crashed service recovers: the lag at that moment
    is genuine evidence of how much backlog accumulated while it was down,
    tied directly to this incident, not retrofittable onto past incidents
    that didn't sample it live.
    """
    if not consumer_group:
        return None
    try:
        out = subprocess.run(
            ["docker", "exec", "infrastructure-kafka-1", "kafka-consumer-groups",
             "--bootstrap-server", "localhost:9092", "--describe", "--group", consumer_group],
            capture_output=True, text=True, timeout=15,
        )
        total_lag = 0
        found = False
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 6 and parts[0] == consumer_group and parts[4].lstrip("-").isdigit():
                total_lag += int(parts[4])
                found = True
        return total_lag if found else None
    except Exception:
        return None


def trigger_crash(root_service, family, token, gen: TrafficGenerator):
    duration = CRASH_DURATION_S[family]
    injection_time = now_iso()
    consumer_group = SERVICE_CONSUMER_GROUPS.get(root_service)
    lag_before = sample_kafka_lag(consumer_group)
    code, body = admin_call("stop", root_service, token)
    if code != 200:
        return None, f"stop failed: {code} {body}"
    time.sleep(duration)
    code, body = admin_call("start", root_service, token)
    recovered = wait_for_service_up(root_service, SERVICE_PORTS[root_service])
    # Sampled immediately on recovery, before the freshly-restarted consumer
    # has had time to drain the backlog -- this is the real post-outage
    # snapshot, not a settled/misleading later value.
    lag_after = sample_kafka_lag(consumer_group)
    return {
        "injection_time": injection_time,
        "duration_seconds": duration,
        "recovered": recovered,
        "kafka_lag_before": lag_before,
        "kafka_lag_after_recovery": lag_after,
    }, None


def trigger_crash_with_gateway_decoy(root_service, family, token, gen: TrafficGenerator):
    """Same real crash as trigger_crash, but fires a real burst of invalid-
    currency payments at gateway during the outage window -- genuinely
    rejected by gateway's own @Valid validation (GlobalExceptionHandler now
    logs these as real PAYMENT_REJECTED events, the same eventType
    validation-enrichment's real business rejections use). This is the
    actual confound: two services showing rejection-shaped symptoms at the
    same time, only one of which (root_service, via the real funnel stall)
    is the true root cause. Not a synthetic flag -- gateway really does
    reject these requests."""
    duration = CRASH_DURATION_S[family]
    injection_time = now_iso()
    consumer_group = SERVICE_CONSUMER_GROUPS.get(root_service)
    lag_before = sample_kafka_lag(consumer_group)
    code, body = admin_call("stop", root_service, token)
    if code != 200:
        return None, f"stop failed: {code} {body}"

    n_decoy = max(3, int(duration / 2))
    decoy_sent = 0
    interval = duration / n_decoy
    for _ in range(n_decoy):
        try:
            bad = traffic.build("clean")
            bad["currency"] = "XX1"  # violates @Pattern([A-Z]{3}) -- real 400
            requests.post(f"{GATEWAY}/api/v1/payments", json=bad,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          timeout=5)
            decoy_sent += 1
        except Exception:
            pass  # gateway may be under real load from the outage; a failed decoy send isn't fatal
        time.sleep(interval)

    code, body = admin_call("start", root_service, token)
    recovered = wait_for_service_up(root_service, SERVICE_PORTS[root_service])
    lag_after = sample_kafka_lag(consumer_group)
    return {
        "injection_time": injection_time,
        "duration_seconds": duration,
        "recovered": recovered,
        "kafka_lag_before": lag_before,
        "kafka_lag_after_recovery": lag_after,
        "decoy_sent": decoy_sent,
    }, None


def trigger_idempotency_collision(token, gen: TrafficGenerator):
    """Real duplicate submission -- same instructionId/amount/debtor within
    the gateway's idempotency TTL. Fires ~15 duplicates of one payload in
    a burst, mirroring the synthetic generator's IDEMPOTENCY_COLLISION_STORM
    shape but against the real gateway.
    """
    # A minority of CLEAN_ENTITIES pairings 400 on IBAN validation (found
    # live: some entries in batch_realistic_v4.py's entity pool carry a
    # checksum-invalid or country-mismatched IBAN, e.g. a GB-format IBAN
    # assigned to a Singapore/Canada entity) -- retry the FIRST submission
    # until it's actually accepted, then replay that same accepted payload
    # to generate the real duplicate-detection responses.
    injection_time = now_iso()
    payload = None
    for _ in range(10):
        candidate = traffic.build("clean")
        r = requests.post(f"{GATEWAY}/api/v1/payments", json=candidate,
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                           timeout=10)
        if r.status_code == 202:
            payload = candidate
            break
    results = []
    original_pid = None
    if payload is not None:
        results.append(202)
        original_pid = r.json().get("paymentId")  # r is still the accepting response from the retry loop above
        append_sent_payment(original_pid, "idempotency_original")
    if payload is None:
        payload = candidate  # fall through with whatever we last tried, for the record
    duplicate_confirmed = False
    for _ in range(14):
        r = requests.post(f"{GATEWAY}/api/v1/payments", json=payload,
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                           timeout=10)
        results.append(r.status_code)
        if r.status_code == 409:
            duplicate_confirmed = True
        time.sleep(0.3)
    duration = 5

    # The 409 rejections are never indexed into ES with a paymentId (they're
    # rejected synchronously in the gateway before any downstream event
    # fires) -- this is the ONLY place this evidence exists. Persist it now,
    # keyed to the ORIGINAL accepted payment, so live_evidence.py can set
    # idempotency_state=DUPLICATE_DETECTED without needing to (impossibly)
    # reconstruct it from logs later.
    if original_pid and duplicate_confirmed:
        dup_path = os.path.join(OUT_DIR, "live_duplicate_confirmations.csv")
        file_exists = os.path.exists(dup_path)
        with open(dup_path, "a", newline="") as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(["payment_id", "confirmed_at"])
            w.writerow([original_pid, now_iso()])

    return {
        "injection_time": injection_time,
        "duration_seconds": duration,
        "response_codes": results,
        "original_payment_id": original_pid,
        "duplicate_confirmed": duplicate_confirmed,
    }, None


def trigger_aml_hold(token, gen: TrafficGenerator):
    # Use the proven "aml_sdn" scenario builder (draws from SDN_ENTITIES, a
    # known-valid IBAN/BIC/currency/channel combo) rather than hand-editing a
    # "clean" payload's debtor name, which can produce a currency/rail
    # mismatch the validation layer legitimately 400s on (found live: a
    # BOKO HARAM debtor paired with a GBP/FEDWIRE/CH-creditor combo 400'd on
    # "Invalid IBAN" before ever reaching AML screening).
    # Not every "aml_sdn" draw is a real hold -- FUZZY/SOUNDEX matches below
    # threshold legitimately clear. Keep sending real payments (not
    # retrying the same one) until one is confirmed HELD, capped at 8 tries.
    injection_time = now_iso()
    pid = None
    matched = False
    for _ in range(8):
        payload = traffic.build("aml_sdn")
        r = requests.post(f"{GATEWAY}/api/v1/payments", json=payload,
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                           timeout=10)
        if r.status_code != 202:
            continue
        candidate_pid = r.json().get("paymentId")
        append_sent_payment(candidate_pid, "aml_sdn")
        time.sleep(3)
        holds = requests.get("http://localhost:8083/api/v1/compliance/holds", timeout=10).json()
        if isinstance(holds, list) and any(h.get("paymentId") == candidate_pid for h in holds):
            pid, matched = candidate_pid, True
            break
        pid = pid or candidate_pid
    return {
        "injection_time": injection_time,
        "duration_seconds": 5,
        "payment_id": pid,
        "confirmed_held": matched,
    }, None


def run_incident(fault_type, root_service, family, mechanism, token, gen: TrafficGenerator, rep):
    print(f"\n=== {fault_type} (root={root_service}, family={family}, mechanism={mechanism}) rep={rep} ===")
    if mechanism == "crash":
        result, err = trigger_crash(root_service, family, token, gen)
    elif mechanism == "crash_with_gateway_decoy":
        result, err = trigger_crash_with_gateway_decoy(root_service, family, token, gen)
    elif mechanism == "idempotency":
        result, err = trigger_idempotency_collision(token, gen)
    elif mechanism == "aml_hold":
        result, err = trigger_aml_hold(token, gen)
    else:
        return None
    if err:
        print(f"  FAILED: {err}")
        return None
    print(f"  OK: {json.dumps(result, default=str)}")
    # Ground-truth confidence: for "crash" this is tautologically certain
    # (root_service IS the process we chose to kill -- no ambiguity). For
    # "aml_hold"/"idempotency" the trigger can genuinely fail to produce the
    # labeled effect (e.g. an SDN-name draw that doesn't actually match) --
    # confirmed_held/duplicate_confirmed says whether it really did.
    if mechanism in ("crash", "crash_with_gateway_decoy"):
        confirmed = result.get("recovered", True)
    else:
        confirmed = result.get("confirmed_held", result.get("duplicate_confirmed", ""))
    return {
        "incident_id": f"LIVE-{uuid.uuid4().hex[:8]}",
        "fault_type": fault_type,
        "fault_family": family,
        "root_service": root_service,
        "mechanism": mechanism,
        "injection_time": result["injection_time"],
        "duration_seconds": result["duration_seconds"],
        "rep": rep,
        # NOT known ahead of time -- filled in post-hoc by live_evidence.py:
        "propagation_path": "", "propagation_depth": "", "severity": "",
        "n_affected_payments": "",
        "confirmed": confirmed,
        "kafka_lag_before": result.get("kafka_lag_before", ""),
        "kafka_lag_after_recovery": result.get("kafka_lag_after_recovery", ""),
        "decoy_sent": result.get("decoy_sent", ""),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run", help="fault_type to run once")
    ap.add_argument("--run-all", action="store_true")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--traffic-rate", type=float, default=3.0, help="background payments/sec")
    ap.add_argument("--spacing-s", type=float, default=240,
                     help="Cooldown between incidents (default 240s = 4min). Must exceed "
                          "live_evidence.py's LOOKBACK_HOURS baseline window (default 3min) "
                          "with margin, or the next incident's baseline gets contaminated by "
                          "this one's crash effects -- found live: incidents packed under a "
                          "minute apart silently broke every z-score baseline computation.")
    args = ap.parse_args()

    if args.list:
        for ft, svc, fam, mech in LIVE_FAULT_CATALOG:
            print(f"{fam:16s} {ft:45s} root={svc:22s} mechanism={mech}")
        return

    # Long runs (--run-all with real --spacing-s can take well over an hour)
    # were previously invisible until the very end -- both stdout (fully
    # buffered when not a TTY) and the incidents CSV (written once, after
    # the whole loop) only appeared after the LAST incident. Found live:
    # this looked exactly like a hang, and combined with this session's
    # earlier OOM kills, meant a crash near the end would lose every
    # incident with nothing recoverable. Line-buffer stdout and persist
    # each incident immediately instead.
    sys.stdout.reconfigure(line_buffering=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    # traffic.get_token() hits /api/v1/auth/token, which returns 200 with no
    # "token" field (found live -- not an exception, so the module's own
    # except-based fallback never triggers and callers silently get a
    # "Bearer None" header). Go straight to the known-good dev JWT.
    token = traffic.localStorage_token()

    gen = TrafficGenerator(token, rate_per_s=args.traffic_rate)
    gen.start()
    print(f"Background traffic started at {args.traffic_rate}/s")

    catalog = LIVE_FAULT_CATALOG
    if args.run:
        catalog = [f for f in LIVE_FAULT_CATALOG if f[0] == args.run]
        if not catalog:
            print(f"Unknown fault_type: {args.run}")
            gen.stop()
            return
    elif not args.run_all:
        print("Nothing to do -- pass --list, --run <fault_type>, or --run-all")
        gen.stop()
        return

    INCIDENT_FIELDS = ["incident_id", "fault_type", "fault_family", "root_service", "mechanism",
                        "injection_time", "duration_seconds", "rep", "propagation_path",
                        "propagation_depth", "severity", "n_affected_payments",
                        # Ground-truth confidence, not previously persisted (found in a
                        # post-hoc audit): trigger_aml_hold's confirmed_held and
                        # trigger_idempotency_collision's duplicate_confirmed were
                        # returned by run_incident() but silently dropped before the CSV
                        # write -- meaning there was no way to tell, from the persisted
                        # dataset alone, whether an "AML_HOLD" incident's root_service
                        # label corresponded to a real confirmed hold or a submission
                        # that just never got flagged. Recovered the 2 currently-collected
                        # AML_HOLD incidents' status from raw run logs (both true) --
                        # going forward this is a real column, not something to grep for.
                        "confirmed",
                        # Real Kafka consumer-group lag, sampled live at trigger time --
                        # current-state-only (Kafka has no historical lag query the way
                        # ES has historical logs), so only meaningful for incidents
                        # collected from here on, not retrofittable onto past ones.
                        "kafka_lag_before", "kafka_lag_after_recovery",
                        # How many gateway-decoy payments actually got sent during
                        # crash_with_gateway_decoy -- was being computed but silently
                        # dropped before the CSV write, same class of bug as confirmed/
                        # kafka_lag above. Lets a future rep check whether a low decoy
                        # count (e.g. 3 of 15 intended) was send failures vs something
                        # else, instead of only being visible in gold_cases_manifest.csv
                        # prose notes.
                        "decoy_sent"]

    def persist_incident(inc):
        file_exists = os.path.exists(LIVE_INCIDENTS_CSV)
        with open(LIVE_INCIDENTS_CSV, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=INCIDENT_FIELDS)
            if not file_exists:
                w.writeheader()
            w.writerow({k: inc.get(k, "") for k in INCIDENT_FIELDS})

    n_done = 0
    try:
        for ft, svc, fam, mech in catalog:
            for rep in range(args.reps):
                inc = run_incident(ft, svc, fam, mech, token, gen, rep)
                if inc:
                    persist_incident(inc)  # written immediately -- a crash mid-run loses at most 1 incident, not all of them
                    n_done += 1
                    print(f"  [{n_done} done, persisted]")
                time.sleep(args.spacing_s)  # cool-down between incidents -- see --spacing-s help
    finally:
        gen.stop()
        print(f"\nBackground traffic stopped. {n_done} incidents persisted, "
              f"{len(gen.sent)} background payments sent total (each already persisted as sent).")


if __name__ == "__main__":
    main()
