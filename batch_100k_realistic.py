#!/usr/bin/env python3
"""
ClearFlow REALISTIC 100K Payment Test
Real-world scenario mix with expected failures:
  ~72% happy path (accepted 202)
  ~10% AML sanctions hit (accepted then BLOCKED downstream)
   ~8% fraud CRITICAL risk (accepted then BLOCKED downstream)
   ~5% duplicate (409 conflict)
   ~3% high-value CTR triggers (accepted, compliance flag)
   ~2% invalid/unsupported params (400 reject at gateway)

200 batches × 500 payments = 100,000 total
10 concurrent workers per batch
"""
import json, random, sys, time, uuid, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

GATEWAY     = "http://localhost:8080"
BATCH_SIZE  = 500
NUM_BATCHES = 200
WORKERS     = 10
COOLDOWN    = 0.5  # seconds between batches

# Clean entities
CLEAN = [
    {"name": "Alpine Logistics GmbH",   "iban": "DE89370400440532013000",     "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "Euro Trade SARL",          "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "HSBC Holdings PLC",        "iban": "GB29NWBK60161331926819",     "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "ING Bank NV",              "iban": "NL91ABNA0417164300",         "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "Banco Santander SA",       "iban": "ES9121000418450200051332",    "bic": "BSCHESMMXXX", "country": "ES"},
    {"name": "Raiffeisen Bank Intl",     "iban": "AT611904300234573201",        "bic": "RZOOAT2LXXX", "country": "AT"},
    {"name": "BNP Paribas",              "iban": "FR7630004000031234567890143", "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "Deutsche Bank AG",         "iban": "DE27100777770209299700",      "bic": "DEUTDEFFXXX", "country": "DE"},
]

# SDN-listed entities — will trigger AML HIT
SANCTIONED = [
    {"name": "Al Qaida Network",         "iban": "DE89370400440532099001",     "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "Hamas Islamic Resistance", "iban": "NL91ABNA0417164399",         "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "Hezbollah Party",          "iban": "FR7630006000011234567890200", "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "Al Shabaab Movement",      "iban": "GB29NWBK60161331926900",     "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "Islamic State Iraq Syria", "iban": "ES9121000418450200051399",    "bic": "BSCHESMMXXX", "country": "ES"},
]

# High-risk names — fuzzy match triggers fraud scoring CRITICAL
HIGH_RISK = [
    {"name": "Rapid Cash Transfer LLC",  "iban": "DE27100777770209299701",     "bic": "DEUTDEFFXXX", "country": "DE"},
    {"name": "Anonymous Holdings Corp",  "iban": "NL91ABNA0417164398",         "bic": "INGBNL2AXXX", "country": "NL"},
]

CHANNELS   = ["SWIFT", "SEPA", "FASTER_PAYMENTS", "FEDWIRE", "INTERNAL"]
CURRENCIES = ["EUR", "USD", "GBP", "CHF", "EUR", "EUR"]  # EUR-weighted

# Scenario mix per 500-payment batch:
# 360 clean, 50 aml, 40 high-value, 25 fraud, 15 dup, 10 ctr
SCENARIO_POOL = (
    ["clean"]      * 360 +
    ["aml"]        * 50  +
    ["high_value"] * 40  +
    ["fraud"]      * 25  +
    ["duplicate"]  * 15  +
    ["ctr"]        * 10
)

lock       = threading.Lock()
stats      = defaultdict(int)
latencies  = []
seen_ids   = []   # for duplicate replay

def get_token():
    try:
        r = requests.post(f"{GATEWAY}/auth/token",
            json={"clientId":"clearflow-demo","clientSecret":"demo-secret-2024","grantType":"client_credentials"},
            timeout=5)
        if r.status_code == 200: return r.json().get("access_token","")
    except: pass
    return ""

def build_payload(scenario):
    d = random.choice(CLEAN)
    c = random.choice([x for x in CLEAN if x != d])

    if scenario == "aml":
        # Sanctioned entity as debtor — will be caught by fuzzy SDN screening
        d = random.choice(SANCTIONED)
        amt = round(random.uniform(5_000, 50_000), 2)
    elif scenario == "high_value":
        amt = round(random.uniform(500_000, 2_000_000), 2)
    elif scenario in ("fraud", "ctr"):
        # Just-under-10K to trigger structuring heuristic
        amt = round(random.uniform(9_750, 9_999), 2)
    elif scenario == "duplicate":
        amt = round(random.uniform(100, 50_000), 2)
    else:
        amt = round(random.uniform(500, 250_000), 2)

    iid = random.choice(seen_ids) if (scenario == "duplicate" and seen_ids) else str(uuid.uuid4())

    return {
        "instructionId":  iid,
        "endToEndId":     f"E2E-{uuid.uuid4().hex[:12].upper()}",
        "uetr":           str(uuid.uuid4()),
        "debtor":   {"name": d["name"], "iban": d["iban"], "bic": d["bic"], "country": d["country"]},
        "creditor": {"name": c["name"], "iban": c["iban"], "bic": c["bic"], "country": c["country"]},
        "amount":   amt,
        "currency": random.choice(CURRENCIES),
        "channel":  random.choice(CHANNELS),
        "remittanceInfo": f"INV-{random.randint(10000,99999)}",
    }, scenario

def send(token, scenario):
    payload, sc = build_payload(scenario)
    t0 = time.monotonic()
    try:
        r = requests.post(f"{GATEWAY}/api/v1/payments",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15)
        ms = (time.monotonic() - t0) * 1000
        code = r.status_code
        with lock:
            latencies.append(ms)
            stats["sent"] += 1
            stats[f"sc_{sc}"] += 1
            if code == 202:
                stats["accepted_202"] += 1
                iid = payload["instructionId"]
                if len(seen_ids) < 500: seen_ids.append(iid)
            elif code == 409:
                stats["duplicate_409"] += 1
            elif code == 429:
                stats["rate_limited_429"] += 1
            elif 400 <= code < 500:
                stats["rejected_4xx"] += 1
            elif code >= 500:
                stats["error_5xx"] += 1
        return code
    except requests.exceptions.ConnectionError:
        with lock: stats["conn_error"] += 1; stats["sent"] += 1
        return 0
    except Exception:
        with lock: stats["exception"] += 1; stats["sent"] += 1
        return -1

def pctile(p):
    if not latencies: return 0
    s = sorted(latencies)
    return round(s[min(int(len(s)*p/100), len(s)-1)])

# ── MAIN ──
print("=" * 60)
print("  ClearFlow REALISTIC 100K Payment Stress Test")
print("  Scenarios: clean/AML/fraud/high-value/duplicate/CTR")
print("  Expected: ~72% gateway-accept, real failures downstream")
print("=" * 60)
print()

token = get_token()
if not token:
    print("WARNING: Could not get auth token, proceeding unauthenticated")

print(f"{'Batch':>6} | {'Accept%':>8} | {'Dup':>5} | {'4xx':>5} | {'Sent':>7}")
print("-" * 45)

start = time.time()

for batch in range(1, NUM_BATCHES + 1):
    scenarios = random.sample(SCENARIO_POOL, BATCH_SIZE)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(send, token, sc) for sc in scenarios]
        for f in as_completed(futs): f.result()

    sent      = stats["sent"]
    accepted  = stats["accepted_202"]
    dups      = stats["duplicate_409"]
    rej4xx    = stats["rejected_4xx"]
    rate      = round(accepted / sent * 100, 1) if sent else 0

    if batch % 10 == 0 or batch <= 5:
        print(f"  {batch:4d}   | {rate:>7}% | {dups:>5} | {rej4xx:>5} | {sent:>7}")
        sys.stdout.flush()

    if batch < NUM_BATCHES: time.sleep(COOLDOWN)

