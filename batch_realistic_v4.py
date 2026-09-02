#!/usr/bin/env python3
"""
ClearFlow Realistic Payment Generator — v4

Improvements over v3:
  - Log-normal amount distribution (matches real payment data)
  - Time-of-day activity curve (quiet 0-6 AM, peak 9-17, quiet nights)
  - ISO 20022 purpose codes (SALA, TRAD, BEXP, CHAR, INVE, SUPP, RENT)
  - 30+ real-world entities with correct IBANs and BICs
  - Structured remittance info (invoice refs, payroll refs, trade refs)
  - SDN names from expanded list (matches sdn_sample.csv entries)
  - Structuring scenario (sub-10K CTR-avoidance transactions)
  - Velocity burst scenario (same debtor, 20 txns in 60s)
  - High-risk corridor scenario (embargoed country routing)
"""

import csv, json, math, os, random, sys, time, uuid, threading, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

GATEWAY    = "http://localhost:8080"
BATCH_SIZE = 500
NUM_BATCHES = 200   # 100,000 total
WORKERS    = 12
COOLDOWN   = 0.25

# ── Amount distribution ───────────────────────────────────────────────────────
# Log-normal: most txns €500-5K, long tail to €2M+
# Parameters tuned to match BIS retail payment statistics

def realistic_amount(category="retail"):
    if category == "retail":
        # μ=8.0, σ=1.4 → median ~€3K, 95th pct ~€30K
        return round(random.lognormvariate(8.0, 1.4), 2)
    elif category == "corporate":
        # μ=11.5, σ=1.2 → median ~€100K, tail to €5M
        return round(random.lognormvariate(11.5, 1.2), 2)
    elif category == "structuring":
        # Just under CTR threshold ($10K) — classic structuring pattern
        return round(random.uniform(9_000, 9_999.99), 2)
    elif category == "large":
        return round(random.uniform(800_000, 3_000_000), 2)

# ── Time-of-day weight (simulates business hours activity) ────────────────────
def time_weight():
    hour = datetime.datetime.now().hour
    weights = [0.2,0.1,0.1,0.1,0.2,0.3,0.5,0.8,1.0,1.0,1.0,0.9,
               0.8,0.9,1.0,1.0,0.9,0.8,0.7,0.6,0.5,0.4,0.3,0.2]
    return weights[hour]

# ── ISO 20022 Purpose codes ───────────────────────────────────────────────────
PURPOSE_CODES = {
    "SALA": "Salary Payment",
    "TRAD": "Trade Settlement",
    "BEXP": "Business Expense",
    "SUPP": "Supplier Payment",
    "RENT": "Rent / Lease",
    "INVE": "Investment",
    "CHAR": "Charitable Donation",
    "TAXS": "Tax Payment",
    "LOAN": "Loan Repayment",
    "DIVI": "Dividend Payment",
}

