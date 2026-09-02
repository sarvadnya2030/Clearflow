#!/usr/bin/env python3
"""
PaySim-style ISO 20022 Transaction Generator
=============================================
Generates 100,000+ realistic financial transactions and sends them to the
ClearFlow gateway API.  Distributions modelled on the real PaySim dataset
and fraud-detection-on-paysim-dataset notebook.

Usage:
    python generate_paysim_iso.py            # send to gateway
    python generate_paysim_iso.py --dry-run  # generate & print stats only
"""

import asyncio
import aiohttp
import uuid
import random
import time
import sys
import math
from datetime import datetime, date, timedelta

random.seed(42)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_URL        = "http://localhost:8080/api/v1/payments"
TOTAL_REQUESTS = 1_00_000        # 100 k+ target
CONCURRENCY    = 300

# PaySim-like type weights (from 6.3 M-row dataset)
TYPE_WEIGHTS = {
    "PAYMENT":  0.34,
    "CASH_OUT": 0.35,
    "CASH_IN":  0.22,
    "TRANSFER": 0.08,
    "DEBIT":    0.01,
}
TYPE_CHOICES = list(TYPE_WEIGHTS.keys())
TYPE_PROBS   = [TYPE_WEIGHTS[t] for t in TYPE_CHOICES]

# Fraud budget: ~5 % overall for demo visibility (real PaySim ≈ 0.13 %)
FRAUD_RATE       = 0.05
AML_RATE         = 0.02
EMBARGO_RATE     = 0.02

