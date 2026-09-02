#!/usr/bin/env python3
"""Real, independent external health-check witness for crash faults.

Root cause of the "22/101 incidents genuinely unsolvable" finding
(2026-09-02): crash faults use `kill -9` (see AdminController.stopServiceByPort),
a SIGKILL, so the dying service never gets to flush a final log line --
there is no self-evidence, by construction, not by difficulty.

Real production systems don't rely on a dead service's own logs either --
they rely on an INDEPENDENT monitor (a load balancer, a Kubernetes
liveness probe, a Nagios/Prometheus check) noticing the service stopped
responding. This script is that independent witness: it polls every
service's /actuator/health on a short interval and, the moment one stops
responding, writes a real document directly to Elasticsearch (a new
`clearflow-healthmonitor-*` index) -- completely independent of the
crashed service's own log stream, exactly like a real ops monitoring
system would.

This does NOT hand the answer to any RCA method directly -- for
confounded incidents (SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND, etc.) the
real reasoning task (disentangling which of several symptoms is the
actual root vs. a downstream confound) is untouched; this only removes
the "there is provably zero evidence anywhere" cases, which is a data-
generation gap, not a difficulty knob.

Usage: python3 health_witness_monitor.py [--interval 1.0]
Run this continuously alongside live_fault_injector.py during any
injection session (or long-running as a background process).
"""
import argparse
import time
from datetime import datetime, timezone

import requests

ES = "http://elastic:changeme@localhost:9200"
SERVICES = {
    "gateway": 8080, "fraud-scoring": 8081, "validation-enrichment": 8082,
    "aml-compliance": 8083, "routing-execution": 8084, "settlement": 8085,
    "audit": 8086, "mcp-readonly-gateway": 8087,
}


def check_one(name, port):
    try:
        r = requests.get(f"http://localhost:{port}/actuator/health", timeout=1.5)
        return r.ok and r.json().get("status") == "UP"
    except Exception:
        return False


def log_event(service, event_type, consecutive_failures):
    doc = {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "service": service,
        "eventType": event_type,
        "message": f"{event_type} service={service} consecutiveFailures={consecutive_failures}",
        "source": "health_witness_monitor",  # explicitly marked as an external witness, not the service's own log
        "level": "WARN" if event_type == "HEALTH_CHECK_FAILED" else "INFO",
    }
    index = f"clearflow-healthmonitor-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"
    try:
        requests.post(f"{ES}/{index}/_doc", json=doc, timeout=3)
    except Exception as e:
        print(f"  WARN: failed to log witness event: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=float, default=0, help="seconds to run, 0 = forever")
    args = ap.parse_args()

    state = {name: True for name in SERVICES}  # assume UP at start
    fail_streak = {name: 0 for name in SERVICES}
    start = time.time()
    print(f"Health witness monitor started, polling {len(SERVICES)} services every {args.interval}s...")

    while args.duration == 0 or (time.time() - start) < args.duration:
        for name, port in SERVICES.items():
            up = check_one(name, port)
            if up and not state[name]:
                fail_streak[name] = 0
                log_event(name, "HEALTH_CHECK_RECOVERED", 0)
                print(f"  {name}: RECOVERED")
            elif not up:
                fail_streak[name] += 1
                if state[name]:  # just went down
                    log_event(name, "HEALTH_CHECK_FAILED", fail_streak[name])
                    print(f"  {name}: DOWN (consecutive={fail_streak[name]})")
            state[name] = up
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
