#!/usr/bin/env python3
"""
ClearFlow REALISTIC 100K - v2
Failures at the RIGHT pipeline stages:

  GATEWAY (4xx):
    - Duplicate instructionId  → 409 Conflict
    - Rate limit bursts        → 429 Too Many Requests

  VALIDATION-ENRICHMENT (downstream block):
    - Embargo country IBANs    → rejected EMBARGO_HIT

  AML-COMPLIANCE (downstream block):
    - SDN-name debtor          → AML_SANCTIONS_HIT (HAMAS, AL QAIDA, etc.)
    - Name fuzzy-match ≥0.92   → FUZZY_MATCH_HIT

  FRAUD-SCORING (downstream CRITICAL):
    - Amount >$1M + velocity   → riskBand=CRITICAL → PAYMENT_BLOCKED

  SETTLEMENT (downstream):
    - Clean + AML-clear        → SETTLEMENT_COMPLETE

  AUDIT (all events):
    - AUDIT_CHAIN_APPENDED for every stage event

Mix per 500-batch:
  350 clean · 50 aml_name · 40 large_amount · 30 duplicate · 20 ctr · 10 burst
"""
import json, random, sys, time, uuid, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

try: import requests
except ImportError: print("pip install requests"); sys.exit(1)

GATEWAY     = "http://localhost:8080"
BATCH_SIZE  = 500
NUM_BATCHES = 200
WORKERS     = 10
COOLDOWN    = 0.3

# ── Valid entities with REAL IBAN checksums ──────────────────────────────────
CLEAN = [
    {"name": "Alpine Logistics GmbH",  "iban": "DE89370400440532013000",     "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "ING Bank NV",            "iban": "NL91ABNA0417164300",         "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "HSBC Holdings PLC",      "iban": "GB29NWBK60161331926819",     "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "Euro Trade SARL",        "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "Banco Santander SA",     "iban": "ES9121000418450200051332",    "bic": "BSCHESMMXXX", "country": "ES"},
    {"name": "Raiffeisen Bank Intl",   "iban": "AT611904300234573201",        "bic": "RZOOAT2LXXX", "country": "AT"},
]

# SDN-name debtors — valid IBANs but NAMES match SDN list (fuzzy ≥0.92)
# AML catches these by name screening, NOT by IBAN
SDN_NAMES = [
    {"name": "Al Qaida Network",        "iban": "DE89370400440532013000",     "bic": "DEUTDEDBXXX", "country": "DE"},  # → "AL QAIDA NETWORK" fuzzy hit
    {"name": "Hamas",                   "iban": "NL91ABNA0417164300",         "bic": "INGBNL2AXXX", "country": "NL"},  # → exact match SDN
    {"name": "Hezbollah",               "iban": "GB29NWBK60161331926819",     "bic": "HBUKGB4BXXX", "country": "GB"},  # → exact match SDN
    {"name": "Al-Shabaab",              "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR"},  # → fuzzy "AL-SHABAAB"
    {"name": "Islamic State of Iraq",   "iban": "ES9121000418450200051332",    "bic": "BSCHESMMXXX", "country": "ES"},  # → fuzzy ISIS/ISIL
    {"name": "Boko Haram",              "iban": "AT611904300234573201",        "bic": "RZOOAT2LXXX", "country": "AT"},  # → exact match SDN
]

CHANNELS   = ["SWIFT", "SEPA", "FASTER_PAYMENTS"]
CURRENCIES = ["EUR", "EUR", "EUR", "USD", "GBP"]

SCENARIO_POOL = (
    ["clean"]        * 350 +
    ["aml_name"]     * 50  +
    ["large_amount"] * 40  +
    ["duplicate"]    * 30  +
    ["ctr"]          * 20  +
    ["burst"]        * 10
)

lock      = threading.Lock()
stats     = defaultdict(int)
latencies = []
seen_iids = []   # for duplicate replay

def get_token():
    try:
        r = requests.post(f"{GATEWAY}/auth/token",
            json={"clientId":"clearflow-demo","clientSecret":"demo-secret-2024","grantType":"client_credentials"},
            timeout=5)
        if r.status_code == 200: return r.json().get("access_token","")
    except: pass
    return ""