# High-risk entities
SANCTIONED_NAMES   = [
    "GAZPROMBANK", "AL RAHMAN TARIQ", "OSAMA BIN LADEN",
    "KIM JONG UN", "HUSSAIN AL-QAEDA", "PYONGYANG TRADING CO",
]
EMBARGO_COUNTRIES  = ["KP", "IR", "CU", "SY", "SD", "RU"]
NORMAL_COUNTRIES   = [
    "US", "GB", "DE", "FR", "NL", "CH", "JP", "AU", "CA", "SG",
    "IE", "BE", "AT", "DK", "SE", "NO", "FI", "IT", "ES", "PT",
]
CHANNELS   = ["WEB", "MOBILE", "API", "BRANCH"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SEK", "NZD"]
PURPOSES   = ["SUPP", "INTC", "SALA", "PENS", "TAXS", "TREA", "CORT", "GDDS"]

# 6 fraud-pattern labels
FRAUD_PATTERNS = [
    "ACCOUNT_TAKEOVER", "VELOCITY_BURST", "ROUND_TRIP",
    "MULE_NETWORK", "IMPOSSIBLE_GEOGRAPHY", "EMBARGOED_TRANSIT",
]

# ---------------------------------------------------------------------------
# PRE-CACHED pools (avoid per-call faker overhead — 100× faster)
# ---------------------------------------------------------------------------
POOL_SIZE = 5000
print("⏳ Pre-generating data pools …", end=" ", flush=True)
_t0 = time.time()

# Company names
_COMPANY_POOL = [
    f"{random.choice(['Global','Apex','Nordic','Pacific','Atlantic','Euro','Trans','Quantum','Stellar','Nova','Prime','Core','Nexus','Titan','Vertex'])} "
    f"{random.choice(['Trading','Finance','Capital','Holdings','Systems','Solutions','Partners','Industries','Group','Logistics','Energy','Tech','Media','Ventures','Dynamics'])} "
    f"{random.choice(['Ltd','GmbH','Inc','Corp','SA','AG','BV','Pty','LLC','PLC','Co','AB','AS','SRL','SpA'])}"
    for _ in range(POOL_SIZE)
]

# Cities
_CITY_POOL = [
    "London", "Berlin", "Paris", "Amsterdam", "Zurich", "Frankfurt",
    "Tokyo", "Sydney", "Toronto", "Singapore", "Dublin", "Brussels",
    "Vienna", "Copenhagen", "Stockholm", "Oslo", "Helsinki", "Milan",
    "Madrid", "Lisbon", "New York", "Chicago", "San Francisco",
    "Munich", "Hamburg", "Barcelona", "Rome", "Prague", "Warsaw",
    "Budapest", "Taipei", "Seoul", "Shanghai", "Hong Kong", "Dubai",
    "Mumbai", "São Paulo", "Mexico City", "Johannesburg", "Lagos",
]

# BIC codes
_BIC_POOL = [
    f"{random.choice(['DEUT','BNPA','HSBC','BARCL','CITI','JPMO','GLDS','UBSW','CRED','SOCI','RABOB','INGB','ABNAAM','RABO','SCBL'])}"
    f"{random.choice(NORMAL_COUNTRIES[:10])}"
    f"{random.choice(['XX','PP','MM','LL','2X','3X'])}"
    for _ in range(POOL_SIZE)
]

# IBANs  (simplified but realistic format)
def _gen_iban():
    cc = random.choice(NORMAL_COUNTRIES[:10])
    digits = ''.join([str(random.randint(0, 9)) for _ in range(20)])
    return f"{cc}{digits[:22]}"

_IBAN_POOL = [_gen_iban() for _ in range(POOL_SIZE)]

# Remittance sentences
_REMIT_POOL = [
    f"Invoice {random.randint(1000,99999)} payment",
    f"PO-{random.randint(10000,99999)} settlement",
    f"Contract {random.randint(100,9999)} fee",
    f"Salary {random.choice(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])} 2026",
    f"Vendor payment ref {random.randint(10000,99999)}",
    f"Service fee Q{random.randint(1,4)} 2026",
    f"Lease payment {random.choice(['monthly','quarterly'])}",
    f"Dividend distribution {random.randint(2024,2026)}",
    f"Tax settlement FY{random.randint(2024,2026)}",
    f"Insurance premium {random.randint(1,12)}/2026",
    f"Loan repayment installment {random.randint(1,60)}",
    f"Commission payment {random.randint(1000,9999)}",
    f"Consulting fee project {random.randint(100,999)}",
    f"Reimbursement claim {random.randint(10000,99999)}",
    f"Subscription renewal {random.randint(1,12)}/2026",
] * 20  # 300 entries

# Account IDs
_orig_accounts = [f"C{random.randint(100000000, 9999999999)}" for _ in range(4000)]
_dest_accounts = [f"C{random.randint(100000000, 9999999999)}" for _ in range(4000)]
_merchant_accounts = [f"M{random.randint(100000000, 9999999999)}" for _ in range(2000)]

print(f"done ({time.time()-_t0:.1f}s)", flush=True)

# Fast random pickers
def _company():     return random.choice(_COMPANY_POOL)
def _city():        return random.choice(_CITY_POOL)
def _bic():         return random.choice(_BIC_POOL)
def _iban():        return random.choice(_IBAN_POOL)
def _remit():       return random.choice(_REMIT_POOL)
def _pick_orig():   return random.choice(_orig_accounts)
def _pick_dest(tx_type):
    return random.choice(_merchant_accounts) if tx_type == "PAYMENT" else random.choice(_dest_accounts)

# ---------------------------------------------------------------------------
# Amount distributions (log-normal, matching PaySim ranges)
# ---------------------------------------------------------------------------
def _normal_amount(tx_type: str) -> float:
    if tx_type == "PAYMENT":
        return round(min(random.lognormvariate(7.5, 1.5), 90_000), 2)
    if tx_type == "CASH_OUT":
        return round(min(random.lognormvariate(8.0, 1.8), 10_000_000), 2)
    if tx_type == "CASH_IN":
        return round(min(random.lognormvariate(8.5, 1.2), 5_000_000), 2)
    if tx_type == "TRANSFER":
        return round(min(random.lognormvariate(9.0, 2.0), 10_000_000), 2)
    return round(min(random.lognormvariate(6.5, 1.0), 50_000), 2)

# ---------------------------------------------------------------------------
# Balance helpers
# ---------------------------------------------------------------------------
def _balances_normal(amount):
    old_orig = round(random.lognormvariate(10, 2), 2)
    new_orig = round(max(old_orig - amount, 0), 2)
    old_dest = round(random.lognormvariate(10, 2), 2)
    new_dest = round(old_dest + amount, 2)
    return old_orig, new_orig, old_dest, new_dest

def _balances_fraud(amount):
    return round(amount, 2), 0.0, 0.0, 0.0

# ---------------------------------------------------------------------------
# ISO 20022 payload builder (uses pre-cached pools)
# ---------------------------------------------------------------------------
def _build_payload(tx_type, amount, is_fraud=False, is_aml=False,
                   is_embargo=False, fraud_pattern=None, step=1):
    debtor_country  = random.choice(NORMAL_COUNTRIES)
    creditor_country = random.choice(EMBARGO_COUNTRIES) if is_embargo else random.choice(NORMAL_COUNTRIES)

    debtor_name   = _company()
    creditor_name = random.choice(SANCTIONED_NAMES) if is_aml else _company()

    if is_fraud:
        old_orig, new_orig, old_dest, new_dest = _balances_fraud(amount)
    else:
        old_orig, new_orig, old_dest, new_dest = _balances_normal(amount)

    name_orig = _pick_orig()
    name_dest = _pick_dest(tx_type)

    return {
        "instructionId": str(uuid.uuid4()),
        "endToEndId": f"E2E-{datetime.now().strftime('%Y%m%d')}-{random.randint(10000, 99999)}",
        "uetr": str(uuid.uuid4()),
        "debtor": {
            "name": debtor_name,
            "iban": _iban(),
            "bic": _bic(),
            "address": _city(),
            "country": debtor_country,
        },
        "creditor": {
            "name": creditor_name,
            "iban": _iban(),
            "bic": _bic(),
            "address": _city(),
            "country": creditor_country,
        },
        "amount": amount,
        "currency": random.choice(CURRENCIES),
        "valueDate": date.today().isoformat(),
        "purpose": random.choice(PURPOSES),
        "remittanceInfo": _remit(),
        "channel": random.choice(CHANNELS),
        "paysim": {
            "step": step,
            "type": tx_type,
            "nameOrig": name_orig,
            "oldBalanceOrig": old_orig,
            "newBalanceOrig": new_orig,
            "nameDest": name_dest,
            "oldBalanceDest": old_dest,
            "newBalanceDest": new_dest,
            "isFraud": 1 if is_fraud else 0,
            "isFlaggedFraud": 1 if (is_fraud and amount > 200_000) else 0,
            "fraudPattern": fraud_pattern,
        },
    }

# ---------------------------------------------------------------------------
# Fraud-pattern factories
# ---------------------------------------------------------------------------
def _gen_account_takeover(step):
    amount = round(random.uniform(50_000, 500_000), 2)
    return [_build_payload("TRANSFER", amount, is_fraud=True,
                           fraud_pattern="ACCOUNT_TAKEOVER", step=step)]

def _gen_velocity_burst(step):
    debtor_name = _company()
    payloads = []
    for _ in range(5):
        p = _build_payload("CASH_OUT", round(random.uniform(9_500, 10_500), 2),
                           is_fraud=True, fraud_pattern="VELOCITY_BURST", step=step)
        p["debtor"]["name"] = debtor_name
        payloads.append(p)
    return payloads

def _gen_round_trip(step):
    seed_amt = round(random.uniform(50_000, 200_000), 2)
    return [
        _build_payload("TRANSFER", seed_amt, is_fraud=True, fraud_pattern="ROUND_TRIP", step=step),
        _build_payload("TRANSFER", round(seed_amt * 0.995, 2), is_fraud=True, fraud_pattern="ROUND_TRIP", step=step),
        _build_payload("TRANSFER", round(seed_amt * 0.990, 2), is_fraud=True, fraud_pattern="ROUND_TRIP", step=step),
    ]

def _gen_mule_network(step):
    source_name = _company()
    total = round(random.uniform(80_000, 300_000), 2)
    payloads = []
    for _ in range(5):
        p = _build_payload("CASH_OUT", round(total / 5, 2), is_fraud=True,
                           fraud_pattern="MULE_NETWORK", step=step)
        p["debtor"]["name"] = source_name
        payloads.append(p)
    return payloads

def _gen_impossible_geography(step):
    debtor_name = _company()
    iban = _iban()
    p1 = _build_payload("CASH_OUT", round(random.uniform(10_000, 50_000), 2),
                        is_fraud=True, fraud_pattern="IMPOSSIBLE_GEOGRAPHY", step=step)
    p2 = _build_payload("CASH_OUT", round(random.uniform(10_000, 50_000), 2),
                        is_fraud=True, fraud_pattern="IMPOSSIBLE_GEOGRAPHY", step=step)
    p1["debtor"].update({"name": debtor_name, "iban": iban, "country": "GB"})
    p2["debtor"].update({"name": debtor_name, "iban": iban, "country": "SG"})
    return [p1, p2]

def _gen_embargoed_transit(step):
    amount = round(random.uniform(100_000, 2_000_000), 2)
    return [_build_payload("TRANSFER", amount, is_fraud=True, is_embargo=True,
                           fraud_pattern="EMBARGOED_TRANSIT", step=step)]

_PATTERN_GENERATORS = [
    _gen_account_takeover, _gen_velocity_burst, _gen_round_trip,
    _gen_mule_network, _gen_impossible_geography, _gen_embargoed_transit,
]

# ---------------------------------------------------------------------------
# Master generator
# ---------------------------------------------------------------------------
def generate_all_payloads():
    """Produce ≥100 000 PaySim-style ISO 20022 payloads."""
    fraud_budget   = int(TOTAL_REQUESTS * FRAUD_RATE)
    aml_budget     = int(TOTAL_REQUESTS * AML_RATE)
    embargo_budget = int(TOTAL_REQUESTS * EMBARGO_RATE)
    normal_budget  = TOTAL_REQUESTS - fraud_budget - aml_budget - embargo_budget

    payloads = []
    sim_steps = 743

    # Normal
    for i in range(normal_budget):
        step = (i % sim_steps) + 1
        tx_type = random.choices(TYPE_CHOICES, weights=TYPE_PROBS, k=1)[0]
        payloads.append(_build_payload(tx_type, _normal_amount(tx_type), step=step))
        if (i + 1) % 10_000 == 0:
            print(f"  … normal {i+1:,}/{normal_budget:,}", flush=True)

    # Fraud (TRANSFER / CASH_OUT only, per PaySim)
    injected = 0
    while injected < fraud_budget:
        step = random.randint(1, sim_steps)
        batch = random.choice(_PATTERN_GENERATORS)(step)
        payloads.extend(batch)
        injected += len(batch)

    # AML
    for _ in range(aml_budget):
        step = random.randint(1, sim_steps)
        tx_type = random.choice(["TRANSFER", "CASH_OUT"])
        payloads.append(_build_payload(tx_type, round(random.uniform(5_000, 500_000), 2),
                                       is_aml=True, step=step))

    # Embargo
    for _ in range(embargo_budget):
        step = random.randint(1, sim_steps)
        tx_type = random.choice(["TRANSFER", "CASH_OUT"])
        payloads.append(_build_payload(tx_type, round(random.uniform(10_000, 2_000_000), 2),
                                       is_embargo=True, step=step))

    random.shuffle(payloads)
    return payloads

# ---------------------------------------------------------------------------
# Async sender
# ---------------------------------------------------------------------------
async def send_payment(session, payload, pbar_queue):
    try:
        async with session.post(API_URL, json=payload) as resp:
            await resp.text()
            await pbar_queue.put(1)
            return resp.status
    except Exception:
        await pbar_queue.put(1)
        return 500

async def worker(queue, session, pbar_queue):
    while True:
        try:
            payload = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        await send_payment(session, payload, pbar_queue)
        queue.task_done()

async def progress_reporter(pbar_queue, total):
    completed = 0
    start = time.time()
    while completed < total:
        _ = await pbar_queue.get()
        completed += 1
        if completed % 1000 == 0 or completed == total:
            elapsed = time.time() - start
            rate = completed / elapsed if elapsed else 0
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Sent {completed:,}/{total:,}  ({rate:,.1f} tx/sec)", flush=True)

async def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 70)
    print("  ClearFlow — PaySim ISO 20022 Transaction Generator")
    print("=" * 70)
    print(f"  Target        : {TOTAL_REQUESTS:,}")
    print(f"  Fraud rate    : {FRAUD_RATE*100:.1f}%")
    print(f"  AML rate      : {AML_RATE*100:.1f}%")
    print(f"  Embargo rate  : {EMBARGO_RATE*100:.1f}%")
    print(f"  Concurrency   : {CONCURRENCY}")
    print(f"  API endpoint  : {API_URL}")
    print(f"  Mode          : {'DRY-RUN (no HTTP)' if dry_run else 'LIVE'}")
    print("=" * 70)

    print("\n⏳ Generating payloads …", flush=True)
    t0 = time.time()
    payloads = generate_all_payloads()
    gen_sec = time.time() - t0
    print(f"✅ Generated {len(payloads):,} payloads in {gen_sec:.1f}s\n", flush=True)

    # Stats
    n_fraud   = sum(1 for p in payloads if p["paysim"]["isFraud"] == 1)
    n_aml     = sum(1 for p in payloads if p["creditor"]["name"] in SANCTIONED_NAMES)
    n_embargo = sum(1 for p in payloads if p["creditor"]["country"] in EMBARGO_COUNTRIES)
    types_count = {}
    patterns = {}
    for p in payloads:
        t = p["paysim"]["type"]
        types_count[t] = types_count.get(t, 0) + 1
        pat = p["paysim"].get("fraudPattern")
        if pat:
            patterns[pat] = patterns.get(pat, 0) + 1

    print("📊 Breakdown:")
    print(f"   Total           : {len(payloads):,}")
    print(f"   Fraud           : {n_fraud:,}  ({n_fraud/len(payloads)*100:.2f}%)")
    print(f"   AML-hit         : {n_aml:,}")
    print(f"   Embargo-hit     : {n_embargo:,}")
    for t in sorted(types_count):
        print(f"   {t:15s}: {types_count[t]:>6,}  ({types_count[t]/len(payloads)*100:.1f}%)")
    if patterns:
        print("\n🚨 Fraud patterns:")
        for p2 in sorted(patterns):
            print(f"   {p2:25s}: {patterns[p2]:>4,}")
    print()

    if dry_run:
        print("🏁 Dry-run complete — no transactions sent.")
        return

    # Send via async HTTP
    queue = asyncio.Queue()
    pbar_queue = asyncio.Queue()
    for p in payloads:
        queue.put_nowait(p)

    total = len(payloads)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        reporter_task = asyncio.create_task(progress_reporter(pbar_queue, total))
        workers = [asyncio.create_task(worker(queue, session, pbar_queue))
                   for _ in range(CONCURRENCY)]
        await queue.join()
        for w in workers:
            w.cancel()
        reporter_task.cancel()

    print(f"\n✅ Finished ingesting {total:,} PaySim-style ISO 20022 transactions!")

if __name__ == "__main__":
    asyncio.run(main())
