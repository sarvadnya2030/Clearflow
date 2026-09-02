#!/usr/bin/env python3
"""
ClearFlow Batched 100k Payment Test
200 batches × 500 payments, 1s cooldown between batches.
10 concurrent workers per batch.

Scenarios per batch of 500:
  400 happy · 40 high-value · 25 AML · 20 fraud · 10 duplicate · 5 CTR

After all batches, waits for Kafka pipeline to drain and shows
a stage-by-stage funnel: submitted → fraud → validated → AML →
routed → settled → audited.
"""
import json, os, random, subprocess, sys, time, uuid, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date, timedelta

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

GATEWAY     = "http://localhost:8080"
BATCH_SIZE  = 500
NUM_BATCHES = 200
WORKERS     = 10
COOLDOWN    = 1.0

INFRA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "infrastructure")

# Service ports for actuator metrics
SVC_PORTS = {
    "gateway":    8080,
    "fraud":      8081,
    "validation": 8082,
    "aml":        8083,
    "routing":    8084,
    "settlement": 8085,
    "audit":      8086,
}

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
SANCTIONS = [
    {"name": "Al-Aqsa Foundation",   "iban": "IR000000000000000000000001", "bic": "IRANBANKXXX", "country": "IR"},
    {"name": "Pyongyang Trading Co", "iban": "KP000000000000000000000002", "bic": "NKORBANKXXX", "country": "KP"},
    {"name": "Crimea Export LLC",    "iban": "RU000000000000000000000003", "bic": "ROSSBANKXXX", "country": "RU"},
]
CHANNELS   = ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS", "INTERNAL"]
CURRENCIES = ["USD", "EUR", "GBP", "CHF", "JPY", "SGD"]

SCENARIOS = (
    ["happy"]      * 400 +
    ["high_value"] * 40  +
    ["aml"]        * 25  +
    ["fraud"]      * 20  +
    ["duplicate"]  * 10  +
    ["ctr"]        * 5
)

lock        = threading.Lock()
total_stats = defaultdict(int)
all_latencies = []
reuse_ids   = []

# ── Payment builder ───────────────────────────────────────────────────────────

def build(scenario, dup_id=None):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    d = random.choice(CLEAN)
    c = random.choice([p for p in CLEAN if p != d])

    if scenario == "aml":
        d = random.choice(SANCTIONS)
        amount = round(random.uniform(5_000, 50_000), 2)
    elif scenario == "high_value":
        amount = round(random.uniform(500_000, 2_000_000), 2)
    elif scenario in ("fraud", "ctr"):
        amount = round(random.uniform(9_800, 10_200), 2)
    else:
        amount = round(random.uniform(100, 750_000), 2)

    iid = dup_id if (scenario == "duplicate" and dup_id) else str(uuid.uuid4())
    return {
        "instructionId":  iid,
        "endToEndId":     f"E2E-{date.today().strftime('%Y%m%d')}-{random.randint(10000,99999)}",
        "uetr":           str(uuid.uuid4()),
        "debtor":   {"name": d["name"], "iban": d["iban"], "bic": d["bic"],
                     "address": f"{d['country']} HQ",     "country": d["country"]},
        "creditor": {"name": c["name"], "iban": c["iban"], "bic": c["bic"],
                     "address": f"{c['country']} Branch", "country": c["country"]},
        "amount": amount, "currency": random.choice(CURRENCIES),
        "valueDate": tomorrow, "purpose": "SUPP",
        "remittanceInfo": f"INV-{random.randint(10000,99999)}",
        "channel": random.choice(CHANNELS),
    }

# ── HTTP send with 429 retry ──────────────────────────────────────────────────

def send(i, scenario):
    dup_id = random.choice(reuse_ids) if (scenario == "duplicate" and reuse_ids) else None
    payload = build(scenario, dup_id)
    corr_id = f"B-{i:06d}-{uuid.uuid4().hex[:6].upper()}"
    delay   = 0.3

    for attempt in range(4):
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{GATEWAY}/api/v1/payments", json=payload,
                headers={"Content-Type": "application/json",
                         "X-Correlation-Id": corr_id},
                timeout=15)
            ms   = (time.monotonic() - t0) * 1000
            code = r.status_code

            if code == 429 and attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue

            with lock:
                all_latencies.append(ms)
                total_stats[f"http_{code}"] += 1
                total_stats[f"sc_{scenario}"] += 1
                if code == 202:
                    total_stats["accepted"] += 1
                    if len(reuse_ids) < 300:
                        reuse_ids.append(payload["instructionId"])
                elif code == 409: total_stats["duplicate_hit"] += 1
                elif code == 429: total_stats["rate_limited"] += 1
                elif code >= 500: total_stats["server_error"] += 1
                else:             total_stats["other_reject"] += 1
            return code

        except requests.exceptions.ConnectionError:
            with lock: total_stats["conn_error"] += 1
            return 0
        except Exception:
            with lock: total_stats["exception"] += 1
            return -1

    return 429  # exhausted retries