def build(scenario):
    d = random.choice(CLEAN)
    c = random.choice([x for x in CLEAN if x != d])

    if scenario == "aml_name":
        d = random.choice(SDN_NAMES)          # valid IBAN, SDN name → AML HIT
        amt = round(random.uniform(5_000, 80_000), 2)
    elif scenario == "large_amount":
        amt = round(random.uniform(800_000, 2_000_000), 2)  # >$1M → HIGH/CRITICAL fraud
    elif scenario in ("ctr", "duplicate"):
        amt = round(random.uniform(9_750, 9_999), 2)        # just-under-10K structuring
    elif scenario == "burst":
        amt = round(random.uniform(50_000, 200_000), 2)
    else:
        amt = round(random.uniform(500, 300_000), 2)

    iid = random.choice(seen_iids) if (scenario == "duplicate" and seen_iids) else str(uuid.uuid4())

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
    }

def send(token, scenario):
    payload = build(scenario)
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
            stats[f"sc_{scenario}"] += 1
            if code == 202:
                stats["accepted_202"] += 1
                iid = payload["instructionId"]
                if len(seen_iids) < 1000: seen_iids.append(iid)
            elif code == 409: stats["duplicate_409"] += 1
            elif code == 429: stats["rate_limited_429"] += 1
            elif 400 <= code < 500: stats["rejected_4xx"] += 1
            elif code >= 500: stats["error_5xx"] += 1
        return code
    except requests.exceptions.ConnectionError:
        with lock: stats["conn_error"] += 1; stats["sent"] += 1; return 0
    except Exception:
        with lock: stats["exception"] += 1; stats["sent"] += 1; return -1

def pctile(p):
    if not latencies: return 0
    s = sorted(latencies)
    return round(s[min(int(len(s)*p/100), len(s)-1)])

# ── MAIN ──────────────────────────────────────────────────────────────────────
print("=" * 65)
print("  ClearFlow REALISTIC 100K — v2 (Failures at Correct Stages)")
print("  AML names → SDN hit | Large amt → Fraud CRITICAL")
print("  Duplicates → 409 | Clean → Settlement complete")
print("=" * 65)

token = get_token()
if not token: print("  WARNING: No auth token, proceeding unauthenticated")

print(f"\n{'Batch':>6} | {'Accept%':>8} | {'Dup409':>7} | {'4xx':>6} | {'Sent':>8}")
print("-" * 50)

start = time.time()
for batch in range(1, NUM_BATCHES + 1):
    scenarios = random.sample(SCENARIO_POOL, BATCH_SIZE)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(send, token, sc) for sc in scenarios]
        for f in as_completed(futs): f.result()

    sent     = stats["sent"]
    accepted = stats["accepted_202"]
    dups     = stats["duplicate_409"]
    rej4xx   = stats["rejected_4xx"]
    rate     = round(accepted / sent * 100, 1) if sent else 0

    if batch % 20 == 0 or batch <= 3:
        print(f"  {batch:4d}   | {rate:>7}% | {dups:>7} | {rej4xx:>6} | {sent:>8}")
        sys.stdout.flush()

    if batch < NUM_BATCHES: time.sleep(COOLDOWN)

elapsed = time.time() - start
sent = stats["sent"]; acc = stats["accepted_202"]

print()
print("=" * 65)
print("  FINAL RESULTS — 100,000 Payments")
print("=" * 65)
print(f"  Total Sent          : {sent:>8,}")
print(f"  Accepted 202        : {acc:>8,}  ({round(acc/sent*100,1)}%) ← gateway accept")
print(f"  Duplicate 409       : {stats['duplicate_409']:>8,}  (idempotency block)")
print(f"  Rejected 4xx        : {stats['rejected_4xx']:>8,}  (validation fail)")
print(f"  Server Error 5xx    : {stats['error_5xx']:>8,}")
print(f"  Conn Errors         : {stats['conn_error']:>8,}")
print()
print("  Scenario mix:")
for sc in ["clean","aml_name","large_amount","duplicate","ctr","burst"]:
    n = stats.get(f"sc_{sc}",0)
    print(f"    {sc:<15}: {n:>8,}")
print()
print("  Latency:")
print(f"    p50={pctile(50)}ms  p95={pctile(95)}ms  p99={pctile(99)}ms")
print(f"  Throughput: {round(sent/elapsed,1)} tx/s  ({round(elapsed,1)}s total)")
print()
print("  Downstream failures (async, check logs):")
print("    aml-compliance.log  → grep AML_SANCTIONS_HIT")
print("    fraud-scoring.log   → grep 'riskBand=HIGH\\|riskBand=CRITICAL'")
print("    settlement.log      → grep SETTLEMENT_COMPLETE")
print("    audit.log           → grep AUDIT_CHAIN_APPENDED")
