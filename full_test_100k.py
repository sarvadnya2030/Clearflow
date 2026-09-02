#!/usr/bin/env python3
"""
ClearFlow Full Functionality Test — 100,000 payments
Tests: happy path, fraud, AML sanctions, duplicates, rate limits,
       high-value, multi-currency, all channels, compliance triggers.
Uses concurrent threads for realistic throughput.
"""
import argparse, json, random, sys, time, uuid, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date, timedelta

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

GATEWAY = "http://localhost:8080"
MCP     = "http://localhost:8087"
TOTAL   = 100_000
WORKERS = 20        # concurrent threads
RATE_HZ = 50        # target req/s (0 = unlimited)

# ── Parties ─────────────────────────────────────────────────────────────────
CLEAN = [
    {"name": "Alpine Logistics GmbH",  "iban": "DE89370400440532013000",      "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "Euro Trade SARL",        "iban": "FR7630006000011234567890189",  "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "HSBC Holdings PLC",      "iban": "GB29NWBK60161331926819",      "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "UBS AG Zurich",          "iban": "CH5604835012345678009",        "bic": "UBSWCHZHXXX", "country": "CH"},
    {"name": "ING Bank NV",            "iban": "NL91ABNA0417164300",          "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "Banco Santander SA",     "iban": "ES9121000418450200051332",     "bic": "BSCHESMM",   "country": "ES"},
    {"name": "UniCredit SpA",          "iban": "IT60X0542811101000000123456",  "bic": "UNCRITMM",   "country": "IT"},
    {"name": "Raiffeisen Bank Intl",   "iban": "AT611904300234573201",         "bic": "RZOOAT2L",   "country": "AT"},
]

# SDN-adjacent names to trigger AML fuzzy match
SANCTIONS = [
    {"name": "Al-Aqsa Foundation",     "iban": "IR000000000000000000000001", "bic": "IRANBANKXXX", "country": "IR"},
    {"name": "Pyongyang Trading Co",   "iban": "KP000000000000000000000001", "bic": "NKORBANKXXX", "country": "KP"},
    {"name": "Crimea Export LLC",      "iban": "RU000000000000000000000001", "bic": "ROSSBANKXXX", "country": "RU"},
]

CHANNELS   = ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS", "INTERNAL"]
CURRENCIES = ["USD", "EUR", "GBP", "CHF", "JPY", "SGD", "AUD", "CAD"]

# ── Scenario mix (out of 100 slots) ─────────────────────────────────────────
# 80% happy path, 8% high-value, 5% AML trigger, 4% fraud, 2% duplicate, 1% CTR
SCENARIO_WEIGHTS = [
    ("happy",      80),
    ("high_value",  8),
    ("aml",         5),
    ("fraud",       4),
    ("duplicate",   2),
    ("ctr",         1),
]
SCENARIO_POOL = []
for name, weight in SCENARIO_WEIGHTS:
    SCENARIO_POOL.extend([name] * weight)

# ── Stats ────────────────────────────────────────────────────────────────────
lock    = threading.Lock()
stats   = defaultdict(int)
latencies = []
dup_ids   = []   # reuse these for duplicate scenario

def _party(pool):
    return random.choice(pool)

def build_payload(scenario: str, dup_id: str = None) -> dict:
    today    = date.today()
    tomorrow = today + timedelta(days=1)

    if scenario == "aml":
        debtor   = _party(SANCTIONS)
        creditor = _party(CLEAN)
        amount   = round(random.uniform(5_000, 50_000), 2)
        channel  = random.choice(CHANNELS)
    elif scenario == "high_value":
        debtor   = _party(CLEAN)
        creditor = _party([p for p in CLEAN if p != debtor])
        amount   = round(random.uniform(500_000, 2_000_000), 2)
        channel  = random.choice(["SWIFT", "FEDWIRE"])
    elif scenario == "fraud":
        debtor   = _party(CLEAN)
        creditor = _party([p for p in CLEAN if p != debtor])
        amount   = round(random.uniform(9_000, 9_999), 2)   # just-under CTR structuring
        channel  = random.choice(CHANNELS)
    elif scenario == "ctr":
        debtor   = _party(CLEAN)
        creditor = _party([p for p in CLEAN if p != debtor])
        amount   = round(random.uniform(10_001, 15_000), 2)  # CTR threshold
        channel  = random.choice(CHANNELS)
    else:  # happy / duplicate
        debtor   = _party(CLEAN)
        creditor = _party([p for p in CLEAN if p != debtor])
        amount   = round(random.uniform(100, 750_000), 2)
        channel  = random.choice(CHANNELS)

    instruction_id = dup_id if (scenario == "duplicate" and dup_id) else str(uuid.uuid4())

    return {
        "instructionId":  instruction_id,
        "endToEndId":     f"E2E-{today.strftime('%Y%m%d')}-{random.randint(10000,99999)}",
        "uetr":           str(uuid.uuid4()),
        "debtor":   {"name": debtor["name"],   "iban": debtor["iban"],   "bic": debtor["bic"],   "address": f"{debtor['country']} HQ",     "country": debtor["country"]},
        "creditor": {"name": creditor["name"], "iban": creditor["iban"], "bic": creditor["bic"], "address": f"{creditor['country']} Branch","country": creditor["country"]},
        "amount":        amount,
        "currency":      random.choice(CURRENCIES),
        "valueDate":     tomorrow.isoformat(),
        "purpose":       "SUPP",
        "remittanceInfo": f"INV-{random.randint(10000,99999)}",
        "channel":       channel,
    }

def send_one(i: int) -> dict:
    scenario = random.choice(SCENARIO_POOL)
    dup_id   = None

    if scenario == "duplicate" and dup_ids:
        dup_id = random.choice(dup_ids)

    payload = build_payload(scenario, dup_id)
    corr_id = f"LT-{i:06d}-{uuid.uuid4().hex[:6].upper()}"
    t0 = time.monotonic()

    try:
        r = requests.post(
            f"{GATEWAY}/api/v1/payments",
            json=payload,
            headers={"Content-Type": "application/json", "X-Correlation-Id": corr_id},
            timeout=15,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        code = r.status_code
        body = {}
        try: body = r.json()
        except: pass

        with lock:
            latencies.append(elapsed_ms)
            stats[f"http_{code}"] += 1
            stats[f"scenario_{scenario}"] += 1
            if code == 202:
                stats["accepted"] += 1
                pid = body.get("paymentId")
                if pid and len(dup_ids) < 500:
                    dup_ids.append(payload["instructionId"])
            elif code == 409: stats["duplicate"] += 1
            elif code == 429: stats["rate_limited"] += 1
            elif code >= 500: stats["server_error"] += 1
            else:             stats["rejected"] += 1
        return {"code": code, "scenario": scenario, "ms": elapsed_ms}

    except requests.exceptions.ConnectionError:
        with lock: stats["connection_error"] += 1
        return {"code": 0, "scenario": scenario, "ms": 0}
    except Exception as e:
        with lock: stats["exception"] += 1
        return {"code": -1, "scenario": scenario, "ms": 0, "err": str(e)}

def print_progress(done: int, total: int, t0: float):
    elapsed = time.monotonic() - t0
    rps     = done / elapsed if elapsed > 0 else 0
    pct     = done / total * 100
    acc     = stats["accepted"]
    errs    = stats["connection_error"] + stats["server_error"] + stats["exception"]
    bar_len = 30
    filled  = int(bar_len * done / total)
    bar     = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:5.1f}%  {done:,}/{total:,}  {rps:5.1f} req/s  "
          f"accepted={acc:,}  errors={errs:,}", end="", flush=True)

def percentile(data, p):
    if not data: return 0
    s = sorted(data)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s)-1)]

