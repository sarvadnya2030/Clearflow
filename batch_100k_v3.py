#!/usr/bin/env python3
"""
ClearFlow REALISTIC 100K - v3
Failures at the CORRECT pipeline stages with all bugs fixed:

  GATEWAY (sync 4xx):
    - Duplicate replay (same instructionId+amount+IBAN) → 409
    - Rate limit bursts                                 → 429

  FRAUD-SCORING (async CRITICAL/HIGH):
    - Amount >$1M + high-risk creditor country (RU/VE/AF/IQ)
      → riskBand=HIGH then CRITICAL (velocity adds ≥0.25 after warm-up)

  AML-COMPLIANCE (async block):
    - SDN-name debtor with valid IBAN → AML_SANCTIONS_HIT

  SETTLEMENT (async):
    - Clean payments → SETTLEMENT_COMPLETE

  AUDIT (all events):
    - AUDIT_CHAIN_APPENDED for every stage event

Fix summary vs v2:
  1. Duplicates: store full (instructionId, amount, debtorIban) and replay verbatim
  2. Fraud HIGH/CRITICAL: creditor country set to RU/VE/AF/IQ (risk 8-9) with valid supported IBANs

Mix per 500-batch:
  350 clean · 50 aml_name · 50 large_amount · 30 duplicate · 20 ctr
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

# ── Clean low-risk entities ──────────────────────────────────────────────────
CLEAN = [
    {"name": "Alpine Logistics GmbH",  "iban": "DE89370400440532013000",     "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "ING Bank NV",            "iban": "NL91ABNA0417164300",         "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "HSBC Holdings PLC",      "iban": "GB29NWBK60161331926819",     "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "Euro Trade SARL",        "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR"},
    {"name": "Banco Santander SA",     "iban": "ES9121000418450200051332",    "bic": "BSCHESMMXXX", "country": "ES"},
    {"name": "Raiffeisen Bank Intl",   "iban": "AT611904300234573201",        "bic": "RZOOAT2LXXX", "country": "AT"},
]

# SDN-name debtors — valid IBANs, names match SDN list (caught by AML fuzzy matching)
SDN_NAMES = [
    {"name": "Al Qaida Network",        "iban": "DE89370400440532013000", "bic": "DEUTDEDBXXX", "country": "DE"},
    {"name": "Hamas",                   "iban": "NL91ABNA0417164300",     "bic": "INGBNL2AXXX", "country": "NL"},
    {"name": "Hezbollah",               "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "GB"},
    {"name": "Al-Shabaab Militants",    "iban": "FR7630006000011234567890189","bic":"BNPAFRPPXXX","country":"FR"},
    {"name": "Boko Haram Group",        "iban": "ES9121000418450200051332","bic":"BSCHESMMXXX","country":"ES"},
    {"name": "Islamic State of Iraq",   "iban": "AT611904300234573201",   "bic": "RZOOAT2LXXX", "country": "AT"},
]

# HIGH-RISK creditors — valid IBANs (pass IBAN validation) but country=RU/VE/AF
# This is realistic: Russian/Venezuelan entity with a European correspondent bank account
# Fraud scoring uses the `country` field (risk 8-9), not the IBAN prefix
HIGH_RISK_CREDITORS = [
    {"name": "Vnesheconombank",        "iban": "NL91ABNA0417164300",     "bic": "INGBNL2AXXX", "country": "RU"},  # Russia risk=9
    {"name": "Gazprombank JSC",        "iban": "DE89370400440532013000", "bic": "DEUTDEDBXXX", "country": "RU"},  # Russia risk=9
    {"name": "Banco de Venezuela",     "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "VE"},  # Venezuela risk=8
    {"name": "Da Afghanistan Bank",    "iban": "FR7630006000011234567890189","bic":"BNPAFRPPXXX","country":"AF"},  # Afghanistan risk=8
    {"name": "Trade Bank of Iraq",     "iban": "ES9121000418450200051332","bic":"BSCHESMMXXX","country":"IQ"},    # Iraq risk=8
    {"name": "Central Bank of Libya",  "iban": "AT611904300234573201",   "bic": "RZOOAT2LXXX", "country": "LY"},  # Libya risk=8
]

CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK"]
CHANNELS   = ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS"]

SCENARIO_POOL = (
    ["clean"]        * 350 +
    ["aml_name"]     * 50  +
    ["large_amount"] * 50  +
    ["duplicate"]    * 30  +
    ["ctr"]          * 20
)

lock          = threading.Lock()
stats         = defaultdict(int)
latencies     = []
# Store (instructionId, amount, debtorIban) tuples for exact duplicate replay
seen_payloads = []

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
        d   = random.choice(SDN_NAMES)
        amt = round(random.uniform(5_000, 80_000), 2)
        iid = str(uuid.uuid4())

    elif scenario == "large_amount":
        # High-risk creditor country triggers fraud HIGH/CRITICAL
        # Amount >$500K: +0.2, >$1M: +0.1 more = +0.3 total
        # Creditor RU/VE (risk 8-9): +0.3
        # Velocity (warm after first few batches): +0.15 to +0.25
        # Combined: 0.3 + 0.3 + 0.15 = 0.75 → HIGH; +velocity = 0.85+ → CRITICAL
        c   = random.choice(HIGH_RISK_CREDITORS)
        amt = round(random.uniform(900_000, 2_500_000), 2)
        iid = str(uuid.uuid4())

    elif scenario == "duplicate":
        # Replay exact same (instructionId + amount + debtorIban) → 409
        with lock:
            if seen_payloads:
                payload_tuple = random.choice(seen_payloads)
                iid = payload_tuple["instructionId"]
                amt = payload_tuple["amount"]
                d   = next((x for x in CLEAN if x["iban"] == payload_tuple["debtorIban"]), d)
            else:
                # No payloads seen yet; fall back to clean
                iid = str(uuid.uuid4())
                amt = round(random.uniform(500, 300_000), 2)

    elif scenario == "ctr":
        amt = round(random.uniform(9_750, 9_999), 2)
        iid = str(uuid.uuid4())

    else:  # clean
        amt = round(random.uniform(500, 300_000), 2)
        iid = str(uuid.uuid4())

    if scenario != "duplicate":
        pass  # iid already set above per scenario

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
        ms  = (time.monotonic() - t0) * 1000
        code = r.status_code
        with lock:
            latencies.append(ms)
            stats["sent"] += 1
            stats[f"sc_{scenario}"] += 1
            if code == 202:
                stats["accepted_202"] += 1
                # Store for future duplicate replay (cap at 500 unique payloads)
                if scenario != "duplicate" and len(seen_payloads) < 500:
                    seen_payloads.append({
                        "instructionId": payload["instructionId"],
                        "amount":        payload["amount"],
                        "debtorIban":    payload["debtor"]["iban"],
                    })
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
print("  ClearFlow REALISTIC 100K — v3")
print("  AML names → SDN hit | High-risk creditor → Fraud CRITICAL")
print("  Exact duplicate replay → 409 | Clean → Settlement")
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
for sc in ["clean","aml_name","large_amount","duplicate","ctr"]:
    n = stats.get(f"sc_{sc}", 0)
    print(f"    {sc:<15}: {n:>8,}")
print()
print("  Latency:")
print(f"    p50={pctile(50)}ms  p95={pctile(95)}ms  p99={pctile(99)}ms")
print(f"  Throughput: {round(sent/elapsed,1)} tx/s  ({round(elapsed,1)}s total)")
print()
print("  Downstream failures (async — check logs):")
print("    aml-compliance.log  → AML_SANCTIONS_HIT count")
print("    fraud-scoring.log   → riskBand=HIGH / riskBand=CRITICAL count")
print("    settlement.log      → SETTLEMENT_COMPLETE count")
print("    audit.log           → AUDIT_CHAIN_APPENDED count")