elapsed = time.time() - start
sent    = stats["sent"]
acc     = stats["accepted_202"]

print()
print("=" * 60)
print("  FINAL RESULTS")
print("=" * 60)
print(f"  Total Sent     : {sent:,}")
print(f"  Accepted (202) : {acc:,}  ({round(acc/sent*100,1)}%)")
print(f"  Duplicate (409): {stats['duplicate_409']:,}")
print(f"  Rejected (4xx) : {stats['rejected_4xx']:,}")
print(f"  Server Err 5xx : {stats['error_5xx']:,}")
print(f"  Conn Errors    : {stats['conn_error']:,}")
print()
print("  Scenario breakdown:")
for sc in ["clean","aml","high_value","fraud","duplicate","ctr"]:
    n = stats.get(f"sc_{sc}", 0)
    print(f"    {sc:<12}: {n:,}")
print()
print("  Latency (gateway accept):")
print(f"    p50 = {pctile(50)}ms  p95 = {pctile(95)}ms  p99 = {pctile(99)}ms")
print(f"  Throughput: {round(sent/elapsed,1)} tx/s over {round(elapsed,1)}s")
print()
print("  Downstream (async pipeline) failures visible in logs:")
print("    aml-compliance.log  → AML_SANCTIONS_HIT")
print("    fraud-scoring.log   → FRAUD_SCORE_COMPUTED riskBand=CRITICAL")
print("    audit.log           → AUDIT_CHAIN_APPENDED for blocked payments")