def run_health_check():
    print("  Checking service health...")
    all_up = True
    for name, port in [("gateway",8080),("fraud-scoring",8081),("validation-enrichment",8082),
                       ("aml-compliance",8083),("routing-execution",8084),("settlement",8085),
                       ("audit",8086),("mcp-readonly-gateway",8087)]:
        try:
            r = requests.get(f"http://localhost:{port}/actuator/health", timeout=3)
            status = r.json().get("status","?") if r.status_code == 200 else f"HTTP {r.status_code}"
        except: status = "DOWN"
        icon = "✓" if status == "UP" else "✗"
        print(f"  {icon}  {name:<28} {status}")
        if status != "UP": all_up = False
    return all_up

def run_mcp_sample(payment_ids: list):
    if not payment_ids:
        return
    pid = payment_ids[0]
    print(f"\n  Sample MCP queries for paymentId={pid}:")
    for endpoint in [f"/mcp/payments/{pid}/timeline", f"/mcp/payments/{pid}/explain"]:
        try:
            r = requests.get(f"{MCP}{endpoint}", headers={"Authorization": "Bearer demo-token"}, timeout=5)
            print(f"  GET {endpoint} → HTTP {r.status_code}")
        except Exception as e:
            print(f"  GET {endpoint} → {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--total",   type=int, default=TOTAL,   help="Number of payments")
    parser.add_argument("--workers", type=int, default=WORKERS, help="Concurrent threads")
    parser.add_argument("--rate",    type=int, default=RATE_HZ, help="Target req/s (0=unlimited)")
    args = parser.parse_args()

    print("=" * 70)
    print("  ClearFlow Full Functionality Test")
    print(f"  {args.total:,} payments · {args.workers} workers · target {args.rate} req/s")
    print("  Scenarios: happy(80%) high-value(8%) aml(5%) fraud(4%) dup(2%) ctr(1%)")
    print("=" * 70)

    if not run_health_check():
        print("\n  ✗ Not all services UP. Aborting.")
        sys.exit(1)

    print(f"\n  Starting {args.total:,} payments...\n")
    t0      = time.monotonic()
    done    = 0
    sample_ids = []
    interval = 1.0 / args.rate if args.rate > 0 else 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {}
        for i in range(args.total):
            fut = pool.submit(send_one, i)
            futs[fut] = i
            if interval > 0:
                time.sleep(interval / args.workers)

        for fut in as_completed(futs):
            done += 1
            result = fut.result()
            if result.get("code") == 202 and len(sample_ids) < 5:
                sample_ids.append(result.get("scenario",""))
            if done % 500 == 0 or done == args.total:
                print_progress(done, args.total, t0)

    elapsed = time.monotonic() - t0
    print("\n")

    # ── Final report ─────────────────────────────────────────────────────────
    lats = sorted(latencies)
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  Total sent        : {args.total:,}")
    print(f"  Duration          : {elapsed:.1f}s  ({args.total/elapsed:.1f} req/s avg)")
    print()
    print(f"  ✓ Accepted (202)  : {stats['accepted']:,}  ({stats['accepted']/args.total*100:.1f}%)")
    print(f"  ⟳ Duplicates (409): {stats['duplicate']:,}")
    print(f"  ⧗ Rate-limited(429): {stats['rate_limited']:,}")
    print(f"  ✗ Server errors   : {stats['server_error']:,}")
    print(f"  ✗ Conn errors     : {stats['connection_error']:,}")
    print()
    print("  Latency (gateway response):")
    print(f"    p50  = {percentile(lats,50):6.1f} ms")
    print(f"    p90  = {percentile(lats,90):6.1f} ms")
    print(f"    p95  = {percentile(lats,95):6.1f} ms")
    print(f"    p99  = {percentile(lats,99):6.1f} ms")
    print(f"    max  = {max(lats,default=0):6.1f} ms")
    print()
    print("  Scenario breakdown:")
    for sc, _ in SCENARIO_WEIGHTS:
        cnt = stats[f"scenario_{sc}"]
        print(f"    {sc:<14} {cnt:>7,}  ({cnt/args.total*100:.1f}%)")
    print()

    # SLA gates
    p99 = percentile(lats, 99)
    p95 = percentile(lats, 95)
    accept_rate = stats['accepted'] / args.total
    err_rate = (stats['connection_error'] + stats['server_error']) / args.total

    print("  SLA gates:")
    print(f"    p99 < 500ms   : {'PASS ✓' if p99 < 500 else 'FAIL ✗'}  ({p99:.0f}ms)")
    print(f"    p95 < 200ms   : {'PASS ✓' if p95 < 200 else 'FAIL ✗'}  ({p95:.0f}ms)")
    print(f"    accept > 95%  : {'PASS ✓' if accept_rate > 0.95 else 'FAIL ✗'}  ({accept_rate*100:.1f}%)")
    print(f"    error  < 1%   : {'PASS ✓' if err_rate < 0.01 else 'FAIL ✗'}  ({err_rate*100:.2f}%)")
    print()

    run_mcp_sample(dup_ids[:3])

    print()
    print("  Pipeline is processing asynchronously.")
    print("  Monitor:")
    print("    tail -f dev-logs/gateway.log | python3 -c \"import sys,json; [print(json.loads(l).get('message','')) for l in sys.stdin]\"")
    print("    tail -f dev-logs/fraud-scoring.log")
    print("    tail -f dev-logs/aml-compliance.log")
    print("=" * 70)

if __name__ == "__main__":
    main()