# ── Helpers ───────────────────────────────────────────────────────────────────

def pct(p):
    if not all_latencies: return 0
    s = sorted(all_latencies)
    return s[min(int(len(s) * p / 100), len(s) - 1)]

def health_ok():
    try:
        r = requests.get(f"{GATEWAY}/actuator/health", timeout=3)
        return r.status_code == 200 and r.json().get("status") == "UP"
    except:
        return False

def get_metric(port, name):
    """Read a counter from the Prometheus scrape endpoint."""
    try:
        r = requests.get(f"http://localhost:{port}/actuator/prometheus", timeout=5)
        if r.status_code != 200:
            return None
        for line in r.text.splitlines():
            if line.startswith(name + " ") or line.startswith(name + "{"):
                parts = line.rsplit(" ", 1)
                return int(float(parts[-1]))
    except:
        pass
    return None

def kafka_group_lag(group):
    """Return total consumer lag for a consumer group, or -1 on error."""
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "kafka",
             "kafka-consumer-groups",
             "--bootstrap-server", "kafka:9092",
             "--describe", "--group", group],
            cwd=INFRA_DIR, capture_output=True, text=True, timeout=10)
        total = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 6 and parts[5].lstrip("-").isdigit():
                lag = int(parts[5])
                if lag > 0:
                    total += lag
        return total
    except Exception:
        return -1

CONSUMER_GROUPS = [
    ("validation", "validation-enrichment-kafka"),
    ("aml",        "aml-compliance-kafka"),
    ("routing",    "routing-execution-kafka"),
    ("settlement", "settlement-service"),
    ("audit",      "audit-service"),
]

def wait_for_drain(timeout_sec=600):
    print("\n  Pipeline drain check (waiting for Kafka consumer lag → 0)...")
    deadline = time.monotonic() + timeout_sec
    dots     = 0
    while time.monotonic() < deadline:
        lags = [(label, kafka_group_lag(group)) for label, group in CONSUMER_GROUPS]
        known = [(l, v) for l, v in lags if v >= 0]
        total = sum(v for _, v in known)
        lag_str = "  ".join(f"{l}={v}" for l, v in lags)
        print(f"  lag → {lag_str}")
        if total == 0 and known:
            print("  ✓ All consumer groups drained.")
            return True
        time.sleep(10)
    print("  ✗ Drain timeout reached.")
    return False

def run_batch(batch_num, scenarios):
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(send, batch_num * BATCH_SIZE + i, sc): sc
                for i, sc in enumerate(scenarios)}
        results = [f.result() for f in as_completed(futs)]
    ok  = results.count(202)
    err = results.count(0) + sum(1 for c in results if isinstance(c, int) and c >= 500)
    return ok, err

# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 68)
print("  ClearFlow Batched 100k Test")
print(f"  {NUM_BATCHES} batches × {BATCH_SIZE:,} payments · {WORKERS} workers · {COOLDOWN}s cooldown")
print("=" * 68)

if not health_ok():
    print("  ✗ Gateway not UP. Run: bash start_live_traffic.sh")
    sys.exit(1)
print("  ✓ Gateway UP — starting\n")

grand_start    = time.monotonic()
batch_scenarios = SCENARIOS[:]

print(f"  {'Batch':>5}  {'Sent':>6}  {'OK':>6}  {'Err':>5}  {'RL':>5}  {'req/s':>6}  {'Done':>8}")
print("  " + "-" * 58)

for b in range(NUM_BATCHES):
    random.shuffle(batch_scenarios)
    bt0 = time.monotonic()
    ok, err = run_batch(b, batch_scenarios)
    elapsed = max(time.monotonic() - bt0, 0.001)
    rps  = BATCH_SIZE / elapsed
    done = (b + 1) * BATCH_SIZE
    rl   = total_stats.get(f"http_429", 0)  # cumulative

    print(f"  {b+1:>5}  {BATCH_SIZE:>6,}  {ok:>6,}  {err:>5,}  {rl:>5,}  {rps:>6.1f}  {done:>8,}")
    sys.stdout.flush()

    if b < NUM_BATCHES - 1:
        if (b + 1) % 20 == 0 and not health_ok():
            print(f"\n  ✗ Gateway DOWN after batch {b+1}. Waiting 15s...")
            time.sleep(15)
            if not health_ok():
                print("  ✗ Still down. Stopping."); break
        time.sleep(COOLDOWN)

