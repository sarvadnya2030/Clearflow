#!/usr/bin/env python3
"""
ClearFlow Live Payment Sender
Sends ISO 20022 pacs.008 payments through the full 7-service pipeline.

Usage:
  python3 live_payment_sender.py          # interactive demo
  python3 live_payment_sender.py --batch 20   # batch mode
  python3 live_payment_sender.py --health     # health check only
"""
import argparse
import json
import random
import sys
import time
import uuid
from datetime import date, timedelta
from typing import Optional

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

GATEWAY = "http://localhost:8080"
MCP     = "http://localhost:8087"

SERVICES = [
    ("gateway",               8080),
    ("fraud-scoring",         8081),
    ("validation-enrichment", 8082),
    ("aml-compliance",        8083),
    ("routing-execution",     8084),
    ("settlement",            8085),
    ("audit",                 8086),
    ("mcp-readonly-gateway",  8087),
]

# Real-format IBANs (structurally valid, not necessarily check-digit verified)
PARTIES = [
    {"name": "Alpine Logistics GmbH",    "iban": "DE89370400440532013000", "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "Euro Trade SARL",          "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "HSBC Holdings PLC",        "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "UBS AG Zurich",            "iban": "CH5604835012345678009", "bic": "UBSWCHZHXXX", "country": "CH"},
    {"name": "ING Bank NV",              "iban": "NL91ABNA0417164300", "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "Banco Santander SA",       "iban": "ES9121000418450200051332", "bic": "BSCHESMM", "country": "ES"},
    {"name": "UniCredit SpA",            "iban": "IT60X0542811101000000123456", "bic": "UNCRITMM", "country": "IT"},
    {"name": "Raiffeisen Bank Intl",     "iban": "AT611904300234573201", "bic": "RZOOAT2L", "country": "AT"},
]

CHANNELS = ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS", "INTERNAL"]

def random_payment(amount: float = None, currency: str = None, channel: str = None) -> dict:
    debtor   = random.choice(PARTIES)
    creditor = random.choice([p for p in PARTIES if p != debtor])
    if amount is None:
        amount = round(random.uniform(100.0, 750_000.0), 2)
    if currency is None:
        currency = random.choice(["USD", "EUR", "GBP", "CHF", "JPY", "SGD"])
    if channel is None:
        channel = random.choice(CHANNELS)

    return {
        "instructionId":  str(uuid.uuid4()),
        "endToEndId":     f"E2E-{date.today().strftime('%Y%m%d')}-{random.randint(10000,99999)}",
        "uetr":           str(uuid.uuid4()),
        "debtor": {
            "name":    debtor["name"],
            "iban":    debtor["iban"],
            "bic":     debtor["bic"],
            "address": f"{debtor['country']} HQ",
            "country": debtor["country"],
        },
        "creditor": {
            "name":    creditor["name"],
            "iban":    creditor["iban"],
            "bic":     creditor["bic"],
            "address": f"{creditor['country']} Branch",
            "country": creditor["country"],
        },
        "amount":        amount,
        "currency":      currency,
        "valueDate":     (date.today() + timedelta(days=1)).isoformat(),
        "purpose":       "SUPP",
        "remittanceInfo": f"Invoice INV-{random.randint(10000, 99999)} settlement",
        "channel":       channel,
    }

def send(payload: dict, correlation_id: str = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    try:
        r = requests.post(
            f"{GATEWAY}/api/v1/payments",
            json=payload,
            headers=headers,
            timeout=10,
        )
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        return {"code": r.status_code, "body": body, "corr": correlation_id}
    except requests.exceptions.ConnectionError:
        return {"code": 0, "body": {}, "corr": correlation_id, "error": "Gateway unreachable"}
    except Exception as e:
        return {"code": 0, "body": {}, "corr": correlation_id, "error": str(e)}

def health_check() -> dict:
    results = {}
    for name, port in SERVICES:
        try:
            r = requests.get(f"http://localhost:{port}/actuator/health", timeout=3)
            if r.status_code == 200:
                status = r.json().get("status", "UNKNOWN")
                results[name] = status
            else:
                results[name] = f"HTTP {r.status_code}"
        except Exception:
            results[name] = "DOWN"
    return results

def print_health(health: dict) -> bool:
    all_up = True
    print("\n  Service Health:")
    print("  " + "-" * 40)
    for name, port in SERVICES:
        status = health.get(name, "?")
        ok = status == "UP"
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name:<28} {status}")
        if not ok:
            all_up = False
    print("  " + "-" * 40)
    return all_up

def demo_mode():
    print("=" * 60)
    print("  ClearFlow Live Payment Demo")
    print("  ISO 20022 pacs.008 → 7-service pipeline")
    print("=" * 60)

    # Health
    print("\n[1] Checking service health...")
    health = health_check()
    all_up = print_health(health)

    if not all_up:
        print("\n  ⚠  Not all services are UP.")
        ans = input("  Continue anyway? [y/N] ").strip().lower()
        if ans != "y":
            print("  Run: bash start_live_traffic.sh")
            return

    # Scenarios
    scenarios = [
        ("SEPA bulk transfer",        125_000.00, "EUR",  "SEPA"),
        ("SWIFT cross-border",        485_500.00, "USD",  "SWIFT"),
        ("UK Faster Payments retail",   2_250.75, "GBP",  "FASTER_PAYMENTS"),
        ("CHF interbank",             320_000.00, "CHF",  "SWIFT"),
        ("High-value USD Fedwire",    890_000.00, "USD",  "FEDWIRE"),
    ]

    print("\n[2] Sending test payments through full pipeline")
    print("    Gateway → Kafka/ActiveMQ → fraud-scoring → validation-enrichment")
    print("           → aml-compliance → routing-execution → settlement → audit\n")

    sent = accepted = rejected = 0
    payment_ids = []

    for label, amount, currency, channel in scenarios:
        payload = random_payment(amount=amount, currency=currency, channel=channel)
        corr_id = f"DEMO-{uuid.uuid4().hex[:8].upper()}"
        txn = payload

        print(f"  ─── {label} ───")
        print(f"    Amount   : {txn['amount']:>12,.2f} {txn['currency']}")
        print(f"    Debtor   : {txn['debtor']['name']} [{txn['debtor']['bic']}]")
        print(f"    Creditor : {txn['creditor']['name']} [{txn['creditor']['bic']}]")
        print(f"    Channel  : {txn['channel']}")
        print(f"    Corr-ID  : {corr_id}")

        result = send(payload, corr_id)
        code = result["code"]
        body = result["body"]

        if "error" in result:
            print(f"    Result   : ✗ ERROR — {result['error']}\n")
        elif code == 202:
            pid = body.get("paymentId", "?")
            print(f"    Result   : ✓ HTTP 202 ACCEPTED — paymentId={pid}\n")
            payment_ids.append(pid)
            accepted += 1
        elif code == 409:
            print(f"    Result   : ⟳ HTTP 409 DUPLICATE (idempotency guard)\n")
            rejected += 1
        elif code == 429:
            print(f"    Result   : ⧗ HTTP 429 RATE LIMITED\n")
            rejected += 1
        else:
            msg = body.get("message", body.get("error", ""))
            print(f"    Result   : ✗ HTTP {code}  {msg}\n")
            rejected += 1

        sent += 1
        time.sleep(1.2)

    # Rapid-fire burst
    print("  ─── Rapid burst (10 payments × 200ms) ───")
    for i in range(10):
        payload = random_payment()
        result  = send(payload, f"BURST-{i:02d}-{uuid.uuid4().hex[:6].upper()}")
        icon = "✓" if result["code"] == 202 else "✗"
        pid  = result["body"].get("paymentId", "?")
        print(f"    {icon} [{i+1:2d}/10] HTTP {result['code']}  paymentId={pid}")
        sent += 1
        if result["code"] == 202:
            accepted += 1
            payment_ids.append(pid)
        else:
            rejected += 1
        time.sleep(0.2)

    # Summary
    print(f"\n[3] Summary")
    print(f"    Sent      : {sent}")
    print(f"    Accepted  : {accepted}  (202 — in pipeline)")
    print(f"    Rejected  : {rejected}  (4xx)")

    print(f"\n[4] Pipeline is now processing asynchronously.")
    print(f"    Messages flow: Kafka topics → consumer services → DB writes\n")

    if payment_ids:
        pid_sample = payment_ids[0]
        print(f"    Example MCP queries (Claude Code):")
        print(f"      getPaymentTimeline(\"{pid_sample}\")")
        print(f"      explainIncidentWithCode(\"{pid_sample}\")")

    print(f"\n    Tail logs:")
    print(f"      tail -f /home/admin-/Desktop/EDI6/clearflow/dev-logs/gateway.log | grep -i payment")
    print(f"      tail -f /home/admin-/Desktop/EDI6/clearflow/dev-logs/fraud-scoring.log")
    print(f"      tail -f /home/admin-/Desktop/EDI6/clearflow/dev-logs/audit.log")

def batch_mode(count: int):
    print(f"Sending {count} payments in batch...")
    health = health_check()
    ups = sum(1 for v in health.values() if v == "UP")
    print(f"Services UP: {ups}/{len(SERVICES)}")

    ok = err = 0
    t0 = time.time()

    for i in range(count):
        payload = random_payment()
        result  = send(payload, f"BATCH-{i:04d}-{uuid.uuid4().hex[:6].upper()}")
        if result["code"] == 202:
            ok += 1
            sys.stdout.write(".")
        else:
            err += 1
            sys.stdout.write(f"[{result['code']}]")
        sys.stdout.flush()
        if (i + 1) % 50 == 0:
            print(f" {i+1}/{count}")
        time.sleep(0.05)

    elapsed = time.time() - t0
    print(f"\nDone. {ok} accepted, {err} rejected in {elapsed:.1f}s ({count/elapsed:.1f} req/s)")

def main():
    parser = argparse.ArgumentParser(description="ClearFlow Live Payment Sender")
    parser.add_argument("--health", action="store_true", help="Health check only")
    parser.add_argument("--batch",  type=int, metavar="N", help="Send N payments in batch")
    args = parser.parse_args()

    if args.health:
        health = health_check()
        print_health(health)
        sys.exit(0 if all(v == "UP" for v in health.values()) else 1)
    elif args.batch:
        batch_mode(args.batch)
    else:
        demo_mode()

if __name__ == "__main__":
    main()