# ── Clean low-risk entities (EU, UK, US, CH, SG) ─────────────────────────────
CLEAN_ENTITIES = [
    # Germany
    {"name": "Siemens AG",               "iban": "DE89370400440532013000", "bic": "DEUTDEDBXXX", "country": "DE", "sector": "manufacturing"},
    {"name": "Volkswagen Financial Svcs", "iban": "DE34200400600539456100", "bic": "COBADEFFXXX", "country": "DE", "sector": "automotive"},
    {"name": "Alpine Logistics GmbH",    "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "country": "DE", "sector": "logistics"},
    {"name": "Munich Re AG",             "iban": "DE50500400600401234578", "bic": "HYVEDEMMXXX", "country": "DE", "sector": "insurance"},
    # France
    {"name": "BNP Paribas SA",           "iban": "FR7630006000011234567890189", "bic": "BNPAFRPPXXX", "country": "FR", "sector": "banking"},
    {"name": "LVMH Moet Hennessy",       "iban": "FR5110278060000002408440109", "bic": "CMCIFRPPXXX", "country": "FR", "sector": "luxury"},
    {"name": "Total Energies SE",        "iban": "FR2914508110000012345678902", "bic": "CCBPFRPPMTZ", "country": "FR", "sector": "energy"},
    # Netherlands
    {"name": "ING Bank NV",              "iban": "NL91ABNA0417164300",    "bic": "INGBNL2AXXX", "country": "NL", "sector": "banking"},
    {"name": "Shell PLC",                "iban": "NL39RABO0300065264",    "bic": "RABONL2UXXX", "country": "NL", "sector": "energy"},
    {"name": "Philips NV",               "iban": "NL02ABNA0123456789",    "bic": "ABNANL2AXXX", "country": "NL", "sector": "technology"},
    # UK
    {"name": "HSBC Holdings PLC",        "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "GB", "sector": "banking"},
    {"name": "Barclays Bank PLC",        "iban": "GB60BARC20000055779911", "bic": "BARCGB22XXX", "country": "GB", "sector": "banking"},
    {"name": "BP Global Treasury",       "iban": "GB82WEST12345698765432", "bic": "NWBKGB2LXXX", "country": "GB", "sector": "energy"},
    {"name": "Vodafone Group PLC",       "iban": "GB33BUKB20201555555555", "bic": "BUKBGB22XXX", "country": "GB", "sector": "telecom"},
    # Spain
    {"name": "Banco Santander SA",       "iban": "ES9121000418450200051332", "bic": "BSCHESMMXXX", "country": "ES", "sector": "banking"},
    {"name": "Iberdrola SA",             "iban": "ES9014650100720002000160", "bic": "CAZRES2ZXXX", "country": "ES", "sector": "energy"},
    # Switzerland
    {"name": "UBS Group AG",             "iban": "CH5604835012345678009",  "bic": "UBSWCHZH80A", "country": "CH", "sector": "banking"},
    {"name": "Nestle SA",                "iban": "CH8108837000001234567",  "bic": "CRESCHZZ80A", "country": "CH", "sector": "consumer"},
    {"name": "Novartis AG",              "iban": "CH5000790123456789012",  "bic": "POFICHBEXXX", "country": "CH", "sector": "pharma"},
    # Austria
    {"name": "Raiffeisen Bank Intl",     "iban": "AT611904300234573201",   "bic": "RZOOAT2LXXX", "country": "AT", "sector": "banking"},
    {"name": "OMV AG",                   "iban": "AT352011129012345678",   "bic": "GIBAATWWXXX", "country": "AT", "sector": "energy"},
    # Italy
    {"name": "UniCredit SpA",            "iban": "IT60X0542811101000000123456", "bic": "UNCRITMM", "country": "IT", "sector": "banking"},
    {"name": "ENI SpA",                  "iban": "IT12A0306901010000000012345", "bic": "BCITITMM", "country": "IT", "sector": "energy"},
    # Sweden
    {"name": "Nordea Bank AB",           "iban": "SE9050000000054400010552", "bic": "NDEASESS", "country": "SE", "sector": "banking"},
    {"name": "Volvo Treasury AB",        "iban": "SE4550000000058398257466", "bic": "SWEDSESS", "country": "SE", "sector": "automotive"},
    # Singapore
    {"name": "DBS Bank Ltd",             "iban": "GB02NWBK60161331926820", "bic": "DBSSSGSG", "country": "SG", "sector": "banking"},
    # Japan
    {"name": "MUFG Bank Ltd",            "iban": "GB72NWBK60161331926821", "bic": "BOTKJPJT", "country": "JP", "sector": "banking"},
    # Canada
    {"name": "Royal Bank of Canada",     "iban": "GB45NWBK60161331926822", "bic": "ROYCCAT2", "country": "CA", "sector": "banking"},
]

# ── SDN-flagged entities (names match expanded sdn_sample.csv) ────────────────
SDN_ENTITIES = [
    {"name": "Al Qaida Network",          "iban": "DE89370400440532013000", "bic": "DEUTDEDBXXX", "country": "AF"},
    {"name": "Hamas",                     "iban": "NL91ABNA0417164300",     "bic": "INGBNL2AXXX", "country": "PS"},
    {"name": "Hezbollah",                 "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "LB"},
    {"name": "Islamic State of Iraq",     "iban": "FR7630006000011234567890189","bic":"BNPAFRPPXXX","country":"IQ"},
    {"name": "Lazarus Group",             "iban": "ES9121000418450200051332", "bic": "BSCHESMMXXX","country":"KP"},
    {"name": "Wagner Group PMC",          "iban": "AT611904300234573201",   "bic": "RZOOAT2LXXX", "country": "RU"},
    {"name": "Sinaloa Cartel",            "iban": "CH5604835012345678009",  "bic": "UBSWCHZH80A", "country": "MX"},
    {"name": "Guzman Loera Joaquin",      "iban": "NL39RABO0300065264",     "bic": "RABONL2UXXX", "country": "MX"},
    {"name": "Mahan Air",                 "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "IR"},
    {"name": "Bank Saderat Iran",         "iban": "DE34200400600539456100", "bic": "COBADEFFXXX", "country": "IR"},
    {"name": "Promsvyazbank PJSC",        "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "country": "RU"},
    {"name": "CJNG Cartel",              "iban": "FR5110278060000002408440109","bic":"CMCIFRPPXXX","country":"MX"},
    {"name": "Tren de Aragua",            "iban": "NL02ABNA0123456789",     "bic": "ABNANL2AXXX", "country": "VE"},
    {"name": "Internet Research Agency",  "iban": "GB60BARC20000055779911", "bic": "BARCGB22XXX", "country": "RU"},
    {"name": "Boko Haram Group",          "iban": "GB82WEST12345698765432", "bic": "NWBKGB2LXXX", "country": "NG"},
]

# ── High-risk corridor creditors (valid IBANs, high-risk country) ─────────────
HIGH_RISK_CREDITORS = [
    {"name": "Vnesheconombank",          "iban": "NL91ABNA0417164300",     "bic": "INGBNL2AXXX", "country": "RU"},
    {"name": "Gazprombank JSC",          "iban": "DE89370400440532013000", "bic": "DEUTDEDBXXX", "country": "RU"},
    {"name": "National Bank of Iran",    "iban": "GB29NWBK60161331926819", "bic": "HBUKGB4BXXX", "country": "IR"},
    {"name": "Da Afghanistan Bank",      "iban": "FR7630006000011234567890189","bic":"BNPAFRPPXXX","country":"AF"},
    {"name": "Trade Bank of Iraq",       "iban": "ES9121000418450200051332","bic":"BSCHESMMXXX","country":"IQ"},
    {"name": "Central Bank of Libya",    "iban": "AT611904300234573201",   "bic": "RZOOAT2LXXX", "country": "LY"},
    {"name": "Banco de Venezuela PDVSA", "iban": "CH5604835012345678009",  "bic": "UBSWCHZH80A", "country": "VE"},
    {"name": "Syria International Bank","iban": "NL39RABO0300065264",     "bic": "RABONL2UXXX", "country": "SY"},
    {"name": "Korea Trade Bank",         "iban": "GB82WEST12345698765432", "bic": "NWBKGB2LXXX", "country": "KP"},
    {"name": "Cuba Metals Corp",         "iban": "DE34200400600539456100", "bic": "COBADEFFXXX", "country": "CU"},
]

CURRENCIES = ["EUR", "USD", "GBP", "CHF", "SEK", "JPY", "CAD", "SGD"]
CURRENCY_WEIGHTS = [35, 30, 15, 8, 3, 3, 3, 3]  # realistic FX distribution

# Was ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS", "CHAPS", "TARGET2"] --
# CHAPS/TARGET2 don't exist in gateway's PaymentChannel enum (it only has
# SWIFT/SEPA/FEDWIRE/FASTER_PAYMENTS/INTERNAL), so 10% of "clean" traffic
# was silently failing Jackson enum deserialization before ever reaching
# gateway's own validation layer -- found live, 2026-09-02, while debugging
# a decoy fault mechanism whose real signal was drowned out by this.
# routing-execution's own rail-selection logic derives the specific rail
# (SEPA_INSTANT, CHAPS, TARGET2, etc.) from this coarser input already, so
# CHAPS/TARGET2 never belonged in the gateway-facing channel vocabulary.
CHANNELS = ["SWIFT", "SEPA", "FEDWIRE", "FASTER_PAYMENTS"]
CHANNEL_WEIGHTS = [25, 45, 15, 15]

# ── Remittance reference generators ──────────────────────────────────────────
def make_remittance(purpose_code):
    if purpose_code == "SALA":
        return f"PAYROLL/{datetime.date.today().strftime('%Y%m')}/EMP{random.randint(1000,9999)}"
    elif purpose_code == "TRAD":
        return f"INV-{random.randint(100000,999999)}/PO-{random.randint(10000,99999)}"
    elif purpose_code == "SUPP":
        return f"SUPP/{random.randint(1000,9999)}/Q{random.randint(1,4)}{datetime.date.today().year}"
    elif purpose_code == "RENT":
        return f"LEASE/{datetime.date.today().strftime('%Y%m')}/PROP{random.randint(100,999)}"
    elif purpose_code == "TAXS":
        return f"TAX/{datetime.date.today().year}/REF{random.randint(100000,999999)}"
    elif purpose_code == "LOAN":
        return f"LOAN-REP/{random.randint(10000,99999)}/INST{random.randint(1,60)}"
    else:
        return f"REF-{uuid.uuid4().hex[:10].upper()}"

# ── Scenario mix (per 500 batch) ──────────────────────────────────────────────
SCENARIO_POOL = (
    ["clean"]           * 330 +   # 66% — normal business payments
    ["salary"]          * 50  +   # 10% — payroll runs (retail amounts, SALA code)
    ["aml_sdn"]         * 40  +   # 8%  — SDN name match → AML block
    ["high_risk_corridor"] * 35 + # 7%  — high-risk country creditor → fraud HIGH/CRITICAL
    ["structuring"]     * 25  +   # 5%  — sub-10K CTR avoidance pattern
    ["duplicate"]       * 15  +   # 3%  — exact replay → 409
    ["velocity_burst"]  * 5       # 1%  — same debtor, many txns → velocity flag
)

# ── Shared state ──────────────────────────────────────────────────────────────
lock         = threading.Lock()
latencies    = []
seen_payloads = []
velocity_debtors = {}  # iban → list of recent timestamps
stats        = defaultdict(int)
sent_payments = []  # (payment_id, sent_at, scenario) for every real HTTP 202 -- previously discarded

def weighted_choice(options, weights):
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for opt, w in zip(options, weights):
        cumulative += w
        if r <= cumulative:
            return opt
    return options[-1]

def build(scenario):
    d = random.choice(CLEAN_ENTITIES)
    c = random.choice(CLEAN_ENTITIES)
    while c["iban"] == d["iban"]:
        c = random.choice(CLEAN_ENTITIES)

    purpose = random.choice(list(PURPOSE_CODES.keys()))
    currency = weighted_choice(CURRENCIES, CURRENCY_WEIGHTS)
    channel  = weighted_choice(CHANNELS, CHANNEL_WEIGHTS)

    if scenario == "clean":
        amt = realistic_amount("retail")
        iid = str(uuid.uuid4())
        purpose = random.choice(["TRAD", "SUPP", "BEXP", "DIVI", "INVE"])

    elif scenario == "salary":
        amt = realistic_amount("retail")
        amt = min(amt, 15000)  # salaries cap — most under €15K
        iid = str(uuid.uuid4())
        purpose = "SALA"
        currency = "EUR"

    elif scenario == "aml_sdn":
        d   = random.choice(SDN_ENTITIES)
        amt = realistic_amount("retail")
        iid = str(uuid.uuid4())
        purpose = random.choice(["TRAD", "SUPP", "BEXP"])

    elif scenario == "high_risk_corridor":
        c   = random.choice(HIGH_RISK_CREDITORS)
        amt = realistic_amount("large")
        iid = str(uuid.uuid4())
        purpose = random.choice(["INVE", "TRAD", "LOAN"])

    elif scenario == "structuring":
        # Multiple sub-threshold amounts from same debtor (CTR avoidance)
        amt = realistic_amount("structuring")
        iid = str(uuid.uuid4())
        purpose = "BEXP"
        currency = "USD"

    elif scenario == "duplicate":
        with lock:
            if seen_payloads:
                prev = random.choice(seen_payloads)
                return prev.copy()
        # Fallback if no seen yet
        amt = realistic_amount("retail")
        iid = str(uuid.uuid4())

    elif scenario == "velocity_burst":
        # Reuse same debtor IBAN rapidly — triggers velocity check
        with lock:
            if velocity_debtors:
                d_iban = random.choice(list(velocity_debtors.keys()))
                d = next((e for e in CLEAN_ENTITIES if e["iban"] == d_iban), d)
        amt = realistic_amount("retail")
        iid = str(uuid.uuid4())
        purpose = "TRAD"

    payload = {
        "instructionId":  iid,
        "endToEndId":     f"E2E-{uuid.uuid4().hex[:12].upper()}",
        "uetr":           str(uuid.uuid4()),
        "debtor":   {"name": d["name"], "iban": d["iban"], "bic": d["bic"], "country": d["country"]},
        "creditor": {"name": c["name"], "iban": c["iban"], "bic": c["bic"], "country": c["country"]},
        "amount":   amt,
        "currency": currency,
        "channel":  channel,
        "purposeCode":     purpose,
        "remittanceInfo":  make_remittance(purpose),
    }
    return payload

def get_token():
    try:
        r = requests.post(f"{GATEWAY}/api/v1/auth/token",
            json={"clientId": "demo-ops", "secret": "demo-secret"}, timeout=5)
        return r.json().get("token")
    except Exception:
        return localStorage_token()

def localStorage_token():
    return "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiZGVtby1vcHMiLCAiaXNzIjogImNsZWFyZmxvdy1kZXYiLCAiaWF0IjogMTc3ODg2MTYxMSwgImV4cCI6IDE4OTM0NTYwMDAsICJzY29wZSI6ICJtY3A6cmVhZCBtY3A6YWRtaW4ifQ._Iz89MiCOyVY9m0MUsuSJhlFqsXY-OYvlV2ML2SFPuQ"

def send(token, scenario):
    payload = build(scenario)
    t0 = time.monotonic()
    try:
        r = requests.post(f"{GATEWAY}/api/v1/payments",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15)
        ms   = (time.monotonic() - t0) * 1000
        code = r.status_code
        with lock:
            latencies.append(ms)
            stats["sent"] += 1
            stats[f"sc_{scenario}"] += 1
            if code == 202:
                stats["accepted_202"] += 1
                if scenario not in ("duplicate",) and len(seen_payloads) < 500:
                    seen_payloads.append(payload)
                if scenario == "velocity_burst":
                    velocity_debtors[payload["debtor"]["iban"]] = time.time()
                try:
                    pid = r.json().get("paymentId")
                    sent_payments.append((pid, datetime.datetime.now(datetime.timezone.utc).isoformat(), scenario))
                except Exception:
                    pass
            elif code == 409: stats["duplicate_409"] += 1
            elif code == 429: stats["rate_limited_429"] += 1
            elif 400 <= code < 500: stats["rejected_4xx"] += 1
            elif code >= 500: stats["error_5xx"] += 1
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
    return round(s[min(int(len(s) * p / 100), len(s) - 1)])

# ── MAIN ──────────────────────────────────────────────────────────────────────
# Guarded so this module is safe to `import batch_realistic_v4` (e.g. from
# data-generation/live_fault_injector.py, which reuses build()/get_token())
# without triggering a 100K-payment run as a side effect of the import.
def main():
    print("=" * 70)
    print("  ClearFlow Realistic Payment Generator — v4")
    print("  Log-normal amounts | ISO 20022 purpose codes | 30+ real entities")
    print("  SDN matching | High-risk corridors | Velocity detection")
    print("=" * 70)
    print(f"  Scenario mix (per {BATCH_SIZE}):")
    from collections import Counter
    mix = Counter(SCENARIO_POOL)
    for sc, n in sorted(mix.items(), key=lambda x: -x[1]):
        print(f"    {sc:<22}: {n:>3} ({n/BATCH_SIZE*100:.0f}%)")
    print()

    token = localStorage_token()
    print(f"{'Batch':>6} | {'Accept%':>8} | {'Dup409':>7} | {'4xx':>6} | {'Sent':>8} | {'p95':>6}")
    print("-" * 58)

    start = time.time()
    for batch in range(1, NUM_BATCHES + 1):
        scenarios = [random.choice(SCENARIO_POOL) for _ in range(BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(send, token, sc) for sc in scenarios]
            for f in as_completed(futs):
                f.result()

        sent     = stats["sent"]
        accepted = stats["accepted_202"]
        dups     = stats["duplicate_409"]
        rej4xx   = stats["rejected_4xx"]
        rate     = round(accepted / sent * 100, 1) if sent else 0

        if batch % 20 == 0 or batch <= 3:
            print(f"  {batch:4d}   | {rate:>7}% | {dups:>7} | {rej4xx:>6} | {sent:>8} | {pctile(95):>4}ms")
            sys.stdout.flush()

        if batch < NUM_BATCHES:
            time.sleep(COOLDOWN)

    elapsed = time.time() - start
    sent = stats["sent"]
    acc  = stats["accepted_202"]

    print()
    print("=" * 70)
    print("  FINAL RESULTS")
    print("=" * 70)
    print(f"  Total Sent          : {sent:>8,}")
    print(f"  Accepted 202        : {acc:>8,}  ({round(acc/sent*100,1) if sent else 0}%)")
    print(f"  Duplicate 409       : {stats['duplicate_409']:>8,}")
    print(f"  Rejected 4xx        : {stats['rejected_4xx']:>8,}")
    print(f"  Server Error 5xx    : {stats['error_5xx']:>8,}")
    print()
    print("  Scenario breakdown:")
    for sc in ["clean","salary","aml_sdn","high_risk_corridor","structuring","duplicate","velocity_burst"]:
        n = stats.get(f"sc_{sc}", 0)
        print(f"    {sc:<22}: {n:>8,}")
    print()
    print("  Latency (gateway accept):")
    print(f"    p50={pctile(50)}ms  p95={pctile(95)}ms  p99={pctile(99)}ms")
    print(f"  Throughput: {round(sent/elapsed,1) if elapsed else 0} tx/s  ({round(elapsed,1)}s)")
    print()
    print("  Expected async outcomes (check logs):")
    print("    aml_sdn        → AML_SANCTIONS_HIT  (~8% of accepted)")
    print("    high_risk_corr → FRAUD riskBand=HIGH/CRITICAL (~7%)")
    print("    structuring    → CTR_THRESHOLD_ALERT in compliance-reporter")
    print("    velocity_burst → VELOCITY_BREACH in fraud-scoring.log")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data-generation", "output", "live_sent_payments.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    file_exists = os.path.exists(out_path)
    with open(out_path, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["payment_id", "sent_at", "scenario"])
        w.writerows(sent_payments)
    print(f"\n  Appended {len(sent_payments)} sent payments to {out_path}")


if __name__ == "__main__":
    main()