total_elapsed = time.monotonic() - grand_start
total_sent    = NUM_BATCHES * BATCH_SIZE

# ── Pipeline drain ────────────────────────────────────────────────────────────

wait_for_drain(timeout_sec=600)

# Brief pause so in-flight DB writes (Cassandra/H2) flush before reading metrics
time.sleep(8)

# ── Final report ──────────────────────────────────────────────────────────────

accepted    = total_stats["accepted"]
accept_rate = accepted / total_sent if total_sent else 0
err_rate    = (total_stats["conn_error"] + total_stats["server_error"]) / total_sent if total_sent else 0

print("\n" + "=" * 68)
print("  FINAL RESULTS")
print("=" * 68)
print(f"  Total sent        : {total_sent:,}")
print(f"  Total time        : {total_elapsed/60:.1f} min  ({total_sent/total_elapsed:.1f} req/s avg)")
print()
print(f"  ✓  Accepted  (202): {accepted:,}  ({accept_rate*100:.1f}%)")
print(f"  ⟳  Duplicate (409): {total_stats['duplicate_hit']:,}")
print(f"  ⧗  RateLimit (429): {total_stats['rate_limited']:,}")
print(f"  ✗  Server err(5xx): {total_stats['server_error']:,}")
print(f"  ✗  Conn errors    : {total_stats['conn_error']:,}")
print()
print("  Latency (p50 / p95 / p99 / max):")
print(f"    {pct(50):.0f}ms / {pct(95):.0f}ms / {pct(99):.0f}ms / {max(all_latencies, default=0):.0f}ms")

# ── Stage funnel from actuator metrics ───────────────────────────────────────

print()
print("  Pipeline stage funnel:")
fraud_scored = get_metric(SVC_PORTS["fraud"],      "clearflow_fraud_scored_total")
validated    = get_metric(SVC_PORTS["validation"], "clearflow_validation_accepted_total")
rejected     = get_metric(SVC_PORTS["validation"], "clearflow_validation_rejected_total")
aml_clear    = get_metric(SVC_PORTS["aml"],        "clearflow_aml_clear_total")
aml_hit      = get_metric(SVC_PORTS["aml"],        "clearflow_aml_hit_total")
routed       = get_metric(SVC_PORTS["routing"],    "clearflow_routing_routed_total")
routing_fail = get_metric(SVC_PORTS["routing"],    "clearflow_routing_failed_total")
settled      = get_metric(SVC_PORTS["settlement"], "clearflow_settlements_total")
audit_fail   = get_metric(SVC_PORTS["audit"],      "clearflow_audit_save_failures_total")

def fmt(v):
    return f"{v:,}" if v is not None else "n/a"

print(f"    Submitted         : {accepted:,}")
print(f"    Fraud scored      : {fmt(fraud_scored)}")
print(f"    Validated (pass)  : {fmt(validated)}")
print(f"    Validated (reject): {fmt(rejected)}")
print(f"    AML clear         : {fmt(aml_clear)}")
print(f"    AML hit           : {fmt(aml_hit)}")
print(f"    Routed            : {fmt(routed)}")
print(f"    Routing failed    : {fmt(routing_fail)}")
print(f"    Settled           : {fmt(settled)}")
print(f"    Audit save errors : {fmt(audit_fail)}")

# ── Scenario breakdown ────────────────────────────────────────────────────────

print()
print("  Scenario breakdown:")
for sc in ["happy", "high_value", "aml", "fraud", "duplicate", "ctr"]:
    print(f"    {sc:<14} {total_stats[f'sc_{sc}']:>7,}")

# ── SLA gates ─────────────────────────────────────────────────────────────────

print()
print("  SLA gates:")
print(f"    p99 < 500ms  : {'PASS ✓' if pct(99) < 500  else 'FAIL ✗'}  ({pct(99):.0f}ms)")
print(f"    p95 < 200ms  : {'PASS ✓' if pct(95) < 200  else 'FAIL ✗'}  ({pct(95):.0f}ms)")
print(f"    accept >= 95%: {'PASS ✓' if accept_rate >= .95 else 'FAIL ✗'}  ({accept_rate*100:.1f}%)")
print(f"    error  < 1%  : {'PASS ✓' if err_rate < .01  else 'FAIL ✗'}  ({err_rate*100:.2f}%)")
print("=" * 68)
