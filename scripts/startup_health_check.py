#!/usr/bin/env python3
"""Real, end-to-end health check for the ClearFlow-RCA benchmark infra.
Run this at the start of every work session (and every loop iteration
that touches infra). Sends one real payment through the gateway and
verifies it is actually traceable through the real pipeline -- not just
"services return 200". Exits non-zero on any real failure.

Per BENCHMARK_GOAL.md's non-trust protocol: never assume infra is healthy
because it was healthy last time.
"""
import importlib.util
import subprocess
import sys
import time
import requests

_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("lps", _REPO_ROOT / "live_payment_sender.py")
lps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lps)

SERVICES = {
    8080: "gateway", 8081: "fraud-scoring", 8082: "validation-enrichment",
    8083: "aml-compliance", 8084: "routing-execution", 8085: "settlement",
    8086: "audit", 8087: "mcp-readonly-gateway",
}
ES = "http://elastic:changeme@localhost:9200"
EXPECTED_EVENTS = [
    ("gateway", "PAYMENT_SUBMITTED"),
    ("validation-enrichment", "PAYMENT_VALIDATED"),
    ("aml-compliance", "AML_SCREENING_COMPLETE"),
    ("routing-execution", "PAYMENT_ROUTED"),
    ("settlement", "SETTLEMENT_COMPLETE"),
]

ok, fail = [], []


def check(name, cond, detail=""):
    (ok if cond else fail).append(name + (f" -- {detail}" if detail else ""))
    print(("PASS" if cond else "FAIL") + f": {name}" + (f" ({detail})" if detail else ""))


def main():
    print("=== 1. Service health ===")
    for port, name in SERVICES.items():
        try:
            r = requests.get(f"http://localhost:{port}/actuator/health", timeout=5)
            check(f"{name}:{port}", r.ok and r.json().get("status") == "UP", r.text[:80])
        except Exception as e:
            check(f"{name}:{port}", False, str(e))

    print("\n=== 2. Infra containers (no Exited) ===")
    # The 8 app services also have containerized definitions in this
    # compose file, but the real architecture (and the fault injector's
    # kill/relaunch-by-port mechanism) expects them as host JVM processes
    # -- intentionally stopped 2026-09-02 to avoid port conflicts, not a
    # real failure. kafka-init is a real one-shot init container (exit 0
    # is its success state). sonarqube/camunda aren't on the RCA data path.
    EXPECTED_STOPPED = {"infrastructure-gateway-1", "infrastructure-settlement-1",
                         "infrastructure-fraud-scoring-1", "infrastructure-mcp-readonly-gateway-1",
                         "infrastructure-validation-enrichment-1", "infrastructure-routing-execution-1",
                         "infrastructure-aml-compliance-1", "infrastructure-audit-1",
                         "infrastructure-kafka-init-1", "infrastructure-sonarqube-1",
                         "infrastructure-camunda-1"}
    out = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
                          capture_output=True, text=True).stdout
    exited = [l for l in out.splitlines() if l.startswith("infrastructure-") and "Exited" in l
              and l.split("\t")[0] not in EXPECTED_STOPPED]
    check("no unexpected exited infra containers", len(exited) == 0, "; ".join(exited) or "none")

    print("\n=== 3. Real payment end-to-end trace ===")
    # reuse the project's own known-good payload builder + sender, rather
    # than a hand-rolled payload that can silently drift from the real
    # validated schema (already caught one such drift this check)
    result = lps.send(lps.random_payment(), f"HEALTHCHECK-{int(time.time())}")
    payment_ok = result.get("code") in (200, 202)
    check("gateway accepted payment", payment_ok, str(result)[:200])
    if not payment_ok:
        print("\nCannot continue trace check -- payment was not accepted.")
        summary()
        return

    payment_id = (result.get("body") or {}).get("paymentId") or (result.get("body") or {}).get("payment_id")
    check("got a paymentId back", bool(payment_id), str(result.get("body"))[:150])
    if not payment_id:
        summary()
        return

    print(f"  paymentId={payment_id} -- waiting for pipeline...")
    seen = set()
    deadline = time.time() + 25
    while time.time() < deadline and not all(ev in seen for ev in EXPECTED_EVENTS):
        resp = requests.get(f"{ES}/clearflow-*/_search", timeout=5, json={
            "size": 50, "query": {"term": {"paymentId": payment_id}},
            "_source": ["service", "eventType"],
        })
        for h in resp.json().get("hits", {}).get("hits", []):
            src = h["_source"]
            seen.add((src.get("service"), src.get("eventType")))
        if not all(ev in seen for ev in EXPECTED_EVENTS):
            time.sleep(2)

    for svc, ev in EXPECTED_EVENTS:
        check(f"stage reached: {svc} -> {ev}", (svc, ev) in seen)

    print("\n=== 4. Jaeger receiving traces (was down for 13h earlier this session) ===")
    try:
        j = requests.get("http://localhost:16686/api/traces", params={"service": "gateway", "limit": 1}, timeout=5)
        check("jaeger has recent gateway traces", j.ok and len(j.json().get("data", [])) > 0)
    except Exception as e:
        check("jaeger reachable", False, str(e))

    print("\n=== 5. Neo4j (agent memory graph, added 2026-09-02) ===")
    try:
        n = requests.get("http://localhost:7474", timeout=5)
        check("neo4j http reachable", n.status_code == 200)
    except Exception as e:
        check("neo4j reachable", False, str(e))

    summary()


def summary():
    print(f"\n=== SUMMARY: {len(ok)} pass, {len(fail)} fail ===")
    if fail:
        print("FAILURES:")
        for f in fail:
            print("  -", f)
        sys.exit(1)
    print("All checks passed -- infra is genuinely healthy and end-to-end data flow is confirmed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
