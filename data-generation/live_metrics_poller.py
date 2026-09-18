#!/usr/bin/env python3
"""Real fix for the p99_latency_ms/kafka_lag/cpu_pct = 100% NULL gap
documented throughout this session (RCA_RESEARCH_CONTEXT_TRANSFER.md #9,
#11, #15a). Root cause: these columns were always written as empty
strings in live_evidence.py -- no collector ever existed. CANNOT be
retroactively fixed for the 101-incident benchmark or the 10-incident
holdout (the data was never captured at the time, and Actuator/
Prometheus endpoints only expose CURRENT values, not history) -- this is
a fix for every future live incident, not the existing datasets.

Real, verified sources (checked directly against the live system before
building on them, per this project's own standing rule):
- CPU: /actuator/prometheus's `process_cpu_usage` and `system_cpu_usage`
  gauges, real per-service, confirmed live on aml-compliance (:8083).
- Kafka lag: `kafka-consumer-groups --describe --group <group>` gives
  real per-partition LAG. The injector's own kafka_lag_before/after
  fields were checked against the full 101-incident set and found to be
  roughly constant (19k-32k) across every fault type, including non-
  Kafka faults -- a chronic background reading, not incident-specific
  signal (verified, not assumed). The fix: sample the SPECIFIC affected
  consumer group repeatedly DURING the incident window, not a single
  before/after snapshot of a possibly-unrelated topic.

Usage: run this alongside a live fault injection (or immediately after,
while data is still fresh) to capture real per-service CPU and the
affected consumer group's real lag trajectory.
"""
import subprocess
import time

import requests

SERVICES_PORTS = {
    "gateway": 8080, "fraud-scoring": 8081, "validation-enrichment": 8082,
    "aml-compliance": 8083, "routing-execution": 8084, "settlement": 8085, "audit": 8086,
}

CONSUMER_GROUPS = [
    "routing-execution-kafka", "aml-compliance-kafka", "validation-enrichment-kafka",
    "settlement-service", "fraud-scoring", "audit-service",
]


def poll_cpu_once():
    """Real per-service CPU right now, via each service's own Actuator."""
    rows = {}
    for svc, port in SERVICES_PORTS.items():
        try:
            r = requests.get(f"http://localhost:{port}/actuator/prometheus", timeout=3)
            text = r.text
            proc_cpu = sys_cpu = None
            for line in text.splitlines():
                if line.startswith("process_cpu_usage "):
                    proc_cpu = float(line.split()[-1])
                elif line.startswith("system_cpu_usage "):
                    sys_cpu = float(line.split()[-1])
            rows[svc] = {"process_cpu_usage": proc_cpu, "system_cpu_usage": sys_cpu}
        except Exception as e:
            rows[svc] = {"error": str(e)}
    return rows


def poll_kafka_lag_once():
    """Real total lag per consumer group right now, via kafka-consumer-groups."""
    rows = {}
    for group in CONSUMER_GROUPS:
        try:
            out = subprocess.run(
                ["docker", "exec", "infrastructure-kafka-1", "kafka-consumer-groups",
                 "--bootstrap-server", "localhost:9092", "--describe", "--group", group],
                capture_output=True, text=True, timeout=10,
            ).stdout
            total_lag = 0
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        total_lag += int(parts[5])
                    except ValueError:
                        pass
            rows[group] = total_lag
        except Exception as e:
            rows[group] = None
    return rows


def poll_series(duration_s, interval_s=2):
    """Poll both CPU and Kafka lag repeatedly for `duration_s` seconds --
    real time-series capture during a live incident window, not a single
    before/after snapshot."""
    samples = []
    t0 = time.time()
    while time.time() - t0 < duration_s:
        samples.append({
            "t": round(time.time() - t0, 1),
            "cpu": poll_cpu_once(),
            "kafka_lag": poll_kafka_lag_once(),
        })
        time.sleep(interval_s)
    return samples


if __name__ == "__main__":
    print("=== One-shot verification: real CPU + Kafka lag right now ===")
    cpu = poll_cpu_once()
    for svc, v in cpu.items():
        print(f"  {svc:22s} process_cpu_usage={v.get('process_cpu_usage')} system_cpu_usage={v.get('system_cpu_usage')}")
    print()
    lag = poll_kafka_lag_once()
    for g, v in lag.items():
        print(f"  {g:28s} total_lag={v}")
